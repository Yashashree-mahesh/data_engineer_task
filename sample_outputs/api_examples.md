# API Examples

Run the stack and ingest the provided workbooks:

```bash
docker compose up -d --build
docker compose exec api python -m app.cli ingest
```

## 1. Health

`GET /health`

```json
{"status":"ok"}
```

## 2. Trigger Pipeline

`POST /pipeline/run`

```json
{"run_id":1,"status":"success","files_seen":4,"files_processed":4,"files_skipped":0}
```

## 3. Companies

`GET /companies`

```json
[
  {"id":1,"natural_key":"company a","current_name":"Company A","current_snapshot":{"version_number":2,"currency":"EUR","country":"Federal Republic of Germany"}},
  {"id":2,"natural_key":"company b","current_name":"Company B","current_snapshot":{"version_number":2,"currency":"CHF","country":"Swiss Confederation"}}
]
```

## 4. Company Detail

`GET /companies/1`

```json
{"id":1,"natural_key":"company a","current_name":"Company A","current_snapshot":{"industry_risks":[{"name":"Consumer Products: Non-Discretionary","score":"BBB","weight":1.0}]}}
```

## 5. Company Versions

`GET /companies/1/versions`

```json
[
  {"version_number":1,"industry_risks":[{"score":"A","weight":1.0}],"is_current":false},
  {"version_number":2,"industry_risks":[{"score":"BBB","weight":1.0}],"is_current":true}
]
```

## 6. Company History

`GET /companies/2/history`

```json
[
  {"version_number":1,"business_risk_profile":"BBB","industry_risks":[{"weight":0.15},{"weight":0.85}]},
  {"version_number":2,"business_risk_profile":"BBB-","industry_risks":[{"weight":0.25},{"weight":0.75}]}
]
```

## 7. Point-in-time Compare

`GET /companies/compare?company_ids=1&company_ids=2&as_of_date=2026-06-17T12:00:00Z`

```json
[
  {"company_id":1,"rated_entity_name":"Company A","currency":"EUR"},
  {"company_id":2,"rated_entity_name":"Company B","currency":"CHF"}
]
```

## 8. Snapshot Filter

`GET /snapshots?currency=CHF`

```json
[
  {"company_id":2,"version_number":2,"currency":"CHF"},
  {"company_id":2,"version_number":1,"currency":"CHF"}
]
```

## 9. Latest Snapshots

`GET /snapshots/latest`

```json
[
  {"company_id":1,"version_number":2,"is_current":true},
  {"company_id":2,"version_number":2,"is_current":true}
]
```

## 10. Upload Stats

`GET /uploads/stats`

```json
{"total_uploads":4,"by_status":{"processed":4}}
```

## 11. Upload Details

`GET /uploads/1/details`

```json
{"id":1,"source_filename":"corporates_A_1.xlsm","status":"processed","row_count":40}
```

## 12. Original File Download

`GET /uploads/1/file`

Returns the original `corporates_A_1.xlsm` file.

## 13. Pipeline Runs

`GET /pipeline/runs`

```json
[
  {
    "id": 1,
    "status": "success",
    "files_seen": 4,
    "files_processed": 4,
    "files_failed": 0,
    "files_skipped": 0,
    "quality_completeness_avg": 1.0,
    "quality_validity_avg": 1.0,
    "extract_ms_total": 19,
    "validate_ms_total": 0,
    "load_ms_total": 9
  }
]
```

## 14. Pipeline Quality Drill-down

`GET /pipeline/runs/1/quality`

```json
{
  "run": {"id": 1, "status": "success", "files_processed": 4},
  "files": [
    {
      "source_filename": "corporates_A_1.xlsm",
      "status": "processed",
      "quality_completeness_rate": 1.0,
      "quality_validity_rate": 1.0,
      "extract_ms": 5,
      "validate_ms": 0,
      "load_ms": 5
    }
  ],
  "findings": []
}
```
