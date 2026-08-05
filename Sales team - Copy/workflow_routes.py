from fastapi import APIRouter, UploadFile, File, Form, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import json
import os
import httpx
import tempfile
import shutil
import uuid
from datetime import datetime

# Import auth and db
from auth_routes import get_current_user_from_token
from fastapi import Depends
from database.poc_db import save_workflow_project, get_workflow_project, list_workflow_projects, delete_workflow_project

router = APIRouter(prefix="/api/workflow", tags=["Workflow Engine (Co-Pilot)"])

# Keep the old Pydantic models for manual parsing of the JSON strings
class NodeData(BaseModel):
    label: Optional[str] = None
    saveOption: Optional[str] = None
    model_config = {"extra": "allow"}

class Node(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]
    position: Dict[str, float]

class Edge(BaseModel):
    id: str
    source: str
    target: str

AGENT_MAPPINGS = {
    "Text Extraction": "/extract",
    "Classification": "/classify/pdf",
    "File Converter": "/api/convert",
    "Data extraction": "/api/gpu/api/extract",
    "RPVE Agent": "/api/rpve/api/extract",
    "Parity Agent": "/api/parity/api/extract",
    "Renewal Agent": "/api/renewal/api/process",
    "Resourcing Agent": "/api/resourcing/api/process-pdf",
    "Payroll Extractor": "/api/payroll/process-pdf"
}

