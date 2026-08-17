"""
start_flow.py - Workspace Orchestrator Runner (Gmail/Outlook -> Classification -> GPU Extraction -> Structured Drive Storage)

Usage:
    # Run once using Outlook
    python start_flow.py --provider outlook --output C:\\Users\\Intern\\OneDrive\\sorted

    # Run once using Gmail
    python start_flow.py --provider gmail --output C:\\Users\\Intern\\OneDrive\\sorted

    # Run continuously (polls every 60 seconds)
    python start_flow.py --provider outlook --output C:\\Users\\Intern\\OneDrive\\sorted --interval 60
"""

from __future__ import annotations

import os
import sys
import io
import glob
import time
import shutil
import base64
import asyncio
import argparse
import logging
from pathlib import Path
import re
from contextlib import contextmanager
from typing import Any, Dict, List, Set

from dotenv import load_dotenv

# Setup path imports for all modules
WORKSPACE_DIR = Path(__file__).parent.resolve()
OUTLOOK_AGENT_DIR = WORKSPACE_DIR / "Outlook_Agent"
CLASSIFIER_DIR = WORKSPACE_DIR / "file-classification-"
GPU_SERVER_DIR = WORKSPACE_DIR / "Gpu_server"
EMAIL_PIPELINE_DIR = GPU_SERVER_DIR / "Email_pipeline"
UNIFIED_PLATFORM_DIR = GPU_SERVER_DIR / "Unified_PDF_Platform"

# Add directories to sys.path
for path in [OUTLOOK_AGENT_DIR, CLASSIFIER_DIR, GPU_SERVER_DIR, UNIFIED_PLATFORM_DIR, EMAIL_PIPELINE_DIR]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

# Ensure local monitor directory exists to satisfy monitor_db.py FileHandler
os.makedirs(WORKSPACE_DIR / "monitor", exist_ok=True)

# Load environment configurations: prioritize workspace root, then classifier
load_dotenv(WORKSPACE_DIR / ".env")
load_dotenv(CLASSIFIER_DIR / ".env")

tess_path = os.getenv("Tesseract_path")
if tess_path:
    os.environ["PATH"] = str(tess_path) + os.pathsep + os.environ.get("PATH", "")
    try:
        import pytesseract
        exe_name = "tesseract.exe" if os.name == "nt" else "tesseract"
        tess_exe = Path(tess_path) / exe_name
        if tess_exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(tess_exe.resolve())
    except ImportError:
        pass

# ── Monitoring DB (SQLite) ────────────────────────────────────────────────────
import uuid as _uuid
from universal_trash import move_to_trash
try:
    import sys as _sys
    _sys.path.insert(0, str(CLASSIFIER_DIR))
    import monitor_db as mdb
    _mdb_ok = True
except Exception as _mdb_err:
    mdb = None
    _mdb_ok = False
    print(f"[WARN] monitor_db not available: {_mdb_err}")

try:
    import sys as _sys
    _workspace_str = str(WORKSPACE_DIR)
    # Force WORKSPACE_DIR to position 0 so 'database' resolves to our package
    if _workspace_str in _sys.path:
        _sys.path.remove(_workspace_str)
    _sys.path.insert(0, _workspace_str)
    # Fallback path: file-classification- subfolder also has a database/ package
    _classifier_str = str(CLASSIFIER_DIR)
    if _classifier_str not in _sys.path:
        _sys.path.insert(1, _classifier_str)
    from database import poc_db
    _poc_db_ok = True
except Exception as _db_err:
    poc_db = None
    _poc_db_ok = False
    print(f"[WARN] poc_db not available in start_flow: {_db_err}", flush=True)

try:
    from outlook_agent_module import OutlookAgentModule, _mark_read, _load_processed_ids, _save_processed_ids
except ImportError:
    OutlookAgentModule = None
    _mark_read = None
    _load_processed_ids = None
    _save_processed_ids = None

try:
    from file_classifier import extract as classifier_extract, load_categories_from_env, DocumentClassifier
except ImportError:
    classifier_extract = None
    load_categories_from_env = None
    DocumentClassifier = None

# from unified_router import UnifiedRouter
UnifiedRouter = None

# Map MICROSOFT_* credentials to AZURE_* variables for OutlookAgentModule compatibility
for key in ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"]:
    m_key = f"MICROSOFT_{key}"
    a_key = f"AZURE_{key}"
    if os.getenv(m_key) and not os.getenv(a_key):
        os.environ[a_key] = os.getenv(m_key)

# Clean up sys.path to prevent namespace collisions (like config.py/utils.py)
for path in [OUTLOOK_AGENT_DIR, CLASSIFIER_DIR]:
    while str(path) in sys.path:
        sys.path.remove(str(path))

