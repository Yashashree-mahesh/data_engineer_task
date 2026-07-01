# Corporate Credit Rating Data Pipeline

This repository implements a containerized data platform for the provided corporate rating workbooks. It extracts the non-tabular `MASTER` sheet from `.xlsm` files, validates and loads the data into a temporal dimensional warehouse, and exposes analytical access through FastAPI.

## Architecture

The solution is intentionally small enough to review, but complete across the requested surfaces:

- `app/etl/extractor.py` reads `.xlsm` workbooks as OpenXML ZIP files and parses the `MASTER` key/value layout directly.
- `app/etl/validation.py` checks required fields, score values, numeric weights, and weight totals.
- `app/etl/pipeline.py` orchestrates extract, validate, transform, and load with idempotency by file hash, retries, transactions, and run metrics.
- `app/db/models.py` defines a dimensional warehouse with upload facts, company dimensions, temporal company snapshots, and pipeline runs.
- `app/api/routes.py` exposes company, snapshot, upload audit, point-in-time comparison, and pipeline endpoints.
- `docker-compose.yml` runs PostgreSQL 16 and the FastAPI application with health checks and persistent database storage.

## Warehouse Design

The warehouse uses:

- `dim_companies`: stable company identity using a normalized natural key.
- `fact_company_snapshots`: one row per uploaded company version, with `effective_from`, `effective_to`, `is_current`, and `version_number` for SCD Type 2 style history.
- `fact_uploads`: upload lineage, source filename, SHA-256, validation status, and data quality summary.
- `pipeline_runs`: operational run state, metrics, duration, and failure details.
- `processed_files`: per-run file audit with status, stage timings, quality rates, upload lineage, and snapshot lineage.
- `validation_findings`: rule-level validation findings with severity, field, and message for BI slicing and auditability.

This supports historical upload audit, point-in-time comparison, company time series, version navigation, country/company/currency classification, and BI-friendly snapshot filtering.

## Run With Docker

```bash
docker compose up -d --build
docker compose exec api python -m app.cli
```

Or run ingestion as an isolated Compose job:

```bash
docker compose --profile pipeline run --rm pipeline
```

Run the containerized test profile:

```bash
docker compose --profile test run --rm test
```

The API is available at:

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## API Endpoints

Company endpoints:

- `GET /companies`
- `GET /companies/{company_id}`
- `GET /companies/{company_id}/versions`
- `GET /companies/{company_id}/history`
- `GET /companies/compare?company_ids=1&company_ids=2&as_of_date=2026-06-17T12:00:00Z`

Snapshot endpoints:

- `GET /snapshots`
- `GET /snapshots/{snapshot_id}`
- `GET /snapshots/latest`

Upload audit endpoints:

- `GET /uploads`
- `GET /uploads/{upload_id}/details`
- `GET /uploads/{upload_id}/file`
- `GET /uploads/stats`

Pipeline endpoint:

- `POST /pipeline/run`
- `GET /pipeline/runs`
- `GET /pipeline/runs/{run_id}`
- `GET /pipeline/runs/{run_id}/quality`

The pipeline quality endpoints expose per-file timing, idempotent skip records, rejected-file details, and structured validation findings.

CLI pipeline runs also write:

- `reports/quality_run_<run_id>.json`
- `reports/pipeline_run_<run_id>.log`

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

For local API development without Docker, set `DATABASE_URL` to a reachable PostgreSQL database and run:

```bash
uvicorn app.main:app --reload
```

## Sample Outputs

The `sample_outputs/` directory contains:

- `api_examples.md`: more than 10 example API calls with representative responses.
- `data_quality_report.json`: sample quality report for the four provided workbooks.
- `pipeline_execution.log`: sample pipeline execution log.

## Production-Oriented Features Added

- Structured validation findings include stable `rule_id` values, so quality rules can be monitored over time.
- Per-file audit rows are written for successful loads, validation rejections, and idempotent skips.
- Pipeline runs persist stage timing totals for extraction, validation, and loading.
- `/pipeline/runs/{run_id}/quality` gives a drill-down view joining run metadata, processed files, and validation findings.
- Additional validation checks cover ISO-like currency format, recognized business year-end months, duplicate methodologies, and duplicate industry risk names.

## Notes

The provided workbooks contain two companies with two versions each:

- `corporates_A_1.xlsm` and `corporates_A_2.xlsm`: Company A changes industry risk score from `A` to `BBB`.
- `corporates_B_1.xlsm` and `corporates_B_2.xlsm`: Company B changes industry weights from `0.15/0.85` to `0.25/0.75`.
