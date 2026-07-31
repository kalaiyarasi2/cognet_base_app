from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from SharePoint_Agent.sharepoint_agent_module import sharepoint_agent
import requests

router = APIRouter(prefix="/api/sharepoint", tags=["SharePoint Automation"])

class StartSharePointAutomationRequest(BaseModel):
    input_folder: str = "Clients/Active/PEO Velocity/Sales Support (PEO Velocity)/Invoice To Census Automation"
    output_folder: str = "Clients/Active/PEO Velocity/Sales Support (PEO Velocity)/Invoice To Census Automation/Processed_Outputs"
    poc_engine: str = "converter" # converter, parity-setup, renewal-process, resourcing-edge, rpve, drive-gpu
    processed_by: Optional[str] = "SYSTEM"

@router.get("/status")
async def get_sharepoint_status():
    """Get current status of SharePoint Automation worker."""
    return {
        "status": "ok",
        "agent": sharepoint_agent.get_status()
    }

@router.post("/start")
async def start_sharepoint_automation(req: StartSharePointAutomationRequest):
    """
    Start SharePoint folder automation worker.

    NOTE: A valid Microsoft Graph delegated token must be available in the agent
    (injected automatically during SSO login via /api/auth/sso/callback).
    The delegated token grants access to private SharePoint group sites.
    """
    if not req.input_folder.strip():
        raise HTTPException(status_code=400, detail="Input folder path is required.")

    if not sharepoint_agent.delegated_token:
        import logging
        logging.getLogger("SharePointAgent").warning(
            "No delegated token available — SharePoint access may fail for private group sites. "
            "Sign out and sign back in with Microsoft to authorize."
        )

    sharepoint_agent.start_automation(
        input_folder=req.input_folder,
        output_folder=req.output_folder or "Processed_Outputs",
        poc_engine=req.poc_engine or "converter",
        processed_by=req.processed_by or "SYSTEM"
    )

    return {
        "status": "ok",
        "message": f"SharePoint Automation started for folder '{req.input_folder}'.",
        "agent": sharepoint_agent.get_status()
    }

@router.post("/stop")
async def stop_sharepoint_automation():
    """Stop SharePoint folder automation worker."""
    sharepoint_agent.stop_automation()
    return {
        "status": "ok",
        "message": "SharePoint Automation worker stopped.",
        "agent": sharepoint_agent.get_status()
    }

@router.get("/logs")
async def get_sharepoint_logs():
    """Get real-time log stream."""
    return {
        "status": "ok",
        "logs": sharepoint_agent.logs[-50:]
    }

@router.get("/browse-folders")
async def browse_sharepoint_folders(path: str = "", folder_id: Optional[str] = None):
    """Browse subfolders in SharePoint for the visual folder picker modal."""
    clean_path = path.strip().strip("/")
    sharepoint_agent._ensure_valid_token()

    # Force drive re-resolution so the Lists API fallback can run if the
    # cached drive_id was previously returning 0 items (wrong drive selected).
    if not sharepoint_agent.drive_id or not clean_path:
        sharepoint_agent.site_id = None
        sharepoint_agent.drive_id = None
        sharepoint_agent.get_site_and_drive_id()

    subfolders = sharepoint_agent.list_subfolders(clean_path, folder_id=folder_id)
    breadcrumbs = sharepoint_agent.get_path_breadcrumbs(clean_path, folder_id=folder_id)
    result = []
    for sf in subfolders:
        name = sf.get("name")
        if not name:
            continue
        full_path = f"{clean_path}/{name}" if clean_path else name
        result.append({
            "name": name,
            "path": full_path,
            "id": sf.get("id"),
            "childCount": sf.get("folder", {}).get("childCount", 0)
        })
    return {"status": "ok", "current_path": clean_path, "folders": result, "breadcrumbs": breadcrumbs}



@router.get("/debug-drives")
async def debug_sharepoint_drives():
    """
    Diagnostic endpoint — lists ALL drives on the SharePoint site with their
    root-level folders. Use this to find which drive contains Clients/ folder.
    Open in browser: http://localhost:8000/api/sharepoint/debug-drives
    """
    sharepoint_agent._ensure_valid_token()
    if not sharepoint_agent.token:
        raise HTTPException(status_code=401, detail="No valid token. Please sign in with Microsoft.")

    headers = {"Authorization": f"Bearer {sharepoint_agent.token}"}

    # Ensure site_id is resolved
    if not sharepoint_agent.site_id:
        sharepoint_agent.get_site_and_drive_id()

    site_id = sharepoint_agent.site_id or "root"
    drives_info = []

    # Fetch all drives on the site
    drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    try:
        res = requests.get(drives_url, headers=headers, timeout=15)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=f"Failed to list drives: {res.text[:300]}")
        drives = res.json().get("value", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    currently_selected_drive = sharepoint_agent.drive_id

    for d in drives:
        drive_id = d.get("id")
        drive_name = d.get("name", "")
        drive_type = d.get("driveType", "")
        is_current = (drive_id == currently_selected_drive)

        # Peek at root children to see what folders are inside each drive
        root_folders = []
        try:
            rc = requests.get(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children",
                headers=headers,
                timeout=10
            )
            if rc.status_code == 200:
                for item in rc.json().get("value", []):
                    root_folders.append({
                        "name": item.get("name"),
                        "type": "folder" if "folder" in item else "file",
                        "id": item.get("id"),
                        "childCount": item.get("folder", {}).get("childCount", 0)
                    })
        except Exception:
            pass

        drives_info.append({
            "id": drive_id,
            "name": drive_name,
            "type": drive_type,
            "is_currently_selected": is_current,
            "root_item_count": len(root_folders),
            "root_folders": root_folders,
            "has_clients_folder": any(f["name"] == "Clients" for f in root_folders)
        })

    # Recommend drive that has 'Clients' folder, else the one with most items
    recommended = next((d for d in drives_info if d["has_clients_folder"]), None)
    if not recommended:
        recommended = max(drives_info, key=lambda d: d["root_item_count"], default=None)

    return {
        "status": "ok",
        "site_id": site_id,
        "currently_selected_drive_id": currently_selected_drive,
        "total_drives": len(drives_info),
        "drives": drives_info,
        "recommended_drive_id": recommended["id"] if recommended else None,
        "recommended_drive_name": recommended["name"] if recommended else None,
        "fix_needed": (recommended["id"] != currently_selected_drive) if recommended else False
    }


@router.post("/set-drive")
async def set_sharepoint_drive(body: dict):
    """
    Manually override the active SharePoint drive ID.
    Use after /debug-drives identifies the correct drive.
    Body: { "drive_id": "<id>" }
    """
    drive_id = body.get("drive_id", "").strip()
    if not drive_id:
        raise HTTPException(status_code=400, detail="drive_id is required.")

    sharepoint_agent.drive_id = drive_id
    # Clear cached site/drive so they re-validate with the new drive
    sharepoint_agent.site_id = None
    sharepoint_agent.get_site_and_drive_id()

    return {
        "status": "ok",
        "message": f"Active SharePoint drive switched to: {drive_id}",
        "drive_id": drive_id
    }