# Monkeypatch OutlookAgentModule.get_access_token to support Client Secret in Device flow
if OutlookAgentModule is not None:
    import msal
    import requests
    from typing import Optional
    
    def patched_get_access_token(self, refresh_token: Optional[str] = None) -> str:
        authority = f"https://login.microsoftonline.com/{self.azure_tenant_id}"
        scopes = [
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.ReadWrite",
            "https://graph.microsoft.com/Files.ReadWrite",
            "https://graph.microsoft.com/User.Read",
        ]
        
        # 1. Simple Cache Check
        simple_cache_name = f"ms_simple_cache_{self.sanitized_user_email}.json" if getattr(self, "sanitized_user_email", None) else "ms_simple_cache.json"
        simple_cache_path = os.path.join(os.path.dirname(self.token_cache_path), simple_cache_name)
        if os.path.exists(simple_cache_path):
            try:
                import json
                with open(simple_cache_path) as fh:
                    cached_data = json.load(fh)
                if cached_data.get("expires_at", 0) > time.time() + 60:
                    logger.info("Token obtained from simple cache.")
                    return cached_data["access_token"]
                
                # If expired but has refresh token, try to refresh
                r_token = cached_data.get("refresh_token")
                if r_token:
                    logger.info("Cached token expired. Attempting refresh...")
                    app = msal.ConfidentialClientApplication(
                        self.azure_client_id,
                        authority=authority,
                        client_credential=self.azure_client_secret,
                    )
                    res = app.acquire_token_by_refresh_token(r_token, scopes=scopes)
                    if "access_token" in res:
                        cached_data["access_token"] = res["access_token"]
                        cached_data["expires_at"] = time.time() + res.get("expires_in", 3600)
                        if res.get("refresh_token"):
                            cached_data["refresh_token"] = res["refresh_token"]
                        with open(simple_cache_path, "w") as fh:
                            json.dump(cached_data, fh)
                        logger.info("Token successfully refreshed and cached.")
                        return res["access_token"]
            except Exception as e:
                logger.warning("Failed to read/refresh from simple cache: %s", e)

        # 1b. Check Active Dashboard Sessions (OneDrive OAuth Cache Sync)
        sessions_dir = WORKSPACE_DIR / ".sessions"

        if sessions_dir.exists():
            import glob
            session_files = []
            if getattr(self, "sanitized_user_email", None):
                user_session = sessions_dir / f"onedrive_{self.sanitized_user_email}.json"
                if user_session.exists():
                    session_files.append(str(user_session))
            if not session_files:
                session_files = glob.glob(str(sessions_dir / "onedrive_*.json"))
                session_files.sort(key=os.path.getmtime, reverse=True)
            for s_file in session_files:
                try:
                    import json
                    with open(s_file) as fh:
                        data = json.load(fh)
                    r_token = data.get("refresh_token")
                    if r_token:
                        logger.info("Found active Microsoft dashboard session: %s", Path(s_file).name)
                        app = msal.ConfidentialClientApplication(
                            self.azure_client_id,
                            authority=authority,
                            client_credential=self.azure_client_secret,
                        )
                        res = app.acquire_token_by_refresh_token(r_token, scopes=scopes)
                        if "access_token" in res:
                            # Update local cache
                            os.makedirs(os.path.dirname(simple_cache_path), exist_ok=True)
                            with open(simple_cache_path, "w") as fh:
                                json.dump({
                                    "access_token": res["access_token"],
                                    "refresh_token": res.get("refresh_token", r_token),
                                    "expires_at": time.time() + res.get("expires_in", 3600),
                                }, fh)
                            logger.info("Token synchronized successfully from dashboard session.")
                            return res["access_token"]
                except Exception as ex:
                    logger.warning("Failed to sync session from %s: %s", Path(s_file).name, ex)

        # 2. Refresh-token path (explicit refresh_token parameter)
        if refresh_token:
            app = msal.ConfidentialClientApplication(
                self.azure_client_id,
                authority=authority,
                client_credential=self.azure_client_secret,
            )
            result = app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)
            if "access_token" in result:
                return result["access_token"]
            raise RuntimeError(f"Token refresh failed: {result.get('error_description')}")

        # 3. Manual Device Code Flow with client secret support
        logger.info("No cached token; initiating device-code flow with client secret...")
        
        device_code_url = f"https://login.microsoftonline.com/{self.azure_tenant_id}/oauth2/v2.0/devicecode"
        token_url = f"https://login.microsoftonline.com/{self.azure_tenant_id}/oauth2/v2.0/token"
        
        resp = requests.post(
            device_code_url,
            data={
                "client_id": self.azure_client_id,
                "client_secret": self.azure_client_secret,
                "scope": " ".join(scopes)
            }
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to initiate device code flow: {resp.text}")
            
        flow_info = resp.json()
        message = flow_info.get("message", f"To sign in, use a web browser to open the page {flow_info.get('verification_uri')} and enter the code {flow_info.get('user_code')} to authenticate.")
        print(f"\n{message}\n", flush=True)
        
        interval = flow_info.get("interval", 5)
        expires_in = flow_info.get("expires_in", 900)
        device_code = flow_info["device_code"]
        
        poll_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": self.azure_client_id,
            "client_secret": self.azure_client_secret
        }
        
        start_time = time.time()
        result = None
        while time.time() - start_time < expires_in:
            time.sleep(interval)
            token_resp = requests.post(token_url, data=poll_data)
            token_json = token_resp.json()
            
            if token_resp.status_code == 200:
                result = token_json
                break
                
            error = token_json.get("error")
            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 2
            else:
                raise RuntimeError(f"MSAL auth failed: {token_json.get('error_description', error)}")
                
        if not result or "access_token" not in result:
            raise RuntimeError("Device authorization flow timed out or failed.")
            
        # Write to simple cache
        try:
            import json
            os.makedirs(os.path.dirname(simple_cache_path), exist_ok=True)
            with open(simple_cache_path, "w") as fh:
                json.dump({
                    "access_token": result["access_token"],
                    "refresh_token": result.get("refresh_token"),
                    "expires_at": time.time() + result.get("expires_in", 3600),
                }, fh)
            logger.info("Access token cached successfully.")
        except Exception as e:
            logger.warning("Failed to save simple cache: %s", e)
            
        return result["access_token"]

    OutlookAgentModule.get_access_token = patched_get_access_token

