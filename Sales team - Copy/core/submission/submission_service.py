import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.tenant.loaders import TenantConfigLoader
from core.submission.payload_transformer import PayloadTransformer
from core.submission.http_adapter import DynamicHttpAdapter, SubmissionResult

logger = logging.getLogger(__name__)


class SubmissionService:
    """
    High-level orchestrator for multi-tenant automated submissions.
    Dynamically routes, transforms, and dispatches data per tenant configuration.
    """

    def __init__(self, workspace_dir: Optional[Path] = None):
        if workspace_dir is None:
            workspace_dir = Path(__file__).resolve().parent.parent.parent
        self.workspace_dir = Path(workspace_dir).resolve()
        self.loader = TenantConfigLoader(self.workspace_dir)
        self.transformer = PayloadTransformer()
        self.adapter = DynamicHttpAdapter()

    def process_and_submit(
        self,
        tenant_folder: str,
        extracted_payloads: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        pdf_file_paths: Optional[List[str]] = None,
        additional_file_paths: Optional[List[str]] = None,
        email_address: str = "",
        modifier: Optional[float] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end transformation and submission for a given tenant.
        """
        config = self.loader.load_submission_config(tenant_folder)

        if not config.enabled:
            logger.info(f"Submission for tenant '{tenant_folder}' is disabled. Skipping dispatch.")
            return {
                "status": "SKIPPED",
                "reason": "Tenant submission is not enabled.",
                "tenant_folder": tenant_folder,
            }

        # 1. Transform Payload
        transformed_payload = self.transformer.transform(
            extracted_payloads=extracted_payloads,
            email_address=email_address,
            modifier=modifier,
            extra_metadata=extra_metadata,
            config_override=config,
        )

        # 1b. Dynamically store copy for local verification
        saved_copy_path = None
        try:
            import json
            import time
            from datetime import datetime
            
            # Destination directory per tenant
            tenant_sub_dir = self.workspace_dir / "output" / tenant_folder / "submissions"
            tenant_sub_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            sanitized_email = "".join(c if c.isalnum() or c in "._-" else "_" for c in email_address) if email_address else "payload"
            out_file = tenant_sub_dir / f"submission_{timestamp_str}_{sanitized_email}.json"
            out_file.write_text(json.dumps(transformed_payload, indent=2), encoding="utf-8")
            
            # Also keep a pointer to latest_submission.json for easy verification
            latest_file = tenant_sub_dir / "latest_submission.json"
            latest_file.write_text(json.dumps(transformed_payload, indent=2), encoding="utf-8")
            
            saved_copy_path = str(out_file)
            logger.info(f"Dynamically saved verification copy of merged JSON for tenant '{tenant_folder}' -> {out_file}")
        except Exception as save_err:
            logger.warning(f"Could not save local verification copy for tenant '{tenant_folder}': {save_err}")

        # 2. Dispatch via HTTP Adapter or SharePoint Native Adapter
        if getattr(config, "delivery_method", "http") == "sharepoint_direct":
            from core.submission.sharepoint_adapter import SharePointDirectAdapter
            adapter = SharePointDirectAdapter(config)
            dispatch_result: SubmissionResult = adapter.dispatch(
                payload=transformed_payload,
                pdf_file_paths=pdf_file_paths,
                additional_file_paths=additional_file_paths,
                config_override=config,
                saved_submission_path=saved_copy_path,
                extra_metadata=extra_metadata,
            )
        else:
            dispatch_result: SubmissionResult = self.adapter.dispatch(
                payload=transformed_payload,
                pdf_file_paths=pdf_file_paths,
                additional_file_paths=additional_file_paths,
                config_override=config,
            )

        # ── 500-only single retry (opt-in per tenant via retry_on_500: true) ──────
        # Triggers ONLY when: HTTP 500 received AND tenant config has retry_on_500=True.
        # Waits 10 seconds, then re-dispatches exactly once.
        # If retry succeeds → flow continues as SUCCESS (no email).
        # If retry also fails → flow continues as FAILED → failure notification email sent.
        if (
            not dispatch_result.success
            and dispatch_result.status_code == 500
            and getattr(config, "retry_on_500", False)
        ):
            import time as _time
            logger.warning(
                "[500-Retry] Tenant '%s' received HTTP 500 on first attempt. "
                "Waiting 10s before retrying ONCE...",
                tenant_folder,
            )
            _time.sleep(10)
            retry_result: SubmissionResult = self.adapter.dispatch(
                payload=transformed_payload,
                pdf_file_paths=pdf_file_paths,
                additional_file_paths=additional_file_paths,
                config_override=config,
            )
            logger.info(
                "[500-Retry] Tenant '%s' retry completed — success=%s, HTTP=%s",
                tenant_folder,
                retry_result.success,
                retry_result.status_code,
            )
            dispatch_result = retry_result  # use retry result for all downstream logic
        # ─────────────────────────────────────────────────────────────────────────

        return {
            "status": "SUCCESS" if dispatch_result.success else "FAILED",
            "tenant_folder": tenant_folder,
            "status_code": dispatch_result.status_code,
            "response": dispatch_result.response_data,
            "error": dispatch_result.error_message,
            "attempts": dispatch_result.attempt_count,
            "execution_time_seconds": dispatch_result.execution_time_seconds,
            "transformed_payload": transformed_payload,
            "saved_submission_path": saved_copy_path,
            "extra_info": getattr(dispatch_result, "extra_info", {})
        }
