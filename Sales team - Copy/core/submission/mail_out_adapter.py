"""
core/submission/mail_out_adapter.py
────────────────────────────────────────────────────────────────────────────────
Generic Mail-Out Adapter

Replaces the HTTP POST (DynamicHttpAdapter) for tenants configured with
  delivery_method = "mail_out"

Instead of POSTing to a partner API, this adapter:
  1. Evaluates exception rules (via ExceptionEvaluator)
  2. Builds a rich HTML result email (matching the UI output view)
  3. Attaches configured output files (JSON + Excel)
  4. Sends the result email to the configured fixed recipient
  5. If exceptions exist → sends a separate exception alert email

Send order (priority):
  1. Graph API with existing Outlook delegated token (passed in extra_metadata)
  2. Graph API with fresh MSAL app token
  3. SMTP fallback

Works for ANY tenant — all behaviour driven by submission.json mail_out config.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests as _req

from core.submission.http_adapter import SubmissionResult
from core.tenant.models import TenantSubmissionConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Env-var placeholder resolver
# ---------------------------------------------------------------------------

def _resolve(text: str) -> str:
    """Resolve ${VAR_NAME} placeholders from environment variables."""
    if not text:
        return ""
    return re.sub(
        r"\$\{([A-Za-z0-9_]+)\}",
        lambda m: os.getenv(m.group(1), ""),
        text,
    )


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

def _build_result_email_html(
    tenant_folder: str,
    subject: str,
    sender_email: str,
    received_at: str,
    doc_results: List[Dict[str, Any]],
    key_fields: Dict[str, Any],
    exceptions: List[Dict[str, str]],
    subject_prefix: str = "[WCUW]",
) -> str:
    """Build the rich HTML result email body."""

    # ── Document table rows ──────────────────────────────────────────────────
    doc_rows = ""
    for doc in doc_results:
        status_icon = "✅" if doc.get("status") == "OK" else "⚠️"
        status_color = "#16a34a" if doc.get("status") == "OK" else "#d97706"
        doc_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#1e293b;">{doc.get('file','')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#334155;">{doc.get('type','')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:{status_color};font-weight:600;">{status_icon} {doc.get('status','')}</td>
        </tr>"""

    # ── Key fields rows ──────────────────────────────────────────────────────
    def _kv_row(label: str, value: Any, highlight: bool = False) -> str:
        color = "#dc2626" if highlight else "#334155"
        return f"""
        <tr>
          <td style="padding:6px 12px;font-size:13px;color:#64748b;font-weight:600;width:40%;">{label}</td>
          <td style="padding:6px 12px;font-size:13px;color:{color};">{value or '—'}</td>
        </tr>"""

    acord = key_fields.get("acord", {})
    lossrun = key_fields.get("lossrun", {})

    acord_rows = (
        _kv_row("Applicant Name", acord.get("applicant_name") or acord.get("applicantName"))
        + _kv_row("FEIN", acord.get("fein") or acord.get("demographics", {}).get("fein") if isinstance(acord.get("demographics"), dict) else acord.get("fein"),
                  highlight=not bool(acord.get("fein") or (isinstance(acord.get("demographics"), dict) and acord["demographics"].get("fein"))))
        + _kv_row("Policy Number", acord.get("policyNumber") or acord.get("policy_number"))
        + _kv_row("State", acord.get("state"))
        + _kv_row("Effective Date", acord.get("effectiveDate") or acord.get("effective_date"))
    )

    lr_rows = (
        _kv_row("Carrier", lossrun.get("carrier_name") or lossrun.get("carrierName"))
        + _kv_row("Valuation Date", lossrun.get("valuation_date") or lossrun.get("valuationDate"))
        + _kv_row("Employee Count", lossrun.get("employee_count") or (lossrun.get("summary", {}) or {}).get("employee_count"))
        + _kv_row("Total Claims", lossrun.get("total_claims") or (lossrun.get("claimsCount", {}) or {}).get("total"))
    )

    # ── Exception table ──────────────────────────────────────────────────────
    if exceptions:
        exc_rows = "".join(
            f"""<tr>
              <td style="padding:8px 12px;border-bottom:1px solid #fecaca;font-size:13px;color:#991b1b;font-weight:600;">{e['id']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #fecaca;font-size:13px;color:#7f1d1d;">{e['message']}</td>
            </tr>"""
            for e in exceptions
        )
        exc_section = f"""
        <div style="margin:20px 0;">
          <div style="font-size:14px;font-weight:700;color:#dc2626;margin-bottom:8px;">⚠️ Exceptions ({len(exceptions)} found)</div>
          <table style="width:100%;border-collapse:collapse;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;overflow:hidden;">
            <thead>
              <tr style="background:#fee2e2;">
                <th style="padding:8px 12px;text-align:left;font-size:12px;color:#991b1b;text-transform:uppercase;">Rule</th>
                <th style="padding:8px 12px;text-align:left;font-size:12px;color:#991b1b;text-transform:uppercase;">Exception</th>
              </tr>
            </thead>
            <tbody>{exc_rows}</tbody>
          </table>
        </div>"""
    else:
        exc_section = """
        <div style="margin:20px 0;padding:12px 16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">
          <span style="color:#16a34a;font-size:13px;font-weight:600;">✅ No exceptions — all checks passed.</span>
        </div>"""

    # ── Full HTML ────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <html>
      <head><meta charset="utf-8"></head>
      <body style="font-family:Arial,sans-serif;color:#1e293b;background:#f8fafc;padding:24px;margin:0;">
        <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:12px;
                    border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);">

          <!-- Header -->
          <div style="background:linear-gradient(135deg,#1d4ed8 0%,#1e40af 100%);padding:24px 28px;">
            <h1 style="color:#fff;margin:0;font-size:18px;font-weight:700;">
              {subject_prefix} Submission Processed
            </h1>
            <p style="color:#bfdbfe;margin:4px 0 0;font-size:13px;">
              Workers Compensation Underwriting &mdash; {ts}
            </p>
          </div>

          <div style="padding:28px;">

            <!-- Summary -->
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                          background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
              <tr>
                <td style="padding:8px 14px;font-size:13px;color:#64748b;font-weight:600;width:40%;">Received From</td>
                <td style="padding:8px 14px;font-size:13px;color:#334155;">{sender_email}</td>
              </tr>
              <tr style="background:#fff;">
                <td style="padding:8px 14px;font-size:13px;color:#64748b;font-weight:600;">Email Subject</td>
                <td style="padding:8px 14px;font-size:13px;color:#334155;">{subject}</td>
              </tr>
              <tr>
                <td style="padding:8px 14px;font-size:13px;color:#64748b;font-weight:600;">Received At</td>
                <td style="padding:8px 14px;font-size:13px;color:#334155;">{received_at}</td>
              </tr>
              <tr style="background:#fff;">
                <td style="padding:8px 14px;font-size:13px;color:#64748b;font-weight:600;">Documents Found</td>
                <td style="padding:8px 14px;font-size:13px;color:#334155;">{len(doc_results)}</td>
              </tr>
              <tr>
                <td style="padding:8px 14px;font-size:13px;color:#64748b;font-weight:600;">Processed By</td>
                <td style="padding:8px 14px;font-size:13px;color:#334155;">CogNet WCUW Automation</td>
              </tr>
            </table>

            <!-- Document Results -->
            <div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:8px;">Document Results</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                          border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#f1f5f9;">
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#475569;text-transform:uppercase;">File</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#475569;text-transform:uppercase;">Classified As</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#475569;text-transform:uppercase;">Status</th>
                </tr>
              </thead>
              <tbody>{doc_rows}</tbody>
            </table>

            <!-- ACORD Key Fields -->
            <div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:8px;">Key Extracted Data — ACORD 130</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                          background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
              <tbody>{acord_rows}</tbody>
            </table>

            <!-- Loss Run Key Fields -->
            <div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:8px;">Key Extracted Data — Loss Run</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                          background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
              <tbody>{lr_rows}</tbody>
            </table>

            <!-- Exceptions -->
            <div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:4px;">Exceptions</div>
            {exc_section}

            <p style="font-size:13px;color:#64748b;margin-top:20px;">
              All output files are attached to this email for your records.
            </p>
          </div>

          <!-- Footer -->
          <div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:14px 28px;text-align:center;">
            <p style="font-size:12px;color:#94a3b8;margin:0;">
              This is an automated result from the CogNet WCUW Submission Engine.
            </p>
          </div>
        </div>
      </body>
    </html>"""


def _build_exception_alert_html(
    tenant_folder: str,
    sender_email: str,
    subject: str,
    received_at: str,
    exceptions: List[Dict[str, str]],
    subject_prefix: str = "[WCUW]",
) -> str:
    """Build the exception alert email HTML."""
    exc_rows = "".join(
        f"""<tr>
          <td style="padding:10px 14px;border-bottom:1px solid #fecaca;font-size:13px;color:#991b1b;font-weight:600;">{e['id']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fecaca;font-size:13px;color:#7f1d1d;">{e['message']}</td>
        </tr>"""
        for e in exceptions
    )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <html>
      <head><meta charset="utf-8"></head>
      <body style="font-family:Arial,sans-serif;color:#1e293b;background:#fff7f7;padding:24px;margin:0;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;
                    border:1px solid #fecaca;overflow:hidden;box-shadow:0 2px 8px rgba(220,38,38,.08);">

          <div style="background:linear-gradient(135deg,#dc2626 0%,#b91c1c 100%);padding:24px 28px;">
            <h1 style="color:#fff;margin:0;font-size:18px;font-weight:700;">⚠️ {subject_prefix} Exception Alert — Action Required</h1>
            <p style="color:#fecaca;margin:4px 0 0;font-size:13px;">Tenant: {tenant_folder.upper()} &mdash; {ts}</p>
          </div>

          <div style="padding:28px;">
            <p style="font-size:14px;color:#374151;line-height:1.6;margin:0 0 20px;">
              A submission received from <strong>{sender_email}</strong> triggered the following
              exception(s). Please review and take action.
            </p>

            <div style="font-size:13px;color:#64748b;margin-bottom:6px;">
              <strong>Original Subject:</strong> {subject}<br>
              <strong>Received At:</strong> {received_at}
            </div>

            <div style="margin:20px 0;">
              <div style="font-size:14px;font-weight:700;color:#dc2626;margin-bottom:8px;">
                {len(exceptions)} Exception(s) Found
              </div>
              <table style="width:100%;border-collapse:collapse;background:#fef2f2;
                            border:1px solid #fecaca;border-radius:8px;overflow:hidden;">
                <thead>
                  <tr style="background:#fee2e2;">
                    <th style="padding:10px 14px;text-align:left;font-size:12px;color:#991b1b;text-transform:uppercase;width:35%;">Rule ID</th>
                    <th style="padding:10px 14px;text-align:left;font-size:12px;color:#991b1b;text-transform:uppercase;">Exception Message</th>
                  </tr>
                </thead>
                <tbody>{exc_rows}</tbody>
              </table>
            </div>

            <p style="font-size:13px;color:#374151;line-height:1.6;">
              The merged JSON payload and original PDF attachments are attached to this email for your review.
            </p>
          </div>

          <div style="background:#fef2f2;border-top:1px solid #fecaca;padding:14px 28px;text-align:center;">
            <p style="font-size:12px;color:#ef4444;margin:0;">
              This is an automated exception notification from the CogNet WCUW Submission Engine.
            </p>
          </div>
        </div>
      </body>
    </html>"""


# ---------------------------------------------------------------------------
# Graph / SMTP send helpers
# ---------------------------------------------------------------------------

def _graph_send_mail(
    access_token: str,
    from_mailbox: str,
    to_address: str,
    subject: str,
    html_body: str,
    attachments: List[Dict[str, str]],  # [{"path": str, "name": str, "mime": str}]
    tag: str = "MailOut",
) -> bool:
    """Send email via Microsoft Graph API."""
    graph_attachments = []
    for att in attachments:
        try:
            with open(att["path"], "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": att["name"],
                "contentType": att.get("mime", "application/octet-stream"),
                "contentBytes": encoded,
            })
        except Exception as e:
            logger.warning("[%s] Could not read attachment '%s': %s", tag, att.get("name"), e)

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
            "attachments": graph_attachments,
        },
        "saveToSentItems": "false",
    }

    endpoint = (
        f"https://graph.microsoft.com/v1.0/users/{from_mailbox}/sendMail"
        if from_mailbox
        else "https://graph.microsoft.com/v1.0/me/sendMail"
    )

    try:
        resp = _req.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 202):
            logger.info("[%s] Sent email to '%s' via Graph API.", tag, to_address)
            return True
        logger.warning("[%s] Graph returned %s: %s", tag, resp.status_code, resp.text[:300])
    except Exception as e:
        logger.warning("[%s] Graph send exception: %s", tag, e)
    return False