# Reconfigure stdout/stderr for UTF-8 support
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Setup logger
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("start_flow_orchestrator")


@contextmanager
def change_working_dir(new_dir: Path):
    """Context manager to temporarily change working directory."""
    old_dir = os.getcwd()
    os.chdir(str(new_dir))
    try:
        yield
    finally:
        os.chdir(old_dir)


def get_outlook_agent(user_email: str | None = None) -> OutlookAgentModule | None:
    try:
        # OUTLOOK_AGENT_DIR was removed from sys.path earlier to prevent namespace
        # collisions. Re-insert it locally so the import succeeds at runtime.
        _agent_dir = str(OUTLOOK_AGENT_DIR)
        if _agent_dir not in sys.path:
            sys.path.insert(0, _agent_dir)
        from outlook_agent_module import OutlookAgentModule as _OAM
        return _OAM(user_email=user_email)
    except Exception as exc:
        logger.error("[INIT] Failed to initialize OutlookAgentModule: %s", exc)
        return None


def fetch_outlook_attachments(dest_folder: Path, mark_read: bool = True, user_email: str | None = None) -> tuple[list[Path], str]:
    """Fetches unread Outlook attachments and saves them locally."""
    agent = get_outlook_agent(user_email=user_email)
    if not agent:
        return [], ""

    dest_folder.mkdir(parents=True, exist_ok=True)
    downloaded_files = []
    token = ""

    try:
        token = agent.get_access_token()
        from outlook_agent_module import _mark_read, _load_processed_ids, _save_processed_ids

        processed_ids_file = agent.processed_ids_file
        processed_ids = _load_processed_ids(processed_ids_file) if _load_processed_ids else set()

        emails = agent.fetch_unread_emails()
        if not emails:
            logger.info("[OUTLOOK] No unread emails found.")
            return [], token
        # DB: record email count (caller logs individual attachments)

        for email in emails:
            if not isinstance(email, dict):
                logger.warning("[OUTLOOK] Skipping non-dict email item: %r", email)
                continue
            email_id = email.get("id")
            if not email_id:
                continue
            attachments = email.get("attachments", [])
            if not isinstance(attachments, list):
                attachments = []
            sender_val = email.get("sender") or email.get("from") or ""
            if isinstance(sender_val, dict):
                email_addr = sender_val.get("emailAddress")
                if isinstance(email_addr, dict):
                    sender_info = email_addr.get("address", "")
                elif isinstance(email_addr, str):
                    sender_info = email_addr
                else:
                    sender_info = str(sender_val.get("address", ""))
            elif isinstance(sender_val, str):
                sender_info = sender_val
            else:
                sender_info = ""
            subject = str(email.get("subject", ""))
            
            if not attachments:
                if mark_read and _mark_read:
                    _mark_read(token, email_id)
                processed_ids.add(email_id)
                continue

            for att in attachments:
                filename = att["filename"]
                if not filename.lower().endswith(".pdf"):
                    continue

                content_bytes = base64.b64decode(att["content_bytes"])
                dest_file = dest_folder / filename
                dest_file.write_bytes(content_bytes)
                logger.info("[OUTLOOK] Downloaded attachment: %s", filename)
                downloaded_files.append(dest_file)

                # Log attachment download to converter.db (universal_history)
                if _poc_db_ok:
                    try:
                        _size_kb = round(dest_file.stat().st_size / 1024, 1) if dest_file.exists() else 0
                        poc_db.log_universal(
                            module="OUTLOOK",
                            action="Email Attachment Downloaded",
                            file_name=filename,
                            status="SUCCESS",
                            details=f"From: {sender_info or 'N/A'} | Subject: {subject or 'N/A'} | Size: {_size_kb} KB | Path: {dest_file}"
                        )
                    except Exception as db_err:
                        logger.warning("Failed to log Outlook attachment download to converter.db: %s", db_err)

            if mark_read and _mark_read:
                _mark_read(token, email_id)
            processed_ids.add(email_id)

        if _save_processed_ids:
            _save_processed_ids(processed_ids, processed_ids_file)

        return downloaded_files, token
    except Exception as e:
        logger.error("[OUTLOOK] [ERR] Outlook sync failed: %s", e)
        return [], token


def fetch_gmail_attachments(dest_folder: Path, mark_read: bool = True) -> list[Path]:
    """Fetches unread Gmail attachments by calling Gpu_server agent_phase."""
    logger.info("[GMAIL] Triggering Gmail ingestion phase...")
    downloaded_files = []

    try:
        # Run inside Gpu_server/Email_pipeline working directory so credentials.json is resolved
        with change_working_dir(EMAIL_PIPELINE_DIR):
            from main import agent_phase
            new_pdf_paths = agent_phase(mark_read=mark_read)

            # Move files from Email_pipeline/downloads to our dest_folder
            for path_str in new_pdf_paths:
                src_path = Path(path_str)
                if src_path.exists():
                    dest_path = dest_folder / src_path.name
                    shutil.move(str(src_path), str(dest_path))
                    logger.info("[GMAIL] Ingested attachment: %s", dest_path.name)
                    downloaded_files.append(dest_path)

                    # Log attachment download to converter.db (universal_history)
                    if _poc_db_ok:
                        try:
                            _size_kb = round(dest_path.stat().st_size / 1024, 1) if dest_path.exists() else 0
                            poc_db.log_universal(
                                module="GMAIL",
                                action="Email Attachment Downloaded",
                                file_name=dest_path.name,
                                status="SUCCESS",
                                details=f"Ingested from Gmail unread attachment | Size: {_size_kb} KB | Path: {dest_path}"
                            )
                        except Exception as db_err:
                            logger.warning("Failed to log Gmail attachment download to converter.db: %s", db_err)
                    
        return downloaded_files
    except Exception as e:
        logger.error("[GMAIL] [ERR] Gmail sync failed: %s", e)
        return []


