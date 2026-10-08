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

    _token_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(self, config: Optional[TenantSubmissionConfig] = None):
        self.config = config or TenantSubmissionConfig()

    def dispatch(
        self,
        payload: Dict[str, Any],
        pdf_file_paths: Optional[List[str]] = None,
        additional_file_paths: Optional[List[str]] = None,
        config_override: Optional[TenantSubmissionConfig] = None,
        **kwargs: Any,
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
        refreshed_for_401 = False

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
                        modifier_field = getattr(active_config.attachments, "modifier_file_field", "modifierPdf") or "modifierPdf"

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
                                elif any(k in pname for k in ["MODIFIER", "EXPERIENCE_MODIFIER", "XMOD", "X-MOD", "EXMOD"]):
                                    multipart_files.append(
                                        (modifier_field, (p.name, f, "application/pdf"))
                                    )
                                else:
                                    multipart_files.append(
                                        (loss_field, (p.name, f, "application/pdf"))
                                    )
                            else:
                                logger.warning(f"Attachment not found or invalid: {path_str}")

                    # Attach any additional files (e.g. generated Excel schemas / trackers)
                    if additional_file_paths and active_config.attachments.include_additional_files:
                        excel_field = getattr(active_config.attachments, "excel_file_field", "excelFile") or "excelFile"
                        for path_str in additional_file_paths:
                            p = Path(path_str)
                            if p.exists() and p.is_file():
                                f = open(p, "rb")
                                open_files.append(f)
                                pname = p.name.lower()
                                if pname.endswith((".xlsx", ".xls")):
                                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                elif pname.endswith(".csv"):
                                    content_type = "text/csv"
                                else:
                                    content_type = "application/octet-stream"
                                multipart_files.append(
                                    (excel_field, (p.name, f, content_type))
                                )
                            else:
                                logger.warning(f"Additional attachment not found or invalid: {path_str}")

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
                    elif response.status_code == 401 and active_config.auth.type == "dynamic_token" and not refreshed_for_401:
                        logger.warning(
                            f"Received HTTP 401 Unauthorized for {target_url}. Invalidate cached token and retry with fresh token."
                        )
                        refreshed_for_401 = True
                        headers = self._build_headers(active_config, force_refresh_token=True)
                        continue
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

    @staticmethod
    def _get_nested_val(data: Any, path: str) -> Any:
        """Extracts nested value using dotted path notation, e.g. 'data.accessToken'."""
        if not path:
            return data
        cur = data
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    def _get_dynamic_token(self, config: TenantSubmissionConfig, force_refresh: bool = False) -> Optional[str]:
        """
        Retrieves a dynamic authentication token for the tenant.
        Caches the token in memory until expiration (with a 60s safety buffer).
        Reuses the existing token if still valid.
        """
        auth_cfg = config.auth
        cache_key = f"{config.tenant_code}_{auth_cfg.token_url}"

        # 1. Check in-memory cache
        if not force_refresh and cache_key in self._token_cache:
            cached_entry = self._token_cache[cache_key]
            expires_at = cached_entry.get("expires_at", 0)
            remaining_seconds = expires_at - time.time()
            if remaining_seconds > 60:
                logger.debug(
                    "[DynamicAuth] Reusing cached token for tenant '%s' (valid for %.0fs remaining)",
                    config.tenant_code, remaining_seconds
                )
                return cached_entry.get("token")

        # 2. Acquire fresh token from token endpoint
        token_url = self._resolve_env_placeholders(auth_cfg.token_url or "")
        if not token_url:
            logger.error("[DynamicAuth] Token URL is empty or unresolvable for tenant '%s'", config.tenant_code)
            return None

        client_id = os.getenv(auth_cfg.client_id_env_var or "", "") if auth_cfg.client_id_env_var else ""
        client_secret = os.getenv(auth_cfg.client_secret_env_var or "", "") if auth_cfg.client_secret_env_var else ""

        if not client_id or not client_secret:
            logger.error(
                "[DynamicAuth] Missing credentials for tenant '%s': client_id_env_var='%s', client_secret_env_var='%s'",
                config.tenant_code, auth_cfg.client_id_env_var, auth_cfg.client_secret_env_var
            )
            return None

        payload = {
            "clientId": client_id,
            "clientSecret": client_secret
        }

        try:
            logger.info("[DynamicAuth] Requesting fresh token from %s for tenant '%s'...", token_url, config.tenant_code)
            resp = requests.post(
                token_url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "*/*"},
                timeout=auth_cfg.custom_headers.get("timeout", 15) if isinstance(auth_cfg.custom_headers, dict) else 15
            )

            if resp.status_code == 200:
                resp_json = resp.json()
                token = self._get_nested_val(resp_json, auth_cfg.token_path or "data.accessToken")
                expires_in_raw = self._get_nested_val(resp_json, auth_cfg.expires_in_path or "data.expiresIn")
                try:
                    expires_in = float(expires_in_raw) if expires_in_raw is not None else 900.0
                except (ValueError, TypeError):
                    expires_in = 900.0

                if token:
                    self._token_cache[cache_key] = {
                        "token": token,
                        "expires_at": time.time() + expires_in
                    }
                    logger.info(
                        "[DynamicAuth] Successfully acquired token for tenant '%s' (expires in %.0fs)",
                        config.tenant_code, expires_in
                    )
                    return token
                else:
                    logger.error("[DynamicAuth] Token path '%s' not found in response: %s", auth_cfg.token_path, resp_json)
            else:
                logger.error("[DynamicAuth] Token request failed with HTTP %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("[DynamicAuth] Exception while acquiring token from %s: %s", token_url, exc)

        return None

    def _build_headers(self, config: TenantSubmissionConfig, force_refresh_token: bool = False) -> Dict[str, str]:
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

        elif auth_cfg.type == "dynamic_token":
            token = self._get_dynamic_token(config, force_refresh=force_refresh_token)
            if token:
                prefix = auth_cfg.token_type or "Bearer"
                headers["Authorization"] = f"{prefix} {token}"

        return headers

    def _build_auth(self, config: TenantSubmissionConfig) -> Optional[HTTPBasicAuth]:
        auth_cfg = config.auth
        if auth_cfg.type == "basic" and auth_cfg.username_env_var and auth_cfg.password_env_var:
            u = os.getenv(auth_cfg.username_env_var, "")
            p = os.getenv(auth_cfg.password_env_var, "")
            return HTTPBasicAuth(u, p)
        return None
