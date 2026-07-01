from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Company, CompanySnapshot, PipelineRun, ProcessedFile, Upload, ValidationFinding
from app.etl.extractor import ExtractedMaster, extract_master
from app.etl.validation import ValidationReport, validate_master

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    pass


def run_pipeline(db: Session, data_dir: Path, retries: int = 3) -> dict:
    started = time.perf_counter()
    run = PipelineRun(status="running")
    db.add(run)
    db.commit()
    files = sorted(data_dir.glob("*.xlsm"))
    processed = 0
    skipped = 0
    failed = 0
    reports: list[dict] = []
    timing_totals = {"extract_ms": 0, "validate_ms": 0, "load_ms": 0}
    try:
        for path in files:
            for attempt in range(1, retries + 1):
                try:
                    outcome = _process_file(db, run, path)
                    processed += int(outcome["processed"])
                    skipped += int(outcome["skipped"])
                    failed += int(outcome["failed"])
                    reports.append(outcome["quality_report"])
                    for key in timing_totals:
                        timing_totals[key] += outcome["timings"][key]
                    break
                except Exception:
                    db.rollback()
                    if attempt == retries:
                        raise
                    sleep_seconds = 2 ** (attempt - 1)
                    logger.warning("Retrying %s after transient failure", path.name, exc_info=True)
                    time.sleep(sleep_seconds)

        run.status = "success"
        run.files_seen = len(files)
        run.files_processed = processed
        run.files_skipped = skipped
        run.files_failed = failed
        run.finished_at = datetime.now(UTC)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        completed_reports = [report for report in reports if not report.get("skipped")]
        if completed_reports:
            run.quality_completeness_avg = sum(report["completeness_rate"] for report in completed_reports) / len(completed_reports)
            run.quality_validity_avg = sum(report["validity_rate"] for report in completed_reports) / len(completed_reports)
            run.quality_warning_count = sum(
                1 for report in completed_reports for issue in report.get("issues", []) if issue["severity"] == "warning"
            )
        run.extract_ms_total = timing_totals["extract_ms"]
        run.validate_ms_total = timing_totals["validate_ms"]
        run.load_ms_total = timing_totals["load_ms"]
        run.metrics = {
            "duration_seconds": round(time.perf_counter() - started, 4),
            "quality_reports": reports,
            "stage_timings_ms": timing_totals,
        }
        db.commit()
        return _run_payload(run)
    except Exception as exc:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.error_message = str(exc)
        run.metrics = {"duration_seconds": round(time.perf_counter() - started, 4)}
        db.add(run)
        db.commit()
        raise PipelineError(str(exc)) from exc


def _process_file(db: Session, run: PipelineRun, path: Path) -> dict:
    started = time.perf_counter()
    extract_started = time.perf_counter()
    master = extract_master(path)
    extract_ms = int((time.perf_counter() - extract_started) * 1000)
    existing = db.scalar(select(Upload).where(Upload.file_sha256 == master.file_sha256))
    if existing:
        processed_file = _record_processed_file(
            db=db,
            run=run,
            master=master,
            status="skipped_idempotent",
            upload_id=existing.id,
            snapshot_id=existing.snapshot.id if existing.snapshot else None,
            report=None,
            timings={"extract_ms": extract_ms, "validate_ms": 0, "load_ms": 0, "total_ms": int((time.perf_counter() - started) * 1000)},
            error_message="Skipped because file hash was already loaded.",
        )
        db.commit()
        return {
            "processed": False,
            "skipped": True,
            "failed": False,
            "quality_report": {"source_filename": path.name, "skipped": True, "processed_file_id": processed_file.id, "reason": "file hash already loaded"},
            "timings": {"extract_ms": extract_ms, "validate_ms": 0, "load_ms": 0},
        }

    validate_started = time.perf_counter()
    report = validate_master(master)
    validate_ms = int((time.perf_counter() - validate_started) * 1000)
    if report.has_errors:
        upload = Upload(
            source_filename=master.source_filename,
            file_sha256=master.file_sha256,
            file_size_bytes=master.file_size_bytes,
            uploaded_at=master.uploaded_at,
            status="rejected",
            row_count=master.row_count,
            validation_summary=report.as_dict(),
        )
        db.add(upload)
        db.flush()
        processed_file = _record_processed_file(
            db=db,
            run=run,
            master=master,
            status="rejected",
            upload_id=upload.id,
            snapshot_id=None,
            report=report,
            timings={"extract_ms": extract_ms, "validate_ms": validate_ms, "load_ms": 0, "total_ms": int((time.perf_counter() - started) * 1000)},
        )
        _record_validation_findings(db, processed_file, report)
        db.commit()
        return {
            "processed": True,
            "skipped": False,
            "failed": True,
            "quality_report": report.as_dict(),
            "timings": {"extract_ms": extract_ms, "validate_ms": validate_ms, "load_ms": 0},
        }

    load_started = time.perf_counter()
    upload, snapshot = _load_valid_snapshot(db, master, report.as_dict())
    load_ms = int((time.perf_counter() - load_started) * 1000)
    processed_file = _record_processed_file(
        db=db,
        run=run,
        master=master,
        status="processed",
        upload_id=upload.id,
        snapshot_id=snapshot.id,
        report=report,
        timings={"extract_ms": extract_ms, "validate_ms": validate_ms, "load_ms": load_ms, "total_ms": int((time.perf_counter() - started) * 1000)},
    )
    _record_validation_findings(db, processed_file, report)
    db.commit()
    logger.info("Processed %s", path.name)
    return {
        "processed": True,
        "skipped": False,
        "failed": False,
        "quality_report": report.as_dict(),
        "timings": {"extract_ms": extract_ms, "validate_ms": validate_ms, "load_ms": load_ms},
    }


