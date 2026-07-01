from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.schemas import CompanyOut, PipelineRunOut, ProcessedFileOut, SnapshotOut, UploadOut, ValidationFindingOut
from app.core.config import get_settings
from app.db.models import Company, CompanySnapshot, PipelineRun, ProcessedFile, Upload, ValidationFinding
from app.db.session import get_db
from app.etl.pipeline import run_pipeline

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/pipeline/run")
def trigger_pipeline(db: Session = Depends(get_db)) -> dict:
    return run_pipeline(db, get_settings().data_dir)


@router.get("/pipeline/runs", response_model=list[PipelineRunOut])
def list_pipeline_runs(db: Session = Depends(get_db)) -> list[PipelineRun]:
    return db.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc())).all()


@router.get("/pipeline/runs/{run_id}", response_model=PipelineRunOut)
def get_pipeline_run(run_id: int, db: Session = Depends(get_db)) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.get("/pipeline/runs/{run_id}/quality")
def get_pipeline_run_quality(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    files = db.scalars(
        select(ProcessedFile).where(ProcessedFile.run_id == run_id).order_by(ProcessedFile.id)
    ).all()
    findings = db.scalars(
        select(ValidationFinding).where(ValidationFinding.run_id == run_id).order_by(ValidationFinding.id)
    ).all()
    return {
        "run": PipelineRunOut.model_validate(run).model_dump(mode="json"),
        "files": [ProcessedFileOut.model_validate(item).model_dump(mode="json") for item in files],
        "findings": [ValidationFindingOut.model_validate(item).model_dump(mode="json") for item in findings],
    }


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyOut]:
    companies = db.scalars(select(Company).order_by(Company.current_name)).all()
    output: list[CompanyOut] = []
    for company in companies:
        snapshot = _current_snapshot(db, company.id)
        output.append(CompanyOut(id=company.id, natural_key=company.natural_key, current_name=company.current_name, current_snapshot=snapshot))
    return output


@router.get("/companies/compare", response_model=list[SnapshotOut])
def compare_companies(
    company_ids: list[int] = Query(...),
    as_of_date: datetime | None = None,
    db: Session = Depends(get_db),
) -> list[CompanySnapshot]:
    as_of = as_of_date or datetime.utcnow()
    return db.scalars(
        select(CompanySnapshot)
        .where(
            CompanySnapshot.company_id.in_(company_ids),
            CompanySnapshot.effective_from <= as_of,
            ((CompanySnapshot.effective_to.is_(None)) | (CompanySnapshot.effective_to > as_of)),
        )
        .order_by(CompanySnapshot.company_id)
    ).all()


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)) -> CompanyOut:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyOut(
        id=company.id,
        natural_key=company.natural_key,
        current_name=company.current_name,
        current_snapshot=_current_snapshot(db, company.id),
    )


@router.get("/companies/{company_id}/versions", response_model=list[SnapshotOut])
def get_company_versions(company_id: int, db: Session = Depends(get_db)) -> list[CompanySnapshot]:
    _require_company(db, company_id)
    return db.scalars(
        select(CompanySnapshot)
        .where(CompanySnapshot.company_id == company_id)
        .order_by(CompanySnapshot.version_number)
    ).all()


@router.get("/companies/{company_id}/history", response_model=list[SnapshotOut])
def get_company_history(company_id: int, db: Session = Depends(get_db)) -> list[CompanySnapshot]:
    return get_company_versions(company_id, db)


@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(
    company_id: int | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    sector: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    db: Session = Depends(get_db),
) -> list[CompanySnapshot]:
    filters = []
    if company_id:
        filters.append(CompanySnapshot.company_id == company_id)
    if from_date:
        filters.append(CompanySnapshot.effective_from >= from_date)
    if to_date:
        filters.append(CompanySnapshot.effective_from <= to_date)
    if sector:
        filters.append(CompanySnapshot.sector == sector)
    if country:
        filters.append(CompanySnapshot.country == country)
    if currency:
        filters.append(CompanySnapshot.currency == currency)
    query = select(CompanySnapshot)
    if filters:
        query = query.where(and_(*filters))
    return db.scalars(query.order_by(CompanySnapshot.effective_from.desc())).all()


@router.get("/snapshots/latest", response_model=list[SnapshotOut])
def latest_snapshots(db: Session = Depends(get_db)) -> list[CompanySnapshot]:
    return db.scalars(
        select(CompanySnapshot).where(CompanySnapshot.is_current.is_(True)).order_by(CompanySnapshot.company_id)
    ).all()


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)) -> CompanySnapshot:
    snapshot = db.get(CompanySnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(db: Session = Depends(get_db)) -> list[Upload]:
    return db.scalars(select(Upload).order_by(Upload.processed_at.desc())).all()


@router.get("/uploads/stats")
def upload_stats(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Upload.status, func.count(Upload.id)).group_by(Upload.status)).all()
    return {"total_uploads": sum(count for _, count in rows), "by_status": {status: count for status, count in rows}}


@router.get("/uploads/{upload_id}/details", response_model=UploadOut)
def upload_details(upload_id: int, db: Session = Depends(get_db)) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


@router.get("/uploads/{upload_id}/file")
def upload_file(upload_id: int, db: Session = Depends(get_db)) -> FileResponse:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    path = Path(get_settings().data_dir) / upload.source_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file is not available")
    return FileResponse(path, filename=upload.source_filename)


def _current_snapshot(db: Session, company_id: int) -> CompanySnapshot | None:
    return db.scalar(select(CompanySnapshot).where(CompanySnapshot.company_id == company_id, CompanySnapshot.is_current.is_(True)))


def _require_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