async def run_local_extraction(category: str, pdf_path: Path, text: str = "") -> dict:
    """Routes the PDF to the correct backend module based on category and text."""
    category_upper = category.upper()
    text_upper = text.upper() if text else ""
    filename_stem = pdf_path.stem
    
    # 1. Parity_setup (SBC)
    if "PARITY" in category_upper or "SBC" in category_upper or "SUMMARY OF BENEFITS" in text_upper or "SBC" in text_upper:
        logger.info("[ROUTING] Routing to Parity_setup (SBC Extractor) for file: %s", pdf_path.name)
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).parent.resolve()
            parity_root = workspace_root / "Parity_setup"
            parity_backend = parity_root / "backend"
            
            if str(parity_root) not in sys.path:
                sys.path.insert(0, str(parity_root))
            if str(parity_backend) not in sys.path:
                sys.path.insert(0, str(parity_backend))
                
            from src.extractors.universal_extractor import UniversalExtractor
            from src.validation.rules_engine import RulesEngine
            from src.output.excel_writer import ExcelWriter
            
            out_dir = parity_backend / "data" / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            
            extractor = UniversalExtractor()
            import uuid
            task_id = str(uuid.uuid4())
            raw_text_path = out_dir / f"{task_id}.txt"
            
            schema_model = extractor.extract_text(str(pdf_path), save_raw_path=str(raw_text_path), filename=pdf_path.name)
            schema_dict = schema_model.model_dump()
            
            rules_engine = RulesEngine()
            validation_results = rules_engine.validate(schema_dict)
            
            excel_writer = ExcelWriter()
            excel_path = out_dir / f"{filename_stem}_extracted.xlsx"
            excel_writer.write(schema_dict, validation_results, str(excel_path))
            
            json_path = out_dir / f"{filename_stem}_extracted.json"
            import json
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(schema_dict, f, indent=4)
                
            return {
                "excel": str(excel_path),
                "json": str(json_path),
            }
        except Exception as e:
            logger.error("Parity_setup extraction failed: %s", e, exc_info=True)
            return {"error": f"Parity_setup extraction failed: {str(e)}"}
            
    # 2. Renewal_process
    elif "RENEWAL" in category_upper or "RENEWAL" in text_upper:
        logger.info("[ROUTING] Routing to Renewal_process for file: %s", pdf_path.name)
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).parent.resolve()
            renewal_root = workspace_root / "Renewal_process"
            
            if str(renewal_root) not in sys.path:
                sys.path.insert(0, str(renewal_root))
                
            import invoice_census_audit
            poppler_path = invoice_census_audit.find_poppler_path()
            
            rates, raw_text = invoice_census_audit.extract_rates_with_llm(pdf_path, poppler_path=poppler_path)
            
            rates_json = {}
            for rate in rates:
                if rate.current_monthly == 0 and rate.renewal_monthly == 0:
                    continue
                if rate.plan_name not in rates_json:
                    rates_json[rate.plan_name] = {}
                rates_json[rate.plan_name][rate.tier] = {
                    "current": rate.current_monthly,
                    "renewal": rate.renewal_monthly
                }
                
            out_json = renewal_root / "output" / f"extracted_rates_{filename_stem}.json"
            out_json.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(rates_json, f, indent=4)
                
            return {
                "json": str(out_json),
            }
        except Exception as e:
            logger.error("Renewal_process extraction failed: %s", e, exc_info=True)
            return {"error": f"Renewal_process extraction failed: {str(e)}"}
            
    # 3. Gpu_server / UnifiedRouter (Insurance Claims, Loss Runs, ACORD, Work Comp, General Invoices)
    #    General insurance documents and standard invoices go to Gpu_server UnifiedRouter.
    elif (
        "INSURANCE_CLAIMS" in category_upper 
        or "LOSS" in category_upper
        or "LOSS_RUN" in category_upper 
        or "LOSS RUN" in category_upper
        or "LOSS" in text_upper
        or "CLAIM" in category_upper
        or "WORK_COMPENSATION" in category_upper
        or "WORK_COMP" in category_upper
        or ("INVOICE" in category_upper and not ("RPVE" in category_upper or "RPVE" in text_upper or "BENEFIT INVOICE" in text_upper or "RAPT" in text_upper or "CENSUS" in text_upper))
    ):
        logger.info("[ROUTING] Routing to Gpu_server / UnifiedRouter (Insurance Claims / Loss Runs / General Invoices) for file: %s", pdf_path.name)
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).parent.resolve()
            unified_platform_dir = workspace_root / "Gpu_server" / "Unified_PDF_Platform"

            if str(unified_platform_dir) not in sys.path:
                sys.path.insert(0, str(unified_platform_dir))
            gpu_server_dir = workspace_root / "Gpu_server"
            if str(gpu_server_dir) not in sys.path:
                sys.path.insert(1, str(gpu_server_dir))

            from unified_router import UnifiedRouter as _UnifiedRouter
            router = _UnifiedRouter()

            # Monkeypatch classify so it reuses the already-known category
            async def _fast_classify(file_path, request_id=None):
                logger.info("[ROUTING] Reusing category '%s' for Gpu_server UnifiedRouter.", category)
                return category, "gpu_server"
            router.classify_document = _fast_classify

            result = await router.process(str(pdf_path))
            return result
        except Exception as e:
            logger.error("Gpu_server (Insurance / Invoice) extraction failed: %s", e, exc_info=True)
            return {"error": f"Gpu_server extraction failed: {str(e)}"}

    # 4. Resourcing-edge  (Plan Rate Comparison ONLY — current vs proposed structure)
    elif ("RESOURCING" in category_upper or "PLAN_COMPARISON" in category_upper) and not ("LOSS" in category_upper or "LOSS" in text_upper or "CLAIM" in category_upper):
        logger.info("[ROUTING] Routing to Resourcing-edge (Plan Rate Comparison) for file: %s", pdf_path.name)
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).parent.resolve()
            resourcing_root = workspace_root / "Resourcing-edge"
            
            if str(resourcing_root) not in sys.path:
                sys.path.insert(0, str(resourcing_root))
                
            from main import process_pdf
            out_folder = process_pdf(pdf_path)
            
            excel_path = out_folder / f"{filename_stem}.xlsx"
            json_path = out_folder / f"{filename_stem}.json"
            
            return {
                "excel": str(excel_path) if excel_path.exists() else None,
                "json": str(json_path) if json_path.exists() else None,
            }
        except Exception as e:
            logger.error("Resourcing-edge extraction failed: %s", e, exc_info=True)
            return {"error": f"Resourcing-edge extraction failed: {str(e)}"}
            
    # 5. rpve (Benefit Invoice / RPVE Specific Ingestion)
    elif "RPVE" in category_upper or "RPVE" in text_upper or "BENEFIT INVOICE" in text_upper or "BENEFIT_INVOICE" in category_upper or "RAPT" in text_upper or "CENSUS" in text_upper:
        logger.info("[ROUTING] Routing to rpve (Benefit Invoice & RAPT Census Extractor) for file: %s", pdf_path.name)
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).parent.resolve()
            rpve_root = workspace_root / "rpve"
            
            if str(rpve_root) not in sys.path:
                sys.path.insert(0, str(rpve_root))
                
            import RPVE_standalone
            
            out_dir = rpve_root / "rpve_outputs"
            out_dir.mkdir(parents=True, exist_ok=True)
            
            extract_result = await RPVE_standalone.process_invoice_data(pdf_path, pdf_path.name, out_dir=out_dir)
            
            return {
                "excel": extract_result.get("excel_path"),
                "json": extract_result.get("json_path"),
            }
        except Exception as e:
            logger.error("rpve extraction failed: %s", e, exc_info=True)
            return {"error": f"rpve extraction failed: {str(e)}"}
            
    else:
        logger.info("[ROUTING] Category '%s' is not mapped to any specific local POC extractor. Falling back to UnifiedRouter.", category)
        try:
            from unified_router import UnifiedRouter
            router = UnifiedRouter()
            
            # Dynamically monkeypatch the router to reuse classification and text snippet
            async def fast_classify(file_path, request_id=None):
                provider = await router._identify_provider(Path(file_path).name, text[:2000], request_id=request_id)
                logger.info("[ROUTING] Bypassed router classification. Reusing category: %s | Provider: %s", category, provider)
                return category, provider
            router.classify_document = fast_classify
            
            # Run the async process method of Gpu_server's UnifiedRouter
            result = await router.process(str(pdf_path))
            return result
        except Exception as e:
            logger.error("[ROUTING] UnifiedRouter fallback failed: %s", e, exc_info=True)
            return {"error": f"UnifiedRouter fallback failed: {str(e)}"}

