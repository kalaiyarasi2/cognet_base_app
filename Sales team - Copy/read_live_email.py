import glob
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

WORKSPACE_DIR = Path(__file__).parent.resolve()
load_dotenv(WORKSPACE_DIR / ".env")

sys.path.insert(0, str(WORKSPACE_DIR / "Outlook_Agent"))
from outlook_agent_module import OutlookAgentModule

def fetch():
    sessions_dir = WORKSPACE_DIR / "file-classification-" / ".sessions"
    session_files = list(sessions_dir.glob("onedrive_*.json"))
    session_files.sort(key=os.path.getmtime, reverse=True)

    if not session_files:
        print("[ERR] No session files found in .sessions")
        return

    with open(session_files[0]) as f:
        d = json.load(f)
    r_token = d.get("refresh_token")

    agent = OutlookAgentModule(user_email="kalaiyarasig@cognethro.com")
    token = agent.get_access_token(refresh_token=r_token, allow_device_flow=False)
    emails = agent.fetch_unread_emails(refresh_token=r_token) or []

    print(f"Total unread email(s) retrieved: {len(emails)}")
    for em in emails:
        sub = em.get("subject", "No Subject")
        sender = em.get("sender") or em.get("from") or "Unknown"
        atts = em.get("attachments", [])
        print(f"  * Subject: '{sub}' | Sender: {sender} | Attachments: {len(atts)}")
        for a in atts:
            print(f"      - {a.get('filename')}")

if __name__ == "__main__":
    fetch()
