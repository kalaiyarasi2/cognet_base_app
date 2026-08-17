import os
import sys
import importlib.util
import jwt
from datetime import datetime, timedelta
from typing import Optional, List, Union
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from email_service import send_otp_email

# ── Robust poc_db import ──────────────────────────────────────────────────────
# The file-classification- sub-app pollutes sys.path with its own 'database'
# package (which has no poc_db). We bypass sys.path entirely by loading the
# correct database/poc_db.py using its absolute file path.
_AUTH_DIR = Path(__file__).parent.resolve()
_POC_DB_PATH = _AUTH_DIR / "database" / "poc_db.py"
if "database.poc_db" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("database.poc_db", str(_POC_DB_PATH))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["database.poc_db"] = _mod
    _spec.loader.exec_module(_mod)
poc_db = sys.modules["database.poc_db"]

_SESSION_DB_PATH = _AUTH_DIR / "database" / "session_db.py"
if "database.session_db" not in sys.modules:
    _spec_s = importlib.util.spec_from_file_location("database.session_db", str(_SESSION_DB_PATH))
    _mod_s = importlib.util.module_from_spec(_spec_s)
    sys.modules["database.session_db"] = _mod_s
    _spec_s.loader.exec_module(_mod_s)
session_db = sys.modules["database.session_db"]

router = APIRouter(prefix="/api", tags=["Authentication & Access Control"])

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fc_sales_team_super_secret_jwt_key_2026")
ALGORITHM = "HS256"

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────
class SSOCallbackRequest(BaseModel):
    code: Optional[str] = None
    email: Optional[str] = None
    provider: Optional[str] = "google"
    code_verifier: Optional[str] = None
    redirect_uri: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None

class GrantAccessRequest(BaseModel):
    email: str
    full_name: Optional[str] = ""
    role: str = "USER"  # 'ADMIN' or 'USER'
    source: str = "MANUAL" # 'MANUAL' or 'EXISTING_DB'
    allowed_modules: Optional[Union[List[str], str]] = "ALL"

class RevokeAccessRequest(BaseModel):
    email: str

# ─────────────────────────────────────────────────────────────────────────────
# JWT Helpers
# ─────────────────────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_from_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        # Default fallback for unauthenticated requests in dev mode
        return {"email": "admin@local", "name": "Super Administrator", "role": "ADMIN", "allowed_modules": "ALL", "can_manage_tenants": True, "can_manage_users": True}
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid session token.")

import requests
from fastapi.responses import RedirectResponse

class ForgotPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str

class VerifyOtpRequest(BaseModel):
    email: str
    otp_code: str

class RequestOtpRequest(BaseModel):
    email: str

class CheckEmailRequest(BaseModel):
    email: str

class SetupPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str

