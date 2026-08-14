import os
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse

from security.security_service import SecurityGatewayService, STORAGE_DIR, CLEAN_DIR, QUARANTINE_DIR, INCOMING_DIR

router = APIRouter(prefix="/api/security", tags=["Security Gateway"])
security_gateway = SecurityGatewayService()

@router.get("/status")
async def get_security_status():
    """Returns Security Gateway operational health, ClamAV service status, and storage metrics."""
    clamd_live = security_gateway.scanner.is_clamd_available()
    
    clean_count = len(os.listdir(CLEAN_DIR)) if os.path.exists(CLEAN_DIR) else 0
    quarantine_count = len(os.listdir(QUARANTINE_DIR)) if os.path.exists(QUARANTINE_DIR) else 0
    incoming_count = len(os.listdir(INCOMING_DIR)) if os.path.exists(INCOMING_DIR) else 0

    return {
        "status": "online",
        "clamav_daemon_connected": clamd_live,
        "mode": "production" if clamd_live else "development_fallback",
        "storage_metrics": {
            "clean_files": clean_count,
            "quarantined_files": quarantine_count,
            "held_files": incoming_count
        }
    }

@router.post("/scan")
async def scan_file_endpoint(
    file: UploadFile = File(...),
    tenant_id: Optional[str] = Form("default_tenant"),
    module_name: Optional[str] = Form("general_upload")
):
    """
    Primary Security Gateway Endpoint.
    Validates file format, checks size, calculates SHA-256, and scans for malware via ClamAV.
    """
    try:
        content = await file.read()
        res = security_gateway.process_incoming_file(
            file_content=content,
            filename=file.filename or "upload.tmp",
            tenant_id=tenant_id,
            module_name=module_name
        )

        if res["is_allowed"]:
            return JSONResponse(status_code=status.HTTP_200_OK, content=res)
        elif res["scan_status"] == "INFECTED":
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=res)
        elif res["scan_status"] == "INVALID":
            return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=res)
        else: # ERROR
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=res)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Security Gateway error during file scan: {str(e)}"
        )
