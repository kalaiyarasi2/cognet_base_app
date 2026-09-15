import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from requests.auth import HTTPBasicAuth
from core.tenant.models import TenantSubmissionConfig

logger = logging.getLogger(__name__)


@dataclass
class SubmissionResult:
    success: bool
    status_code: Optional[int] = None
    response_data: Optional[Any] = None
    error_message: Optional[str] = None
    attempt_count: int = 1
    execution_time_seconds: float = 0.0
    extra_info: Dict[str, Any] = field(default_factory=dict)


class DynamicHttpAdapter:
    """
    Resilient HTTP Dispatch Adapter driven by TenantSubmissionConfig.
    Handles dynamic secret resolution, multipart bundling (JSON + PDFs),
    retries, and structured error responses.
    """

    def __init__(self, config: Optional[TenantSubmissionConfig] = None):
        self.config = config or TenantSubmissionConfig()

    def dispatch(
        self,
        payload: Dict[str, Any],
        pdf_file_paths: Optional[List[str]] = None,
        config_override: Optional[TenantSubmissionConfig] = None,
    ) -> SubmissionResult:
        """
        Dispatches payload and attachments to the configured tenant endpoint.
        """
        active_config = config_override or self.config

        if not active_config.enabled:
            return SubmissionResult(
                success=False,
                error_message="Tenant submission is disabled in configuration.",
            )

        target_url = self._resolve_env_placeholders(active_config.target_url)
        if not target_url:
            return SubmissionResult(
                success=False,
                error_message="Target URL is empty or unresolvable.",
            )

        headers = self._build_headers(active_config)
        auth = self._build_auth(active_config)
        retry_policy = active_config.retry_policy

        start_time = time.time()
        last_error = None
        attempt = 0

        while attempt < max(1, retry_policy.max_retries):
            attempt += 1
            try:
                # Open PDF attachments safely
                open_files = []
                multipart_files = []
                try:
                    # Always package the transformed JSON payload as a JSON file attachment
                    json_bytes = json.dumps(payload, indent=2).encode("utf-8")
                    file_field = active_config.attachments.multipart_file_field or "file"
                    multipart_files.append(
                        (file_field, ("submission.json", json_bytes, "application/json"))
                    )

                    if active_config.attachments.include_original_pdfs and pdf_file_paths:
                        acord_field = getattr(active_config.attachments, "acord_file_field", "acordPdf") or "acordPdf"
                        loss_field = getattr(active_config.attachments, "loss_runs_file_field", "lossRunsPdf") or "lossRunsPdf"

                        for path_str in pdf_file_paths:
                            p = Path(path_str)
                            if p.exists() and p.is_file():
                                f = open(p, "rb")
                                open_files.append(f)
                                pname = p.name.upper()
                                if any(k in pname for k in ["ACORD", "COMPENSATION", "WORK_COMP", "WC "]):
                                    multipart_files.append(
                                        (acord_field, (p.name, f, "application/pdf"))
                                    )
                                else:
                                    multipart_files.append(
                                        (loss_field, (p.name, f, "application/pdf"))
                                    )
                            else:
                                logger.warning(f"Attachment not found or invalid: {path_str}")

                    # Dispatch Multipart Form Data with JSON payload file and optional attachments
                    response = requests.request(
                        method=active_config.http_method,
                        url=target_url,
                        headers=headers,
                        auth=auth,
                        files=multipart_files,
                        timeout=retry_policy.timeout_seconds,
                    )

                    elapsed = time.time() - start_time

                    # Try parsing response body as JSON
                    try:
                        resp_body = response.json()
                    except Exception:
                        resp_body = response.text

                    if 200 <= response.status_code < 300:
                        logger.info(
                            f"Submission succeeded for {target_url} (HTTP {response.status_code}) on attempt {attempt}"
                        )
                        return SubmissionResult(
                            success=True,
                            status_code=response.status_code,
                            response_data=resp_body,
                            attempt_count=attempt,
                            execution_time_seconds=elapsed,
                        )
                    else:
                        last_error = f"HTTP {response.status_code}: {resp_body}"
                        logger.warning(
                            f"Submission attempt {attempt} failed with HTTP {response.status_code}: {resp_body}"
                        )

                finally:
                    for f in open_files:
                        try:
                            f.close()
                        except Exception:
                            pass

            except requests.exceptions.RequestException as req_err:
                last_error = str(req_err)
                logger.warning(f"Submission attempt {attempt} encountered network error: {req_err}")

            if attempt < retry_policy.max_retries:
                sleep_time = retry_policy.backoff_factor * attempt
                time.sleep(sleep_time)

        elapsed = time.time() - start_time
        return SubmissionResult(
            success=False,
            error_message=f"All {attempt} attempts failed. Last error: {last_error}",
            attempt_count=attempt,
            execution_time_seconds=elapsed,
        )

    def _resolve_env_placeholders(self, text: str) -> str:
        """Resolves ${VAR_NAME} environment variable placeholders."""
        if not text:
            return ""

        def replace_match(match):
            var_name = match.group(1)
            return os.getenv(var_name, "")

        return re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_match, text)

    def _build_headers(self, config: TenantSubmissionConfig) -> Dict[str, str]:
        headers = dict(config.auth.custom_headers)
        auth_cfg = config.auth

        if auth_cfg.type == "api_key" and auth_cfg.header_name and auth_cfg.secret_env_var:
            secret = os.getenv(auth_cfg.secret_env_var, "")
            if secret:
                headers[auth_cfg.header_name] = secret

        elif auth_cfg.type == "bearer" and auth_cfg.secret_env_var:
            token = os.getenv(auth_cfg.secret_env_var, "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        return headers

    def _build_auth(self, config: TenantSubmissionConfig) -> Optional[HTTPBasicAuth]:
        auth_cfg = config.auth
        if auth_cfg.type == "basic" and auth_cfg.username_env_var and auth_cfg.password_env_var:
            u = os.getenv(auth_cfg.username_env_var, "")
            p = os.getenv(auth_cfg.password_env_var, "")
            return HTTPBasicAuth(u, p)
        return None
