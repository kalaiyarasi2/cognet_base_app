import sys
import importlib.util
import traceback
from pathlib import Path
from typing import List, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.middleware.cors import CORSMiddleware

WORKSPACE_DIR = Path(__file__).parent.resolve()

# Ensure CWD is always WORKSPACE_DIR so relative paths (e.g. monitor/monitor.log) resolve correctly
import os
os.chdir(WORKSPACE_DIR)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Add workspace root to sys.path
# ─────────────────────────────────────────────────────────────────────────────
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# ─────────────────────────────────────────────────────────────────────────────
# 1b. Environment & Global OCR Configuration
# ─────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(WORKSPACE_DIR / ".env")
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

tess_path = os.getenv("Tesseract_path")
if tess_path:
    os.environ["PATH"] = str(tess_path) + os.pathsep + os.environ.get("PATH", "")
    try:
        import pytesseract
        exe_name = "tesseract.exe" if os.name == "nt" else "tesseract"
        tess_exe = Path(tess_path) / exe_name
        if tess_exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(tess_exe.resolve())
            print(f"[INFO] Pytesseract configured globally to use: {tess_exe}")
    except ImportError:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# 2. Dynamic sub-app loader (scoped sys.path per sub-app)
# ─────────────────────────────────────────────────────────────────────────────
with open(WORKSPACE_DIR / "import_errors.log", "w", encoding="utf-8") as _f:
    _f.write("=== Import Diagnostics Startup ===\n\n")

def load_sub_app(module_name: str, file_path: Path) -> FastAPI:
    log_file = WORKSPACE_DIR / "import_errors.log"
    if not file_path.exists():
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[WARN] File path does not exist: {file_path}\n")
        return FastAPI()

    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[WARN] Could not create module spec for: {file_path}\n")
        return FastAPI()

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    parent_dir = str(file_path.parent.resolve())
    sys.path.insert(0, parent_dir)

    # Snapshot which 'common' modules are already cached before loading this sub-app
    # so we can evict any that got bound to the sub-app's own local packages.
    _SHARED_NAMES = {"database", "database.db", "config", "models", "utils", "main"}
    _pre_snapshot = {k for k in sys.modules if k in _SHARED_NAMES}

    try:
        spec.loader.exec_module(module)
    except Exception:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[ERROR] Failed to load module {module_name} from {file_path}:\n")
            traceback.print_exc(file=f)
            f.write("\n" + "=" * 80 + "\n\n")
        return FastAPI()
    finally:
        try:
            rel_to_workspace = file_path.resolve().relative_to(WORKSPACE_DIR.resolve())
            top_sub_dir = str(WORKSPACE_DIR / rel_to_workspace.parts[0]).lower()
        except Exception:
            top_sub_dir = parent_dir.lower()

        # Remove sub-app and parent directory paths that may have been inserted into sys.path
        for p in list(sys.path):
            if p and (top_sub_dir in p.lower() or parent_dir.lower() in p.lower()):
                while p in sys.path:
                    sys.path.remove(p)

        if str(WORKSPACE_DIR) in sys.path:
            sys.path.remove(str(WORKSPACE_DIR))
        sys.path.insert(0, str(WORKSPACE_DIR))

        # Evict all local sub-app modules loaded from the sub-app tree so they don't shadow packages for subsequent sub-apps
        for mod_name in list(sys.modules):
            if mod_name == module_name:
                continue
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            mod_file = getattr(mod, "__file__", None) or ""
            if mod_file and (parent_dir.lower() in mod_file.lower() or top_sub_dir in mod_file.lower()):
                del sys.modules[mod_name]

    sub_app = getattr(module, "app", FastAPI())
    print(f"[INFO] Loaded sub-app '{module_name}' from {file_path.name} ({len(sub_app.routes)} routes)")
    return sub_app


