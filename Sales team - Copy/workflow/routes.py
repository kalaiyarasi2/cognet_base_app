import os
import json
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, Request, Depends, HTTPException
from fastapi.responses import FileResponse

from auth_routes import get_current_user_from_token
from database.poc_db import (
    save_workflow_project,
    get_workflow_project,
    list_workflow_projects,
    delete_workflow_project
)
from workflow.models import Node, Edge, SaveProjectRequest
from workflow.engine import execute_workflow, WORKFLOW_LOGS_DIR, WORKFLOW_OUTPUTS_DIR, logger

router = APIRouter(prefix="/api/workflow", tags=["Workflow Engine (Co-Pilot)"])

@router.post("/run-workflow")
async def run_workflow(
    request: Request,
    nodes: str = Form(...),
    edges: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """Executes a designer workflow topology with live logging and artifact capture."""
    try:
        nodes_list = [Node(**n) for n in json.loads(nodes)]
        edges_list = [Edge(**e) for e in json.loads(edges)]
    except Exception as e:
        logger.error(f"Failed to parse workflow topology: {e}")
        return {"status": "error", "message": f"Failed to parse workflow topology: {e}"}

    result = await execute_workflow(request, nodes_list, edges_list, files)
    return result

# ── Project Persistence Endpoints ─────────────────────────────────────────────

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

# ── Workflow Logs and Outputs Inspection ──────────────────────────────────────

@router.get("/logs")
def get_workflow_logs(lines: int = 100):
    """Retrieves the most recent log lines from workflow/logs/workflow.log."""
    log_file = WORKFLOW_LOGS_DIR / "workflow.log"
    if not log_file.exists():
        return {"status": "ok", "logs": []}
    
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            return {"status": "ok", "logs": all_lines[-lines:]}
    except Exception as e:
        return {"status": "error", "message": str(e), "logs": []}

@router.get("/outputs")
def list_workflow_outputs():
    """Lists files saved in the dedicated workflow/outputs directory."""
    files = []
    if WORKFLOW_OUTPUTS_DIR.exists():
        for p in WORKFLOW_OUTPUTS_DIR.glob("*"):
            if p.is_file():
                files.append({
                    "name": p.name,
                    "size_bytes": p.stat().st_size,
                    "modified": p.stat().st_mtime
                })
    return {"status": "ok", "files": sorted(files, key=lambda x: x["modified"], reverse=True)}

@router.get("/outputs/{filename}")
def download_workflow_output(filename: str):
    """Directly serves a file from workflow/outputs/."""
    file_path = WORKFLOW_OUTPUTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(path=str(file_path), filename=filename)
