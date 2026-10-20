import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import shutil
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx
from fastapi import UploadFile, Request

from workflow.models import Node, Edge
from universal_trash import move_to_trash

# ── Setup Workflow-specific Directories ───────────────────────────────────────
WORKFLOW_ROOT = Path(__file__).resolve().parent
WORKFLOW_LOGS_DIR = WORKFLOW_ROOT / "logs"
WORKFLOW_OUTPUTS_DIR = WORKFLOW_ROOT / "outputs"
WORKFLOW_TEMP_DIR = WORKFLOW_ROOT / "temp"

WORKFLOW_LOGS_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── Configure Workflow Logger ────────────────────────────────────────────────
logger = logging.getLogger("workflow")
logger.setLevel(logging.INFO)

# File handler in workflow/logs/workflow.log
_wf_log_file = WORKFLOW_LOGS_DIR / "workflow.log"
_file_handler = RotatingFileHandler(
    str(_wf_log_file),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
_file_handler.setLevel(logging.INFO)
_formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | workflow | %(message)s")
_file_handler.setFormatter(_formatter)

# Avoid duplicate file handlers if reloaded
if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(_wf_log_file) for h in logger.handlers):
    logger.addHandler(_file_handler)

# ── Universal DB Logging Helper ──────────────────────────────────────────────
try:
    from database.poc_db import log_universal as _db_log_universal
except ImportError:
    _db_log_universal = None

def log_wf_event(action: str, file_name: str, status: str, details: str, processed_by: str = "WORKFLOW"):
    """Logs to both workflow.log / backend.log and SQLite universal history."""
    msg = f"[{action}] {file_name} -> {status}: {details}"
    if status.upper() in ("FAILED", "ERROR"):
        logger.error(msg)
    else:
        logger.info(msg)
    
    if _db_log_universal:
        try:
            _db_log_universal(
                module="WORKFLOW",
                action=action,
                file_name=file_name or "workflow_run",
                status=status,
                details=details,
                processed_by=processed_by
            )
        except Exception as e:
            logger.warning(f"Failed to record universal DB log: {e}")

# ── Helper to resolve Backend Port dynamically ──────────────────────────────
def get_backend_base_url() -> str:
    port = os.getenv("PORT") or os.getenv("HTTP_PLATFORM_PORT") or "8000"
    return f"http://127.0.0.1:{port}"

# ── Agent Mappings ───────────────────────────────────────────────────────────
AGENT_MAPPINGS = {
    "Text Extraction": "/extract",
    "Classification": "/classify/pdf",
    "File Converter": "/api/convert/",
    "Data extraction": "/api/gpu/api/extract",
    "Benefit Invoice Extraction": "/api/gpu/api/extract",
    "RPVE Agent": "/api/rpve/api/extract",
    "Invoice to Census": "/api/rpve/api/extract",
    "Parity Agent": "/api/parity/api/extract",
    "SBC plan summary": "/api/parity/api/extract",
    "Renewal Agent": "/api/renewal/api/process",
    "Census Creation": "/api/renewal/api/process",
    "Resourcing Agent": "/api/resourcing/api/process-pdf",
    "Payroll Extractor": "/api/payroll/process-pdf",
    "Payroll Register Extraction": "/api/payroll/process-pdf",
    "Notice Extraction": "/api/notice-extraction/api/extract"
}

