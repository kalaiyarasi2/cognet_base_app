import sys
import os

# Force unbuffered stdout/stderr so logs appear immediately in real-time
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass

# IMPORTANT (Windows): torch must be imported BEFORE paddle/paddleocr, otherwise
# torch fails with "Error loading torch\lib\shm.dll" due to DLL load-order clashes.
try:
    import torch  # noqa: F401
except Exception:
    pass

import importlib.util
import traceback
from pathlib import Path
from typing import List, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.middleware.cors import CORSMiddleware

WORKSPACE_DIR = Path(__file__).parent.resolve()

# Ensure CWD is always WORKSPACE_DIR so relative paths resolve correctly
os.chdir(WORKSPACE_DIR)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Add workspace root to sys.path
# ─────────────────────────────────────────────────────────────────────────────
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# ─────────────────────────────────────────────────────────────────────────────
# 1b. Environment & Global OCR Configuration & Logger Deduplication
# ─────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
from core.env_loader import load_workspace_env
load_workspace_env()
try:
    from core.prompt_cache_manager import enable_global_prompt_caching, get_cache_stats
    enable_global_prompt_caching()
except Exception:
    pass
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
# Propagate prompt caching to every child subprocess (Payroll, Renewal, RPVE, Invoice-to-Excel)
# via core/_subprocess_boot/sitecustomize.py, auto-imported by Python through PYTHONPATH.
_PCB_DIR = str(WORKSPACE_DIR.parent / "subprocess_boot")
if _PCB_DIR not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (_PCB_DIR, os.environ.get("PYTHONPATH", "")) if p)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

# Deduplicate handlers on root logger so logs don't repeat 3 times
class DeduplicatedStreamHandler(logging.StreamHandler):
    pass

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
try:
    with open(WORKSPACE_DIR / "import_errors.log", "w", encoding="utf-8") as _f:
        _f.write("=== Import Diagnostics Startup ===\n\n")
except Exception:
    pass

def load_sub_app(module_name: str, file_path: Path) -> FastAPI:
    log_file = WORKSPACE_DIR / "import_errors.log"
    if not file_path.exists():
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[WARN] File path does not exist: {file_path}\n")
        except Exception:
            pass
        return FastAPI()

    if module_name in sys.modules:
        del sys.modules[module_name]
    keys_to_del = [k for k in sys.modules if k == "src" or k.startswith("src.")]
    for k in keys_to_del:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[WARN] Could not create module spec for: {file_path}\n")
        except Exception:
            pass
        return FastAPI()

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    parent_dir = str(file_path.parent.resolve())
    sys.path.insert(0, parent_dir)

    # Snapshot & temporarily pop 'common' modules so sub-app local modules with the same name can resolve
    _SHARED_NAMES = {"database", "database.db", "config", "models", "utils", "main"}
    _saved_shared = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if k in _SHARED_NAMES or any(k.startswith(s + ".") for s in _SHARED_NAMES)}

    try:
        spec.loader.exec_module(module)
    except Exception:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[ERROR] Failed to load module {module_name} from {file_path}:\n")
                traceback.print_exc(file=f)
                f.write("\n" + "=" * 80 + "\n\n")
        except Exception:
            pass
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

        # Restore original shared modules
        sys.modules.update(_saved_shared)

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
invoice_excel_app = load_sub_app("invoice_excel_api", WORKSPACE_DIR / "Invoice-to-excel-2026" / "app_fastapi.py")
summary_app    = load_sub_app("summary_api",    WORKSPACE_DIR / "summary & chatbot" / "app.py")
notice_extraction_app = load_sub_app("notice_extraction_api", WORKSPACE_DIR / "Notice-extraction" / "api.py")
modifier_app   = load_sub_app("modifier_api",   WORKSPACE_DIR / "Modifier_Poc" / "app.py")
benefits_uw_app = load_sub_app("benefits_uw_api", WORKSPACE_DIR / "agent-census-creation" / "backend" / "api.py")
file_identifier_app = load_sub_app("file_identifier_api", WORKSPACE_DIR.parent / "File_identifier" / "app.py")