# ─────────────────────────────────────────────────────────────────────────────
# Authentication Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/auth/sso/callback")
async def sso_callback(req: SSOCallbackRequest, request: Request):
    """
    SSO Callback Gatekeeper:
    Verifies user identity via Microsoft OAuth 2.0 or direct email SSO.
    Enforces STRICT DB Permission check.
    """
    target_email = None
    
    # Real Microsoft OAuth 2.0 Authorization Code Exchange
    if req.code:
        client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID", "")
        redirect_uri = req.redirect_uri or os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:5173/auth/callback")
        
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": client_id,
            "code": req.code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read Files.ReadWrite.All Sites.ReadWrite.All offline_access",
        }
        
        # If we have a PKCE code_verifier, we MUST NOT send a client_secret (even if one is in .env).
        # This prevents invalid client secret errors when a placeholder is present in .env.
        if not req.code_verifier and client_secret and client_secret.strip() != "":
            data["client_secret"] = client_secret
            
        if req.code_verifier:
            data["code_verifier"] = req.code_verifier
            
        try:
            res = requests.post(token_url, data=data, timeout=10)
            if res.status_code == 200:
                tok_data = res.json()
                id_token = tok_data.get("id_token")
                # Decode id_token to extract email
                if id_token:
                    decoded = jwt.decode(id_token, options={"verify_signature": False})
                    target_email = decoded.get("email") or decoded.get("preferred_username") or decoded.get("upn")
                else:
                    print(f"[WARN] No id_token in Microsoft response: {tok_data}")
                
                # ── Inject the Graph access_token into the SharePoint agent ──
                graph_access_token = tok_data.get("access_token")
                expires_in_sec = int(tok_data.get("expires_in", 3600))
                if graph_access_token:
                    try:
                        from SharePoint_Agent.sharepoint_agent_module import sharepoint_agent
                        sharepoint_agent.set_delegated_token(graph_access_token, expires_in=expires_in_sec)
                        print(f"[INFO] SharePoint agent updated with delegated Graph token for '{target_email}' (expires in {expires_in_sec}s)")
                    except Exception as sp_err:
                        print(f"[WARN] Could not inject token into SharePoint agent: {sp_err}")
            else:
                print(f"[ERROR] Microsoft Token Exchange Failed: {res.status_code} {res.text}")
                raise HTTPException(status_code=401, detail=f"Microsoft SSO Failed: {res.json().get('error_description', 'Unknown error')}")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            print(f"[WARN] Microsoft OAuth token exchange failed: {e}")
            raise HTTPException(status_code=401, detail="Microsoft OAuth token exchange failed due to a network or server error.")
            
    if not target_email and req.email:
        target_email = req.email.strip().lower()
        
    if not target_email:
        raise HTTPException(status_code=401, detail="Failed to extract email from Microsoft login. Please try again.")
    
    # 1. Strict DB Permission Check
    perm = poc_db.get_user_permission(target_email)
    
    if not perm:
        raise HTTPException(
            status_code=403,
            detail=f"Access Denied: The account '{target_email}' has not been granted access by an Administrator."
        )
    
    if perm.get("access_status") == "REVOKED":
        raise HTTPException(
            status_code=403,
            detail=f"Access Revoked: Your access for '{target_email}' has been disabled by an Administrator."
        )
    
    # 2. Issue JWT Token
    modules = perm.get("allowed_modules", "ALL") or "ALL"
    user_payload = {
        "email": perm["email"],
        "name": perm["full_name"],
        "role": perm["role"],
        "allowed_modules": modules.split(",") if isinstance(modules, str) and modules != "ALL" else modules,
        "can_manage_tenants": perm["role"] == "ADMIN",
        "can_manage_users": perm["role"] in ("ADMIN", "TENANT_ADMIN")
    }
    token = create_access_token(user_payload)
    
    # Record User Session & IP in user_sessions.db
    try:
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.headers.get("X-Real-IP") or (request.client.host if request.client else "127.0.0.1")
        user_agent = request.headers.get("User-Agent", "Browser")
        session_db.record_session(perm["email"], perm.get("full_name", ""), perm.get("role", "USER"), client_ip, user_agent)
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "SSO authentication successful.",
        "token": token,
        "user": user_payload
    }

# ─────────────────────────────────────────────────────────────────────────────
# Microsoft SSO GET Callback (server-side redirect flow)
# Microsoft redirects here with ?code=... — we exchange it and redirect
# the user back to the frontend with a JWT.
# ─────────────────────────────────────────────────────────────────────────────
_FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

