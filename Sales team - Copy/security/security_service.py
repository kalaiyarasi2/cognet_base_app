import os
import shutil
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

from security.file_validator import FileValidator
from security.malware_scanner import ClamAVScanner, ScanStatus

logger = logging.getLogger("cognet.security.gateway")

# Default base directory for Security Gateway safe storage
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
INCOMING_DIR = os.path.join(STORAGE_DIR, "incoming")
CLEAN_DIR = os.path.join(STORAGE_DIR, "clean")
QUARANTINE_DIR = os.path.join(STORAGE_DIR, "quarantine")

class SecurityGatewayService:
    """
    Centralized CogNet Security Gateway Service.
    Orchestrates File Validation -> Malware Scanning -> Safe Storage Routing & Audit Logging.
    """

    def __init__(self, storage_base_dir: Optional[str] = None):
        self.base_storage = storage_base_dir or STORAGE_DIR
        self.incoming_dir = os.path.join(self.base_storage, "incoming")
        self.clean_dir = os.path.join(self.base_storage, "clean")
        self.quarantine_dir = os.path.join(self.base_storage, "quarantine")

        self._ensure_directories()
        self.validator = FileValidator()
        self.scanner = ClamAVScanner()

    def _ensure_directories(self):
        """Create storage directories if they do not exist."""
        for d in [self.incoming_dir, self.clean_dir, self.quarantine_dir]:
            os.makedirs(d, exist_ok=True)

    def process_incoming_file(
        self,
        file_content: bytes,
        filename: str,
        tenant_id: str = "default_tenant",
        module_name: str = "general_upload"
    ) -> Dict[str, Any]:
        """
        Process a newly received file through the Security Gateway pipeline.
        
        Returns a comprehensive Security Result Dictionary:
        {
            "is_allowed": bool,
            "scan_status": "CLEAN" | "INFECTED" | "ERROR" | "INVALID",
            "message": str,
            "tenant_id": str,
            "module_name": str,
            "clean_file_path": Optional[str],
            "quarantine_file_path": Optional[str],
            "metadata": dict,
            "timestamp": str
        }
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # 1. Structural Validation & Hashing
        is_valid, val_msg, metadata = self.validator.validate_file(filename, file_content)
        
        if not is_valid:
            logger.warning(f"[SECURITY GATEWAY] Validation failed for '{filename}' ({tenant_id}/{module_name}): {val_msg}")
            return {
                "is_allowed": False,
                "scan_status": "INVALID",
                "message": val_msg,
                "tenant_id": tenant_id,
                "module_name": module_name,
                "clean_file_path": None,
                "quarantine_file_path": None,
                "metadata": metadata,
                "timestamp": timestamp
            }

        sha256 = metadata["sha256"]
        safe_filename = f"{sha256[:12]}_{os.path.basename(filename)}"

        # 2. ClamAV Malware Scanning
        scan_status, scan_msg = self.scanner.scan_bytes(file_content, filename)
        metadata["scan_message"] = scan_msg

        # 3. Decision & Storage Routing
        if scan_status == ScanStatus.CLEAN:
            clean_path = os.path.join(self.clean_dir, safe_filename)
            with open(clean_path, "wb") as f:
                f.write(file_content)

            logger.info(f"[SECURITY GATEWAY - CLEAN] File '{filename}' passed scan (SHA256: {sha256[:8]}). Saved to clean storage.")
            return {
                "is_allowed": True,
                "scan_status": ScanStatus.CLEAN.value,
                "message": "File verified clean and passed Security Gateway.",
                "tenant_id": tenant_id,
                "module_name": module_name,
                "clean_file_path": clean_path,
                "quarantine_file_path": None,
                "metadata": metadata,
                "timestamp": timestamp
            }

        elif scan_status == ScanStatus.INFECTED:
            quarantine_path = os.path.join(self.quarantine_dir, safe_filename)
            with open(quarantine_path, "wb") as f:
                f.write(file_content)

            logger.error(f"[SECURITY GATEWAY - INFECTED ALERT] File '{filename}' is INFECTED. Quarantined to {quarantine_path}.")
            return {
                "is_allowed": False,
                "scan_status": ScanStatus.INFECTED.value,
                "message": f"SECURITY BLOCK: File infected. {scan_msg}",
                "tenant_id": tenant_id,
                "module_name": module_name,
                "clean_file_path": None,
                "quarantine_file_path": quarantine_path,
                "metadata": metadata,
                "timestamp": timestamp
            }

        else: # ScanStatus.ERROR (Fail closed)
            incoming_path = os.path.join(self.incoming_dir, safe_filename)
            with open(incoming_path, "wb") as f:
                f.write(file_content)

            logger.error(f"[SECURITY GATEWAY - SCAN ERROR] File '{filename}' scan encountered error. Held in incoming for review.")
            return {
                "is_allowed": False,
                "scan_status": ScanStatus.ERROR.value,
                "message": f"SECURITY HOLD: Scanner error (fail-closed). {scan_msg}",
                "tenant_id": tenant_id,
                "module_name": module_name,
                "clean_file_path": None,
                "quarantine_file_path": None,
                "metadata": metadata,
                "timestamp": timestamp
            }
