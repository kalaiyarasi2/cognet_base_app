import os
from pathlib import Path
from start_flow import fetch_outlook_attachments

def check_live_inbox():
    email_user = "kalaiyarasig@cognethro.com"
    print(f"Connecting to Outlook mailbox for: {email_user}...")
    temp_dir = Path("./temp_test_inbox")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_files, token = fetch_outlook_attachments(
        dest_folder=temp_dir,
        mark_read=False,
        user_email=email_user
    )
    print(f"Total downloaded attachment(s): {len(downloaded_files)}")
    for f in downloaded_files:
        print(f"  * Downloaded PDF: {f.name} ({round(f.stat().st_size / 1024, 1)} KB)")

if __name__ == "__main__":
    check_live_inbox()