@router.get("/auth/sso/callback")
async def sso_get_callback(code: str = None, error: str = None, error_description: str = None):
    if error:
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error={error_description or error}")

    if not code:
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error=No+authorization+code+received")

    client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "")
    redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", f"{_FRONTEND_ORIGIN}/api/auth/sso/callback")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "openid profile email User.Read Files.ReadWrite.All Sites.ReadWrite.All offline_access",
    }
    if client_secret and client_secret.strip():
        data["client_secret"] = client_secret

    try:
        res = requests.post(token_url, data=data, timeout=10)
        if res.status_code != 200:
            print(f"[ERROR] Microsoft Token Exchange Failed (GET): {res.status_code} {res.text}")
            err_desc = res.json().get("error_description", "Token exchange failed") if res.text else "Token exchange failed"
            return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error={err_desc}")

        tok_data = res.json()
        id_token = tok_data.get("id_token")
        target_email = None
        target_name = None

        if id_token:
            decoded = jwt.decode(id_token, options={"verify_signature": False})
            target_email = decoded.get("email") or decoded.get("preferred_username") or decoded.get("upn")
            target_name = decoded.get("name", "")

        graph_access_token = tok_data.get("access_token")
        expires_in_sec = int(tok_data.get("expires_in", 3600))
        if graph_access_token:
            try:
                from SharePoint_Agent.sharepoint_agent_module import sharepoint_agent
                sharepoint_agent.set_delegated_token(graph_access_token, expires_in=expires_in_sec)
                print(f"[INFO] SharePoint agent updated with delegated Graph token for '{target_email}' (expires in {expires_in_sec}s)")
            except Exception as sp_err:
                print(f"[WARN] Could not inject token into SharePoint agent: {sp_err}")

    except Exception as e:
        print(f"[ERROR] Microsoft OAuth GET token exchange failed: {e}")
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error=Microsoft+OAuth+exchange+failed")

    if not target_email:
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error=Could+not+extract+email+from+Microsoft+login")

    perm = poc_db.get_user_permission(target_email)
    if not perm:
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error=Access+Denied:+Account+not+granted+access")

    if perm.get("access_status") == "REVOKED":
        return RedirectResponse(f"{_FRONTEND_ORIGIN}/auth/callback?error=Access+Revoked:+Your+access+has+been+disabled")

    modules = perm.get("allowed_modules", "ALL") or "ALL"
    user_payload = {
        "email": perm["email"],
        "name": perm["full_name"],
        "role": perm["role"],
        "allowed_modules": modules.split(",") if isinstance(modules, str) and modules != "ALL" else modules,
        "can_manage_tenants": perm["role"] == "ADMIN",
        "can_manage_users": perm["role"] in ("ADMIN", "TENANT_ADMIN")
    }
    token = create_access_token(user_payload)

    import urllib.parse
    encoded_token = urllib.parse.quote(token)
    encoded_email = urllib.parse.quote(target_email or "")
    encoded_name = urllib.parse.quote(target_name or "")
    encoded_role = urllib.parse.quote(user_payload["role"])
    encoded_modules = urllib.parse.quote(",".join(user_payload["allowed_modules"]) if isinstance(user_payload["allowed_modules"], list) else str(user_payload["allowed_modules"]))

    frontend_redirect = (
        f"{_FRONTEND_ORIGIN}/auth/callback"
        f"?sso_token={encoded_token}"
        f"&email={encoded_email}"
        f"&name={encoded_name}"
        f"&role={encoded_role}"
        f"&allowed_modules={encoded_modules}"
    )
    return RedirectResponse(frontend_redirect)

@router.post("/auth/check-email")
async def check_email(req: CheckEmailRequest):
    """Check if email exists and if it's a first time login."""
    clean_email = req.email.strip().lower()
    perm = poc_db.get_user_permission(clean_email)
    if not perm:
        raise HTTPException(
            status_code=403, 
            detail=f"Access Denied: The account '{clean_email}' has not been granted access by an Administrator."
        )
        
    if not perm.get("password_hash"):
        # First time setup
        otp_code = poc_db.store_otp(clean_email, "setup")
        send_otp_email(clean_email, otp_code, "account setup")
        return {"status": "first_time_setup", "message": "OTP sent to your email for account setup."}
    else:
        return {"status": "existing_user"}

