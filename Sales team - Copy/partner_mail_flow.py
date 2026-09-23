"""
partner_mail_flow.py - Dedicated Mail Ingestion & Multi-Tenant Submission Orchestrator

Monitors a designated inbox, classifies & extracts ACORD and Loss Run documents,
and automatically transforms and dispatches the unified submission payload to the
partner/tenant endpoint using the Config-Driven Submission Engine.
"""

from __future__ import annotations

import os
import sys
import time
import json
import base64
import hashlib
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup workspace directory
WORKSPACE_DIR = Path(__file__).parent.resolve()
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [PARTNER-FLOW] %(message)s"
)
root_l = logging.getLogger()
if len(root_l.handlers) > 1:
    root_l.handlers = [root_l.handlers[0]]
logger = logging.getLogger("PartnerMailFlow")


# Load environment configurations
from dotenv import load_dotenv
load_dotenv(WORKSPACE_DIR / ".env")

# Core imports
from core.submission.submission_service import SubmissionService
from core.tenant.loaders import TenantConfigLoader

# Optional DB and Outlook agents
try:
    from database import poc_db
    _poc_db_ok = True
except Exception as _db_err:
    poc_db = None
    _poc_db_ok = False
    logger.warning("poc_db not available: %s", _db_err)

try:
    OUTLOOK_AGENT_DIR = WORKSPACE_DIR / "Outlook_Agent"
    if str(OUTLOOK_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(OUTLOOK_AGENT_DIR))
    from outlook_agent_module import OutlookAgentModule, _mark_read
except Exception as _agent_err:
    OutlookAgentModule = None
    _mark_read = None
    logger.warning("OutlookAgentModule not available: %s", _agent_err)

# Extraction imports from start_flow
from start_flow import (
    run_local_extraction,
    classifier_extract,
    load_categories_from_env,
    DocumentClassifier,
    get_active_refresh_token,
)


# ---------------------------------------------------------------------------
# Generic Failure Notification Helper (config-driven, no tenant hardcoding)
# ---------------------------------------------------------------------------