@router.post("/run-workflow")
async def run_workflow(
    request: Request,
    nodes: str = Form(...),
    edges: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    try:
        nodes_list = [Node(**n) for n in json.loads(nodes)]
        edges_list = [Edge(**e) for e in json.loads(edges)]
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse workflow topology: {e}"}

    nodes_by_id = {node.id: node for node in nodes_list}
    
    # 1. Find the Starting Node
    start_node = next((n for n in nodes_list if n.type in ["startNode", "inputNode"]), None)
    if not start_node:
        return {"status": "error", "message": "No Start or Input Node found in the workflow."}
    
    execution_log = []
    execution_log.append(f"Started at node '{start_node.data.get('label', start_node.type)}' ({start_node.id}).")
    
    graph = {node.id: [] for node in nodes_list}
    for edge in edges_list:
        if edge.source in graph:
            graph[edge.source].append(edge.target)

    # Save uploaded files to temporary files
    temp_file_paths = []
    folder_input_node = next((n for n in nodes_list if n.type == "inputNode" and n.data.get("inputType") == "folder"), None)
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
            execution_log.append(f"Loaded {len(temp_file_paths)} files from folder: {folder_path}")
        else:
            execution_log.append(f"Error: Provided folder path is invalid: {folder_path}")
    elif files:
        for f in files:
            if getattr(f, "filename", None):
                suffix = os.path.splitext(f.filename)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                    shutil.copyfileobj(f.file, temp)
                    temp_file_paths.append((temp.name, f.filename, getattr(f, "content_type", "application/octet-stream")))
                execution_log.append(f"Received file: {f.filename} (Size: {os.path.getsize(temp.name)} bytes)")

    global_execution_log = execution_log.copy()
    batch_results = []
    
    files_to_iterate = temp_file_paths if is_folder_input and temp_file_paths else [None]
    
    for file_meta in files_to_iterate:
        if len(files_to_iterate) > 1 and file_meta:
            global_execution_log.append(f"--- Processing file: {file_meta[1]} ---")
        
        # Override temp_file_paths for this iteration so existing agent logic uses this file
        current_temp_files = [file_meta] if file_meta else temp_file_paths
        execution_log = []
        current_node = start_node
        final_output_data = None
        last_agent_name = "workflow"
        visited_nodes = set()

        while graph.get(current_node.id):
            next_node_id = graph[current_node.id][0]
            if next_node_id in visited_nodes:
                execution_log.append(f"Cycle detected at node {next_node_id}. Aborting to prevent infinite loop.")
                break
            visited_nodes.add(next_node_id)

            next_node = nodes_by_id[next_node_id]

            if next_node.type in ["agentNode", "invoiceAgentNode", "classifierNode", "payrollAgentNode"]:
                label = next_node.data.get("label", "Agent")
                if next_node.type in ["agentNode", "invoiceAgentNode", "payrollAgentNode"]:
                    last_agent_name = label.split("(")[0].strip().lower()

                # --- START SCHEMA MERGING ---
                if next_node.type in ["agentNode", "invoiceAgentNode", "payrollAgentNode"]:
                    # Detect any Customization Agents present in the workflow
                    connected_custom_nodes = [n for n in nodes_list if n.type == "customAgentNode"]

                    if connected_custom_nodes:
                        # 1. Load Dummy Base Schema
                        base_schema = {"name": "string", "dob": "string", "city": "string"}

                        # 2. Extract Custom Schema from payload
                        custom_schema = connected_custom_nodes[0].data.get("customSchema", {})

                        # 3. Merge Schemas
                        merged_schema = {**base_schema, **custom_schema}

                        execution_log.append(f"Detected Customization Agent. Base Schema: {list(base_schema.keys())}")
                        execution_log.append(f"Extracted Custom Schema: {list(custom_schema.keys())}")

                        # 4. Simulate AI Execution Step
                        execution_log.append("Simulating AI schema merge execution...")
                        await asyncio.sleep(1.5)
                        execution_log.append(f"Successfully Merged Schema: {json.dumps(merged_schema)}")
                # --- END SCHEMA MERGING ---

                if label in AGENT_MAPPINGS:
                    endpoint = AGENT_MAPPINGS[label]
                    execution_log.append(f"Reached {label} Node ({next_node.id}). Forwarding file to {endpoint} ...")


                    if not current_temp_files:
                        execution_log.append(f"Error: {label} requires a file, but no file was uploaded.")
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
                                    params_payload["force_ocr"] = next_node.data.get("force_ocr") == "true"
                                elif label == "Classification":
                                    params_payload["llm_model"] = next_node.data.get("llm_model", "gpt-4o")
                                    params_payload["threshold"] = float(next_node.data.get("threshold", 3.0))

                                resp = None
                                if label == "Renewal Agent":
                                    invoice_meta = next((t for t in temp_file_paths if t[1].lower().endswith(".pdf")), None)
                                    census_meta = next((t for t in temp_file_paths if t[1].lower().endswith((".xlsx", ".xls", ".csv"))), None)
                                    if not invoice_meta or not census_meta:
                                        execution_log.append(f"Error: {label} requires an invoice (.pdf) and a census (.xlsx/.csv).")
                                    else:
                                        with open(invoice_meta[0], "rb") as inv_f, open(census_meta[0], "rb") as cen_f:
                                            client_files = {
                                                "invoice": (invoice_meta[1], inv_f, invoice_meta[2]),
                                                "census": (census_meta[1], cen_f, census_meta[2])
                                            }
                                            resp = await client.post(f"http://127.0.0.1:8000{endpoint}", files=client_files, data=data_payload, params=params_payload)
                                            resp.raise_for_status()
                                else:
                                    target_file_meta = current_temp_files[0]
                                    with open(target_file_meta[0], "rb") as f_out:
                                        client_files = {"file": (target_file_meta[1], f_out, target_file_meta[2])}
                                        resp = await client.post(f"http://127.0.0.1:8000{endpoint}", files=client_files, data=data_payload, params=params_payload)
                                        resp.raise_for_status()

                                if resp is not None:
                                    try:
                                        final_output_data = resp.json()
                                    except Exception:
                                        final_output_data = {"message": f"Successfully processed by {label}, but output was not JSON."}
                                    execution_log.append(f"{label} processing completed successfully.")

                                    # --- INJECT CUSTOM SCHEMA DEMO DATA ---
                                    if next_node.type in ["agentNode", "invoiceAgentNode", "payrollAgentNode"] and 'custom_schema' in locals() and custom_schema:
                                        try:
                                            output_json_rel = final_output_data.get("output_json", "")
                                            if output_json_rel:
                                                json_filename = os.path.basename(output_json_rel)
                                                gpu_outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Gpu_server", "Unified_PDF_Platform", "unified_outputs")
                                                target_json_path = os.path.join(gpu_outputs_dir, json_filename)

                                                if os.path.exists(target_json_path):
                                                    with open(target_json_path, "r") as jf:
                                                        existing_data = json.load(jf)

                                                    injected = False

                                                    def inject_into_dict(d):
                                                        nonlocal injected
                                                        for k, v in custom_schema.items():
                                                            if k not in d:
                                                                v_type = v.get("type", "string") if isinstance(v, dict) else v
                                                                if v_type == "string":
                                                                    d[k] = "Male" if k.lower() == "gender" else "Extracted Demo Data"
                                                                elif v_type == "number":
                                                                    d[k] = 100
                                                                elif v_type == "boolean":
                                                                    d[k] = True
                                                                else:
                                                                    d[k] = "Demo"
                                                                injected = True

                                                    if isinstance(existing_data, list):
                                                        for item in existing_data:
                                                            if isinstance(item, dict):
                                                                inject_into_dict(item)
                                                    elif isinstance(existing_data, dict):
                                                        inject_into_dict(existing_data)

                                                    if injected:
                                                        with open(target_json_path, "w") as jf:
                                                            json.dump(existing_data, jf, indent=4)
                                                        execution_log.append(f"Injected custom fields into generated JSON.")
                                        except Exception as json_err:
                                            execution_log.append(f"Failed to inject custom fields: {str(json_err)}")
                                    # --------------------------------------
                        except Exception as e:
                            execution_log.append(f"{label} processing failed: {str(e)}")
                else:
                    execution_log.append(f"Reached {label} Node ({next_node.id}). No backend mapping found. Skipping.")

            elif next_node.type == "outputNode":
                output_type = next_node.data.get("outputType", "local")
                save_option = next_node.data.get("saveOption", "Save Locally")
                save_path = next_node.data.get("savePath")

                # If no real data was processed, fallback to dummy
                simulated_data = final_output_data or {
                    "message": "No real data extracted. Ensure you connected a valid Agent node."
                }

                if output_type == "onedrive":
                    import sys
                    sys.path.append(os.path.join(os.path.dirname(__file__), "file-classification-old"))
                    try:
                        from onedrive_oauth import get_valid_token
                        token = get_valid_token(request)
                    except ImportError:
                        token = None

                    if not token:
                        execution_log.append("Error: OneDrive output selected but user is not authenticated.")
                    else:
                        folder_name = f"{last_agent_name} workflow_outputs"
                        execution_log.append(f"Uploading to OneDrive folder: {folder_name}")
                        headers = {"Authorization": f"Bearer {token}"}

                        try:
                            async with httpx.AsyncClient(timeout=120) as client:
                                check_res = await client.get("https://graph.microsoft.com/v1.0/me/drive/root/children", headers=headers)
                                target_folder_id = None
                                if check_res.status_code == 200:
                                    for item in check_res.json().get("value", []):
                                        if item.get("name") == folder_name and "folder" in item:
                                            target_folder_id = item.get("id")
                                            break
                                if not target_folder_id:
                                    create_res = await client.post(
                                        "https://graph.microsoft.com/v1.0/me/drive/root/children",
                                        headers=headers,
                                        json={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
                                    )
                                    if create_res.status_code in (200, 201):
                                        target_folder_id = create_res.json().get("id")
                                        execution_log.append(f"Created folder '{folder_name}' in OneDrive.")
                                    else:
                                        execution_log.append(f"Failed to create folder in OneDrive: {create_res.text}")

                                if target_folder_id:
                                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

                                    async def upload_url_to_onedrive(url, target_id, filename):
                                        try:
                                            r = await client.get(url)
                                            r.raise_for_status()
                                            up_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{target_id}:/{filename}:/content"
                                            up_res = await client.put(up_url, headers=headers, content=r.content)
                                            if up_res.status_code in (200, 201):
                                                execution_log.append(f"Successfully uploaded {filename} to OneDrive.")
                                            else:
                                                execution_log.append(f"Failed to upload {filename} to OneDrive: {up_res.text}")
                                        except Exception as e:
                                            execution_log.append(f"Error uploading {filename}: {e}")

                                    has_downloaded_json = False
                                    if "json" in simulated_data and isinstance(simulated_data["json"], str) and simulated_data["json"].startswith("http"):
                                        json_url = simulated_data["json"]
                                        from urllib.parse import unquote
                                        json_filename = unquote(json_url.split('/')[-1])
                                        await upload_url_to_onedrive(json_url, target_folder_id, json_filename)
                                        has_downloaded_json = True
                                        try:
                                            j_res = await client.get(json_url)
                                            final_output_data = j_res.json()
                                        except: pass

                                    if not has_downloaded_json:
                                        json_filename = f"workflow_result_{file_meta[1]}_{ts}.json" if file_meta else f"workflow_result_{ts}.json"
                                        up_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{target_folder_id}:/{json_filename}:/content"
                                        up_res = await client.put(up_url, headers=headers, content=json.dumps(simulated_data, indent=2))
                                        if up_res.status_code in (200, 201):
                                            execution_log.append(f"Successfully uploaded {json_filename} to OneDrive.")

                                    if "excel" in simulated_data and isinstance(simulated_data["excel"], str) and simulated_data["excel"].startswith("http"):
                                        excel_url = simulated_data["excel"]
                                        from urllib.parse import unquote
                                        excel_filename = unquote(excel_url.split('/')[-1])
                                        await upload_url_to_onedrive(excel_url, target_folder_id, excel_filename)
                        except Exception as e:
                            execution_log.append(f"OneDrive upload failed: {str(e)}")

                elif output_type == "local" or not output_type:
                    if not save_path:
                        # Two-way save method: fallback to local Downloads if no path is given
                        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
                        os.makedirs(download_dir, exist_ok=True)
                        # Create a dynamic filename using a timestamp to avoid overriding
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        save_path = os.path.join(download_dir, f'workflow_result_{file_meta[1]}_{ts}.json' if file_meta else f'workflow_result_{ts}.json')

                    try:
                        is_dir = os.path.isdir(save_path) or not save_path.lower().endswith('.json')

                        if is_dir:
                            target_dir = save_path
                            os.makedirs(target_dir, exist_ok=True)
                            json_save_path = None
                        else:
                            target_dir = os.path.dirname(save_path)
                            os.makedirs(target_dir, exist_ok=True)
                            json_save_path = save_path

                        # Helper to download files
                        async def download_file(url, target_folder, specific_filename=None):
                            filename = specific_filename or url.split('/')[-1]
                            from urllib.parse import unquote
                            filename = unquote(filename)
                            out_path = os.path.join(target_folder, filename)
                            try:
                                async with httpx.AsyncClient(timeout=120) as dl_client:
                                    r = await dl_client.get(url)
                                    r.raise_for_status()
                                    with open(out_path, 'wb') as out_f:
                                        out_f.write(r.content)
                                return out_path
                            except Exception as dl_err:
                                return f"Error downloading {filename}: {dl_err}"

                        # Download actual output JSON if present
                        has_downloaded_json = False
                        if "json" in simulated_data and isinstance(simulated_data["json"], str) and simulated_data["json"].startswith("http"):
                            specific_name = os.path.basename(json_save_path) if json_save_path else None
                            path = await download_file(simulated_data["json"], target_dir, specific_filename=specific_name)
                            execution_log.append(f"Downloaded final processed JSON to: {path}")
                            has_downloaded_json = True

                            # Update final_output_data so the frontend shows the actual processed data
                            try:
                                with open(path, 'r', encoding='utf-8') as f:
                                    final_output_data = json.load(f)
                            except Exception:
                                pass

                        # If we didn't download a JSON (e.g. not a GPU agent), just dump the raw simulated_data
                        if not has_downloaded_json:
                            final_path = json_save_path if json_save_path else os.path.join(target_dir, f'workflow_result_{file_meta[1]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json' if file_meta else f'workflow_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
                            with open(final_path, 'w', encoding='utf-8') as f:
                                json.dump(simulated_data, f, indent=2)
                            execution_log.append(f"Saved workflow output to: {final_path}")
                            
                            # Also save as CSV if extracted_records exists
                            if isinstance(simulated_data, dict) and "extracted_records" in simulated_data:
                                records = simulated_data["extracted_records"]
                                if records and isinstance(records, list) and len(records) > 0:
                                    csv_path = final_path.replace(".json", ".csv")
                                    try:
                                        import csv
                                        with open(csv_path, 'w', newline='', encoding='utf-8') as cf:
                                            # Use the keys of the first dictionary as fieldnames
                                            fieldnames = list(records[0].keys())
                                            writer = csv.DictWriter(cf, fieldnames=fieldnames)
                                            writer.writeheader()
                                            writer.writerows(records)
                                        execution_log.append(f"Saved workflow CSV output to: {csv_path}")
                                    except Exception as ce:
                                        execution_log.append(f"Failed to save CSV: {ce}")


                        # Also download the Excel file if present
                        if "excel" in simulated_data and isinstance(simulated_data["excel"], str) and simulated_data["excel"].startswith("http"):
                            path = await download_file(simulated_data["excel"], target_dir)
                            execution_log.append(f"Downloaded Excel output to: {path}")

                    except Exception as e:
                        execution_log.append(f"Reached Output Node ({next_node.id}). Failed to save output to {save_path}: {e}")

            current_node = next_node


        global_execution_log.extend(execution_log)
        batch_results.append(final_output_data or {"message": "No data"})

    # Cleanup temp files if we created them
    if not is_folder_input:
        for t_path, _, _ in temp_file_paths:
            if os.path.exists(t_path):
                try:
                    os.remove(t_path)
                except:
                    pass

    final_output_data = batch_results if len(batch_results) > 1 else (batch_results[0] if batch_results else {"message": "No data"})

    return {
        "status": "success",
        "message": "Workflow executed successfully.",
        "execution_log": global_execution_log,
        "simulated_output_data": final_output_data
    }

# =====================================================================
# Workflow Projects Persistence
# =====================================================================

class SaveProjectRequest(BaseModel):
    id: Optional[str] = None
    name: str
    nodes: list
    edges: list

@router.post("/projects/save")
def save_project(req: SaveProjectRequest, current_user: dict = Depends(get_current_user_from_token)):
    email = current_user.get("email")
    if not email:
        return {"status": "error", "message": "User email not found in token."}

    project_id = req.id if req.id else str(uuid.uuid4())
    nodes_str = json.dumps(req.nodes)
    edges_str = json.dumps(req.edges)

    success = save_workflow_project(project_id, req.name, nodes_str, edges_str, email)
    if success:
        return {"status": "success", "id": project_id, "message": "Workflow saved successfully."}
    else:
        return {"status": "error", "message": "Failed to save workflow."}

@router.get("/projects")
def list_projects(current_user: dict = Depends(get_current_user_from_token)):
    email = current_user.get("email")
    if not email:
        return []
    return list_workflow_projects(email)

@router.get("/projects/{project_id}")
def load_project(project_id: str, current_user: dict = Depends(get_current_user_from_token)):
    email = current_user.get("email")
    if not email:
        return {"status": "error", "message": "Unauthorized"}

    project = get_workflow_project(project_id, email)
    if project:
        # Parse JSON strings back to objects
        project["nodes"] = json.loads(project["nodes"])
        project["edges"] = json.loads(project["edges"])
        return {"status": "success", "project": project}
    else:
        return {"status": "error", "message": "Project not found"}

@router.delete("/projects/{project_id}")
def delete_project(project_id: str, current_user: dict = Depends(get_current_user_from_token)):
    email = current_user.get("email")
    if not email:
        return {"status": "error", "message": "Unauthorized"}

    success = delete_workflow_project(project_id, email)
    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Failed to delete project"}

