from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when path traversal or unauthorized directory access is detected."""
    pass


class TenantStorageService:
    """
    Handles tenant-specific storage routing and enforces path security.
    All files are stored under: output/{tenant_code}/{module_code}/{job_id}/
    """

    def __init__(self, workspace_dir: Path, tenant_code: str = "CLIENT_A"):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.tenant_code = tenant_code
        self.base_output_dir = (self.workspace_dir / "output" / self.tenant_code).resolve()
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def get_job_output_dir(self, module_code: str, job_id: str) -> Path:
        """
        Calculates and validates the target directory for a job.
        Enforces path traversal checks.
        """
        clean_module = str(module_code).strip().upper()
        clean_job_id = str(job_id).strip()

        # Security check against path traversal
        if ".." in clean_module or "/" in clean_module or "\\" in clean_module:
            raise SecurityError(f"Invalid module_code detected: {clean_module}")
        if ".." in clean_job_id or "/" in clean_job_id or "\\" in clean_job_id:
            raise SecurityError(f"Invalid job_id detected: {clean_job_id}")

        target_dir = (self.base_output_dir / clean_module / clean_job_id).resolve()

        # Enforce that target_dir stays strictly under base_output_dir
        try:
            target_dir.relative_to(self.base_output_dir)
        except ValueError:
            raise SecurityError(f"Path traversal detected for job path: {target_dir}")

        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def save_json_output(self, module_code: str, job_id: str, filename: str, data: Dict[str, Any]) -> Path:
        out_dir = self.get_job_output_dir(module_code, job_id)
        target_path = (out_dir / filename).resolve()
        
        # Verify target file path security
        try:
            target_path.relative_to(out_dir)
        except ValueError:
            raise SecurityError(f"Path traversal attempt in filename: {filename}")

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Saved JSON output to: {target_path}")
        return target_path

    def save_raw_output(self, module_code: str, job_id: str, filename: str, content: Union[str, bytes]) -> Path:
        out_dir = self.get_job_output_dir(module_code, job_id)
        target_path = (out_dir / filename).resolve()

        try:
            target_path.relative_to(out_dir)
        except ValueError:
            raise SecurityError(f"Path traversal attempt in filename: {filename}")

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        with open(target_path, mode, encoding=encoding) as f:
            f.write(content)

        logger.info(f"Saved raw output to: {target_path}")
        return target_path