def upload_to_onedrive_cloud(token: str, category: str, filename: str, file_path: Path, user_email: str = None, bundle: str = None):
    import requests
    import os
    import re
    
    sanitized_cat = category.strip().upper().replace(" ", "_").replace("-", "_")
    cloud_path = "sorted"
    if user_email:
        sanitized_user = re.sub(r'[^a-zA-Z0-9]', '_', user_email.lower())
        cloud_path += f"/{sanitized_user}"
    cloud_path += f"/{sanitized_cat}"
    if bundle:
        cloud_path += f"/{bundle}"
        
    logger.info("Uploading %s directly to OneDrive Cloud (Path: %s)", filename, cloud_path)
    
    upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{cloud_path}/{filename}:/content"
    
    with open(file_path, 'rb') as f:
        file_data = f.read()
        
    content_type = "application/pdf"
    if filename.endswith(".json"):
        content_type = "application/json"
    elif filename.endswith(".xlsx"):
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type
    }
    
    try:
        resp = requests.put(upload_url, headers=headers, data=file_data)
        resp.raise_for_status()
        logger.info("[CLOUD STORE] Successfully uploaded %s to cloud OneDrive.", filename)
    except Exception as e:
        logger.error("[CLOUD STORE] Failed to upload %s to OneDrive: %s", filename, e)

