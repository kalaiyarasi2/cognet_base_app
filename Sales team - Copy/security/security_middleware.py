import logging
from typing import Callable
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import UploadFile

from security.security_service import SecurityGatewayService

logger = logging.getLogger("cognet.security.middleware")

# Endpoints or paths to skip (e.g., auth, static files, docs)
EXEMPT_PATHS = {
    "/docs", "/redoc", "/openapi.json", "/health", "/config",
    "/api/auth/login", "/api/auth/register", "/api/universal-logs"
}

class SecurityGatewayMiddleware(BaseHTTPMiddleware):
    """
    Global Security Gateway Middleware for CogNet.
    Automatically intercepts file uploads across ALL POC sub-apps & endpoints,
    performing File Validation and ClamAV Malware Scanning BEFORE downstream processing.
    """

    def __init__(self, app, storage_base_dir=None):
        super().__init__(app)
        self.gateway = SecurityGatewayService(storage_base_dir=storage_base_dir)

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        # 1. Skip non-upload requests or exempt endpoints
        if request.method not in ("POST", "PUT") or any(path.startswith(p) for p in EXEMPT_PATHS):
            return await call_next(request)

        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("multipart/form-data"):
            return await call_next(request)

        # 2. Intercept multipart file uploads
        try:
            # Buffer the body so we can read the form and then pass the body to downstream apps
            body_bytes = await request.body()
            
            async def receive_for_mw():
                if not getattr(receive_for_mw, "done", False):
                    receive_for_mw.done = True
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                return {"type": "http.request", "body": b"", "more_body": False}
                
            request._receive = receive_for_mw
            
            form = await request.form()
            upload_files = []

            for field_name, value in form.multi_items():
                if hasattr(value, "filename") and value.filename:
                    upload_files.append(value)

            if not upload_files:
                # Reset receive for downstream even if no files
                async def receive_downstream_empty():
                    if not getattr(receive_downstream_empty, "done", False):
                        receive_downstream_empty.done = True
                        return {"type": "http.request", "body": body_bytes, "more_body": False}
                    return {"type": "http.request", "body": b"", "more_body": False}
                request.scope["receive"] = receive_downstream_empty
                return await call_next(request)

            # 3. Process each uploaded file through the Security Gateway
            for upload_file in upload_files:
                filename = upload_file.filename or "upload.tmp"
                content = await upload_file.read()
                
                # Determine module name from URL path
                module_name = path.strip("/").replace("/", "_") or "general_upload"

                # Extract tenant/user from headers or query if available
                tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("user_email") or "default_tenant"

                # Run Gateway Pipeline: Validate -> ClamAV Scan -> Storage Routing
                res = self.gateway.process_incoming_file(
                    file_content=content,
                    filename=filename,
                    tenant_id=tenant_id,
                    module_name=module_name
                )

                # 4. If Security Check Fails -> HALT REQUEST IMMEDIATELY
                if not res["is_allowed"]:
                    logger.error(
                        f"[SECURITY BLOCK] Request to '{path}' blocked by Gateway. "
                        f"Status: {res['scan_status']} | File: {filename} | Msg: {res['message']}"
                    )
                    
                    if res["scan_status"] == "INFECTED":
                        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=res)
                    elif res["scan_status"] == "INVALID":
                        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=res)
                    else: # ERROR / TIMEOUT
                        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=res)

            # 5. File is verified CLEAN -> Proceed to target POC extractor/processor
            # Reset the receive channel so downstream mounted apps can parse the form again
            async def receive_downstream():
                if not getattr(receive_downstream, "done", False):
                    receive_downstream.done = True
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                return {"type": "http.request", "body": b"", "more_body": False}
                
            request.scope["receive"] = receive_downstream
            return await call_next(request)

        except Exception as e:
            logger.error(f"[SECURITY MIDDLEWARE ERROR] Error inspecting request for '{path}': {e}")
            return await call_next(request)

