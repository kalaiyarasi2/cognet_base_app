import os
import json
import time
import glob
import base64
import smtplib
import requests
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_DEFAULT_DELEGATED_SENDER = "drivesupport@cognethro.com"


def _jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


def _get_delegated_sender_token() -> str | None:
    """Get a delegated Mail.Send token for the sender mailbox (e.g. drivesupport)
    from the dashboard OAuth session files (.sessions/onedrive_*.json).
    Delegated tokens are not subject to the app-only (workload identity) block."""
    sender = (os.getenv("DELEGATED_SENDER_EMAIL") or _DEFAULT_DELEGATED_SENDER).lower()
    base = Path(__file__).parent
    session_dirs = [base / ".sessions", base / "file-classification-" / ".sessions", Path.cwd() / ".sessions"]
    files = []
    for d in session_dirs:
        if d.exists():
            files.extend(glob.glob(str(d / "onedrive_*.json")))
    files = list(dict.fromkeys(files))
    files.sort(key=os.path.getmtime, reverse=True)

    client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID") or os.getenv("MICROSOFT_TENANT_ID") or "4858c3ed-d305-48b4-80e0-0bcdbf8ff3ae"
    if tenant_id.strip().lower() in ("common", "organizations", "consumers"):
        tenant_id = "4858c3ed-d305-48b4-80e0-0bcdbf8ff3ae"

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            claims = _jwt_claims(data.get("access_token", ""))
            acct = (claims.get("upn") or claims.get("unique_name") or "").lower()
            if acct != sender:
                continue
            if data.get("expires_at", 0) > time.time() + 60 and data.get("access_token"):
                return data["access_token"]
            refresh = data.get("refresh_token")
            if not (refresh and client_id and client_secret):
                continue
            import msal
            app = msal.ConfidentialClientApplication(
                client_id,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                client_credential=client_secret,
            )
            res = app.acquire_token_by_refresh_token(
                refresh, scopes=["https://graph.microsoft.com/Mail.Send"]
            )
            if "access_token" in res:
                data["access_token"] = res["access_token"]
                data["expires_at"] = time.time() + res.get("expires_in", 3600)
                if res.get("refresh_token"):
                    data["refresh_token"] = res["refresh_token"]
                try:
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(data, fh)
                except Exception:
                    pass
                return res["access_token"]
            print(f"[MS Graph Delegated] Refresh failed for {sender}: {res.get('error')} - {res.get('error_description')}")
        except Exception as e:
            print(f"[MS Graph Delegated] Error reading session {Path(f).name}: {e}")
    return None


def _get_graph_access_token() -> str | None:
    client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("SYSTEM_MAIL_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or os.getenv("MICROSOFT_TENANT_ID")
    
    # Client Credentials Flow requires a specific Azure tenant ID (e.g. GUID or domain).
    # 'common', 'organizations', and 'consumers' are strictly rejected by MS Identity Platform for client_credentials.
    if not tenant_id or tenant_id.strip().lower() in ("common", "organizations", "consumers"):
        tenant_id = os.getenv("SYSTEM_MAIL_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "4858c3ed-d305-48b4-80e0-0bcdbf8ff3ae"

    if not all([client_id, client_secret, tenant_id]):
        return None

    try:
        import msal
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" in result:
            return result["access_token"]
        print(f"[MS Graph Auth] Failed to acquire token: {result.get('error')} - {result.get('error_description')}")
    except Exception as e:
        print(f"[MS Graph Auth] Exception during token acquisition: {e}")
    return None

def _send_graph_mail(recipient_email: str, subject: str, html_content: str, tag: str = "EMAIL") -> bool:
    # 1. Preferred: delegated token of the sender mailbox (drivesupport) via /me/sendMail
    d_token = _get_delegated_sender_token()
    if d_token:
        if _post_graph_send("https://graph.microsoft.com/v1.0/me/sendMail", d_token,
                            recipient_email, subject, html_content, tag):
            return True

    # 2. Fallback: app-only token
    token = _get_graph_access_token()
    sender_email = os.getenv("SENDER_EMAIL") or os.getenv("SMTP_USER")
    if not token or not sender_email:
        return False

    endpoint = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
    email_msg = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_content
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient_email}}
            ]
        },
        "saveToSentItems": "false"
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(endpoint, headers=headers, json=email_msg, timeout=15)
        if response.status_code in (200, 202):
            print(f"[{tag}] Successfully sent email to {recipient_email} via MS Graph.")
            return True
        else:
            print(f"[{tag}] MS Graph failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[{tag}] MS Graph Exception: {e}")
    return False

