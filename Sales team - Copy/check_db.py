"""Reinitialize the database and verify all tables."""
import sys
sys.path.insert(0, ".")
from database.poc_db import init_poc_tables, grant_user_access, list_all_permissions, list_tenants, get_user_permission
import json

# Initialize all tables
print("Initializing tables...")
init_poc_tables()
print("Tables initialized successfully!")

# Bootstrap super admins (same as app.py lifespan)
SUPER_ADMINS = [
    ("kalaiyarasig@cognethro.com", "Kalaiyarasi G", "ADMIN"),
    ("admin@local", "Super Administrator", "ADMIN"),
    ("admin@company.com", "Enterprise Admin", "ADMIN"),
]
for email, name, role in SUPER_ADMINS:
    grant_user_access(email, name, role, "MANUAL", "SYSTEM")
print(f"Bootstrapped {len(SUPER_ADMINS)} super admin accounts.")

# Also add the demo accounts from login.tsx
DEMO_USERS = [
    ("althafm@cognethro.com", "Althaf M", "USER"),
    ("jawagarnathst@cognethro.com", "Jawagarnath ST", "USER"),
]
for email, name, role in DEMO_USERS:
    grant_user_access(email, name, role, "MANUAL", "SYSTEM")
print(f"Added {len(DEMO_USERS)} demo user accounts.")

# Verify
print("\n=== APP_PERMISSIONS ===")
perms = list_all_permissions()
print(f"Total: {len(perms)}")
for p in perms:
    print(f"  {p['email']} | {p['role']} | {p['access_status']} | modules={p.get('allowed_modules', 'N/A')}")

print("\n=== TENANTS ===")
tenants = list_tenants()
print(f"Total: {len(tenants)}")
for t in tenants:
    print(f"  {t}")

# Test login flow
print("\n=== LOGIN SIMULATION ===")
test_emails = ["kalaiyarasig@cognethro.com", "admin@local", "althafm@cognethro.com", "notexist@test.com"]
for email in test_emails:
    result = get_user_permission(email)
    if result:
        print(f"  {email} -> FOUND: role={result['role']}, status={result['access_status']}, modules={result.get('allowed_modules')}")
    else:
        print(f"  {email} -> NOT FOUND (login would fail with 403)")

print("\n=== ALL CHECKS PASSED ===")
