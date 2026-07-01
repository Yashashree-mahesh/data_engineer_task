from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Upload(Base):
    __tablename__ = "fact_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processed")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    snapshot: Mapped["CompanySnapshot"] = relationship(back_populates="upload")


class Company(Base):
    __tablename__ = "dim_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    natural_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    current_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    snapshots: Mapped[list["CompanySnapshot"]] = relationship(back_populates="company")


class CompanySnapshot(Base):
    __tablename__ = "fact_company_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "version_number", name="uq_company_version"),
        Index("ix_snapshots_company_effective", "company_id", "effective_from"),
        Index("ix_snapshots_filters", "sector", "country", "currency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("dim_companies.id"), nullable=False)
    upload_id: Mapped[int] = mapped_column(ForeignKey("fact_uploads.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    rated_entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    accounting_principles: Mapped[str | None] = mapped_column(String(64))
    business_year_end_month: Mapped[str | None] = mapped_column(String(32))
    rating_methodologies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    industry_risks: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    business_risk_profile: Mapped[str | None] = mapped_column(String(32))
    blended_industry_risk_profile: Mapped[str | None] = mapped_column(String(32))
    competitive_positioning: Mapped[str | None] = mapped_column(String(32))
    raw_master_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    company: Mapped[Company] = relationship(back_populates="snapshots")
    upload: Mapped[Upload] = relationship(back_populates="snapshot")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    files_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_completeness_avg: Mapped[float | None] = mapped_column(Float)
    quality_validity_avg: Mapped[float | None] = mapped_column(Float)
    quality_warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extract_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validate_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    processed_files: Mapped[list["ProcessedFile"]] = relationship(back_populates="run")


class ProcessedFile(Base):
    __tablename__ = "processed_files"
    __table_args__ = (Index("ix_processed_files_run_status", "run_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("fact_uploads.id"))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("fact_company_snapshots.id"))
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_completeness_rate: Mapped[float | None] = mapped_column(Float)
    quality_validity_rate: Mapped[float | None] = mapped_column(Float)
    quality_warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extract_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validate_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    run: Mapped[PipelineRun] = relationship(back_populates="processed_files")
    findings: Mapped[list["ValidationFinding"]] = relationship(back_populates="processed_file")


class ValidationFinding(Base):
    __tablename__ = "validation_findings"
    __table_args__ = (Index("ix_validation_findings_rule", "rule_id", "severity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processed_file_id: Mapped[int] = mapped_column(ForeignKey("processed_files.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    field: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    processed_file: Mapped[ProcessedFile] = relationship(back_populates="findings")