@router.post("/auth/setup-password")
async def setup_password(req: SetupPasswordRequest, request: Request):
    """Verify OTP and set password for a first time user."""
    clean_email = req.email.strip().lower()
    perm = poc_db.get_user_permission(clean_email)
    if not perm:
        raise HTTPException(status_code=403, detail="Email not recognized.")
        
    if not poc_db.verify_otp(clean_email, req.otp_code, "setup"):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP.")
        
    # Save password
    poc_db.update_user_password(clean_email, req.new_password)
    
    # Return JWT
    modules = perm.get("allowed_modules", "ALL") or "ALL"
    user_payload = {
        "email": perm["email"],
        "name": perm["full_name"],
        "role": perm["role"],
        "allowed_modules": modules.split(",") if isinstance(modules, str) and modules != "ALL" else modules,
        "can_manage_tenants": perm["role"] == "ADMIN",
        "can_manage_users": perm["role"] in ("ADMIN", "TENANT_ADMIN")
    }
    token = create_access_token(user_payload)
    
    try:
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.headers.get("X-Real-IP") or (request.client.host if request.client else "127.0.0.1")
        user_agent = request.headers.get("User-Agent", "Browser")
        session_db.record_session(perm["email"], perm.get("full_name", ""), perm.get("role", "USER"), client_ip, user_agent)
    except Exception:
        pass

    return {
        "status": "ok",
        "token": token,
        "user": user_payload,
        "message": "Account setup complete!"
    }

@router.post("/auth/login")
async def direct_login(req: LoginRequest, request: Request):
    """Direct email + password login with DB permission verification."""
    clean_email = req.email.strip().lower()
    
    if not req.password or not req.password.strip():
        raise HTTPException(status_code=400, detail="Password is required.")
        
    # Check DB permissions
    perm = poc_db.get_user_permission(clean_email)
    
    if not perm:
        raise HTTPException(
            status_code=403,
            detail=f"Access Denied: The email '{clean_email}' is not authorized. Please ask an Admin for access."
        )
    
    # Password Verification (if password_hash is set)
    if not perm.get("password_hash"):
        raise HTTPException(status_code=400, detail="Account not setup. Please go back and enter your email first to complete setup.")
        
    if not poc_db.verify_user_password(clean_email, req.password):
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again or use Forgot Password.")
        
    # After password verification succeeds, send OTP
    otp_code = poc_db.store_otp(clean_email, "login")
    send_otp_email(clean_email, otp_code, "login")

    return {
        "status": "otp_required",
        "email": clean_email,
        "message": "Please enter the OTP sent to your email to continue."
    }

@router.post("/auth/verify-otp")
async def verify_otp(req: VerifyOtpRequest, request: Request):
    """Verify OTP and return final JWT."""
    clean_email = req.email.strip().lower()
    
    if not poc_db.verify_otp(clean_email, req.otp_code, "login"):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP.")
        
    perm = poc_db.get_user_permission(clean_email)
    if not perm:
        raise HTTPException(status_code=403, detail="User not found or access revoked.")
        
    modules = perm.get("allowed_modules", "ALL") or "ALL"
    user_payload = {
        "email": perm["email"],
        "name": perm["full_name"],
        "role": perm["role"],
        "allowed_modules": modules.split(",") if isinstance(modules, str) and modules != "ALL" else modules,
        "can_manage_tenants": perm["role"] == "ADMIN",
        "can_manage_users": perm["role"] in ("ADMIN", "TENANT_ADMIN")
    }
    token = create_access_token(user_payload)
    
    # Record User Session & IP in user_sessions.db
    try:
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.headers.get("X-Real-IP") or (request.client.host if request.client else "127.0.0.1")
        user_agent = request.headers.get("User-Agent", "Browser")
        session_db.record_session(perm["email"], perm.get("full_name", ""), perm.get("role", "USER"), client_ip, user_agent)
    except Exception:
        pass

    return {
        "status": "ok",
        "token": token,
        "user": user_payload
    }

class RevokeSessionRequest(BaseModel):
    session_id: int

