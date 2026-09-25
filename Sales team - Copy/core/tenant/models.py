from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ModuleConfig(BaseModel):
    module_code: str
    enabled: bool = True
    prompt_file: str
    schema_file: str
    confidence_threshold: float = 0.80
    required_fields: List[str] = Field(default_factory=list)
    output_formats: List[str] = Field(default_factory=lambda: ["json"])
    manual_review_below_threshold: bool = True
    extension_key: Optional[str] = None


class TenantSettings(BaseModel):
    tenant_id: int
    tenant_code: str
    tenant_name: str
    email: str = Field(default="", description="Tenant contact email required for DB connection")
    active: bool = True
    enabled_modules: List[str] = Field(default_factory=list)
    output_root: str = "output/CLIENT_A"
    default_confidence_threshold: float = 0.85
    timezone: str = "UTC"


class ProcessingContext(BaseModel):
    job_id: str
    tenant_id: int
    tenant_code: str
    module_code: str
    original_file_name: str
    input_path: str
    prompt_text: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    confidence_threshold: float = 0.85
    required_fields: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessingJob(BaseModel):
    job_id: str
    tenant_id: int
    tenant_code: str
    module_code: str
    original_file_name: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, MANUAL_REVIEW, FAILED, ACCESS_DENIED
    confidence_score: float = 0.0
    input_path: str
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_date: Optional[str] = None
    started_date: Optional[str] = None
    completed_date: Optional[str] = None


class AuditLog(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    tenant_code: str
    module_code: str
    job_id: str
    event_type: str
    message: str
    timestamp: Optional[str] = None


class SubmissionAuthConfig(BaseModel):
    type: str = "none"  # "none", "api_key", "bearer", "basic", "custom_headers"
    header_name: Optional[str] = None
    secret_env_var: Optional[str] = None
    username_env_var: Optional[str] = None
    password_env_var: Optional[str] = None
    custom_headers: Dict[str, str] = Field(default_factory=dict)


class SubmissionTransformRules(BaseModel):
    strip_summary_level_keys: List[str] = Field(default_factory=lambda: ["policy_number", "carrier_name"])
    unified_acord_lossrun: bool = True
    inject_metadata: bool = False
    merge_multiple_documents: bool = True
    payload_mapping: Dict[str, str] = Field(default_factory=dict)
    poc_routing_overrides: Dict[str, str] = Field(default_factory=dict)
    custom_field_mappings: Dict[str, str] = Field(default_factory=dict)
    default_poc_engine: Optional[str] = None


class SubmissionAttachmentRules(BaseModel):
    include_original_pdfs: bool = True
    include_additional_files: bool = True   # set false to skip Excel/extra outputs
    multipart_file_field: str = "file"
    acord_file_field: str = "acordPdf"
    loss_runs_file_field: str = "lossRunsPdf"
    excel_file_field: str = "excelFile"
    max_attachment_size_mb: int = 50


class SubmissionRetryPolicy(BaseModel):
    max_retries: int = 3
    backoff_factor: float = 1.5
    timeout_seconds: int = 30


class FailureNotificationConfig(BaseModel):
    """Config for sending failure alert emails back to the sender on HTTP errors."""
    enabled: bool = False
    # Which HTTP status codes should trigger a failure notification email
    trigger_on_status_codes: List[int] = Field(default_factory=lambda: [400, 401, 403, 422, 500])
    # Set this email in submission.json to control where failure alerts go.
    # If left empty (""), the alert is sent back to the original email sender.
    notify_email: str = ""
    # Whether to attach the merged JSON in the failure email
    attach_merged_json: bool = True
    # Whether to attach the original input PDFs in the failure email
    attach_input_pdfs: bool = True
    # Custom subject prefix (e.g. "[SELVA TEAM]") – tenant name used if empty
    subject_prefix: Optional[str] = None


class TenantSubmissionConfig(BaseModel):
    enabled: bool = True
    delivery_method: str = "http" # "http" or "sharepoint_direct"
    sharepoint_base_folder: str = "Notices"
    target_url: str = ""
    http_method: str = "POST"
    auth: SubmissionAuthConfig = Field(default_factory=SubmissionAuthConfig)
    default_modifier: float = 1.30
    default_submitter_email: Optional[str] = None
    override_sender_email: bool = False
    transform_rules: SubmissionTransformRules = Field(default_factory=SubmissionTransformRules)
    attachments: SubmissionAttachmentRules = Field(default_factory=SubmissionAttachmentRules)
    retry_policy: SubmissionRetryPolicy = Field(default_factory=SubmissionRetryPolicy)
    failure_notification: FailureNotificationConfig = Field(default_factory=FailureNotificationConfig)
    # When True: if the first dispatch returns HTTP 500, the system retries ONCE automatically.
    # If the retry also fails → failure notification email is sent. Default False (opt-in per tenant).
    retry_on_500: bool = False