def _smtp_send_mail(
    to_address: str,
    subject: str,
    html_body: str,
    attachments: List[Dict[str, str]],
    tag: str = "MailOut",
) -> bool:
    """SMTP fallback sender."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        logger.warning("[%s] No SMTP config — cannot send via SMTP.", tag)
        return False

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_address
        msg.attach(MIMEText(html_body, "html"))

        for att in attachments:
            try:
                with open(att["path"], "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{att["name"]}"')
                msg.attach(part)
            except Exception as e:
                logger.warning("[%s] Could not attach '%s': %s", tag, att.get("name"), e)

        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_address, msg.as_string())

        logger.info("[%s] Sent email to '%s' via SMTP.", tag, to_address)
        return True
    except Exception as e:
        logger.error("[%s] SMTP send failed: %s", tag, e)
        return False


def _send_email(
    to_address: str,
    subject: str,
    html_body: str,
    attachments: List[Dict[str, str]],
    graph_token: Optional[str],
    from_mailbox: str,
    tag: str = "MailOut",
) -> bool:
    """Try Graph API first, then SMTP fallback."""
    if graph_token and to_address:
        if _graph_send_mail(graph_token, from_mailbox, to_address, subject, html_body, attachments, tag):
            return True

    # Attempt fresh MSAL app token
    client_id     = os.getenv("AZURE_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id     = os.getenv("AZURE_TENANT_ID") or os.getenv("MICROSOFT_TENANT_ID")
    sender_acct   = from_mailbox or os.getenv("SENDER_EMAIL") or os.getenv("SMTP_USER", "")

    if all([client_id, client_secret, tenant_id, sender_acct]):
        try:
            import msal
            app = msal.ConfidentialClientApplication(
                client_id,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                client_credential=client_secret,
            )
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" in result:
                if _graph_send_mail(result["access_token"], sender_acct, to_address, subject, html_body, attachments, tag):
                    return True
        except Exception as e:
            logger.warning("[%s] MSAL token acquisition failed: %s", tag, e)

    return _smtp_send_mail(to_address, subject, html_body, attachments, tag)


# ---------------------------------------------------------------------------
# MailOutAdapter — public class
# ---------------------------------------------------------------------------

class MailOutAdapter:
    """
    Generic mail-out delivery adapter.
    Activated when submission.json has delivery_method = "mail_out".
    Reads all behaviour from the tenant's mail_out config block.
    """

    def __init__(self, config: TenantSubmissionConfig):
        self.config = config

    def dispatch(
        self,
        payload: Dict[str, Any],
        pdf_file_paths: Optional[List[str]] = None,
        additional_file_paths: Optional[List[str]] = None,
        config_override: Optional[TenantSubmissionConfig] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> SubmissionResult:
        """
        Main entry point called by SubmissionService when delivery_method == "mail_out".
        """
        start = time.time()
        active_config = config_override or self.config
        mail_cfg = active_config.mail_out
        extra = extra_metadata or {}

        # ── Resolve addresses ────────────────────────────────────────────────
        result_to  = _resolve(mail_cfg.result_to)
        exc_to     = _resolve(mail_cfg.exception_recipient)
        prefix     = mail_cfg.subject_prefix or "[COGNET]"
        graph_token = extra.get("graph_token", "")
        from_mailbox = extra.get("from_mailbox", os.getenv("SENDER_EMAIL", ""))
        sender_email = extra.get("sender_email", extra.get("email_address", "unknown@sender"))
        subject      = extra.get("subject", "WCUW Submission")
        received_at  = extra.get("received_at", datetime.now().isoformat())
        tenant_folder = payload.get("tenant_folder", "wcuw")

        if not result_to:
            logger.error("[MailOut] result_to address is empty — check WCUW_CLIENT_OUTPUT_EMAIL env var.")
            return SubmissionResult(
                success=False,
                error_message="mail_out.result_to is empty. Set WCUW_CLIENT_OUTPUT_EMAIL in .env.",
                execution_time_seconds=time.time() - start,
            )

        # ── Evaluate exception rules ─────────────────────────────────────────
        workspace_dir = Path(__file__).resolve().parent.parent.parent
        extracted_payloads: Dict[str, List[Dict]] = extra.get("extracted_payloads", {})
        # Also try to read from payload structure if not in extra_metadata
        if not extracted_payloads and isinstance(payload, dict):
            extracted_payloads = payload.get("extracted_payloads", {})

        exceptions: List[Dict[str, str]] = []
        try:
            from core.tenant.exception_evaluator import ExceptionEvaluator
            evaluator = ExceptionEvaluator(workspace_dir, tenant_folder)
            exceptions = evaluator.evaluate(extracted_payloads, merged_payload=payload)
        except Exception as e:
            logger.warning("[MailOut] ExceptionEvaluator failed: %s", e)

        # ── Build document results list for email ────────────────────────────
        doc_results: List[Dict[str, Any]] = []
        for cat, docs in extracted_payloads.items():
            for i, _ in enumerate(docs):
                doc_results.append({
                    "file": f"{cat.lower()}_{i+1}.pdf",
                    "type": cat,
                    "status": "OK",
                })
        # Add files from pdf_file_paths if available
        if pdf_file_paths and not doc_results:
            for p in pdf_file_paths:
                doc_results.append({
                    "file": Path(p).name,
                    "type": "—",
                    "status": "OK",
                })

        # ── Extract key fields from payload for email display ────────────────
        key_fields: Dict[str, Any] = {}
        acord_raw = {}
        lr_raw = {}
        for cat, docs in extracted_payloads.items():
            cat_up = cat.upper()
            if cat_up in ("WORK_COMP", "WORK_COMPENSATION") and docs:
                acord_raw = docs[0] if isinstance(docs[0], dict) else {}
            elif cat_up in ("INSURANCE_CLAIMS", "INSURANCE") and docs:
                lr_raw = docs[0] if isinstance(docs[0], dict) else {}
        key_fields["acord"] = acord_raw
        key_fields["lossrun"] = lr_raw

        # ── Collect output file attachments ──────────────────────────────────
        attach_keys = set(mail_cfg.attach_outputs)
        attachments: List[Dict[str, str]] = []

        def _try_attach(path_str: Optional[str], name: str, mime: str) -> None:
            if path_str and Path(path_str).exists():
                attachments.append({"path": path_str, "name": name, "mime": mime})

        # merged JSON is always saved by SubmissionService — get from payload
        merged_json_path = extra.get("saved_submission_path")

        unified_filename = getattr(mail_cfg, "unified_json_filename", None) or "merged_output.json"
        if "merged_json" in attach_keys:
            _try_attach(merged_json_path, unified_filename, "application/json")

        # Additional files (Excels and per-engine JSONs) from additional_file_paths
        if additional_file_paths:
            for path_str in additional_file_paths:
                p = Path(path_str)
                if not p.exists():
                    continue
                name_lower = p.name.lower()
                if "lossrun" in name_lower or "loss_run" in name_lower or "insurance" in name_lower:
                    if name_lower.endswith(".json") and "lossrun_json" in attach_keys:
                        _try_attach(path_str, "lossrun_data.json", "application/json")
                    elif name_lower.endswith((".xlsx", ".xls")) and "lossrun_excel" in attach_keys:
                        _try_attach(path_str, "lossrun.xlsx",
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                elif "acord" in name_lower or "work_comp" in name_lower or "compensation" in name_lower:
                    if name_lower.endswith(".json") and "acord_json" in attach_keys:
                        _try_attach(path_str, "acord_data.json", "application/json")
                    elif name_lower.endswith((".xlsx", ".xls")) and "acord_excel" in attach_keys:
                        _try_attach(path_str, "acord.xlsx",
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # ── Send result email ────────────────────────────────────────────────
        result_subject = f"{prefix} Submission Processed — {subject[:60]}"
        if exceptions:
            result_subject = f"{prefix} ⚠️ Submission Processed (Exceptions Found) — {subject[:50]}"

        should_send_result = (
            mail_cfg.send_result_even_if_exceptions or not exceptions
        )

        result_sent = False
        if should_send_result and result_to:
            result_html = _build_result_email_html(
                tenant_folder=tenant_folder,
                subject=subject,
                sender_email=sender_email,
                received_at=received_at,
                doc_results=doc_results,
                key_fields=key_fields,
                exceptions=exceptions,
                subject_prefix=prefix,
            )
            result_sent = _send_email(
                to_address=result_to,
                subject=result_subject,
                html_body=result_html,
                attachments=attachments,
                graph_token=graph_token,
                from_mailbox=from_mailbox,
                tag="MailOut-Result",
            )
            if not result_sent:
                logger.error("[MailOut] Failed to send result email to '%s'", result_to)

        # ── Send exception alert email ───────────────────────────────────────
        exc_sent = False
        if exceptions and exc_to:
            exc_subject = f"{prefix} ⚠️ Exception Alert — {len(exceptions)} issue(s) found — {subject[:50]}"
            # Attach merged JSON + original PDFs for the exception alert
            exc_attachments = []
            if merged_json_path and Path(merged_json_path).exists():
                exc_attachments.append({
                    "path": merged_json_path,
                    "name": unified_filename,
                    "mime": "application/json",
                })
            if pdf_file_paths:
                for p in pdf_file_paths:
                    if Path(p).exists():
                        exc_attachments.append({
                            "path": p,
                            "name": Path(p).name,
                            "mime": "application/pdf",
                        })

            exc_html = _build_exception_alert_html(
                tenant_folder=tenant_folder,
                sender_email=sender_email,
                subject=subject,
                received_at=received_at,
                exceptions=exceptions,
                subject_prefix=prefix,
            )
            exc_sent = _send_email(
                to_address=exc_to,
                subject=exc_subject,
                html_body=exc_html,
                attachments=exc_attachments,
                graph_token=graph_token,
                from_mailbox=from_mailbox,
                tag="MailOut-Exception",
            )
            if not exc_sent:
                logger.warning("[MailOut] Failed to send exception alert to '%s'", exc_to)
        elif exceptions and not exc_to:
            logger.warning("[MailOut] Exceptions found but exception_recipient is empty — set WCUW_EXCEPTIONAL_MAIL.")

        elapsed = time.time() - start
        success = result_sent or (not should_send_result and exc_sent)

        logger.info(
            "[MailOut] Done in %.1fs | result_sent=%s | exceptions=%d | exc_alert_sent=%s",
            elapsed, result_sent, len(exceptions), exc_sent,
        )

        return SubmissionResult(
            success=success,
            status_code=202 if success else 500,
            response_data={
                "result_email_sent": result_sent,
                "result_to": result_to,
                "exception_count": len(exceptions),
                "exception_alert_sent": exc_sent,
                "exceptions": exceptions,
            },
            error_message=None if success else "Mail-out delivery failed — check logs.",
            attempt_count=1,
            execution_time_seconds=elapsed,
        )
