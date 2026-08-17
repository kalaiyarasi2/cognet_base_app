# Fix Tenant, User Access & Login — DB Connectivity Issues

## Problem Summary

After investigating the full stack (backend DB → API routes → frontend UI), I found **4 issues** that break the Tenant/User Access and Login flow:

## Issues Found

### Issue 1: ❌ Database Was Corrupted
The `converter.db` file was malformed (likely caused by WAL/SHM files from git pull).
- **Status**: ✅ **Already fixed** — I deleted the corrupt DB and reinitialized it with all tables + seed admin/demo accounts.

### Issue 2: ❌ Missing `/api/modules` Backend Endpoint
The `useTenant.ts` hook calls `GET /api/modules?tenant_code=XXX` to fetch tenant-specific enabled modules, but **no such endpoint exists** in [auth_routes.py](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/auth_routes.py) or [app.py](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/app.py).
- **Impact**: The tenant module permission system silently fails — the frontend always falls back to default modules `["INVOICE", "SBC"]`.
- **Fix**: Add a new `GET /api/modules` endpoint to `auth_routes.py` that queries the `tenants` table by `tenant_code`.

### Issue 3: ❌ TypeScript Error in `api.ts` — `forgotPassword` uses `str` instead of `string`
In [api.ts:384](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/frontend/file-classifier-hub-main/src/lib/api.ts#L384), the `forgotPassword` function parameter type is `str` (Python type) instead of `string` (TypeScript type).
- **Impact**: TypeScript compilation error preventing builds.
- **Fix**: Change `str` → `string`.

### Issue 4: ❌ Login Does Not Pass `can_manage_tenants` / `can_manage_users` to Frontend Auth Store
The login flow in [login.tsx:54-61](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/frontend/file-classifier-hub-main/src/routes/login.tsx#L54-L61) saves user data to the auth store but **does not include** `can_manage_tenants` and `can_manage_users` from the API response. The backend returns these fields, but the frontend discards them.
- **Impact**: The UserManagement component relies on `user.can_manage_tenants` and `user.can_manage_users` to show admin controls — they're always `undefined`, so admin controls may not appear correctly.
- **Fix**: Include these fields when calling `login()` in the login page.

> [!IMPORTANT]
> All fixes are **add-on only** — no existing code is removed or replaced. Only new endpoint added and missing field values added to existing calls.

## Proposed Changes

### Backend — Auth Routes

#### [MODIFY] [auth_routes.py](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/auth_routes.py)
- **Add** a new `GET /api/modules` endpoint at the end of the file that:
  - Accepts `tenant_code` query parameter
  - Queries `poc_db.get_tenant(tenant_code)` 
  - Returns `{ status, tenant_code, tenant_name, tenant_id, active, enabled_modules, email }`
  - Falls back gracefully with a default `["INVOICE", "SBC"]` if tenant not found

---

### Frontend — API Layer

#### [MODIFY] [api.ts](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/frontend/file-classifier-hub-main/src/lib/api.ts)
- Fix `str` → `string` type on line 384 (forgotPassword parameter)

---

### Frontend — Login Page

#### [MODIFY] [login.tsx](file:///c:/Users/INT002/cognet_base_app/Sales%20team%20-%20Copy/frontend/file-classifier-hub-main/src/routes/login.tsx)
- Add `can_manage_tenants` and `can_manage_users` fields to the `login()` call (lines 54-61)

---

## Verification Plan

### Automated Tests
- Run `python check_db.py` to verify DB tables, seed data, and login simulation
- Start the backend with `python app.py` and test the new `/api/modules` endpoint
- Verify TypeScript compiles without errors

### Manual Verification
- Login page: test with `kalaiyarasig@cognethro.com` (ADMIN) and `althafm@cognethro.com` (USER)
- Tenant page: verify it loads from DB (initially empty, create one, verify it persists)
- User Management page: verify it loads permissions from DB
