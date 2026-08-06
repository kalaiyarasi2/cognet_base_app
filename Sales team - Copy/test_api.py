"""Test all API endpoints for Tenant, User Access, and Login."""
import requests
import json

BASE = "http://localhost:8000"

def test(name, method, url, **kwargs):
    print(f"\n=== {name} ===")
    try:
        r = getattr(requests, method)(url, **kwargs, timeout=10)
        print(f"  Status: {r.status_code}")
        data = r.json()
        print(f"  Response: {json.dumps(data, indent=2)}")
        return data
    except Exception as e:
        print(f"  ERROR: {e}")
        return {}

# 1. Login as admin
d = test("Login admin@local", "post", f"{BASE}/api/auth/login",
         json={"email": "admin@local"})
token = d.get("token", "")
user = d.get("user", {})
print(f"\n  [CHECK] can_manage_tenants = {user.get('can_manage_tenants')}")
print(f"  [CHECK] can_manage_users = {user.get('can_manage_users')}")

# 2. Login as demo user
d = test("Login kalaiyarasig@cognethro.com", "post", f"{BASE}/api/auth/login",
         json={"email": "kalaiyarasig@cognethro.com"})

# 3. Login with unauthorized email
test("Login notexist@test.com (should 403)", "post", f"{BASE}/api/auth/login",
     json={"email": "notexist@test.com"})

# 4. Admin users
d = test("GET /api/admin/users", "get", f"{BASE}/api/admin/users",
         headers={"Authorization": f"Bearer {token}"})
perms = d.get("permissions", [])
emps = d.get("employee_directory", [])
print(f"\n  Permissions count: {len(perms)}")
print(f"  Employees count: {len(emps)}")

# 5. Tenants list
test("GET /api/admin/tenants", "get", f"{BASE}/api/admin/tenants")

# 6. NEW: Modules endpoint (fallback when tenant not found)
test("GET /api/modules?tenant_code=GLOBAL", "get",
     f"{BASE}/api/modules", params={"tenant_code": "GLOBAL"})

# 7. Create tenant then query modules
test("POST create tenant TEST_ORG", "post", f"{BASE}/api/admin/tenants",
     json={
         "tenant_code": "TEST_ORG",
         "tenant_name": "Test Organization",
         "email": "admin@testorg.com",
         "active": True,
         "enabled_modules": ["INVOICE", "SBC", "RPVE"],
         "default_confidence_threshold": 0.85
     })

# 8. Query modules for the tenant we just created
test("GET /api/modules?tenant_code=TEST_ORG", "get",
     f"{BASE}/api/modules", params={"tenant_code": "TEST_ORG"})

# 9. Delete test tenant
test("DELETE /api/admin/tenants/TEST_ORG", "delete",
     f"{BASE}/api/admin/tenants/TEST_ORG")

print("\n\n=== ALL ENDPOINT TESTS COMPLETE ===")
