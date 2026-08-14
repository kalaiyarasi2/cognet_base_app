"""
connector.py - Workspace Unified Pipeline: Outlook Sync -> Classifier -> GPU Extraction -> structured Drive storage

Flow:
  1. Poll/Fetch unread Outlook emails and download PDF attachments using OutlookAgentModule.
  2. Classify each PDF into a category (e.g. INVOICE, BANK_STATEMENT) using file-classification's DocumentClassifier.
  3. Create category folder <output_root>/<Category>/ on the local path or OneDrive.
  4. Save the original PDF there.
  5. Run Gpu_server's UnifiedRouter asynchronously on the PDF.
  6. Save processed outputs (Excel, JSON, TXT) under the same category folder.
  7. Mark email as read in Outlook.
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
from typing import Any, Dict, List, Set

from dotenv import load_dotenv

# Setup path imports for components
WORKSPACE_DIR = Path(__file__).parent.resolve()
# Ensure local monitor directory exists to satisfy monitor_db.py FileHandler
os.makedirs(WORKSPACE_DIR / "monitor", exist_ok=True)

OUTLOOK_AGENT_DIR = WORKSPACE_DIR / "Outlook_Agent"
CLASSIFIER_DIR = WORKSPACE_DIR / "file-classification-"
GPU_SERVER_DIR = WORKSPACE_DIR / "Gpu_server"
UNIFIED_PLATFORM_DIR = GPU_SERVER_DIR / "Unified_PDF_Platform"

for path in [OUTLOOK_AGENT_DIR, CLASSIFIER_DIR, GPU_SERVER_DIR, UNIFIED_PLATFORM_DIR, GPU_SERVER_DIR / "Email_pipeline"]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

# Mock 'auth' module to prevent Gmail auth error on imports
from unittest.mock import MagicMock
class MockAuth:
    gmail = MagicMock()
sys.modules['auth'] = MockAuth

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

# Map MICROSOFT_* credentials to AZURE_* variables for OutlookAgentModule compatibility
for key in ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"]:
    m_key = f"MICROSOFT_{key}"
    a_key = f"AZURE_{key}"
    if os.getenv(m_key) and not os.getenv(a_key):
        os.environ[a_key] = os.getenv(m_key)

# Now import components
try:
    import sys as _sys
    _workspace_str = str(WORKSPACE_DIR)
    if _workspace_str not in _sys.path:
        _sys.path.insert(0, _workspace_str)
    from database import poc_db
    _poc_db_ok = True
except Exception as _db_err:
    poc_db = None
    _poc_db_ok = False
    print(f"[WARN] poc_db not available in connector: {_db_err}")

try:
    from outlook_agent_module import OutlookAgentModule, _mark_read, _load_processed_ids, _save_processed_ids
except ImportError:
    OutlookAgentModule = None
    _mark_read = None
    _load_processed_ids = None
    _save_processed_ids = None

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
        simple_cache_path = os.path.join(os.path.dirname(self.token_cache_path), "ms_simple_cache.json")
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
        sessions_dir = Path(r"c:\Users\Intern\file classifier agent\sessions")
        # Fallback to general sibling directory pattern
        if not sessions_dir.exists():
            sessions_dir = Path(r"c:\Users\Intern\file classifier agent\.sessions")
        if not sessions_dir.exists():
            sessions_dir = WORKSPACE_DIR / ".." / "file classifier agent" / ".sessions"

        if sessions_dir.exists():
            import glob
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

from file_classifier import extract as classifier_extract, load_categories_from_env, DocumentClassifier
# from unified_router import UnifiedRouter

# Clean up sys.path to prevent namespace collisions (like config.py/utils.py)
for path in [OUTLOOK_AGENT_DIR, CLASSIFIER_DIR]:
    while str(path) in sys.path:
        sys.path.remove(str(path))

# Reconfigure stdout/stderr for UTF-8 support
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Configure logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("unified_workspace_connector")


def get_outlook_agent(user_email: str | None = None) -> OutlookAgentModule | None:
    if OutlookAgentModule is None:
        logger.error("OutlookAgentModule could not be imported.")
        return None
    try:
        return OutlookAgentModule(user_email=user_email)
    except Exception as exc:
        logger.error("Failed to initialize OutlookAgentModule: %s", exc)
        return None


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



def process_outlook_emails(
    temp_inbox: Path,
    output_root: Path,
    pdf_max_pages: int = 3,
    min_score: float = 3.0,
    llm_model: str = "gpt-4o",
    user_email: str | None = None,
) -> int:
    """
    Executes the entire end-to-end multi-repo pipeline.
    """
    agent = get_outlook_agent(user_email=user_email)
    if not agent:
        return 0

    temp_inbox.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        # Load categories from file-classification- .env
        categories = load_categories_from_env()
        if not categories:
            logger.error("No categories loaded from file-classification- environment.")
            return 0
        
        # Instantiate Classifier
        classifier = DocumentClassifier(categories=categories, threshold=min_score, llm_model=llm_model)

        # Get MS Graph token
        token = agent.get_access_token()
        processed_ids_file = agent.processed_ids_file
        
        if _load_processed_ids:
            processed_ids = _load_processed_ids(processed_ids_file)
        else:
            processed_ids = set()

        emails = agent.fetch_unread_emails()
        if not emails:
            logger.info("[PIPELINE] No new unread emails found in Outlook.")
            return 0

        logger.info("[PIPELINE] Found %d new unread email(s). Processing...", len(emails))
        processed_emails_count = 0
        
        # Local routing extraction (no external router needed)
        pass

        for email in emails:
            email_id = email["id"]
            attachments = email.get("attachments", [])
            
            if not attachments:
                if _mark_read:
                    _mark_read(token, email_id)
                processed_ids.add(email_id)
                continue

            for att in attachments:
                filename = att["filename"]
                if not filename.lower().endswith(".pdf"):
                    continue

                content_bytes = base64.b64decode(att["content_bytes"])
                temp_pdf_path = temp_inbox / filename
                temp_pdf_path.write_bytes(content_bytes)

                # ── STAGE 1: Classify using file-classification- ──────────────────
                logger.info("[CLASSIFY] Extracting text layer for classification: %s", filename)
                try:
                    # extract PDF text (reads up to max_pages)
                    text, pdf_type, rotation_info = classifier_extract(temp_pdf_path, max_pages=pdf_max_pages)
                    category, score = classifier.classify(text)
                except Exception as e:
                    logger.error("[CLASSIFY] [ERR] Classification failed: %s. Defaulting to 'Others'.", e)
                    category, score = "Others", 0.0

                logger.info("[CLASSIFY] Result: '%s' (score: %.2f) for file %s", category, score, filename)

                # ── STAGE 2: Create structured target directory (Category/Filename_Without_Ext) ────
                filename_stem = Path(filename).stem
                sanitized_cat = category.strip().upper().replace(" ", "_").replace("-", "_")
                dest_dir = output_root / sanitized_cat / filename_stem
                dest_dir.mkdir(parents=True, exist_ok=True)

                dest_pdf_path = dest_dir / filename
                # Move original PDF into category folder
                shutil.copy2(temp_pdf_path, dest_pdf_path)
                logger.info("[STORE] Original PDF copied to: %s", dest_pdf_path)

                # ── STAGE 3: Run Gpu_server Unified Extraction ────────────────────
                is_others = category.strip().upper() == "OTHERS"
                if is_others:
                    logger.info("[PIPELINE] Document classified as 'OTHERS'. Skipping extraction.")
                    extract_result = {"error": "Skipped extraction for category OTHERS"}
                else:
                    # Run the async local extraction method synchronously inside our block
                    extract_result = asyncio.run(run_local_extraction(category, dest_pdf_path, text))

                # ── STAGE 4: Store processed outputs in category folder ──────────
                if "error" not in extract_result:
                    # Move Excel output
                    excel_out = extract_result.get("excel")
                    if excel_out and os.path.exists(excel_out):
                        excel_dest = dest_dir / f"{filename_stem}_extracted.xlsx"
                        shutil.copy2(excel_out, excel_dest)
                        logger.info("[STORE] Excel output saved to: %s", excel_dest)

                    # Move JSON output
                    json_out = extract_result.get("json")
                    if json_out and os.path.exists(json_out):
                        json_dest = dest_dir / f"{filename_stem}_extracted.json"
                        shutil.copy2(json_out, json_dest)
                        logger.info("[STORE] JSON output saved to: %s", json_dest)

                    # Write TXT text logs
                    txt_dest = dest_dir / f"{filename_stem}_text.txt"
                    txt_dest.write_text(
                        f"Category: {category}\nClassification Score: {score}\nPDF Type: {pdf_type}\nRotation Applied: {rotation_info}\n",
                        encoding="utf-8"
                    )
                    logger.info("[STORE] TXT metadata saved to: %s", txt_dest)

                    # Log to universal_history in converter.db
                    if _poc_db_ok:
                        try:
                            poc_db.log_universal(
                                module="OUTLOOK",
                                action="Email Attachment Processing",
                                file_name=filename,
                                status="SUCCESS",
                                details=f"Classified: {category} (score: {score:.2f}) | PDF: {pdf_type} | Extracted",
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
                                poc_db.log_universal(
                                    module="OUTLOOK",
                                    action="Email Attachment Processing",
                                    file_name=filename,
                                    status="SUCCESS",
                                    details=f"Classified: {category} (score: {score:.2f}) | Skipped (Category: Others)",
                                    processed_by=user_email or "SYSTEM"
                                )
                            except Exception as db_err:
                                logger.warning("Failed to log OTHERS to converter.db: %s", db_err)
                    else:
                        logger.error("[PIPELINE] Extraction failed for %s: %s", filename, extract_result.get("error"))

                        # Log failure to universal_history in converter.db
                        if _poc_db_ok:
                            try:
                                poc_db.log_universal(
                                    module="OUTLOOK",
                                    action="Email Attachment Processing",
                                    file_name=filename,
                                    status="FAILED",
                                    details=str(extract_result.get("error")),
                                    processed_by=user_email or "SYSTEM"
                                )
                            except Exception as db_err:
                                logger.warning("Failed to log error to converter.db: %s", db_err)

                # Clean up temp inbox PDF
                if temp_pdf_path.exists():
                    temp_pdf_path.unlink()

            # Mark email as read and add to processed
            if _mark_read:
                _mark_read(token, email_id)
            processed_ids.add(email_id)
            processed_emails_count += 1

        if _save_processed_ids:
            _save_processed_ids(processed_ids, processed_ids_file)

        logger.info("[PIPELINE] Run complete. Processed %d email(s).", processed_emails_count)
        return processed_emails_count

    except Exception as exc:
        logger.error("[PIPELINE] [CRITICAL] Pipeline failed: %s", exc, exc_info=True)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Workspace Unified Pipeline Runner")
    parser.add_argument(
        "--input",
        default="./temp_inbox",
        help="Temporary local inbox path to store attachments during pipeline run",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Structured drive output root path. If not provided, defaults to ONEDRIVE_OUTPUT, GOOGLE_DRIVE_OUTPUT, or './sorted'.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="If set, polls Outlook continuously every N seconds. If unset, runs once.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Max pages to read per PDF for classification",
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
        "--user",
        default=None,
        help="User email context for isolated email processing",
    )

    args = parser.parse_args()

    user_email = args.user
    import re
    sanitized_user = re.sub(r'[^a-zA-Z0-9]', '_', user_email.lower()) if user_email else None

    # Resolve input staging path
    if args.input and args.input != "./temp_inbox":
        temp_inbox = Path(args.input).resolve()
    else:
        # connector.py always uses Outlook, so default to OneDrive uploads
        in_env = "C:\\Users\\Intern\\OneDrive - Cognet HR Solutions Pvt Ltd\\uploads"
        base_temp = Path(in_env).resolve()
        temp_inbox = base_temp / sanitized_user if sanitized_user else base_temp
        logger.info("[CONFIG] Input staging folder resolved to: %s", temp_inbox)

    # Resolve output storage path
    if args.output:
        output_root = Path(args.output).resolve()
    else:
        # connector.py always uses Outlook, so default to OneDrive sorted
        out_env = "C:\\Users\\Intern\\OneDrive - Cognet HR Solutions Pvt Ltd\\sorted"
        base_out = Path(out_env).resolve()
        output_root = base_out / sanitized_user if sanitized_user else base_out
        logger.info("[CONFIG] Output storage folder resolved to: %s", output_root)

    if args.interval is not None and args.interval > 0:
        logger.info("Continuous watcher started for user %s. Press Ctrl+C to stop.", user_email or "SYSTEM")
        while True:
            try:
                process_outlook_emails(
                    temp_inbox=temp_inbox,
                    output_root=output_root,
                    pdf_max_pages=args.pages,
                    min_score=args.score,
                    llm_model=args.model,
                    user_email=user_email,
                )
                logger.info("Sleeping for %d seconds...", args.interval)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Stopped by user (Ctrl+C).")
                break
    else:
        process_outlook_emails(
            temp_inbox=temp_inbox,
            output_root=output_root,
            pdf_max_pages=args.pages,
            min_score=args.score,
            llm_model=args.model,
            user_email=user_email,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