@router.get("/auth/active-sessions")
async def get_active_sessions():
    """Retrieve all user login sessions with IP addresses and timestamps from user_sessions.db."""
    sessions = session_db.get_active_sessions()
    return {"status": "ok", "sessions": sessions}

@router.post("/auth/revoke-session")
async def revoke_session_endpoint(req: RevokeSessionRequest):
    """Revoke a specific user login session."""
    success = session_db.revoke_session(req.session_id)
    return {"status": "ok" if success else "error"}

@router.post("/auth/request-otp")
async def request_otp(req: RequestOtpRequest):
    """Request OTP for forgot password flow."""
    clean_email = req.email.strip().lower()
    perm = poc_db.get_user_permission(clean_email)
    if not perm:
        raise HTTPException(status_code=404, detail=f"No active account found for '{clean_email}'.")
        
    otp_code = poc_db.store_otp(clean_email, "reset")
    send_otp_email(clean_email, otp_code, "reset password")
    return {"status": "ok", "message": "OTP sent to your email."}

@router.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """Reset or update user password in DB after OTP verification."""
    clean_email = req.email.strip().lower()
    perm = poc_db.get_user_permission(clean_email)
    
    if not perm:
        raise HTTPException(status_code=404, detail=f"No active account found for '{clean_email}'.")
        
    if not poc_db.verify_otp(clean_email, req.otp_code, "reset"):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
    success = poc_db.update_user_password(clean_email, req.new_password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update password.")
        
    return {"status": "ok", "message": "Password updated successfully. You can now sign in with your new password."}

@router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user_from_token)):
    return {"status": "ok", "user": user}

# ─────────────────────────────────────────────────────────────────────────────
# Admin User & Permission Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/admin/users")
async def list_admin_users(user: dict = Depends(get_current_user_from_token)):
    """Fetch granted permissions list and company employee directory."""
    permissions = poc_db.list_all_permissions()
    employees = poc_db.list_company_employees()
    
    return {
        "status": "ok",
        "current_admin": user,
        "permissions": permissions,
        "employee_directory": employees
    }

@router.post("/admin/grant-access")
async def admin_grant_access(req: GrantAccessRequest, user: dict = Depends(get_current_user_from_token)):
    """Admin grants access to a user manually or from the company employee directory."""
    admin_email = user.get("email", "admin@local")
    admin_role = user.get("role", "USER")
    
    if admin_role == "TENANT_ADMIN" and req.role == "ADMIN":
        raise HTTPException(status_code=403, detail="Tenant admins cannot create global ADMIN accounts.")

    
    modules_val = req.allowed_modules
    if isinstance(modules_val, list):
        modules_val = ",".join(modules_val)
        
    poc_db.grant_user_access(
        email=req.email,
        full_name=req.full_name,
        role=req.role,
        source=req.source,
        granted_by=admin_email,
        allowed_modules=modules_val or "ALL"
    )
    
    return {
        "status": "ok",
        "message": f"Successfully granted {req.role} access to {req.email}."
    }

@router.post("/admin/revoke-access")
async def admin_revoke_access(req: RevokeAccessRequest, user: dict = Depends(get_current_user_from_token)):
    """Admin revokes access for a user."""
    poc_db.revoke_user_access(req.email)
    
    return {
        "status": "ok",
        "message": f"Successfully revoked access for {req.email}."
    }

@router.post("/admin/delete-access")
async def admin_delete_access(req: RevokeAccessRequest, user: dict = Depends(get_current_user_from_token)):
    """Admin permanently deletes a user permission record."""
    poc_db.delete_user_permission(req.email)
    
    return {
        "status": "ok",
        "message": f"Successfully deleted user permission for {req.email}."
    }

# ─────────────────────────────────────────────────────────────────────────────
# Tenant Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────
class CreateTenantRequest(BaseModel):
    tenant_code: str
    tenant_name: str
    email: str
    active: bool = True
    enabled_modules: Optional[List[str]] = ["INVOICE", "SBC"]
    default_confidence_threshold: Optional[float] = 0.85
    output_root: Optional[str] = ""