def _send_failure_notification(
    sender_email: str,
    error_message: str,
    status_code: Optional[int],
    tenant_folder: str,
    submission_config,
    saved_json_path: Optional[str] = None,
    pdf_paths: Optional[List[str]] = None,
    graph_token: Optional[str] = None,
    from_mailbox: Optional[str] = None,
) -> None:
    """
    Sends a failure alert email back to the original sender.
    Entirely driven by submission_config.failure_notification — no tenant-specific logic.
    Reuses the already-obtained Outlook Graph token (graph_token) so no new MSAL
    token acquisition is needed. Falls back to MSAL app-token, then SMTP.
    """
    fn_cfg = submission_config.failure_notification
    if not fn_cfg.enabled:
        return

    # Only fire if the status code matches the configured trigger codes
    if status_code is not None and status_code not in fn_cfg.trigger_on_status_codes:
        logger.info(
            "Failure notification skipped: HTTP %s not in trigger_on_status_codes %s",
            status_code, fn_cfg.trigger_on_status_codes
        )
        return

    recipient = fn_cfg.notify_email or sender_email
    if not recipient:
        logger.warning("Failure notification: no recipient email available. Skipping.")
        return

    prefix = fn_cfg.subject_prefix or f"[{tenant_folder.upper().replace('_', ' ')}]"
    subject = f"{prefix} Submission Failed - HTTP {status_code or 'N/A'}: {error_message[:80]}"

    error_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
        <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 10px;
                    border: 1px solid #e2e8f0; overflow: hidden;">
          <div style="background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
                      padding: 22px 28px;">
            <h1 style="color:#fff; margin:0; font-size:18px; font-weight:700;">&#9888; Submission Failed</h1>
            <p style="color:#fecaca; margin:4px 0 0 0; font-size:13px;">Tenant: {tenant_folder}</p>
          </div>
          <div style="padding: 28px;">
            <p style="color:#374151; font-size:14px; line-height:1.6;">
              Your document submission was processed but the partner API rejected it.
              Please review the details below and re-submit or contact support.
            </p>
            <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:8px;
                        padding:14px 18px; margin:16px 0;">
              <div style="font-size:12px; color:#991b1b; font-weight:700; text-transform:uppercase;
                          margin-bottom:4px;">Error Details</div>
              <div style="font-size:14px; color:#7f1d1d; font-family:monospace; word-break:break-all;">
                HTTP {status_code or 'N/A'} &mdash; {error_message}
              </div>
            </div>
            <p style="font-size:13px; color:#6b7280;">
              The merged JSON payload{' and original PDF attachments are' if fn_cfg.attach_input_pdfs else ' is'}
              attached to this email for your reference.
            </p>
          </div>
          <div style="background:#f8fafc; border-top:1px solid #e2e8f0; padding:14px 28px;
                      text-align:center;">
            <p style="font-size:12px; color:#94a3b8; margin:0;">
              This is an automated notification from the CogNet Submission Engine.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    # Build attachments list
    attachments = []
    if fn_cfg.attach_merged_json and saved_json_path and os.path.exists(saved_json_path):
        attachments.append({"path": saved_json_path, "name": "merged_submission.json",
                             "mime": "application/json"})
    if fn_cfg.attach_input_pdfs and pdf_paths:
        for p in pdf_paths:
            if os.path.exists(p):
                attachments.append({"path": p, "name": Path(p).name, "mime": "application/pdf"})

    import requests as _req

    def _graph_send(access_token: str, mailbox: str = "") -> bool:
        """Send via Graph API. Uses /me/sendMail for delegated tokens (no mailbox needed).
        Falls back to /users/{mailbox}/sendMail if mailbox is provided (app tokens)."""
        try:
            graph_attachments = []
            for att in attachments:
                with open(att["path"], "rb") as af:
                    encoded = base64.b64encode(af.read()).decode("utf-8")
                graph_attachments.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att["name"],
                    "contentType": att["mime"],
                    "contentBytes": encoded,
                })

            graph_payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": error_html},
                    "toRecipients": [{"emailAddress": {"address": recipient}}],
                    "attachments": graph_attachments,
                },
                "saveToSentItems": "false",
            }
            # Delegated token -> /me/sendMail (token already scoped to the user)
            # App token -> /users/{mailbox}/sendMail
            if mailbox:
                endpoint = f"https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail"
            else:
                endpoint = "https://graph.microsoft.com/v1.0/me/sendMail"

            resp = _req.post(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}",
                         "Content-Type": "application/json"},
                json=graph_payload,
                timeout=30,
            )
            if resp.status_code in (200, 202):
                logger.info(
                    "[FailureNotify] Sent failure email to '%s' via Graph (%s | tenant: %s)",
                    recipient,
                    f"from: {mailbox}" if mailbox else "/me",
                    tenant_folder,
                )
                return True
            else:
                logger.warning(
                    "[FailureNotify] Graph sendMail returned %s: %s", resp.status_code, resp.text
                )
        except Exception as exc:
            logger.warning("[FailureNotify] Graph send attempt failed: %s", exc)
        return False

    # --- Priority 1: Reuse the already-obtained Outlook delegated token (/me/sendMail) ---
    if graph_token:
        logger.info("[FailureNotify] Using existing Outlook session token (/me/sendMail) to send failure email.")
        if _graph_send(graph_token):  # no mailbox needed — delegated token
            return

    # --- Priority 2: Try acquiring a fresh app token via MSAL ---
    # Supports both AZURE_ and MICROSOFT_ env var naming conventions
    client_id     = os.getenv("AZURE_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")
    ms_tenant_id  = os.getenv("AZURE_TENANT_ID") or os.getenv("MICROSOFT_TENANT_ID")
    sender_acct   = from_mailbox or os.getenv("SENDER_EMAIL") or os.getenv("PARTNER_POC_MONITOR_EMAIL")

    if all([client_id, client_secret, ms_tenant_id, sender_acct]):
        try:
            import msal
            authority = f"https://login.microsoftonline.com/{ms_tenant_id}"
            app = msal.ConfidentialClientApplication(
                client_id, authority=authority, client_credential=client_secret
            )
            token_result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            if "access_token" in token_result:
                if _graph_send(token_result["access_token"], sender_acct):
                    return
            else:
                logger.warning("[FailureNotify] MSAL token error: %s", token_result.get("error"))
        except Exception as msal_err:
            logger.warning("[FailureNotify] MSAL token acquisition failed: %s", msal_err)

    # --- Priority 3: Fallback to SMTP ---
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        logger.warning(
            "[FailureNotify] All send methods failed. Could not send failure email to '%s'.",
            recipient
        )
        return

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = recipient
        msg.attach(MIMEText(error_html, "html"))

        for att in attachments:
            with open(att["path"], "rb") as af:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(af.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{att["name"]}"')
                msg.attach(part)

        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())

        logger.info(
            "[FailureNotify] Sent failure email via SMTP to '%s' for tenant '%s'",
            recipient, tenant_folder
        )
    except Exception as smtp_err:
        logger.error("[FailureNotify] SMTP send also failed: %s", smtp_err)


