import os
from dotenv import load_dotenv
load_dotenv()
from start_flow import *
from Outlook_Agent.outlook_agent_module import OutlookAgentModule
import requests

test_email = os.getenv("TEST_MONITOR_EMAIL") or os.getenv("DELEGATED_SENDER_EMAIL") or os.getenv("SENDER_EMAIL") or 'drivesupport@cognethro.com'
agent = OutlookAgentModule(user_email=test_email)
token = agent.get_access_token()
print("Got Token. Testing Graph API...")

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
print("1. Testing /users endpoint...")
resp1 = requests.get("https://graph.microsoft.com/v1.0/users", headers=headers)
print("Response:", resp1.status_code)

print(f"2. Testing /users/{test_email}...")
resp2 = requests.get(f"https://graph.microsoft.com/v1.0/users/{test_email}", headers=headers)
print("Response:", resp2.status_code, resp2.text[:100])

target_user = os.getenv("WCUW_MONITOR_EMAIL") or "kalaiyarasi2@cognethro.com"
print(f"3. Testing {target_user}...")
resp3 = requests.get(f"https://graph.microsoft.com/v1.0/users/{target_user}/messages?$top=1", headers=headers)
print("Response:", resp3.status_code, resp3.text[:100])

