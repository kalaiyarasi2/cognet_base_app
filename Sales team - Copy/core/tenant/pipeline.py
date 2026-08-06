from __future__ import annotations
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import jsonschema
    _jsonschema_available = True
except ImportError:
    jsonschema = None
    _jsonschema_available = False

from pydantic import BaseModel

from core.tenant.models import ProcessingContext, ProcessingJob, AuditLog
from core.tenant.provider import SingleTenantProvider, MODULE_INVOICE, MODULE_SBC
from core.tenant.adapters import ModuleRegistry
from core.tenant.storage import TenantStorageService


logger = logging.getLogger(__name__)


class PipelineResponse(BaseModel):
    status: str  # COMPLETED, MANUAL_REVIEW, ACCESS_DENIED, FAILED
    job_id: str
    tenant_id: int
    tenant_code: str
    module_code: str
    confidence_score: float
    output_path: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class DocumentPipeline:
    """
    Shared Document Ingestion Pipeline for Single-Tenant Architecture.
    Orchestrates ingestion, authorization, extraction, schema validation,
    confidence scoring, output storage, and database auditing.
    """

    def __init__(self, workspace_dir: Optional[Path] = None):
        if workspace_dir is None:
            workspace_dir = Path(__file__).resolve().parent.parent.parent
        self.workspace_dir = Path(workspace_dir).resolve()

        self.provider = SingleTenantProvider.get_instance(self.workspace_dir)
        self.registry = ModuleRegistry()
        self.storage = TenantStorageService(self.workspace_dir, tenant_code=self.provider.tenant.tenant_code)

        # Lazy import of database module to avoid circular dependency
        self.db = self._get_db_module()

    def _get_db_module(self):
        try:
            import sys
            if str(self.workspace_dir) not in sys.path:
                sys.path.insert(0, str(self.workspace_dir))
            from database import poc_db
            return poc_db
        except Exception as e:
            logger.warning(f"[DocumentPipeline] poc_db import fallback: {e}")
            return None

    def _record_audit(self, job_id: str, module_code: str, event_type: str, message: str) -> None:
        try:
            tenant = self.provider.tenant
            if self.db and hasattr(self.db, "add_audit_log"):
                self.db.add_audit_log(
                    tenant_id=tenant.tenant_id,
                    tenant_code=tenant.tenant_code,
                    module_code=module_code,
                    job_id=job_id,
                    event_type=event_type,
                    message=message
                )
        except Exception as err:
            logger.warning(f"Failed to record audit log: {err}")

    def _save_job(self, job: ProcessingJob) -> None:
        try:
            if self.db and hasattr(self.db, "upsert_processing_job"):
                self.db.upsert_processing_job(job.model_dump())
        except Exception as err:
            logger.warning(f"Failed to persist processing job: {err}")


    async def process_document(
        self,
        input_path: str,
        module_code: str,
        original_file_name: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> PipelineResponse:
        created_at = datetime.utcnow().isoformat()
        job_id = job_id or f"job_{uuid.uuid4().hex[:12]}"
        module_code = module_code.upper().strip()
        original_name = original_file_name or Path(input_path).name

        tenant = self.provider.tenant

        job = ProcessingJob(
            job_id=job_id,
            tenant_id=tenant.tenant_id,
            tenant_code=tenant.tenant_code,
            module_code=module_code,
            original_file_name=original_name,
            status="PENDING",
            confidence_score=0.0,
            input_path=str(input_path),
            created_date=created_at,
            started_date=datetime.utcnow().isoformat()
        )
        self._save_job(job)
        self._record_audit(job_id, module_code, "JOB_STARTED", f"Processing started for file {original_name}")

        # Step 1: Validate Tenant Active
        if not tenant.active:
            err_msg = f"Tenant {tenant.tenant_code} is inactive."
            job.status = "ACCESS_DENIED"
            job.error_message = err_msg
            job.completed_date = datetime.utcnow().isoformat()
            self._save_job(job)
            self._record_audit(job_id, module_code, "TENANT_INACTIVE", err_msg)
            return PipelineResponse(
                status="ACCESS_DENIED",
                job_id=job_id,
                tenant_id=tenant.tenant_id,
                tenant_code=tenant.tenant_code,
                module_code=module_code,
                confidence_score=0.0,
                error_message=err_msg
            )

        # Step 2: Check Module Access
        if not self.provider.access_service.can_access(module_code):
            err_msg = f"Access denied: Module {module_code} is disabled for tenant {tenant.tenant_code}."
            job.status = "ACCESS_DENIED"
            job.error_message = err_msg
            job.completed_date = datetime.utcnow().isoformat()
            self._save_job(job)
            self._record_audit(job_id, module_code, "ACCESS_DENIED", err_msg)
            return PipelineResponse(
                status="ACCESS_DENIED",
                job_id=job_id,
                tenant_id=tenant.tenant_id,
                tenant_code=tenant.tenant_code,
                module_code=module_code,
                confidence_score=0.0,
                error_message=err_msg
            )

        # Step 3 & 4: Load module config, prompt, and JSON schema
        mod_cfg = self.provider.get_module_config(module_code)
        prompt_text = self.provider.load_prompt_for_module(module_code)
        json_schema = self.provider.load_schema_for_module(module_code)

        threshold = mod_cfg.confidence_threshold if mod_cfg else tenant.default_confidence_threshold
        req_fields = mod_cfg.required_fields if mod_cfg else []

        # Step 5: Create ProcessingContext
        context = ProcessingContext(
            job_id=job_id,
            tenant_id=tenant.tenant_id,
            tenant_code=tenant.tenant_code,
            module_code=module_code,
            original_file_name=original_name,
            input_path=str(input_path),
            prompt_text=prompt_text,
            json_schema=json_schema,
            confidence_threshold=threshold,
            required_fields=req_fields
        )

        # Step 6: Invoke module adapter
        try:
            adapter = self.registry.get_adapter(module_code)
            adapter_res = await adapter.process(context)
        except Exception as e:
            err_msg = f"Adapter execution error for module {module_code}: {str(e)}"
            logger.error(err_msg, exc_info=True)
            job.status = "FAILED"
            job.error_message = err_msg
            job.completed_date = datetime.utcnow().isoformat()
            self._save_job(job)
            self._record_audit(job_id, module_code, "JOB_FAILED", err_msg)
            return PipelineResponse(
                status="FAILED",
                job_id=job_id,
                tenant_id=tenant.tenant_id,
                tenant_code=tenant.tenant_code,
                module_code=module_code,
                confidence_score=0.0,
                error_message=err_msg
            )

        extracted = adapter_res.get("extracted_data", {})
        confidence = float(adapter_res.get("confidence_score", 0.0))

        # Step 7: Validate Required Fields & JSON Schema
        schema_valid = True
        schema_errors = []
        if json_schema:
            if _jsonschema_available and jsonschema is not None:
                try:
                    jsonschema.validate(instance=extracted, schema=json_schema)
                except jsonschema.ValidationError as ve:
                    schema_valid = False
                    schema_errors.append(ve.message)
            else:
                # Fallback schema check for required properties
                schema_reqs = json_schema.get("required", [])
                for req in schema_reqs:
                    if req not in extracted or extracted[req] is None:
                        schema_valid = False
                        schema_errors.append(f"Property '{req}' missing from extraction")


        missing_fields = [f for f in req_fields if f not in extracted or extracted[f] is None]
        if missing_fields:
            schema_valid = False
            schema_errors.append(f"Missing required fields: {missing_fields}")

        # Step 8 & 9: Determine Final Status & Manual Review Tagging
        if not schema_valid or confidence < threshold:
            final_status = "MANUAL_REVIEW"
            self._record_audit(
                job_id, module_code, "MANUAL_REVIEW_FLAGGED",
                f"Flagged for manual review. Confidence: {confidence} (Threshold: {threshold}). Errors: {schema_errors}"
            )
        else:
            final_status = "COMPLETED"
            self._record_audit(job_id, module_code, "JOB_COMPLETED", f"Extraction completed successfully with confidence {confidence}")

        # Step 10: Save Configured Outputs under output/CLIENT_A/{module_code}/{job_id}/
        output_file_path = self.storage.save_json_output(
            module_code=module_code,
            job_id=job_id,
            filename=f"result_{job_id}.json",
            data={
                "job_id": job_id,
                "tenant_code": tenant.tenant_code,
                "module_code": module_code,
                "confidence_score": confidence,
                "status": final_status,
                "extracted_data": extracted,
                "schema_errors": schema_errors
            }
        )

        job.status = final_status
        job.confidence_score = confidence
        job.output_path = str(output_file_path)
        job.completed_date = datetime.utcnow().isoformat()
        self._save_job(job)

        return PipelineResponse(
            status=final_status,
            job_id=job_id,
            tenant_id=tenant.tenant_id,
            tenant_code=tenant.tenant_code,
            module_code=module_code,
            confidence_score=confidence,
            output_path=str(output_file_path),
            extracted_data=extracted,
            error_message="; ".join(schema_errors) if schema_errors else None
        )
