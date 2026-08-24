import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

    # 1. Try Microsoft Graph API
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    sender_email = os.getenv("SENDER_EMAIL")

    if all([client_id, client_secret, tenant_id, sender_email]):
        try:
            import msal
            
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            app = msal.ConfidentialClientApplication(
                client_id, authority=authority, client_credential=client_secret
            )
            
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            
            if "access_token" in result:
                endpoint = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
                email_msg = {
                    "message": {
                        "subject": f"Your Verification Code: {otp_code}",
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
                    "Authorization": f"Bearer {result['access_token']}",
                    "Content-Type": "application/json"
                }
                
                response = requests.post(endpoint, headers=headers, json=email_msg)
                if response.status_code == 202 or response.status_code == 200:
                    print(f"[LOGIN OTP] Successfully sent OTP to {recipient_email} via MS Graph.")
                    return
                else:
                    print(f"[LOGIN OTP] MS Graph failed with status {response.status_code}: {response.text}")
            else:
                print(f"[LOGIN OTP] Failed to acquire token for MS Graph: {result.get('error')}")
        except Exception as e:
            print(f"[LOGIN OTP] MS Graph Exception: {e}")

    # 2. Fallback to SMTP
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        print(f"[LOGIN OTP] No SMTP/Graph config found. MOCKING EMAIL TO {recipient_email}: {otp_code}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your Verification Code: {otp_code}"
        msg["From"] = smtp_user
        msg["To"] = recipient_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
            
        print(f"[LOGIN OTP] Successfully sent OTP to {recipient_email} via SMTP.")
    except Exception as e:
        print(f"[LOGIN OTP] Failed to send email via SMTP to {recipient_email}. Error: {e}")
        # Fallback to console print if SMTP fails
        print(f"[LOGIN OTP] MOCKING EMAIL TO {recipient_email}: {otp_code}")

def send_access_granted_email(recipient_email: str, recipient_name: str, granted_by: str, login_url: str = "http://localhost:5173/login"):
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eaeaea; border-radius: 8px;">
          <h2 style="color: #0057FF; margin-top: 0;">Access Granted</h2>
          <p>Hello {recipient_name or 'User'},</p>
          <p>You have been granted access to the workspace by <strong>{granted_by}</strong>.</p>
          <p>You can access the project using the following link:</p>
          <div style="margin: 20px 0;">
            <a href="{login_url}" style="background-color: #0057FF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Go to Project</a>
          </div>
          <p style="font-size: 13px; color: #6b7280;">If you have any questions, please contact your administrator.</p>
        </div>
      </body>
    </html>
    """

    # 1. Try Microsoft Graph API
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    sender_email = os.getenv("SENDER_EMAIL")

    if all([client_id, client_secret, tenant_id, sender_email]):
        try:
            import msal
            
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            app = msal.ConfidentialClientApplication(
                client_id, authority=authority, client_credential=client_secret
            )
            
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            
            if "access_token" in result:
                endpoint = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
                email_msg = {
                    "message": {
                        "subject": "Welcome! You have been granted access",
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
                    "Authorization": f"Bearer {result['access_token']}",
                    "Content-Type": "application/json"
                }
                
                response = requests.post(endpoint, headers=headers, json=email_msg)
                if response.status_code == 202 or response.status_code == 200:
                    print(f"[ACCESS EMAIL] Successfully sent access email to {recipient_email} via MS Graph.")
                    return
                else:
                    print(f"[ACCESS EMAIL] MS Graph failed with status {response.status_code}: {response.text}")
            else:
                print(f"[ACCESS EMAIL] Failed to acquire token for MS Graph: {result.get('error')}")
        except Exception as e:
            print(f"[ACCESS EMAIL] MS Graph Exception: {e}")

    # 2. Fallback to SMTP
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        print(f"[ACCESS EMAIL] No SMTP/Graph config found. MOCKING EMAIL TO {recipient_email}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Welcome! You have been granted access"
        msg["From"] = smtp_user
        msg["To"] = recipient_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
            
        print(f"[ACCESS EMAIL] Successfully sent access email to {recipient_email} via SMTP.")
    except Exception as e:
        print(f"[ACCESS EMAIL] Failed to send email via SMTP to {recipient_email}. Error: {e}")
        print(f"[ACCESS EMAIL] MOCKING EMAIL TO {recipient_email}")