class UpdateTenantRequest(BaseModel):
    tenant_name: Optional[str] = None
    email: Optional[str] = None
    active: Optional[bool] = None
    enabled_modules: Optional[List[str]] = None
    default_confidence_threshold: Optional[float] = None
    output_root: Optional[str] = None

@router.get("/admin/tenants")
async def list_tenants_endpoint():
    """List all tenant organizations."""
    tenants = poc_db.list_tenants()
    return {"status": "ok", "tenants": tenants}

@router.post("/admin/tenants")
async def create_tenant_endpoint(req: CreateTenantRequest):
    """Create a new tenant organization connected to DB."""
    try:
        existing = poc_db.get_tenant(req.tenant_code)
        if existing:
            raise HTTPException(status_code=400, detail=f"Tenant code '{req.tenant_code}' already exists.")
        
        success = poc_db.create_tenant(
            tenant_code=req.tenant_code,
            tenant_name=req.tenant_name,
            email=req.email,
            active=req.active,
            enabled_modules=req.enabled_modules,
            default_confidence_threshold=req.default_confidence_threshold or 0.85,
            output_root=req.output_root or ""
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create tenant in database.")
            
        if req.email:
            poc_db.grant_user_access(
                email=req.email,
                full_name=f"{req.tenant_name} Admin",
                role="TENANT_ADMIN",
                source="MANUAL",
                granted_by="admin@local",
                allowed_modules=req.enabled_modules or "ALL"
            )
            
        return {"status": "ok", "message": f"Tenant '{req.tenant_code}' created successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/admin/tenants/{tenant_code}")
async def update_tenant_endpoint(tenant_code: str, req: UpdateTenantRequest):
    """Update tenant settings, module access, or status."""
    success = poc_db.update_tenant(
        tenant_code=tenant_code,
        tenant_name=req.tenant_name,
        email=req.email,
        active=req.active,
        enabled_modules=req.enabled_modules,
        default_confidence_threshold=req.default_confidence_threshold,
        output_root=req.output_root
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_code}' not found or update failed.")
    return {"status": "ok", "message": f"Tenant '{tenant_code}' updated successfully."}

@router.delete("/admin/tenants/{tenant_code}")
async def delete_tenant_endpoint(tenant_code: str):
    """Delete a tenant record."""
    success = poc_db.delete_tenant(tenant_code)
    if not success:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_code}' not found.")
    return {"status": "ok", "message": f"Tenant '{tenant_code}' deleted successfully."}

# ─────────────────────────────────────────────────────────────────────────────
# Tenant Module Access Endpoint (used by useTenant.ts frontend hook)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/modules")
async def get_tenant_modules(tenant_code: str = "GLOBAL"):
    """
    Return enabled modules for a given tenant_code.
    Called by the frontend useTenant() hook to enforce tenant-level module permissions.
    Falls back to a default module list if the tenant is not found.
    """
    tenant = poc_db.get_tenant(tenant_code)
    if tenant:
        return {
            "status": "ok",
            "tenant_id": tenant.get("tenant_id"),
            "tenant_code": tenant.get("tenant_code", tenant_code),
            "tenant_name": tenant.get("tenant_name", tenant_code),
            "active": tenant.get("active", True),
            "enabled_modules": tenant.get("enabled_modules", ["INVOICE", "SBC"]),
            "email": tenant.get("email", ""),
        }
    # Fallback: tenant not found — return a permissive default
    return {
        "status": "ok",
        "tenant_id": None,
        "tenant_code": tenant_code,
        "tenant_name": tenant_code,
        "active": True,
        "enabled_modules": ["INVOICE", "SBC", "RPVE", "RE", "ACCORD", "LOSS_RUN", "BANK_STATEMENT", "VENDOR_INVOICE"],
        "email": "",
    }

