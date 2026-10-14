import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

WORKSPACE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE_DIR / "Outlook_Agent"))
load_dotenv(WORKSPACE_DIR / ".env")

from outlook_agent_module import OutlookAgentModule, _graph_get
from start_flow import get_active_refresh_token

def main():
    target_email = sys.argv[1] if len(sys.argv) > 1 else (
        os.getenv("TEST_MONITOR_EMAIL") 
        or os.getenv("WCUW_MONITOR_EMAIL") 
        or os.getenv("DELEGATED_SENDER_EMAIL") 
        or os.getenv("SENDER_EMAIL") 
        or "drivesupport@cognethro.com"
    )
    agent = OutlookAgentModule(user_email=target_email)
    token = agent.get_access_token(refresh_token=get_active_refresh_token(target_email), allow_device_flow=False)
    
    data = _graph_get(
        token,
        "https://graph.microsoft.com/v1.0/me/messages",
        params={
            "$filter": "isRead eq false",
            "$top": 10,
            "$select": "id,subject,from,receivedDateTime,hasAttachments",
        }
    )
    
    messages = data.get("value", [])
    print(f"Found {len(messages)} unread messages")
    
    for msg in messages:
        msg_id = msg.get("id")
        print(f"\nMessage ID: {msg_id}")
        print(f"HasAttachments flag: {msg.get('hasAttachments')}")
        
        att_data = _graph_get(token, f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments")
        attachments = att_data.get("value", [])
        
        print(f"Total attachments returned by API: {len(attachments)}")
        for i, att in enumerate(attachments):
            print(f"  [{i}] Name: {att.get('name')}")
            print(f"      Type: {att.get('@odata.type')}")
            print(f"      isInline: {att.get('isInline')}")
            print(f"      Size: {att.get('size')} bytes")

if __name__ == "__main__":
    main()