def execute_flow(
    provider: str,
    temp_inbox: Path,
    output_root: Path,
    pdf_max_pages: int = 3,
    min_score: float = 3.0,
    llm_model: str = "gpt-4o",
    mark_read: bool = True,
    run_id: str = None,
    user_email: str = None,
) -> int:
    """Executes the complete multi-repo pipeline for a single cycle."""
    # ── DB: start run ─────────────────────────────────────────────────────────
    if run_id is None:
        run_id = str(_uuid.uuid4())
    if _mdb_ok:
        try:
            mdb.run_start(run_id, provider)
            mdb.heartbeat("classifier", "online")
        except Exception:
            pass
    logger.info("=" * 70)
    logger.info("STAGE 1: Ingesting files from %s (User: %s)", provider.upper(), user_email or "SYSTEM")
    logger.info("=" * 70)

    # Ingest files
    outlook_token = ""
    if provider == "outlook":
        ingested_files, outlook_token = fetch_outlook_attachments(temp_inbox, mark_read=mark_read, user_email=user_email)
    elif provider == "gmail":
        # Temporary remove sys.modules['auth'] if mocked to allow authenticating with Gmail
        auth_mocked = False
        if 'auth' in sys.modules and isinstance(sys.modules['auth'], MagicMock):
            del sys.modules['auth']
            auth_mocked = True
            
        ingested_files = fetch_gmail_attachments(temp_inbox, mark_read=mark_read)
        
        # Restore mock for other operations
        if auth_mocked:
            from unittest.mock import MagicMock
            class MockAuth:
                gmail = MagicMock()
            sys.modules['auth'] = MockAuth
    elif provider == "drive":
        # Ingest PDFs directly from the input staging folder
        temp_inbox_path = Path(temp_inbox)
        if temp_inbox_path.exists() and temp_inbox_path.is_dir():
            ingested_files = [Path(p) for p in glob.glob(os.path.join(str(temp_inbox_path), "*.pdf"))]
        else:
            ingested_files = []
    else:
        logger.error("Unsupported provider: %s", provider)
        return 0

    if not ingested_files:
        logger.info("[PIPELINE] No unread PDF attachments to process.")
        if _mdb_ok:
            try:
                mdb.run_update(run_id, emails_found=0, attachments=0)
                mdb.run_finish(run_id, status="completed")
            except Exception:
                pass
        return 0

    logger.info("[PIPELINE] Ingested %d file(s). Starting classification and extraction...", len(ingested_files))
    if _mdb_ok:
        try:
            mdb.run_update(run_id, attachments=len(ingested_files))
        except Exception:
            pass

    # Load classification categories from file-classification- .env
    categories = load_categories_from_env()
    from file_classifier import extract as classifier_extract, DocumentClassifier
    classifier = DocumentClassifier(categories=categories, threshold=min_score, llm_model=llm_model)

    # Local routing extraction (no external router needed)
    pass

    processed_count = 0

    for temp_pdf_path in ingested_files:
        filename = temp_pdf_path.name
        
        # ── STAGE 2: Classify using file-classification- ──────────────────
        logger.info("[CLASSIFY] Extracting text layer for classification: %s", filename)
        _t0_classify = time.time()
        _classify_error = None
        try:
            text, pdf_type, rotation_info = classifier_extract(temp_pdf_path, max_pages=pdf_max_pages)
            category, score = classifier.classify(text)
        except Exception as e:
            logger.error("[CLASSIFY] [ERR] Classification failed: %s. Defaulting to 'Others'.", e)
            category, score = "Others", 0.0
            _classify_error = str(e)
        _classify_ms = int((time.time() - _t0_classify) * 1000)

        logger.info("[CLASSIFY] Category: '%s' (score: %.2f)", category, score)

        # ── STAGE 3: Create structured target directory (Category/Filename_Without_Ext) ───
        filename_stem = Path(filename).stem
        sanitized_cat = category.strip().upper().replace(" ", "_").replace("-", "_")
        dest_dir = output_root / sanitized_cat / filename_stem
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_pdf_path = dest_dir / filename
        shutil.copy2(temp_pdf_path, dest_pdf_path)
        logger.info("[STORE] PDF saved locally to: %s", dest_pdf_path)
        if outlook_token and provider == "outlook":
            upload_to_onedrive_cloud(outlook_token, category, filename, temp_pdf_path, user_email=user_email, bundle=filename_stem)

        # ── DB: log file classification ───────────────────────────────────
        if _mdb_ok:
            try:
                mdb.log_file(
                    run_id=run_id,
                    filename=filename,
                    category=category,
                    pdf_type=pdf_type if '_classify_error' not in dir() else None,
                    score=score,
                    file_size=temp_pdf_path.stat().st_size if temp_pdf_path.exists() else None,
                    processing_ms=_classify_ms,
                    sent_to_gpu=False,   # updated below
                    error=_classify_error,
                )
                mdb.run_update(run_id, files_classified=processed_count + 1)
            except Exception:
                pass

        # ── STAGE 4: Run Gpu_server Unified Extraction ────────────────────
        is_others = category.strip().upper() == "OTHERS"
        if is_others:
            logger.info("[PIPELINE] Document classified as 'OTHERS'. Skipping GPU extraction.")
            extract_result = {"error": "Skipped GPU extraction for category OTHERS"}
            if _mdb_ok:
                try:
                    mdb.run_update(run_id, files_others=1)   # incremented per file
                except Exception:
                    pass
        else:
            _t0_gpu = time.time()
            extract_result = asyncio.run(run_local_extraction(category, dest_pdf_path, text))
            _gpu_ms = int((time.time() - _t0_gpu) * 1000)

            # DB: log GPU job
            if _mdb_ok:
                try:
                    _gpu_err = extract_result.get("error") if isinstance(extract_result, dict) else None
                    _gpu_ok  = _gpu_err is None
                    mdb.log_gpu_job(
                        run_id=run_id,
                        filename=filename,
                        status="completed" if _gpu_ok else "failed",
                        processing_ms=_gpu_ms,
                        output_file=extract_result.get("excel") if _gpu_ok else None,
                        error=_gpu_err,
                    )
                    mdb.run_update(run_id, files_gpu=1)
                except Exception:
                    pass

        # ── STAGE 5: Store outputs under Category folder ──────────────────
        if "error" not in extract_result:
            # Excel
            excel_out = extract_result.get("excel")
            if excel_out and os.path.exists(excel_out):
                excel_dest = dest_dir / f"{filename_stem}_extracted.xlsx"
                shutil.copy2(excel_out, excel_dest)
                logger.info("[STORE] Excel output saved locally to: %s", excel_dest)
                if outlook_token and provider == "outlook":
                    upload_to_onedrive_cloud(outlook_token, category, f"{filename_stem}_extracted.xlsx", Path(excel_out), user_email=user_email, bundle=filename_stem)

            # JSON
            json_out = extract_result.get("json")
            if json_out and os.path.exists(json_out):
                json_dest = dest_dir / f"{filename_stem}_extracted.json"
                shutil.copy2(json_out, json_dest)
                logger.info("[STORE] JSON output saved locally to: %s", json_dest)
                if outlook_token and provider == "outlook":
                    upload_to_onedrive_cloud(outlook_token, category, f"{filename_stem}_extracted.json", Path(json_out), user_email=user_email, bundle=filename_stem)

            # TXT Log
            txt_dest = dest_dir / f"{filename_stem}_text.txt"
            txt_dest.write_text(
                f"Category: {category}\nClassification Score: {score}\nPDF Type: {pdf_type}\nRotation Applied: {rotation_info}\n",
                encoding="utf-8"
            )
            logger.info("[STORE] TXT metadata saved to: %s", txt_dest)

            # Log to universal_history in converter.db
            if _poc_db_ok:
                try:
                    module_name = provider.strip().upper()
                    _out_path = str(dest_dir)
                    _file_size = round(dest_pdf_path.stat().st_size / 1024, 1) if dest_pdf_path.exists() else 0
                    poc_db.log_universal(
                        module=module_name,
                        action="Email Attachment Processing" if provider in ["outlook", "gmail"] else "Drive Folder Ingestion",
                        file_name=filename,
                        status="SUCCESS",
                        details=f"Category: {category} | Score: {score:.2f} | PDF Type: {pdf_type} | Rotation: {rotation_info} | Size: {_file_size} KB | Output: {_out_path}",
                        processed_by=user_email or "SYSTEM"
                    )
                except Exception as db_err:
                    logger.warning("Failed to log success to converter.db: %s", db_err)
        else:
            if is_others:
                txt_dest = dest_dir / f"{filename_stem}_text.txt"
                txt_dest.write_text(
                    f"Category: {category}\nClassification Score: {score}\nPDF Type: {pdf_type}\nRotation Applied: {rotation_info}\nGPU Extraction: Skipped (Category: Others)\n",
                    encoding="utf-8"
                )
                logger.info("[STORE] TXT metadata saved to: %s", txt_dest)

                # Log to universal_history in converter.db for OTHERS
                if _poc_db_ok:
                    try:
                        module_name = provider.strip().upper()
                        _out_path = str(dest_dir)
                        poc_db.log_universal(
                            module=module_name,
                            action="Email Attachment Processing" if provider in ["outlook", "gmail"] else "Drive Folder Ingestion",
                            file_name=filename,
                            status="SKIPPED",
                            details=f"Category: Others | Score: {score:.2f} | PDF Type: {pdf_type} | Rotation: {rotation_info} | GPU Skipped | Output: {_out_path}",
                            processed_by=user_email or "SYSTEM"
                        )
                    except Exception as db_err:
                        logger.warning("Failed to log OTHERS to converter.db: %s", db_err)
            else:
                logger.error("[PIPELINE] Extraction failed for %s: %s", filename, extract_result.get("error"))

                # Log failure to universal_history in converter.db
                if _poc_db_ok:
                    try:
                        module_name = provider.strip().upper()
                        poc_db.log_universal(
                            module=module_name,
                            action="Email Attachment Processing" if provider in ["outlook", "gmail"] else "Drive Folder Ingestion",
                            file_name=filename,
                            status="FAILED",
                            details=f"Category: {category} | Score: {score:.2f} | PDF Type: {pdf_type} | Error: {extract_result.get('error', 'Unknown')}",
                            processed_by=user_email or "SYSTEM"
                        )
                    except Exception as db_err:
                        logger.warning("Failed to log error to converter.db: %s", db_err)

        # Clean up temp PDF
        if temp_pdf_path.exists():
            move_to_trash(temp_pdf_path, module_name="Sales team - Copy")

        processed_count += 1

    logger.info("[PIPELINE] Cycle complete. Successfully processed %d file(s).", processed_count)

    # ── DB: finish run ────────────────────────────────────────────────────────
    if _mdb_ok:
        try:
            mdb.run_finish(run_id, status="completed", files_classified=processed_count)
            mdb.heartbeat("classifier", "online", emails_processed=processed_count)
        except Exception:
            pass

    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified Workspace Pipeline Orchestrator (Gmail/Outlook)")
    parser.add_argument(
        "--provider",
        choices=["outlook", "gmail"],
        required=True,
        help="Email provider to read files from: outlook, gmail",
    )
    parser.add_argument(
        "--input",
        default="./temp_inbox",
        help="Temporary local folder to stage attachments",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Target structured output folder. If not provided, defaults to ONEDRIVE_OUTPUT, GOOGLE_DRIVE_OUTPUT, or './sorted'.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Poll interval in seconds. If unset, script runs once.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Max pages to scan per PDF for classification",
    )
    parser.add_argument(
        "--score",
        type=float,
        default=3.0,
        help="Classification score threshold (0-10)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="LLM model override for classification",
    )
    parser.add_argument(
        "--no-mark-read",
        action="store_true",
        help="Do not mark emails as read after processing",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="User email context for isolated email monitoring and processing",
    )

    args = parser.parse_args()

    user_email = args.user
    sanitized_user = re.sub(r'[^a-zA-Z0-9]', '_', user_email.lower()) if user_email else None

    def resolve_onedrive_base_path():
        import glob
        import json
        import os
        import jwt
        
        sessions_dir = '.sessions'
        email = user_email
        name = None
        # 1. Get email/name from active session
        if os.path.exists(sessions_dir):
            session_files = []
            if sanitized_user:
                u_sess = os.path.join(sessions_dir, f'onedrive_{sanitized_user}.json')
                if os.path.exists(u_sess):
                    session_files.append(u_sess)
            if not session_files:
                session_files = glob.glob(os.path.join(sessions_dir, 'onedrive_*.json'))
                session_files.sort(key=os.path.getmtime, reverse=True)
            if session_files:
                with open(session_files[0], 'r') as f:
                    data = json.load(f)
                    token = data.get('access_token')
                    if token:
                        try:
                            decoded = jwt.decode(token, options={'verify_signature': False})
                            email = decoded.get('upn') or decoded.get('unique_name') or decoded.get('email') or email
                            name = decoded.get('name')
                        except Exception:
                            pass
        
        # 2. Search for the OneDrive folder
        user_profile = os.path.expanduser('~')
        possible_folders = glob.glob(os.path.join(user_profile, '*Cognet HR Solutions*'))
        
        if not possible_folders and os.path.exists('C:\\Users'):
            for user_dir in os.listdir('C:\\Users'):
                user_path = os.path.join('C:\\Users', user_dir)
                if os.path.isdir(user_path):
                    folders = glob.glob(os.path.join(user_path, '*Cognet HR Solutions*'))
                    possible_folders.extend(folders)
                    
        if not possible_folders:
            return os.path.join(user_profile, 'OneDrive - Cognet HR Solutions Pvt Ltd')
            
        if email or name:
            # Try to find a folder that matches the name or email
            search_terms = []
            if name: search_terms.extend(name.lower().split())
            if email: search_terms.append(email.split('@')[0].lower())
            
            for folder in possible_folders:
                folder_name_lower = os.path.basename(folder).lower()
                for term in search_terms:
                    if term and term in folder_name_lower:
                        return folder
                        
        # Default to the first one found if no match
        return possible_folders[0]

    dynamic_onedrive_base = resolve_onedrive_base_path()

    # Resolve input staging path
    if args.input and args.input != "./temp_inbox":
        temp_inbox = Path(args.input).resolve()
    else:
        if args.provider == "outlook":
            import os
            in_env = os.path.join(dynamic_onedrive_base, "uploads")
        else:
            in_env = os.getenv("GOOGLE_DRIVE_ROOT") or "./temp_inbox"
        
        base_temp = Path(in_env).resolve()
        temp_inbox = base_temp / sanitized_user if sanitized_user else base_temp
        logger.info("[CONFIG] Input staging folder resolved to: %s", temp_inbox)

    # Resolve output storage path
    if args.output:
        output_root = Path(args.output).resolve()
    else:
        if args.provider == "outlook":
            import os
            out_env = os.path.join(dynamic_onedrive_base, "sorted")
        else:
            out_env = os.getenv("GOOGLE_DRIVE_OUTPUT") or "./sorted"
        
        base_out = Path(out_env).resolve()
        output_root = base_out / sanitized_user if sanitized_user else base_out
        logger.info("[CONFIG] Output storage folder resolved to: %s", output_root)
    mark_read = not args.no_mark_read

    if args.interval is not None and args.interval > 0:
        logger.info("[WATCHER] Watcher started for user %s. Polling every %d seconds. Ctrl+C to stop.", user_email or "SYSTEM", args.interval)
        while True:
            try:
                cycle_run_id = str(_uuid.uuid4())
                execute_flow(
                    provider=args.provider,
                    temp_inbox=temp_inbox,
                    output_root=output_root,
                    pdf_max_pages=args.pages,
                    min_score=args.score,
                    llm_model=args.model,
                    mark_read=mark_read,
                    run_id=cycle_run_id,
                    user_email=user_email,
                )
                time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("[WATCHER] Watcher stopped by user (Ctrl+C).")
                if _mdb_ok:
                    try:
                        mdb.run_finish(cycle_run_id, status="stopped")
                    except Exception:
                        pass
                break
    else:
        execute_flow(
            provider=args.provider,
            temp_inbox=temp_inbox,
            output_root=output_root,
            pdf_max_pages=args.pages,
            min_score=args.score,
            llm_model=args.model,
            mark_read=mark_read,
            user_email=user_email,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