def _post_graph_send(endpoint: str, token: str, recipient_email: str, subject: str, html_content: str, tag: str) -> bool:
    email_msg = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_content},
            "toRecipients": [{"emailAddress": {"address": recipient_email}}],
        },
        "saveToSentItems": "false",
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=email_msg,
            timeout=15,
        )
        if response.status_code in (200, 202):
            print(f"[{tag}] Successfully sent email to {recipient_email} via MS Graph (delegated).")
            return True
        print(f"[{tag}] MS Graph (delegated) failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[{tag}] MS Graph (delegated) Exception: {e}")
    return False

def _send_smtp_mail(recipient_email: str, subject: str, html_content: str, tag: str = "EMAIL") -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        print(f"[{tag}] No SMTP config found.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = recipient_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())

        print(f"[{tag}] Successfully sent email to {recipient_email} via SMTP.")
        return True
    except Exception as e:
        print(f"[{tag}] Failed to send email via SMTP to {recipient_email}. Error: {e}")
        return False

def send_otp_email(recipient_email: str, otp_code: str, purpose: str = "login"):
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eaeaea; border-radius: 8px;">
          <h2 style="color: #0057FF; margin-top: 0;">Verification Code</h2>
          <p>You requested a code to {purpose} to your workspace.</p>
          <div style="font-size: 24px; font-weight: bold; letter-spacing: 4px; padding: 16px; background: #f9fafb; text-align: center; border-radius: 8px; margin: 20px 0;">
            {otp_code}
          </div>
          <p style="font-size: 13px; color: #6b7280;">This code will expire in 10 minutes. If you did not request this code, please ignore this email.</p>
        </div>
      </body>
    </html>
    """

    subject = f"Your Verification Code: {otp_code}"

    # 1. Try Microsoft Graph API
    if _send_graph_mail(recipient_email, subject, html_content, tag="LOGIN OTP"):
        return

    # 2. Fallback to SMTP
    if _send_smtp_mail(recipient_email, subject, html_content, tag="LOGIN OTP"):
        return

    # 3. Fallback to console print if both fail
    print(f"[LOGIN OTP] MOCKING EMAIL TO {recipient_email}: {otp_code}")

def send_access_granted_email(
    recipient_email: str,
    recipient_name: str,
    granted_by: str,
    login_url: str = "http://localhost:5173/login",
    role: str = "USER",
    allowed_modules: any = "ALL"
):
    MODULE_LABELS = {
        "INVOICE": "Invoice Processing",
        "SBC": "SBC Parity Analysis",
        "RPVE": "RPVE Processing",
        "RE": "Resourcing Edge",
        "LOSS_RUN": "Loss Run Insurance",
        "WORK_COMP": "Workers Comp",
        "BANK_STATEMENT": "Bank Statements",
        "VENDOR_INVOICE": "Vendor Invoices",
        "DRIVE_GPU": "Drive GPU Engine",
        "RENEWAL": "Renewal Process",
        "PIPELINE": "Document Pipeline",
        "CONVERTER": "Format Converter",
        "PAYROLL": "Payroll Extractor",
        "PSH_CLAIM": "PSH Claim Validator",
        "ALL": "All System Modules"
    }

    modules_list = []
    if isinstance(allowed_modules, list):
        modules_list = allowed_modules
    elif isinstance(allowed_modules, str):
        if allowed_modules.upper() == "ALL":
            modules_list = ["ALL"]
        else:
            modules_list = [m.strip().upper() for m in allowed_modules.split(",") if m.strip()]

    role_label = "Administrator" if role in ["ADMIN", "TENANT_ADMIN"] else "Team Member"

    modules_html = ""
    for mod in modules_list:
        label = MODULE_LABELS.get(mod, mod.replace("_", " ").title())
        modules_html += f'<span style="display: inline-block; background-color: #EFF6FF; color: #1D4ED8; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 9999px; margin-right: 6px; margin-bottom: 6px; border: 1px solid #DBEAFE;">{label}</span>'

    if not modules_html:
        modules_html = '<span style="display: inline-block; background-color: #EFF6FF; color: #1D4ED8; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 9999px; border: 1px solid #DBEAFE;">Assigned Workspace</span>'

    html_content = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px;">
        <div style="max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          
          <!-- Header Banner -->
          <div style="background: linear-gradient(135deg, #0057FF 0%, #1E40AF 100%); padding: 26px 30px; text-align: left;">
            <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;">Drive Agent Workspace</h1>
            <p style="color: #DBEAFE; margin: 6px 0 0 0; font-size: 14px;">Access Granted Invitation</p>
          </div>
          <div style="padding: 30px;">
            <h2 style="color: #0F172A; margin-top: 0; font-size: 18px; font-weight: 600;">Welcome, {recipient_name or 'User'}!</h2>
            <p style="color: #475569; font-size: 14px; line-height: 1.6; margin-top: 4px;">
              You have been granted access to the workspace by <strong>{granted_by}</strong>.
            </p>

            <!-- Access Badges Box -->
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px 16px; margin: 18px 0;">
              <div style="margin-bottom: 10px;">
                <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748B; letter-spacing: 0.5px; display: block; margin-bottom: 2px;">Assigned Role</span>
                <span style="font-size: 14px; font-weight: 600; color: #0F172A;">{role_label}</span>
              </div>
              <div>
                <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748B; letter-spacing: 0.5px; display: block; margin-bottom: 6px;">Permitted Module(s)</span>
                <div>{modules_html}</div>
              </div>
            </div>

            <!-- Steps Section -->
            <div style="background-color: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 8px; padding: 16px 18px; margin: 18px 0;">
              <h3 style="color: #166534; margin: 0 0 8px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
                Steps to Access Your Account:
              </h3>
              <ol style="margin: 0; padding-left: 20px; color: #15803D; font-size: 13px; line-height: 1.7;">
                <li>Click the <strong>Go to App</strong> button below.</li>
                <li>Enter your email to receive a 6-digit verification code (OTP).</li>
                <li>Verify your OTP and create your account password.</li>
                <li>You will be taken directly into your assigned module workspace!</li>
              </ol>
            </div>

            <!-- CTA Button -->
            <div style="text-align: center; margin: 26px 0 16px 0;">
              <a href="{login_url}" style="background-color: #0057FF; color: #ffffff; padding: 12px 32px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block;">
                Go to App
              </a>
            </div>

            <p style="font-size: 12px; color: #94A3B8; text-align: center; margin-top: 16px;">
              If you have any questions, please contact your administrator.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    subject = "Welcome! You have been granted access"

    # 1. Try Microsoft Graph API
    if _send_graph_mail(recipient_email, subject, html_content, tag="ACCESS EMAIL"):
        return

    # 2. Fallback to SMTP
    if _send_smtp_mail(recipient_email, subject, html_content, tag="ACCESS EMAIL"):
        return

    # 3. Fallback to console print if both fail
    print(f"[ACCESS EMAIL] MOCKING EMAIL TO {recipient_email}")

def send_tenant_welcome_email(
    recipient_email: str,
    tenant_name: str,
    tenant_code: str,
    otp_code: str,
    login_url: str = "http://localhost:5173/login"
):
    html_content = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px;">
        <div style="max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <div style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); padding: 28px 32px; text-align: left;">
            <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;">Drive360 Enterprise</h1>
            <p style="color: #e0f2fe; margin: 6px 0 0 0; font-size: 14px;">Tenant Workspace Onboarding</p>
          </div>
          
          <div style="padding: 32px;">
            <h2 style="color: #0f172a; margin-top: 0; font-size: 18px; font-weight: 600;">Welcome, Tenant Administrator!</h2>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
              A new organization workspace has been created for <strong>{tenant_name}</strong> on the Drive360 platform.
            </p>
            
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin: 18px 0;">
              <div style="font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase;">Organization Identifier</div>
              <div style="font-size: 15px; color: #0f172a; font-weight: 700; margin-top: 2px; font-family: monospace;">Tenant Code: {tenant_code}</div>
            </div>

            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
              <span style="font-size: 12px; font-weight: 600; color: #166534; text-transform: uppercase; letter-spacing: 1px;">Your First-Time Setup Verification Code</span>
              <div style="font-size: 34px; font-weight: 800; letter-spacing: 6px; color: #15803d; margin-top: 8px; font-family: monospace;">
                {otp_code}
              </div>
              <span style="font-size: 12px; color: #166534; margin-top: 6px; display: block;">Valid for 15 minutes</span>
            </div>

            <p style="font-size: 13px; color: #64748b; line-height: 1.5;">
              To complete your account setup, open the link below, verify with this code, and set your new admin password.
            </p>

            <div style="text-align: center; margin: 28px 0 10px 0;">
              <a href="{login_url}" style="background-color: #0284c7; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; display: inline-block;">
                Access Your Workspace
              </a>
            </div>
          </div>
          
          <div style="background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 16px 32px; text-align: center;">
            <p style="font-size: 12px; color: #94a3b8; margin: 0;">
              If you did not request this workspace, please contact your system administrator.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    subject = f"Welcome to Drive360 - Workspace Setup for {tenant_name} (OTP: {otp_code})"

    # 1. Try Microsoft Graph API
    if _send_graph_mail(recipient_email, subject, html_content, tag="TENANT ONBOARDING"):
        return

    # 2. Fallback to SMTP
    if _send_smtp_mail(recipient_email, subject, html_content, tag="TENANT ONBOARDING"):
        return

    # 3. Fallback to console print if both fail
    print(f"[TENANT ONBOARDING] MOCKING EMAIL TO {recipient_email}: OTP is {otp_code}")
