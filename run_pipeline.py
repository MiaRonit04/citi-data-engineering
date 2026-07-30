"""ACME Analytics — pipeline orchestrator / CLI entry point.

Run the full Medallion pipeline or any individual stage:

    python run_pipeline.py all        # bronze → silver → gold → lineage
    python run_pipeline.py bronze     # raw ingestion only
    python run_pipeline.py silver     # clean/validate only (requires bronze)
    python run_pipeline.py gold       # curate 7 datasets (requires silver)
    python run_pipeline.py lineage    # regenerate lineage artefacts

Each stage is independently executable and idempotent. The run is recorded to
``reports/execution_history.jsonl`` and summarised in
``reports/pipeline_summary.json`` / ``reports/execution_summary.json``.
"""

from __future__ import annotations

import argparse
import sys
import time

from etl.bronze import bronze_pipeline
from etl.common.config import get_settings
from etl.common.logging import get_logger
from etl.common.metadata import (
    PipelineExecution,
    StageMetrics,
    append_execution_history,
)
from etl.common.utils import new_batch_id, utc_now, utc_now_iso, write_json
from etl.gold import gold_pipeline
from etl.silver import silver_pipeline
from lineage import lineage_builder

STAGE_ORDER = ["bronze", "silver", "gold"]
STAGE_FN = {
    "bronze": bronze_pipeline.run,
    "silver": silver_pipeline.run,
    "gold": gold_pipeline.run,
}


def _resolve_stages(target: str) -> list[str]:
    if target == "all":
        return STAGE_ORDER
    if target in STAGE_ORDER:
        return [target]
    if target == "lineage":
        return []
    raise SystemExit(f"Unknown stage '{target}'. Choose from: all, {', '.join(STAGE_ORDER)}, lineage")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACME Medallion pipeline orchestrator")
    parser.add_argument("stage", nargs="?", default="all",
                        choices=["all", "bronze", "silver", "gold", "lineage"],
                        help="Which stage(s) to run (default: all)")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_directories()
    batch_id = new_batch_id("RUN")
    log = get_logger("orchestrator", batch_id=batch_id)

    start = utc_now()
    started_perf = time.perf_counter()
    stages = _resolve_stages(args.stage)
    all_metrics: list[StageMetrics] = []
    errors: list[str] = []

    log.info("Pipeline '{s}' starting — batch {b}", s=args.stage, b=batch_id)
    for stage in stages:
        try:
            all_metrics.extend(STAGE_FN[stage](batch_id=batch_id, settings=settings))
        except Exception as exc:  # noqa: BLE001 - record and continue/stop gracefully
            log.exception("Stage '{st}' failed", st=stage)
            errors.append(f"{stage}: {exc}")
            break  # downstream stages depend on upstream output

    # Lineage after data stages (or standalone).
    if args.stage in {"all", "lineage"} and not errors:
        lineage_builder.run(settings)

    duration = round(time.perf_counter() - started_perf, 3)
    status = "failed" if errors else ("partial" if any(m.status != "success" for m in all_metrics) else "success")

    execution = PipelineExecution(
        pipeline_name=f"medallion:{args.stage}",
        batch_id=batch_id,
        start_time=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time=utc_now_iso(),
        duration_seconds=duration,
        stages_run=stages or ["lineage"],
        datasets_processed=sorted({m.dataset for m in all_metrics}),
        rows_processed=int(sum(m.rows_written for m in all_metrics)),
        status=status,
        stage_metrics=all_metrics,
        errors=errors,
        output_locations={
            "bronze": str(settings.bronze_path),
            "silver": str(settings.silver_path),
            "gold": str(settings.gold_path),
            "reports": str(settings.reports_path),
        },
    )
    append_execution_history(execution, settings.reports_path)
    write_json(execution.model_dump(), settings.reports_path / "execution_summary.json")
    write_json(
        {
            "batch_id": batch_id,
            "status": status,
            "duration_seconds": duration,
            "stages_run": stages or ["lineage"],
            "rows_processed": execution.rows_processed,
            "per_stage": [
                {"stage": s, "datasets": [m.dataset for m in all_metrics if m.stage == s],
                 "rows_written": sum(m.rows_written for m in all_metrics if m.stage == s),
                 "rows_rejected": sum(m.rows_rejected for m in all_metrics if m.stage == s)}
                for s in STAGE_ORDER if any(m.stage == s for m in all_metrics)
            ],
            "errors": errors,
        },
        settings.reports_path / "pipeline_summary.json",
    )

    log.info("Pipeline '{s}' {status} in {d:.2f}s — {rows} rows",
             s=args.stage, status=status, d=duration, rows=execution.rows_processed)
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
