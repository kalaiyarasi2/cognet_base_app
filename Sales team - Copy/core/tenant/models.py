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
    type: str = "none"  # "none", "api_key", "bearer", "basic", "custom_headers", "dynamic_token"
    header_name: Optional[str] = None
    secret_env_var: Optional[str] = None
    username_env_var: Optional[str] = None
    password_env_var: Optional[str] = None
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    # Dynamic Token / OAuth2 Fields
    token_url: Optional[str] = None
    client_id_env_var: Optional[str] = None
    client_secret_env_var: Optional[str] = None
    token_path: str = "data.accessToken"
    expires_in_path: str = "data.expiresIn"
    token_type: str = "Bearer"


class SubmissionTransformRules(BaseModel):
    strip_summary_level_keys: List[str] = Field(default_factory=lambda: ["policy_number", "carrier_name"])
    unified_acord_lossrun: bool = True
    inject_metadata: bool = False
    merge_multiple_documents: bool = True
    payload_mapping: Dict[str, str] = Field(default_factory=dict)
    poc_routing_overrides: Dict[str, str] = Field(default_factory=dict)
    custom_field_mappings: Dict[str, str] = Field(default_factory=dict)
    default_poc_engine: Optional[str] = None
    # ── POC Whitelist ──────────────────────────────────────────────────────────
    # When non-empty, ONLY the listed POC engine identifiers are permitted for
    # this tenant.  Any document classified into a category that does NOT resolve
    # to one of these engines will be re-routed to `default_poc_engine` instead
    # of being processed by an unauthorised engine.
    #
    # Supported engine identifiers (match start_flow.py routing branch names):
    #   "INSURANCE_CLAIMS"    → Gpu_server / Insurance_pdf_extractor-main
    #   "WORK_COMPENSATION"   → Gpu_server / work_compensation
    #   "LOSS_RUN"            → Gpu_server / UnifiedRouter (loss runs)
    #   "RENEWAL"             → Renewal_process
    #   "SBC"                 → Parity_setup
    #   "RPVE"                → rpve (Benefit Invoice)
    #   "NOTICE_EXTRACTION"   → Notice-extraction
    #
    # Leave empty ([]) to allow all POC engines (default global behaviour).
    allowed_poc_engines: List[str] = Field(default_factory=list)
    # ── Reject-on-Mismatch ─────────────────────────────────────────────────────
    # When True AND allowed_poc_engines is non-empty:
    #   • Any document whose category is NOT in the whitelist is SKIPPED entirely.
    #   • An exception notification email is sent to failure_notification.notify_email
    #     (or back to the original sender) informing them that the document type is
    #     not accepted by this tenant.
    # When False (default): mismatched documents are silently redirected to
    #   default_poc_engine instead of being rejected.
    reject_unmatched_poc: bool = False
    # ── Generic Tenant Transformation & Schema Extension Rules ──────────────
    include_tenant_code: bool = False
    include_modifier_data: bool = False
    clean_metadata_summary: bool = False
    opportunity_template: Optional[Dict[str, Any]] = None
    email_extraction_rules: Optional[Dict[str, str]] = None
    # Optional dotted-path sources, e.g. {"opportunityName": "acord.demographics.applicantName"}
    opportunity_field_sources: Dict[str, str] = Field(default_factory=dict)
    # Optional dotted-path list sources for metadata counts, e.g. {"totalClaims": "lossRuns.claims"}
    metadata_count_sources: Dict[str, str] = Field(default_factory=dict)


class SubmissionAttachmentRules(BaseModel):
    include_original_pdfs: bool = True
    include_additional_files: bool = True   # set false to skip Excel/extra outputs
    multipart_file_field: str = "file"
    acord_file_field: str = "acordPdf"
    loss_runs_file_field: str = "lossRunsPdf"
    modifier_file_field: str = "modifierPdf"
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


class MailOutDisplayField(BaseModel):
    label: str                                   # e.g., "Applicant Name", "FEIN", "Total Claims"
    path: str                                    # Dotted JSON path, e.g., "acord.data.demographics.applicantName"
    highlight_if_empty: bool = False             # Highlight in red if empty/missing (e.g. FEIN)
    fallback_paths: List[str] = Field(default_factory=list)  # Alternative paths if primary is missing


class MailOutDisplaySection(BaseModel):
    title: str                                   # Table title, e.g., "Key Extracted Data — ACORD 130"
    fields: List[MailOutDisplayField] = Field(default_factory=list)


class MailOutConfig(BaseModel):
    """
    Config for mail-out delivery mode: instead of POSTing to an API,
    the system emails the processed outputs to a fixed recipient.
    Activated when TenantSubmissionConfig.delivery_method == "mail_out".
    """
    # "fixed": always send to result_to address
    # "sender": reply back to the original email sender
    result_recipient_mode: str = "fixed"
    result_to: str = ""              # env var placeholders supported e.g. ${WCUW_CLIENT_OUTPUT_EMAIL}
    exception_recipient: str = ""    # env var placeholders supported e.g. ${WCUW_EXCEPTIONAL_MAIL}
    # If True, send result email even when exceptions are found (plus send exception alert)
    # If False, only send the exception alert and skip the result email
    send_result_even_if_exceptions: bool = True
    subject_prefix: str = "[COGNET]"
    # Which output files to attach in the result email.
    # Supported values: "lossrun_json", "acord_json", "merged_json", "lossrun_excel", "acord_excel"
    attach_outputs: List[str] = Field(default_factory=lambda: ["merged_json"])
    # Custom filename for the attached merged/unified json (defaults to merged_output.json or <tenant>_unified_payload.json)
    unified_json_filename: Optional[str] = None
    # Config-driven display sections for result email body
    display_sections: List[MailOutDisplaySection] = Field(default_factory=list)


class TenantSubmissionConfig(BaseModel):
    tenant_code: str = ""
    enabled: bool = True
    # Delivery method: "http" | "sharepoint_direct" | "mail_out"
    delivery_method: str = "http"
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
    # Mail-out delivery config — only used when delivery_method == "mail_out"
    mail_out: MailOutConfig = Field(default_factory=MailOutConfig)