# ─────────────────────────────────────────────────────────────────────────────
# 3. Custom ASGI dispatcher
#    Routes by path prefix — sub-apps receive the path with prefix stripped.
#    Anything not matched by a prefix falls through to the default (classifier).
# ─────────────────────────────────────────────────────────────────────────────
class PrefixDispatcher:
    """
    Lightweight ASGI prefix router.

    For each (prefix, sub_app) pair:
      - A request whose path equals the prefix OR starts with prefix + "/"
        is forwarded to sub_app with the prefix stripped from scope["path"]
        and scope["root_path"] updated accordingly.
    All other requests go to `default`.
    """

    def __init__(
        self,
        routes: List[Tuple[str, ASGIApp]],
        default: ASGIApp,
    ) -> None:
        self.dispatch_routes = routes          # [(prefix, asgi_app), ...]
        self.default = default        # fallback ASGI app

        # Build Starlette Mounts to allow url_for to traverse sub-app routes
        from starlette.routing import Mount
        self.routes = [
            Mount(prefix, app=sub_app) for prefix, sub_app in routes
        ] + [Mount("", app=default)]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            # Lifespan and other events go straight to default
            await self.default(scope, receive, send)
            return

        path: str = scope.get("path", "/")

        for prefix, sub_app in self.dispatch_routes:
            if path == prefix or path.startswith(prefix + "/"):
                # Strip prefix; keep at least "/"
                remaining = path[len(prefix):] or "/"
                child_scope = dict(scope)
                child_scope["path"] = remaining
                child_scope["root_path"] = scope.get("root_path", "") + prefix
                await sub_app(child_scope, receive, send)
                return

        # No prefix matched — forward unchanged to default
        await self.default(scope, receive, send)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Load all sub-applications
# ─────────────────────────────────────────────────────────────────────────────
print("[INFO] Loading sub-applications...")
classifier_app = load_sub_app("classifier_api", WORKSPACE_DIR / "file-classification-" / "api.py")
gpu_app        = load_sub_app("gpu_api",        WORKSPACE_DIR / "Gpu_server" / "Unified_PDF_Platform" / "unified_app.py")
parity_app     = load_sub_app("parity_api",     WORKSPACE_DIR / "Parity_setup" / "backend" / "api_server.py")
renewal_app    = load_sub_app("renewal_api",    WORKSPACE_DIR / "Renewal_process" / "api_server.py")
resourcing_app = load_sub_app("resourcing_api", WORKSPACE_DIR / "Resourcing-edge" / "app.py")
rpve_app       = load_sub_app("rpve_api",       WORKSPACE_DIR / "rpve" / "RPVE_standalone.py")
converter_app  = load_sub_app("converter_api",  WORKSPACE_DIR / "File-Convertor" / "main.py")
payroll_app    = load_sub_app("payroll_api",    WORKSPACE_DIR / "Payroll_extractor" / "api_server.py")
claim_app      = load_sub_app("claim_api",      WORKSPACE_DIR / "base-claim-" / "app.py")
invoice_excel_app = load_sub_app("invoice_excel_api", WORKSPACE_DIR / "Invoice-to-excel-2026" / "Invoice-to-excel-2026" / "app_fastapi.py")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Build the unified ASGI app via PrefixDispatcher
#    Sub-app prefixes are checked first; classifier_app is the fallback.
# ─────────────────────────────────────────────────────────────────────────────

# Wrap classifier_app with CORS so direct pass-through requests get the header
classifier_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_dispatcher = PrefixDispatcher(
    routes=[
        ("/api/parity",     parity_app),
        ("/api/renewal",    renewal_app),
        ("/api/resourcing", resourcing_app),
        ("/api/rpve",       rpve_app),
        ("/api/convert",    converter_app),
        ("/api/gpu",        gpu_app),
        ("/api/payroll",    payroll_app),
        ("/api/invoice-excel", invoice_excel_app),
        ("/claim",          claim_app),
    ],
    default=classifier_app,
)

# ─────────────────────────────────────────────────────────────────────────────
# 6. Outer CORS + lifespan wrapper
#    We wrap the dispatcher in a thin FastAPI so uvicorn gets lifespan support,
#    and all responses get CORS headers regardless of which sub-app handled them.
# ─────────────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

# ── Robust poc_db import (bypasses sys.path pollution from sub-apps) ──────────
import importlib.util as _ilu
_POC_DB_PATH = WORKSPACE_DIR / "database" / "poc_db.py"
if "database.poc_db" not in sys.modules:
    _s = _ilu.spec_from_file_location("database.poc_db", str(_POC_DB_PATH))
    _m = _ilu.module_from_spec(_s)
    sys.modules["database.poc_db"] = _m
    _s.loader.exec_module(_m)
_poc_db = sys.modules["database.poc_db"]

