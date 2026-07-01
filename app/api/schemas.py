from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SnapshotOut(BaseModel):
    id: int
    company_id: int
    upload_id: int
    version_number: int
    effective_from: datetime
    effective_to: datetime | None
    is_current: bool
    rated_entity_name: str
    sector: str
    country: str
    currency: str
    accounting_principles: str | None
    business_year_end_month: str | None
    rating_methodologies: list[str]
    industry_risks: list[dict]
    business_risk_profile: str | None
    blended_industry_risk_profile: str | None
    competitive_positioning: str | None

    model_config = ConfigDict(from_attributes=True)


class CompanyOut(BaseModel):
    id: int
    natural_key: str
    current_name: str
    current_snapshot: SnapshotOut | None = None


class UploadOut(BaseModel):
    id: int
    source_filename: str
    file_sha256: str
    file_size_bytes: int
    uploaded_at: datetime
    processed_at: datetime
    status: str
    row_count: int
    validation_summary: dict

    model_config = ConfigDict(from_attributes=True)


class PipelineRunOut(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    files_seen: int
    files_processed: int
    files_failed: int
    files_skipped: int
    quality_completeness_avg: float | None
    quality_validity_avg: float | None
    quality_warning_count: int
    extract_ms_total: int
    validate_ms_total: int
    load_ms_total: int
    duration_ms: int | None
    error_message: str | None
    metrics: dict

    model_config = ConfigDict(from_attributes=True)


class ProcessedFileOut(BaseModel):
    id: int
    run_id: int
    upload_id: int | None
    snapshot_id: int | None
    source_filename: str
    file_sha256: str
    status: str
    quality_completeness_rate: float | None
    quality_validity_rate: float | None
    quality_warning_count: int
    extract_ms: int
    validate_ms: int
    load_ms: int
    total_ms: int
    error_message: str | None
    processed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationFindingOut(BaseModel):
    id: int
    processed_file_id: int
    run_id: int
    source_filename: str
    rule_id: str
    severity: str
    field: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
