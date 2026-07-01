from pathlib import Path
import json

import typer

from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.etl.pipeline import run_pipeline

cli = typer.Typer(help="Corporate credit rating ETL commands.")


@cli.command()
def ingest(data_dir: Path | None = None, reports_dir: Path | None = None) -> None:
    init_db()
    settings = get_settings()
    artifact_dir = reports_dir or settings.reports_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        result = run_pipeline(db, data_dir or settings.data_dir)
    quality_path = artifact_dir / f"quality_run_{result['run_id']}.json"
    log_path = artifact_dir / f"pipeline_run_{result['run_id']}.log"
    quality_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log_path.write_text(_format_pipeline_log(result), encoding="utf-8")
    typer.echo(result)


def _format_pipeline_log(result: dict) -> str:
    lines = [
        (
            f"run_id={result['run_id']} status={result['status']} "
            f"files_seen={result['files_seen']} files_processed={result['files_processed']} "
            f"files_failed={result['files_failed']} files_skipped={result['files_skipped']} "
            f"duration_ms={result['duration_ms']}"
        )
    ]
    for report in result.get("metrics", {}).get("quality_reports", []):
        lines.append(f"file={report.get('source_filename')} report={json.dumps(report, sort_keys=True)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    cli()