@asynccontextmanager
async def unified_lifespan(a: FastAPI):
    # ── Shared SQLite DB ──
    try:
        _poc_db.init_poc_tables()
        print("[INIT] Shared SQLite DB tables initialized successfully.")

        # ── Bootstrap Super Admins (always ensure these are ADMIN) ──
        SUPER_ADMINS = [
            ("kalaiyarasig@cognethro.com", "Kalaiyarasi G",    "ADMIN"),
            ("admin@local",               "Super Administrator", "ADMIN"),
            ("admin@company.com",         "Enterprise Admin",    "ADMIN"),
        ]
        for _email, _name, _role in SUPER_ADMINS:
            _poc_db.grant_user_access(_email, _name, _role, "MANUAL", "SYSTEM")
        print(f"[INIT] Bootstrapped {len(SUPER_ADMINS)} super admin account(s).")
    except Exception as e:
        print(f"[WARN] Failed to initialize SQLite DB tables: {e}")

    # ── RPVE background workers ──
    print("[INIT] Running RPVE startup...")
    try:
        rpve_path = str(WORKSPACE_DIR / "rpve")
        if rpve_path not in sys.path:
            sys.path.insert(0, rpve_path)
        import job_store
        import job_worker
        job_store.get_job("dummy_check")
        recovered = job_store.recover_stale_jobs()
        if recovered:
            print(f"[RPVE] Recovered {recovered} stale job(s) from previous run.")
        job_worker.start_workers()
        print("[INIT] RPVE background worker pool started successfully.")
    except Exception as e:
        print(f"[WARN] Failed to start RPVE worker threads: {e}")

    # ── Universal Trash Cleanup Service ──
    print("[INIT] Starting Universal Trash background service...")
    cleanup_task = None
    try:
        import universal_trash
        start_func = getattr(universal_trash, "start_cleanup_service", None) or getattr(universal_trash, "start_scheduled_cleanup", None)
        if start_func:
            cleanup_task = start_func()
            print("[INIT] Universal Trash cleanup service started successfully.")
        else:
            print("[WARN] No start cleanup service function found in universal_trash.")
    except Exception as e:
        print(f"[WARN] Failed to start Universal Trash cleanup service: {e}")

    yield

    # Cancel cleanup task on shutdown if it exists
    if cleanup_task and hasattr(cleanup_task, "cancel"):
        try:
            cleanup_task.cancel()
        except Exception:
            pass


