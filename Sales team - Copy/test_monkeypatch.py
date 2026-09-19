import os
from dotenv import load_dotenv
load_dotenv()
from start_flow import *
from Outlook_Agent.outlook_agent_module import OutlookAgentModule
import requests

agent = OutlookAgentModule(user_email='drivesupport@cognethro.com')
token = agent.get_access_token()
print("Got Token. Testing Graph API...")

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
print("1. Testing /users endpoint...")
resp1 = requests.get("https://graph.microsoft.com/v1.0/users", headers=headers)
print("Response:", resp1.status_code)

print("2. Testing /users/drivesupport@cognethro.com...")
resp2 = requests.get("https://graph.microsoft.com/v1.0/users/drivesupport@cognethro.com", headers=headers)
print("Response:", resp2.status_code, resp2.text[:100])

print("3. Testing kalaiyarasi...")
resp3 = requests.get("https://graph.microsoft.com/v1.0/users/kalaiyarasi2@cognethro.com/messages?$top=1", headers=headers)
print("Response:", resp3.status_code, resp3.text[:100])