# Patch renewal_api to guarantee subprocesses execute using sys.executable & log to converter.db
try:
    renewal_mod = sys.modules.get("renewal_api")
    if renewal_mod and hasattr(renewal_mod, "run_pipeline_sync"):
        _orig_run_pipeline = renewal_mod.run_pipeline_sync
        def _fixed_run_pipeline_sync(job_id, command, out_census_path, log_path):
            if isinstance(command, list) and len(command) > 0:
                command[0] = sys.executable

            # Log STARTED to converter.db (Universal POC DB Logs)
            try:
                from database.poc_db import log_universal
                jobs_dict = getattr(renewal_mod, "jobs", {})
                job_info = jobs_dict.get(job_id, {})
                c_name = job_info.get("census_name", "census.xlsx")
                inv_name = job_info.get("invoice_name", "invoice.pdf")
                log_universal(
                    module="Renewal Process",
                    action="extract",
                    file_name=f"{c_name} & {inv_name}",
                    status="STARTED",
                    details="Starting renewal census & invoice audit",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            res = _orig_run_pipeline(job_id, command, out_census_path, log_path)

            # Log SUCCESS/FAILED to converter.db
            try:
                from database.poc_db import log_universal
                jobs_dict = getattr(renewal_mod, "jobs", {})
                job_info = jobs_dict.get(job_id, {})
                c_name = job_info.get("census_name", "census.xlsx")
                inv_name = job_info.get("invoice_name", "invoice.pdf")
                st = job_info.get("status", "unknown")
                if st == "success":
                    log_universal(
                        module="Renewal Process",
                        action="extract",
                        file_name=f"{c_name} & {inv_name}",
                        status="SUCCESS",
                        details=f"Census updated successfully: {out_census_path.name}",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                else:
                    err = job_info.get("error", "Process exited with error")
                    log_universal(
                        module="Renewal Process",
                        action="extract",
                        file_name=f"{c_name} & {inv_name}",
                        status="FAILED",
                        details=str(err),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
            except Exception:
                pass

            return res

        renewal_mod.run_pipeline_sync = _fixed_run_pipeline_sync
        print("[INIT] Patched renewal_api to use sys.executable and log to converter.db")
except Exception as _r_err:
    print(f"[WARN] Failed to patch renewal_api: {_r_err}")

# Patch rpve_api and job_worker to unify token logging & write to converter.db
try:
    rpve_mod = sys.modules.get("rpve_api")
    if rpve_mod and hasattr(rpve_mod, "process_invoice_data"):
        _orig_rpve_process = rpve_mod.process_invoice_data
        async def _fixed_rpve_process(file_path, original_filename, out_dir=None):
            import os
            os.environ["COGNET_ACTIVE_FILE_NAME"] = str(original_filename)
            try:
                from core.universal_token_monitor import set_context
                set_context(poc_name="RPVE", file_name=str(original_filename))
            except Exception:
                pass
            try:
                from database.poc_db import log_universal
                log_universal(
                    module="RPVE Extractor",
                    action="extract",
                    file_name=str(original_filename),
                    status="STARTED",
                    details="Starting RPVE invoice extraction",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            try:
                result = await _orig_rpve_process(file_path, original_filename, out_dir=out_dir)
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="SUCCESS",
                        details="RPVE benefit invoice extracted successfully",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=str(original_filename),
                        status="FAILED",
                        details=str(e),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                raise e

        rpve_mod.process_invoice_data = _fixed_rpve_process

    # Also patch job_worker._execute_job for async flow pipelines (PartnerMailFlow / /api/process-flow)
    rpve_dir = WORKSPACE_DIR / "rpve"
    if str(rpve_dir) not in sys.path:
        sys.path.insert(0, str(rpve_dir))
    import job_worker
    if hasattr(job_worker, "_execute_job"):
        _orig_execute_job = job_worker._execute_job
        def _monitored_execute_job(job_id: str):
            fname = "invoice.pdf"
            try:
                job_dir = job_worker.get_job_dir(job_id)
                input_dir = job_dir / "input"
                pdf_files = list(input_dir.glob("*.pdf"))
                if pdf_files:
                    fname = pdf_files[0].name

                # Unify token logger filename so chunk extractions aren't named 'document'
                import os
                os.environ["COGNET_ACTIVE_FILE_NAME"] = fname
                from core.universal_token_monitor import set_context
                set_context(poc_name="RPVE", file_name=fname)

                # Log START to converter.db (Universal POC DB Logs)
                from database.poc_db import log_universal
                log_universal(
                    module="RPVE Extractor",
                    action="extract",
                    file_name=fname,
                    status="STARTED",
                    details=f"Starting RPVE flow pipeline (job={job_id})",
                    processed_by="kalaiyarasig@cognethro.com"
                )
            except Exception:
                pass

            try:
                res = _orig_execute_job(job_id)
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=fname,
                        status="SUCCESS",
                        details=f"RPVE extraction completed for {fname}",
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                return res
            except Exception as _err:
                try:
                    from database.poc_db import log_universal
                    log_universal(
                        module="RPVE Extractor",
                        action="extract",
                        file_name=fname,
                        status="FAILED",
                        details=str(_err),
                        processed_by="kalaiyarasig@cognethro.com"
                    )
                except Exception:
                    pass
                raise _err

        job_worker._execute_job = _monitored_execute_job
        print("[INIT] Patched rpve_api & job_worker to log to converter.db & unify token names")
except Exception as _rp_err:
    print(f"[WARN] Failed to patch rpve_api / job_worker: {_rp_err}")

# One-time migration: merge split 'document' entries into their real file names
try:
    import sqlite3
    _db_path = WORKSPACE_DIR / "monitor" / "universal_token_usage.db"
    if _db_path.exists():
        _c = sqlite3.connect(str(_db_path), timeout=5.0)
        _c.execute("""
            UPDATE token_calls 
            SET file_name = 'BCBS Invoice April 2026_b3ab9bbc-caf6-4d7e-97a8-fdb539714fe9 1 1.pdf' 
            WHERE file_name = 'document' AND session_id LIKE '%851-1%'
        """)
        _c.commit()
        # Regenerate file summaries
        from core.universal_token_monitor import _rebuild_file_summary
        _rebuild_file_summary()
        _c.close()
except Exception:
    pass

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
        ("/api/summary",    summary_app),
        ("/api/notice-extraction", notice_extraction_app),
        ("/api/modifier",   modifier_app),
        ("/api/benefits-uw", benefits_uw_app),
        ("/api/benefits",   benefits_uw_app),
        ("/api/identify",   file_identifier_app),
        ("/api/file-identifier", file_identifier_app),
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
        admin_emails_env = os.getenv("SUPER_ADMIN_EMAILS", "").strip()
        if admin_emails_env:
            raw_admins = [e.strip() for e in admin_emails_env.split(",") if e.strip()]
            SUPER_ADMINS = [(email, email.split("@")[0].replace(".", " ").title(), "ADMIN") for email in raw_admins]
        else:
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
        import importlib.util as _ilu
        _TRASH_PATH = WORKSPACE_DIR / "universal_trash" / "__init__.py"
        _s = _ilu.spec_from_file_location("universal_trash", str(_TRASH_PATH))
        universal_trash = _ilu.module_from_spec(_s)
        sys.modules["universal_trash"] = universal_trash
        _s.loader.exec_module(universal_trash)
        
        start_func = getattr(universal_trash, "start_cleanup_service", None) or getattr(universal_trash, "start_scheduled_cleanup", None)
        if start_func:
            cleanup_task = start_func()
            print("[INIT] Universal Trash cleanup service started successfully.")
        else:
            print("[WARN] No start cleanup service function found in universal_trash.")
    except Exception as e:
        print(f"[WARN] Failed to start Universal Trash cleanup service: {e}")

    # ── Multi-Tenant Partner Mail Flow Background Worker ──
    print("[INIT] Starting Multi-Tenant Partner Mail Flow background listener...")
    mail_flow_tasks = []
    try:
        import asyncio
        import json
        from partner_mail_flow import PartnerMailFlowOrchestrator
        
        tenants_dir = WORKSPACE_DIR / "config" / "tenants"
        active_tenants = []
        if tenants_dir.exists():
            for t_path in tenants_dir.iterdir():
                if t_path.is_dir() and (t_path / "submission.json").exists():
                    try:
                        with open(t_path / "submission.json", "r", encoding="utf-8") as _f:
                            cfg = json.load(_f)
                            if cfg.get("enabled", True):
                                active_tenants.append(t_path.name)
                    except Exception:
                        active_tenants.append(t_path.name)

        interval = int(os.getenv("PARTNER_MAIL_POLL_INTERVAL", "60"))
        
        if not active_tenants:
            print("[INIT] No active tenant submission configs found in config/tenants/.")
        else:
            for t_code in active_tenants:
                orch = PartnerMailFlowOrchestrator(tenant_folder=t_code)
                t_task = asyncio.create_task(orch.run_listener(poll_interval=interval))
                mail_flow_tasks.append(t_task)
                print(f"[INIT] Started mail ingestion worker for tenant '{t_code}' (interval: {interval}s)")
    except Exception as e:
        print(f"[WARN] Failed to start Partner Mail listener: {e}")

    yield

    # Cancel background tasks on shutdown
    if cleanup_task and hasattr(cleanup_task, "cancel"):
        try:
            cleanup_task.cancel()
        except Exception:
            pass

    for m_task in mail_flow_tasks:
        if hasattr(m_task, "cancel"):
            try:
                m_task.cancel()
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
async def automation_status(request: Request, user_email: str = None):
    """
    Delegate to classifier_app's get_automation_status which returns:
    outlook_connected, gmail_connected, running, active_provider, pid, started_at, user_email.
    """
    try:
        classifier_mod = sys.modules.get("classifier_api")
        if classifier_mod and hasattr(classifier_mod, "get_automation_status"):
            return classifier_mod.get_automation_status(request=request, user_email=user_email)
    except Exception as e:
        pass
    return {"status": "idle", "user_email": user_email, "active_jobs": 0, "outlook_connected": False, "gmail_connected": False, "running": False}

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

from fastapi import File, UploadFile

@app.post("/api/gpu/api/extract", tags=["GPU Extract"])
@app.post("/api/gpu/extract", tags=["GPU Extract"])
async def gpu_extract_proxy(request: Request, file: UploadFile = File(...)):
    """Direct proxy bridge for GPU document extraction."""
    processed_by = request.headers.get("X-Processed-By")
    if not processed_by:
        try:
            form = await request.form()
            processed_by = form.get("processed_by")
        except Exception:
            pass
    processed_by = processed_by or "SYSTEM"

    try:
        try:
            from database.poc_db import log_universal
            log_universal("GPU_EXTRACTION", "extract", file.filename, "STARTED", "Processing document", processed_by)
        except Exception:
            pass

        gpu_parent = str(WORKSPACE_DIR / "Gpu_server")
        gpu_dir = str(WORKSPACE_DIR / "Gpu_server" / "Unified_PDF_Platform")
        if gpu_parent not in sys.path:
            sys.path.insert(0, gpu_parent)
        if gpu_dir not in sys.path:
            sys.path.insert(0, gpu_dir)
        try:
            import importlib.util as _spc_ilu
            _spc_path = WORKSPACE_DIR / "Gpu_server" / "smart_pdf_connector.py"
            if _spc_path.exists():
                _spc_spec = _spc_ilu.spec_from_file_location("smart_pdf_connector", str(_spc_path))
                _spc_mod = _spc_ilu.module_from_spec(_spc_spec)
                sys.modules["smart_pdf_connector"] = _spc_mod
                _spc_spec.loader.exec_module(_spc_mod)
        except Exception:
            pass
        try:
            import importlib
            if "shared_configs" in sys.modules:
                importlib.reload(sys.modules["shared_configs"])
        except Exception:
            pass
        from shared_configs import _perform_extraction
        result = await _perform_extraction(file, request)
        
        if isinstance(result, dict):
            if "error" in result:
                try:
                    from database.poc_db import log_universal
                    log_universal("GPU_EXTRACTION", "extract", file.filename, "FAILED", result["error"], processed_by)
                except Exception:
                    pass
            else:
                try:
                    from database.poc_db import log_universal
                    doc_type = result.get("type", "GPU_EXTRACTION")
                    pages = result.get("pages", 0)
                    log_universal(doc_type, "extract", file.filename, "SUCCESS", f"Extracted {pages} pages", processed_by)
                except Exception:
                    pass
                    
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            from database.poc_db import log_universal
            log_universal("GPU_EXTRACTION", "extract", file.filename if file else "unknown", "FAILED", str(e), processed_by)
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})

@app.get("/api/download/{filepath:path}", tags=["GPU Download"])
async def download_proxy(filepath: str):
    """Bridge proxy for direct GPU download paths."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/gpu/api/download/{filepath}")

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
        from core.prompt_cache_manager import get_cache_stats
        return {"status": "ok", "data": data, "file_summaries": file_sums, "prompt_cache_stats": get_cache_stats()}
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





@app.get("/api/renewal/output/{filename:path}", tags=["Renewal Download"])
@app.get("/output/{filename:path}", tags=["Renewal Download"])
async def download_renewal_output(filename: str):
    import urllib.parse
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    decoded_name = urllib.parse.unquote(filename).strip("/\\")
    out_dir = (WORKSPACE_DIR / "Renewal_process" / "output").resolve()
    file_path = (out_dir / decoded_name).resolve()
    if not str(file_path).startswith(str(out_dir)) or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{decoded_name}' not found")

    media_type = "application/octet-stream"
    if file_path.suffix.lower() == ".xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif file_path.suffix.lower() == ".json":
        media_type = "application/json"
    elif file_path.suffix.lower() == ".txt":
        media_type = "text/plain"

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type
    )

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
        reload_excludes=["*.log", "*.db", "*.sqlite", "*.sqlite3", "database/*", "logs/*", "temp_uploads/*"],
        log_level="info",
        access_log=True,
    )