class PartnerMailFlowOrchestrator:
    """
    Orchestrates dedicated email intake, extraction, and partner submission.
    """

    def __init__(self, tenant_folder: str = "client_a"):
        self.tenant_folder = tenant_folder
        self.submission_service = SubmissionService(workspace_dir=WORKSPACE_DIR)
        self.config_loader = TenantConfigLoader(base_dir=WORKSPACE_DIR)
        self.submission_config = self.config_loader.load_submission_config(tenant_folder)
        self.staging_dir = WORKSPACE_DIR / "temp_partner_staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self._processed_msg_ids = set()

    def is_submission_enabled(self) -> bool:
        return self.submission_config.enabled

    async def process_email_package(
        self,
        email_item: Dict[str, Any],
        downloaded_pdfs: List[Path],
        token: str = "",
    ) -> Dict[str, Any]:
        """
        Processes all attachments for an email submission, runs GPU extraction,
        and submits the unified payload via SubmissionService.
        """
        sender_val = email_item.get("sender") or email_item.get("from") or {}
        if isinstance(sender_val, dict):
            sender_email = sender_val.get("emailAddress", {}).get("address", "unknown@sender.com")
        elif isinstance(sender_val, str):
            sender_email = sender_val
        else:
            sender_email = "unknown@sender.com"

        subject = str(email_item.get("subject", "No Subject"))
        message_id = str(email_item.get("id", ""))
        received_time = str(email_item.get("receivedDateTime", ""))

        logger.info("=" * 60)
        logger.info("Processing Email Submission: Sender=%s | Subject='%s'", sender_email, subject)
        logger.info("=" * 60)

        categories = load_categories_from_env()
        classifier = DocumentClassifier(categories=categories)

        from collections import defaultdict
        extracted_payloads: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        source_pdf_paths: List[str] = []
        additional_file_paths: List[str] = []
        
        has_exception = False
        overall_category = None

        for pdf_path in downloaded_pdfs:
            if not pdf_path.exists() or not pdf_path.name.lower().endswith(".pdf"):
                continue

            source_pdf_paths.append(str(pdf_path.resolve()))
            logger.info("Classifying document: %s", pdf_path.name)

            try:
                text, pdf_type, rotation = classifier_extract(pdf_path, max_pages=3)
                
                # --- PRIORITY SKIP CHECK ---
                # If a category is configured to SKIP, its keywords take absolute precedence
                priority_category = None
                if text:
                    import re
                    # Normalize whitespace (replace newlines/tabs/multiple spaces with a single space)
                    text_normalized = re.sub(r'\s+', ' ', text.lower())
                    for cat_name, force_engine in self.submission_config.transform_rules.poc_routing_overrides.items():
                        if force_engine == "SKIP":
                            skip_keywords = categories.get(cat_name.upper(), [])
                            for kw in skip_keywords:
                                kw_normalized = re.sub(r'\s+', ' ', kw.lower())
                                if kw_normalized in text_normalized:
                                    priority_category = cat_name.upper()
                                    break
                            if priority_category:
                                break
                if priority_category:
                    category = priority_category
                    score = 1.0
                    logger.info("Priority SKIP keyword matched! Overriding LLM classification to %s", category)
                else:
                    category, score = classifier.classify(text, file_name=pdf_path.name)
            except Exception as e:
                logger.error("Classification error for %s: %s", pdf_path.name, e)
                category, score = "Others", 0.0
                text = ""

            logger.info("Category determined: %s (Confidence: %.2f)", category, score)
            
            if not overall_category:
                overall_category = category

            # Run GPU / Local Extraction with optional Tenant POC Override
            force_poc_engine = self.submission_config.transform_rules.poc_routing_overrides.get(category.upper())
            
            if force_poc_engine == "SKIP":
                logger.info("Category %s is set to SKIP. Bypassing extraction.", category)
                has_exception = True
                overall_category = category
                continue
                
            if not force_poc_engine:
                force_poc_engine = self.submission_config.transform_rules.default_poc_engine
            extract_result = await run_local_extraction(category, pdf_path, text, force_poc_engine=force_poc_engine, user_email=sender_email)
            
            cat_upper = category.upper()
            json_target = extract_result.get("json") or extract_result.get("json_path")
            json_content = None
            if json_target and os.path.exists(json_target):
                try:
                    with open(json_target, "r", encoding="utf-8") as f:
                        json_content = json.load(f)
                except Exception as ex:
                    logger.warning("Failed to load extracted JSON (%s): %s", json_target, ex)
            elif isinstance(extract_result.get("data"), dict):
                json_content = extract_result.get("data")
            elif isinstance(extract_result, dict) and any(k in extract_result for k in ["Applicant", "SummaryLevel", "claims"]):
                json_content = extract_result

            if json_content and isinstance(json_content, dict):
                extracted_payloads[cat_upper].append(json_content)
                
            excel_target = extract_result.get("excel")
            if excel_target and os.path.exists(excel_target):
                additional_file_paths.append(str(Path(excel_target).resolve()))

        # (Loss run merging logic is now dynamically handled in PayloadTransformer)

        # Execute submission via SubmissionService
        logger.info("Invoking Multi-Tenant Submission Service for tenant '%s'...", self.tenant_folder)
        submission_result = self.submission_service.process_and_submit(
            tenant_folder=self.tenant_folder,
            extracted_payloads=extracted_payloads,
            pdf_file_paths=source_pdf_paths,
            additional_file_paths=additional_file_paths,
            email_address=sender_email,
            extra_metadata={
                "subject": subject,
                "message_id": message_id,
                "received_at": received_time,
                "category": overall_category
            }
        )

        status = submission_result.get("status", "UNKNOWN")
        logger.info("Submission Result: Status=%s | StatusCode=%s", status, submission_result.get("status_code"))

        # --- Generic Failure Notification (config-driven, works for any tenant) ---
        if status == "FAILED":
            fn_cfg = self.submission_config.failure_notification
            notify_target = fn_cfg.notify_email or sender_email
            if fn_cfg.enabled:
                logger.info(
                    "Submission FAILED for tenant '%s' | Error: %s | "
                    "Sending failure notification email to: %s",
                    self.tenant_folder,
                    submission_result.get("error") or "Unknown error",
                    notify_target,
                )
            _send_failure_notification(
                sender_email=sender_email,
                error_message=submission_result.get("error") or "Unknown error",
                status_code=submission_result.get("status_code"),
                tenant_folder=self.tenant_folder,
                submission_config=self.submission_config,
                saved_json_path=submission_result.get("saved_submission_path"),
                pdf_paths=source_pdf_paths,
                graph_token=token,        # reuse the already-working Outlook token
                from_mailbox="",          # empty = /me/sendMail (delegated token)
            )
            if fn_cfg.enabled:
                logger.info(
                    "Failure notification dispatched -> To: %s | Tenant: %s | HTTP Status: %s",
                    notify_target,
                    self.tenant_folder,
                    submission_result.get("status_code"),
                )

        # Log Audit entry into SQLite
        if _poc_db_ok:
            try:
                poc_db.log_universal(
                    module="PARTNER_SUBMISSION",
                    action=f"Tenant Submission ({self.tenant_folder})",
                    file_name=subject,
                    status=status,
                    details=json.dumps({
                        "sender": sender_email,
                        "status_code": submission_result.get("status_code"),
                        "error": submission_result.get("error"),
                        "pdf_count": len(source_pdf_paths),
                    }),
                    processed_by=sender_email
                )
            except Exception as db_err:
                logger.warning("Failed to log audit entry to converter.db: %s", db_err)

        # Mark Email Read in Outlook once processed
        if token and message_id and _mark_read:
            try:
                _mark_read(token, message_id)
                logger.info("Marked message %s as READ in mailbox.", message_id)
            except Exception as e:
                logger.warning("Could not mark message as read: %s", e)

        return submission_result

    @staticmethod
    def _merge_loss_runs(docs: List[dict]) -> dict:
        """
        Merges multiple loss-run documents extracted from the same email.
        Concatenates claims and SummaryLevel; sums claimsCount; keeps first
        non-empty value for any other top-level key.
        """
        if len(docs) == 1:
            return docs[0]

        merged: Dict[str, Any] = {}
        all_claims: List[dict] = []
        all_summary: List[dict] = []
        counts = {"lastFiveYears": 0, "olderThanFiveYears": 0, "total": 0}
        merged_keys: set = set()

        for doc in docs:
            # Concatenate claims
            claims = doc.get("claims")
            if isinstance(claims, list):
                all_claims.extend(claims)

            # Concatenate SummaryLevel (any key variant)
            for sk in ("SummaryLevel", "summary_level", "summaryLevel"):
                if sk in doc and isinstance(doc[sk], list):
                    all_summary.extend(doc[sk])
                    break

            # Sum claimsCount
            cc = doc.get("claimsCount")
            if isinstance(cc, dict):
                for field in counts:
                    counts[field] += cc.get(field, 0) or 0

            # First non-empty value for every other key
            for k, v in doc.items():
                if k in ("claims", "SummaryLevel", "summary_level", "summaryLevel", "claimsCount"):
                    continue
                if k not in merged_keys:
                    merged[k] = v
                    merged_keys.add(k)

        merged["claims"] = all_claims
        merged["SummaryLevel"] = all_summary
        merged["claimsCount"] = counts

        logger.info(
            "Merged %d loss-run docs: %d claims, %d summary rows",
            len(docs), len(all_claims), len(all_summary),
        )
        return merged

    async def run_listener(self, poll_interval: int = 30, user_email: Optional[str] = None, once: bool = False):
        """
        Continuously polls the designated mailbox and processes submissions.
        """
        # Resolve target email from argument, tenant config, or .env
        # Folder names contain spaces (e.g. "Notice Manager") but .env keys use
        # underscores (e.g. NOTICE_MANAGER_MONITOR_EMAIL) — normalize to match.
        clean_tenant = self.tenant_folder.upper().replace(" ", "_")
        resolved_email = (
            user_email
            or os.getenv(f"{clean_tenant}_MONITOR_EMAIL")
            or os.getenv(f"{clean_tenant.replace('_TEAM', '')}_MONITOR_EMAIL")
            or os.getenv("PARTNER_POC_MONITOR_EMAIL")
            or None
        )
        
        logger.info(
            "Starting Partner Mail Flow Listener for Tenant: '%s' | Monitored Mailbox: %s (Interval: %ds)",
            self.tenant_folder,
            resolved_email or "Default Connected Dashboard Account",
            poll_interval
        )
        
        while True:
            try:
                if OutlookAgentModule is not None:
                    agent = OutlookAgentModule(user_email=resolved_email)
                    refresh_token = get_active_refresh_token(resolved_email)
                    token = agent.get_access_token(refresh_token=refresh_token, allow_device_flow=False)
                    emails = agent.fetch_unread_emails(refresh_token=refresh_token) or []

                    if emails:
                        logger.info("Detected %d unread email(s).", len(emails))
                        for email in emails:
                            msg_id = str(email.get("id", str(time.time())))
                            if msg_id in self._processed_msg_ids:
                                continue

                            attachments = email.get("attachments", [])
                            if not attachments:
                                self._processed_msg_ids.add(msg_id)
                                logger.info("Email '%s' has no attachments. Skipping.", email.get("subject", "No Subject"))
                                continue

                            msg_staging = self.staging_dir / hashlib.sha256(msg_id.encode("utf-8")).hexdigest()[:16]
                            msg_staging.mkdir(parents=True, exist_ok=True)

                            downloaded = []
                            for att in attachments:
                                fname = att.get("filename") or att.get("name") or ""
                                if fname.lower().endswith(".pdf") and att.get("content_bytes"):
                                    fpath = msg_staging / fname
                                    fpath.write_bytes(base64.b64decode(att["content_bytes"]))
                                    downloaded.append(fpath)

                            if downloaded:
                                self._processed_msg_ids.add(msg_id)
                                await self.process_email_package(email, downloaded, token=token)
                            else:
                                self._processed_msg_ids.add(msg_id)
                                logger.info("Email '%s' has no valid PDF attachments. Skipping.", email.get("subject", "No Subject"))
                    else:
                        logger.debug("No new unread emails.")

            except Exception as err:
                logger.error("Error during listener cycle: %s", err, exc_info=True)

            if once:
                break

            await asyncio.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Dedicated Partner Mail Ingestion & Submission Flow")
    parser.add_argument("--tenant", default="client_a", help="Tenant configuration code (default: client_a)")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds (default: 60)")
    parser.add_argument("--email", default=None, help="Target mailbox to monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    orchestrator = PartnerMailFlowOrchestrator(tenant_folder=args.tenant)
    asyncio.run(orchestrator.run_listener(poll_interval=args.interval, user_email=args.email, once=args.once))


if __name__ == "__main__":
    main()