def _load_valid_snapshot(db: Session, master: ExtractedMaster, validation_summary: dict) -> tuple[Upload, CompanySnapshot]:
    assert master.rated_entity_name is not None
    natural_key = master.rated_entity_name.strip().lower()
    company = db.scalar(select(Company).where(Company.natural_key == natural_key))
    if company is None:
        company = Company(natural_key=natural_key, current_name=master.rated_entity_name)
        db.add(company)
        db.flush()
    else:
        company.current_name = master.rated_entity_name

    latest = db.scalar(
        select(CompanySnapshot)
        .where(CompanySnapshot.company_id == company.id, CompanySnapshot.is_current.is_(True))
        .order_by(CompanySnapshot.version_number.desc())
    )
    next_version = (
        db.scalar(select(func.coalesce(func.max(CompanySnapshot.version_number), 0)).where(CompanySnapshot.company_id == company.id))
        or 0
    ) + 1
    now = datetime.now(UTC)
    if latest:
        latest.is_current = False
        latest.effective_to = now

    upload = Upload(
        source_filename=master.source_filename,
        file_sha256=master.file_sha256,
        file_size_bytes=master.file_size_bytes,
        uploaded_at=master.uploaded_at,
        status="processed",
        row_count=master.row_count,
        validation_summary=validation_summary,
    )
    db.add(upload)
    db.flush()

    snapshot = CompanySnapshot(
        company_id=company.id,
        upload_id=upload.id,
        version_number=next_version,
        effective_from=now,
        is_current=True,
        rated_entity_name=master.rated_entity_name,
        sector=master.sector or "",
        country=master.country or "",
        currency=master.currency or "",
        accounting_principles=master.accounting_principles,
        business_year_end_month=master.business_year_end_month,
        rating_methodologies=master.rating_methodologies,
        industry_risks=master.industry_risks,
        business_risk_profile=master.business_risk_profile,
        blended_industry_risk_profile=master.blended_industry_risk_profile,
        competitive_positioning=master.competitive_positioning,
        raw_master_payload=master.raw_fields,
    )
    db.add(snapshot)
    db.flush()
    return upload, snapshot


def _record_processed_file(
    db: Session,
    run: PipelineRun,
    master: ExtractedMaster,
    status: str,
    upload_id: int | None,
    snapshot_id: int | None,
    report: ValidationReport | None,
    timings: dict[str, int],
    error_message: str | None = None,
) -> ProcessedFile:
    issue_count = 0 if report is None else sum(1 for issue in report.issues if issue.severity == "warning")
    processed_file = ProcessedFile(
        run_id=run.id,
        upload_id=upload_id,
        snapshot_id=snapshot_id,
        source_filename=master.source_filename,
        file_sha256=master.file_sha256,
        status=status,
        quality_completeness_rate=report.completeness_rate if report else None,
        quality_validity_rate=report.validity_rate if report else None,
        quality_warning_count=issue_count,
        extract_ms=timings["extract_ms"],
        validate_ms=timings["validate_ms"],
        load_ms=timings["load_ms"],
        total_ms=timings["total_ms"],
        error_message=error_message,
    )
    db.add(processed_file)
    db.flush()
    return processed_file


def _record_validation_findings(db: Session, processed_file: ProcessedFile, report: ValidationReport) -> None:
    for issue in report.issues:
        db.add(
            ValidationFinding(
                processed_file_id=processed_file.id,
                run_id=processed_file.run_id,
                source_filename=processed_file.source_filename,
                rule_id=issue.rule_id,
                severity=issue.severity,
                field=issue.field,
                message=issue.message,
            )
        )


def _run_payload(run: PipelineRun) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "files_seen": run.files_seen,
        "files_processed": run.files_processed,
        "files_failed": run.files_failed,
        "files_skipped": run.files_skipped,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "quality_completeness_avg": run.quality_completeness_avg,
        "quality_validity_avg": run.quality_validity_avg,
        "quality_warning_count": run.quality_warning_count,
        "stage_timings_ms": {
            "extract": run.extract_ms_total,
            "validate": run.validate_ms_total,
            "load": run.load_ms_total,
        },
        "metrics": run.metrics,
    }