# Thin FastAPI wrapper — only owns the lifespan and the CORS outer middleware.
# ALL actual request handling is delegated to _dispatcher via app.mount.
app = FastAPI(title="Unified Sales Team Workspace API", lifespan=unified_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Security Gateway Middleware - Protects ALL file uploads across ALL sub-apps & POCs
try:
    from security import SecurityGatewayMiddleware
    app.add_middleware(SecurityGatewayMiddleware)
    print("[INFO] Global Security Gateway Middleware initialized across all POCs.")
except Exception as _mw_err:
    print(f"[WARN] Failed to initialize Security Gateway Middleware: {_mw_err}")


# /api/universal-logs lives here so it is never shadowed by any sub-app
@app.get("/api/universal-logs", tags=["Universal Logs"])
async def get_universal_logs(limit: int = 100):
    try:
        logs = _poc_db.get_universal_logs(limit=limit)
        return {"status": "ok", "logs": logs}
    except Exception as e:
        return {"status": "error", "error": str(e), "logs": []}

@app.get("/api/dashboard-stats", tags=["Dashboard Stats"])
async def get_dashboard_stats_endpoint():
    try:
        stats = _poc_db.get_dashboard_stats()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        return {"status": "error", "error": str(e), "stats": {}}

@app.get("/health", tags=["System"])
async def health_check():
    """Basic liveness probe — used by the frontend and monitoring tools."""
    return {"status": "ok"}

@app.get("/config", tags=["System"])
async def get_config():
    """Returns basic server config metadata expected by the frontend."""
    return {"status": "ok", "version": "1.0", "environment": "production"}

@app.get("/api/automation/status", tags=["Automation"])
async def automation_status(user_email: str = None):
    """
    Automation heartbeat endpoint polled by the frontend after login.
    Returns idle status when no automation jobs are active.
    """
    return {"status": "idle", "user_email": user_email, "active_jobs": 0}

@app.get("/api/gpu/api/drive/status", tags=["GPU Drive"])
@app.get("/api/gpu/drive/status", tags=["GPU Drive"])
async def gpu_drive_status_proxy(request: Request, input_folder: str = None):
    """Bridge frontend GPU drive status request to classifier drive_status."""
    try:
        classifier_mod = sys.modules.get("classifier_api")
        if classifier_mod and hasattr(classifier_mod, "drive_status"):
            return classifier_mod.drive_status(input_folder=input_folder)
        from file_classifier.api import drive_status
        return drive_status(input_folder=input_folder)
    except Exception as e:
        return {"connected": True, "input_folder": input_folder or "", "pdf_count": 0, "pdf_files": []}

@app.post("/api/gpu/api/drive/classify", tags=["GPU Drive"])
@app.post("/api/gpu/drive/classify", tags=["GPU Drive"])
async def gpu_drive_classify_proxy(request: Request):
    """Bridge frontend GPU drive classify request to classifier drive_classify."""
    try:
        classifier_mod = sys.modules.get("classifier_api")
        if classifier_mod and hasattr(classifier_mod, "drive_classify") and hasattr(classifier_mod, "DriveClassifyRequest"):
            body = await request.json()
            req_obj = classifier_mod.DriveClassifyRequest(**body)
            return classifier_mod.drive_classify(req_obj)
        from file_classifier.api import drive_classify, DriveClassifyRequest
        body = await request.json()
        req_obj = DriveClassifyRequest(**body)
        return drive_classify(req_obj)
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/token-usage", tags=["Token Usage"])
async def get_token_usage(
    poc_name: str = None,
    file_name: str = None,
    recent: int = None
):
    """
    Universal Token Usage endpoint.
    - No params           → grand totals + per-POC breakdown + file_summaries (1 row per file)
    - ?recent=50          → 50 most recent individual LLM call records
    """
    try:
        from core.universal_token_monitor import get_summary, get_recent_calls, get_file_summaries
        if recent is not None:
            data = get_recent_calls(limit=recent, poc_name=poc_name)
            file_sums = get_file_summaries(limit=recent, poc_name=poc_name)
            return {"status": "ok", "recent_calls": data, "file_summaries": file_sums}
        data = get_summary(poc_name=poc_name, file_name=file_name)
        file_sums = get_file_summaries(limit=100, poc_name=poc_name)
        return {"status": "ok", "data": data, "file_summaries": file_sums}
    except Exception as e:
        return {"status": "error", "error": str(e), "data": {}}

# Include Auth & Admin User Management Routes
try:
    from auth_routes import router as auth_router
    app.include_router(auth_router)
    print("[INFO] Auth & Admin Access Management router included successfully.")
except Exception as _auth_err:
    print(f"[WARN] Failed to include auth router: {_auth_err}")

# Include SharePoint Automation Routes
try:
    from sharepoint_routes import router as sharepoint_router
    app.include_router(sharepoint_router)
    print("[INFO] SharePoint Automation router included successfully.")
except Exception as _sp_err:
    print(f"[WARN] Failed to include sharepoint router: {_sp_err}")

# Include Workflow Routes (Co-Pilot)
try:
    from workflow_routes import router as workflow_router
    app.include_router(workflow_router)
    print("[INFO] Workflow router included successfully.")
except Exception as _wf_err:
    print(f"[WARN] Failed to include workflow router: {_wf_err}")

# Include Security Gateway Routes
try:
    from security import security_router
    app.include_router(security_router)
    print("[INFO] Security Gateway router included successfully.")
except Exception as _sec_err:
    print(f"[WARN] Failed to include security router: {_sec_err}")




# Mount the full dispatcher at root — every other request goes through it.
# We use Starlette's Mount directly so we control path stripping ourselves.
from starlette.routing import Mount
app.router.routes.append(
    Mount("", app=_dispatcher)
)

print("[INFO] Unified Sales Team Workspace API Server initialized successfully.")

if __name__ == "__main__":
    import uvicorn
    import logging
    import os
    
    # Check if running under IIS HttpPlatformHandler
    iis_port = os.getenv("HTTP_PLATFORM_PORT") or os.getenv("PORT")
    port = int(iis_port) if iis_port else 8000
    host = "127.0.0.1" if iis_port else "0.0.0.0"
    is_reload = False if iis_port else True

    # Silence the chatty watchfiles logger
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
    
    print(f"[INFO] Launching API server on {host}:{port} (IIS HttpPlatformHandler: {bool(iis_port)})")
    
    # Run uvicorn with reload exclusions so it ignores DB/log file changes
    uvicorn.run(
        "app:app", 
        host=host, 
        port=port, 
        reload=is_reload,
        reload_excludes=["*.log", "*.db", "*.sqlite", "*.sqlite3", "database/*", "logs/*", "temp_uploads/*"]
    )

