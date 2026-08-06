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