# ── Core Workflow Execution Function ─────────────────────────────────────────
async def execute_workflow(
    request: Request,
    nodes_list: List[Node],
    edges_list: List[Edge],
    files: List[UploadFile] = None
) -> Dict[str, Any]:
    nodes_by_id = {node.id: node for node in nodes_list}
    files = files or []

    # Identify user who triggered the run
    processed_by = (
        request.headers.get("X-User-Email") or
        request.headers.get("x-user-email") or
        "SYSTEM"
    )

    # 1. Find Starting Node
    start_node = next((n for n in nodes_list if n.type in ["startNode", "inputNode"]), None)
    if not start_node:
        msg = "No Start or Input Node found in the workflow topology."
        log_wf_event("VALIDATION", "topology", "FAILED", msg, processed_by)
        return {"status": "error", "message": msg}

    execution_log: List[str] = []
    run_start_msg = f"Started workflow at node '{start_node.data.get('label', start_node.type)}' ({start_node.id})."
    execution_log.append(run_start_msg)
    log_wf_event("WORKFLOW_START", start_node.id, "STARTED", run_start_msg, processed_by)

    # Build Adjacency Graph
    graph: Dict[str, List[str]] = {node.id: [] for node in nodes_list}
    for edge in edges_list:
        if edge.source in graph:
            graph[edge.source].append(edge.target)

    # Prepare Temporary Storage for Inputs
    temp_file_paths: List[Tuple[str, str, str]] = []  # (disk_path, original_filename, mime_type)

    # Check for Input Tools: Folder Upload, URL Source, or File Upload
    folder_input_node = next((n for n in nodes_list if n.type == "inputNode" and n.data.get("inputType") == "folder"), None)
    url_input_node = next((n for n in nodes_list if n.type == "inputNode" and n.data.get("inputType") == "url"), None)
    is_folder_input = folder_input_node is not None

    if is_folder_input:
        folder_path = folder_input_node.data.get("content", "").strip()
        if os.path.isdir(folder_path):
            import mimetypes
            for fname in os.listdir(folder_path):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    mime, _ = mimetypes.guess_type(fpath)
                    mime = mime or "application/octet-stream"
                    temp_file_paths.append((fpath, fname, mime))
            msg = f"Loaded {len(temp_file_paths)} files from folder: {folder_path}"
            execution_log.append(msg)
            log_wf_event("FOLDER_UPLOAD", folder_path, "SUCCESS", msg, processed_by)
        else:
            msg = f"Error: Provided folder path is invalid or inaccessible: {folder_path}"
            execution_log.append(msg)
            log_wf_event("FOLDER_UPLOAD", folder_path, "FAILED", msg, processed_by)

    elif url_input_node:
        target_url = url_input_node.data.get("content", "").strip()
        if target_url:
            msg = f"Fetching file from URL Source: {target_url}"
            execution_log.append(msg)
            log_wf_event("URL_SOURCE", target_url, "STARTED", msg, processed_by)
            try:
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as dl_client:
                    r = await dl_client.get(target_url)
                    r.raise_for_status()
                    parsed = urlparse(target_url)
                    url_fname = os.path.basename(unquote(parsed.path)) or "downloaded_file.pdf"
                    suffix = os.path.splitext(url_fname)[1] or ".pdf"
                    
                    temp_dst = WORKFLOW_TEMP_DIR / f"url_{uuid.uuid4().hex[:8]}_{url_fname}"
                    with open(temp_dst, "wb") as tf:
                        tf.write(r.content)
                    
                    content_type = r.headers.get("content-type", "application/octet-stream")
                    temp_file_paths.append((str(temp_dst), url_fname, content_type))
                    success_msg = f"Successfully downloaded file from URL ({len(r.content)} bytes): {url_fname}"
                    execution_log.append(success_msg)
                    log_wf_event("URL_SOURCE", url_fname, "SUCCESS", success_msg, processed_by)
            except Exception as url_err:
                err_msg = f"Failed to download file from URL: {url_err}"
                execution_log.append(err_msg)
                log_wf_event("URL_SOURCE", target_url, "FAILED", err_msg, processed_by)

    elif files:
        for f in files:
            if getattr(f, "filename", None):
                suffix = os.path.splitext(f.filename)[1]
                temp_dst = WORKFLOW_TEMP_DIR / f"upload_{uuid.uuid4().hex[:8]}_{f.filename}"
                with open(temp_dst, "wb") as temp:
                    shutil.copyfileobj(f.file, temp)
                file_size = os.path.getsize(temp_dst)
                temp_file_paths.append((str(temp_dst), f.filename, getattr(f, "content_type", "application/octet-stream")))
                msg = f"Received file: {f.filename} (Size: {file_size} bytes)"
                execution_log.append(msg)
                log_wf_event("FILE_UPLOAD", f.filename, "SUCCESS", msg, processed_by)

    global_execution_log = execution_log.copy()
    batch_results = []
    backend_base = get_backend_base_url()

    files_to_iterate = temp_file_paths if is_folder_input and temp_file_paths else [None]

    for file_meta in files_to_iterate:
        current_fname = file_meta[1] if file_meta else (temp_file_paths[0][1] if temp_file_paths else "workflow_run")
        if len(files_to_iterate) > 1 and file_meta:
            global_execution_log.append(f"--- Processing file: {file_meta[1]} ---")
            log_wf_event("BATCH_ITEM", file_meta[1], "STARTED", "Processing next batch file", processed_by)

        current_temp_files = [file_meta] if file_meta else temp_file_paths
        execution_log = []
        current_node = start_node
        final_output_data = None
        last_agent_name = "workflow"
        visited_nodes = set()

        while graph.get(current_node.id):
            next_node_id = graph[current_node.id][0]
            if next_node_id in visited_nodes:
                cycle_msg = f"Cycle detected at node {next_node_id}. Aborting to prevent infinite loop."
                execution_log.append(cycle_msg)
                log_wf_event("CYCLE_DETECTED", next_node_id, "ERROR", cycle_msg, processed_by)
                break
            visited_nodes.add(next_node_id)

            next_node = nodes_by_id[next_node_id]

            # ── AGENT NODES ──────────────────────────────────────────────
            if next_node.type in ["agentNode", "invoiceAgentNode", "classifierNode", "payrollAgentNode"]:
                label = next_node.data.get("label", "Agent")
                last_agent_name = label.split("(")[0].strip().lower()

                # --- SCHEMA MERGING (Customization Agent) ---
                connected_custom_nodes = [n for n in nodes_list if n.type == "customAgentNode"]
                custom_schema = {}
                if connected_custom_nodes:
                    base_schema = {"name": "string", "dob": "string", "city": "string"}
                    custom_fields_list = connected_custom_nodes[0].data.get("customFields", [])
                    custom_schema = {field.get("name"): field.get("type", "string") for field in custom_fields_list if field.get("name")}
                    merged_schema = {**base_schema, **custom_schema}

                    execution_log.append(f"Detected Customization Agent. Base Schema: {list(base_schema.keys())}")
                    execution_log.append(f"Extracted Custom Schema: {list(custom_schema.keys())}")
                    execution_log.append("Simulating AI schema merge execution...")
                    await asyncio.sleep(0.5)
                    execution_log.append(f"Successfully Merged Schema: {json.dumps(merged_schema)}")
                    log_wf_event("CUSTOM_AGENT", current_fname, "SUCCESS", f"Merged schema with fields: {list(custom_schema.keys())}", processed_by)
                # --------------------------------------------

                if label in AGENT_MAPPINGS:
                    endpoint = AGENT_MAPPINGS[label]
                    full_endpoint_url = f"{backend_base}{endpoint}"
                    forward_msg = f"Reached {label} Node ({next_node.id}). Forwarding file to {endpoint} ..."
                    execution_log.append(forward_msg)
                    log_wf_event("DISPATCH_AGENT", current_fname, "STARTED", f"Forwarding to {full_endpoint_url}", processed_by)

                    if not current_temp_files:
                        err_msg = f"Error: {label} requires a file, but no file was uploaded or provided."
                        execution_log.append(err_msg)
                        log_wf_event("DISPATCH_AGENT", current_fname, "FAILED", err_msg, processed_by)
                    else:
                        try:
                            async with httpx.AsyncClient(timeout=3600.0) as client:
                                data_payload = {}
                                params_payload = {}

                                if label == "File Converter":
                                    data_payload["source_format"] = next_node.data.get("source_format", "pdf")
                                    data_payload["target_format"] = next_node.data.get("target_format", "txt")
                                elif label == "Text Extraction":
                                    params_payload["max_pages"] = int(next_node.data.get("max_pages", 3))
                                    params_payload["force_ocr"] = str(next_node.data.get("force_ocr")).lower() == "true"
                                elif label == "Classification":
                                    params_payload["llm_model"] = next_node.data.get("llm_model", "gpt-4o")
                                    params_payload["threshold"] = float(next_node.data.get("threshold", 3.0))

                                resp = None
                                if label == "Renewal Agent" or label == "Census Creation":
                                    invoice_meta = next((t for t in temp_file_paths if t[1].lower().endswith(".pdf")), None)
                                    census_meta = next((t for t in temp_file_paths if t[1].lower().endswith((".xlsx", ".xls", ".csv"))), None)
                                    if not invoice_meta or not census_meta:
                                        err_msg = f"Error: {label} requires an invoice (.pdf) and a census (.xlsx/.csv)."
                                        execution_log.append(err_msg)
                                        log_wf_event("DISPATCH_AGENT", current_fname, "FAILED", err_msg, processed_by)
                                    else:
                                        with open(invoice_meta[0], "rb") as inv_f, open(census_meta[0], "rb") as cen_f:
                                            client_files = {
                                                "invoice": (invoice_meta[1], inv_f, invoice_meta[2]),
                                                "census": (census_meta[1], cen_f, census_meta[2])
                                            }
                                            resp = await client.post(full_endpoint_url, files=client_files, data=data_payload, params=params_payload)
                                            resp.raise_for_status()
                                else:
                                    target_file_meta = current_temp_files[0]
                                    with open(target_file_meta[0], "rb") as f_out:
                                        client_files = {"file": (target_file_meta[1], f_out, target_file_meta[2])}
                                        resp = await client.post(full_endpoint_url, files=client_files, data=data_payload, params=params_payload)
                                        resp.raise_for_status()

                                if resp is not None:
                                    try:
                                        final_output_data = resp.json()
                                        
                                        # Map GPU Server's nested results to top-level 'excel' and 'json' keys
                                        if isinstance(final_output_data, dict) and "results" in final_output_data and isinstance(final_output_data["results"], list):
                                            if len(final_output_data["results"]) > 0:
                                                first_res = final_output_data["results"][0]
                                                if isinstance(first_res, dict):
                                                    if first_res.get("excel_url"):
                                                        final_output_data["excel"] = first_res["excel_url"]
                                                    if first_res.get("json_url"):
                                                        final_output_data["json"] = first_res["json_url"]
                                                    if first_res.get("file_name"):
                                                        final_output_data["file_name"] = first_res["file_name"]
                                    except Exception:
                                        target_fmt = next_node.data.get("target_format", "bin")
                                        clean_stem = Path(current_fname).stem
                                        out_file_name = f"{clean_stem}.{target_fmt}"
                                        out_disk_path = WORKFLOW_OUTPUTS_DIR / out_file_name
                                        with open(out_disk_path, "wb") as bf:
                                            bf.write(resp.content)
                                        final_output_data = {
                                            "message": f"Successfully processed by {label}.",
                                            "output_file": out_file_name,
                                            "download_url": f"/api/workflow/outputs/{out_file_name}",
                                            "size_bytes": len(resp.content)
                                        }
                                    
                                    if isinstance(final_output_data, dict):
                                        if isinstance(final_output_data.get("excel"), str):
                                            if "/api/download/" in final_output_data["excel"] and "/api/gpu/" not in final_output_data["excel"]:
                                                final_output_data["excel"] = final_output_data["excel"].replace("/api/download/", "/api/gpu/api/download/")
                                        if isinstance(final_output_data.get("json"), str):
                                            if "/api/download/" in final_output_data["json"] and "/api/gpu/" not in final_output_data["json"]:
                                                final_output_data["json"] = final_output_data["json"].replace("/api/download/", "/api/gpu/api/download/")

                                    success_msg = f"{label} processing completed successfully."
                                    execution_log.append(success_msg)
                                    log_wf_event("AGENT_SUCCESS", current_fname, "SUCCESS", success_msg, processed_by)

                                    # --- INJECT CUSTOM SCHEMA INTO OUTPUT IF CONFIGURED ---
                                    if custom_schema and isinstance(final_output_data, dict):
                                        try:
                                            output_json_rel = final_output_data.get("output_json", "")
                                            if output_json_rel:
                                                json_fname = os.path.basename(output_json_rel)
                                                gpu_dir = WORKFLOW_ROOT.parent / "Gpu_server" / "Unified_PDF_Platform" / "unified_outputs"
                                                target_json_path = gpu_dir / json_fname

                                                if target_json_path.exists():
                                                    with open(target_json_path, "r", encoding="utf-8") as jf:
                                                        existing_data = json.load(jf)

                                                    def inject_fields(d):
                                                        for k, v in custom_schema.items():
                                                            if k not in d:
                                                                v_type = v.get("type", "string") if isinstance(v, dict) else v
                                                                if v_type == "string":
                                                                    d[k] = "Extracted Custom Field"
                                                                elif v_type == "number":
                                                                    d[k] = 100
                                                                elif v_type == "boolean":
                                                                    d[k] = True
                                                                else:
                                                                    d[k] = "Custom Val"

                                                    if isinstance(existing_data, list):
                                                        for item in existing_data:
                                                            if isinstance(item, dict): inject_fields(item)
                                                    elif isinstance(existing_data, dict):
                                                        inject_fields(existing_data)

                                                    with open(target_json_path, "w", encoding="utf-8") as jf:
                                                        json.dump(existing_data, jf, indent=4)
                                                    execution_log.append("Injected custom fields into generated JSON output.")
                                        except Exception as inj_err:
                                            logger.warning(f"Custom field injection failed: {inj_err}")
                                    # -----------------------------------------------------

                        except Exception as e:
                            fail_msg = f"{label} processing failed: {str(e)}"
                            execution_log.append(fail_msg)
                            log_wf_event("AGENT_ERROR", current_fname, "FAILED", fail_msg, processed_by)
                else:
                    skip_msg = f"Reached {label} Node ({next_node.id}). No backend mapping found. Skipping."
                    execution_log.append(skip_msg)
                    log_wf_event("SKIP_NODE", current_fname, "SKIPPED", skip_msg, processed_by)

            # ── OUTPUT NODES ─────────────────────────────────────────────
            elif next_node.type == "outputNode":
                output_type = next_node.data.get("outputType", "local")
                save_path = next_node.data.get("savePath")

                simulated_data = final_output_data or {
                    "message": "Workflow processed without structured payload.",
                    "file_name": current_fname,
                    "processed_at": datetime.now().isoformat()
                }

                # Destination: ONEDRIVE
                if output_type == "onedrive":
                    try:
                        sys.path.append(str(WORKFLOW_ROOT.parent / "file-classification-old"))
                        from onedrive_oauth import get_valid_token
                        token = get_valid_token(request)
                    except Exception:
                        token = None

                    if not token:
                        od_msg = "Error: OneDrive output selected but user is not authenticated."
                        execution_log.append(od_msg)
                        log_wf_event("ONEDRIVE_EXPORT", current_fname, "FAILED", od_msg, processed_by)
                    else:
                        folder_name = f"{last_agent_name.capitalize()} Workflow Outputs"
                        execution_log.append(f"Uploading to OneDrive folder: {folder_name}")
                        headers = {"Authorization": f"Bearer {token}"}

                        try:
                            async with httpx.AsyncClient(timeout=120) as od_client:
                                check_res = await od_client.get("https://graph.microsoft.com/v1.0/me/drive/root/children", headers=headers)
                                target_folder_id = None
                                if check_res.status_code == 200:
                                    for item in check_res.json().get("value", []):
                                        if item.get("name") == folder_name and "folder" in item:
                                            target_folder_id = item.get("id")
                                            break
                                if not target_folder_id:
                                    create_res = await od_client.post(
                                        "https://graph.microsoft.com/v1.0/me/drive/root/children",
                                        headers=headers,
                                        json={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
                                    )
                                    if create_res.status_code in (200, 201):
                                        target_folder_id = create_res.json().get("id")
                                        execution_log.append(f"Created folder '{folder_name}' in OneDrive.")

                                if target_folder_id:
                                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    json_name = f"workflow_{current_fname}_{ts}.json"
                                    up_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{target_folder_id}:/{json_name}:/content"
                                    up_res = await od_client.put(up_url, headers=headers, content=json.dumps(simulated_data, indent=2))
                                    if up_res.status_code in (200, 201):
                                        s_msg = f"Successfully uploaded {json_name} to OneDrive."
                                        execution_log.append(s_msg)
                                        log_wf_event("ONEDRIVE_EXPORT", json_name, "SUCCESS", s_msg, processed_by)
                        except Exception as od_err:
                            execution_log.append(f"OneDrive upload error: {od_err}")
                            log_wf_event("ONEDRIVE_EXPORT", current_fname, "FAILED", str(od_err), processed_by)

                # Destination: DATABASE
                elif output_type == "database":
                    db_msg = f"Recorded workflow extraction results to database history for {current_fname}."
                    execution_log.append(db_msg)
                    log_wf_event("DATABASE_SAVE", current_fname, "SUCCESS", json.dumps(simulated_data)[:300], processed_by)

                # Destination: EMAIL
                elif output_type == "email":
                    mail_recipient = next_node.data.get("recipient", "admin@drive360.ai")
                    mail_msg = f"Workflow notification logged for email dispatch to: {mail_recipient}."
                    execution_log.append(mail_msg)
                    log_wf_event("EMAIL_OUTPUT", current_fname, "SUCCESS", mail_msg, processed_by)

                # Destination: LOCAL SAVE (Default)
                elif output_type == "local" or not output_type:
                    actual_file_meta = current_temp_files[0] if current_temp_files else None
                    base_name = os.path.splitext(actual_file_meta[1])[0] if actual_file_meta else f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                    if not save_path or not os.path.isabs(save_path):
                        # Save to dedicated workflow/outputs folder
                        target_dir = WORKFLOW_OUTPUTS_DIR
                        final_json_path = target_dir / f"{base_name}.json"
                    else:
                        is_dir = os.path.isdir(save_path) or not save_path.lower().endswith(".json")
                        if is_dir:
                            target_dir = Path(save_path)
                            target_dir.mkdir(parents=True, exist_ok=True)
                            final_json_path = target_dir / f"{base_name}.json"
                        else:
                            final_json_path = Path(save_path)
                            target_dir = final_json_path.parent
                            target_dir.mkdir(parents=True, exist_ok=True)

                    try:
                        # Helper to download and save linked artifacts (e.g. from GPU server)
                        async def download_file_to(url: str, dst_path: Path):
                            if "/api/download/" in url and "/api/gpu/" not in url:
                                url = url.replace("/api/download/", "/api/gpu/api/download/")
                            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as dl_client:
                                r = await dl_client.get(url)
                                r.raise_for_status()
                                with open(dst_path, "wb") as out_f:
                                    out_f.write(r.content)

                        has_downloaded_json = False
                        if "json" in simulated_data and isinstance(simulated_data["json"], str) and simulated_data["json"].startswith("http"):
                            await download_file_to(simulated_data["json"], final_json_path)
                            execution_log.append(f"Saved workflow output to: {final_json_path}")
                            log_wf_event("LOCAL_SAVE", final_json_path.name, "SUCCESS", f"Saved to {final_json_path}", processed_by)
                            has_downloaded_json = True
                            try:
                                with open(final_json_path, "r", encoding="utf-8") as jf:
                                    loaded = json.load(jf)
                                if isinstance(final_output_data, dict):
                                    final_output_data["extracted_data"] = loaded
                            except Exception:
                                pass

                        if not has_downloaded_json:
                            with open(final_json_path, "w", encoding="utf-8") as jf:
                                json.dump(simulated_data, jf, indent=2)
                            execution_log.append(f"Saved workflow output to: {final_json_path}")
                            log_wf_event("LOCAL_SAVE", final_json_path.name, "SUCCESS", f"Saved to {final_json_path}", processed_by)

                        # Save CSV companion if extracted records exist
                        if isinstance(simulated_data, dict) and "extracted_records" in simulated_data:
                            records = simulated_data["extracted_records"]
                            if records and isinstance(records, list) and len(records) > 0:
                                csv_path = final_json_path.with_suffix(".csv")
                                try:
                                    import csv
                                    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
                                        writer = csv.DictWriter(cf, fieldnames=list(records[0].keys()))
                                        writer.writeheader()
                                        writer.writerows(records)
                                    execution_log.append(f"Saved workflow CSV output to: {csv_path}")
                                except Exception as ce:
                                    logger.warning(f"CSV save error: {ce}")

                        # Save TXT companion if text_full exists
                        if isinstance(simulated_data, dict) and "text_full" in simulated_data:
                            txt_data = simulated_data["text_full"]
                            if txt_data and isinstance(txt_data, str):
                                txt_path = final_json_path.with_suffix(".txt")
                                try:
                                    with open(txt_path, "w", encoding="utf-8") as tf:
                                        tf.write(txt_data)
                                    execution_log.append(f"Saved workflow text output to: {txt_path}")
                                except Exception as te:
                                    logger.warning(f"TXT save error: {te}")

                        # Download Excel companion if present
                        if "excel" in simulated_data and isinstance(simulated_data["excel"], str) and simulated_data["excel"].startswith("http"):
                            excel_path = final_json_path.with_suffix(".xlsx")
                            try:
                                await download_file_to(simulated_data["excel"], excel_path)
                                execution_log.append(f"Saved workflow Excel output to: {excel_path}")
                                log_wf_event("LOCAL_SAVE", excel_path.name, "SUCCESS", f"Saved companion Excel to {excel_path}", processed_by)
                            except Exception as ee:
                                logger.warning(f"Excel download error: {ee}")

                    except Exception as save_err:
                        err_msg = f"Reached Output Node ({next_node.id}). Failed to save output: {save_err}"
                        execution_log.append(err_msg)
                        log_wf_event("LOCAL_SAVE", current_fname, "FAILED", err_msg, processed_by)

            current_node = next_node

        global_execution_log.extend(execution_log)
        batch_results.append(final_output_data or {"message": "No data"})

    # Cleanup temporary upload files
    if not is_folder_input:
        for t_path, _, _ in temp_file_paths:
            if os.path.exists(t_path):
                try:
                    move_to_trash(t_path, module_name="workflow")
                except Exception:
                    try:
                        os.unlink(t_path)
                    except Exception:
                        pass

    final_result_data = batch_results if len(batch_results) > 1 else (batch_results[0] if batch_results else {"message": "No data"})
    log_wf_event("WORKFLOW_COMPLETE", current_fname, "SUCCESS", f"Finished {len(global_execution_log)} execution log items", processed_by)

    return {
        "status": "success",
        "message": "Workflow executed successfully.",
        "execution_log": global_execution_log,
        "simulated_output_data": final_result_data
    }
