"""Bronze pipeline — orchestrates raw ingestion of every registered source.

Guarantees
----------
* **Immutable:** data is written exactly as read (all-string), no cleaning.
* **Isolated:** each dataset ingests independently; one failure does not abort
  the batch (``status='partial'`` is returned instead).
* **Idempotent:** re-running for the same ingest date overwrites the partition.
* **Observable:** every ingestion emits :class:`IngestionMetadata` and a
  :class:`StageMetrics`, plus structured logs.
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.bronze.ingest_files import read_source, validate_readable
from etl.common.config import Settings, get_settings, load_source_registry
from etl.common.exceptions import IngestionError
from etl.common.logging import get_logger
from etl.common.metadata import IngestionMetadata, StageMetrics, write_metadata
from etl.common.utils import (
    dataframe_sha256,
    file_sha256,
    new_batch_id,
    utc_now,
    write_parquet,
)


def ingest_one(
    source: dict,
    batch_id: str,
    ts,
    settings: Settings,
) -> tuple[StageMetrics, IngestionMetadata | None]:
    """Ingest a single source into Bronze. Never raises for data problems —
    returns a failed :class:`StageMetrics` so the batch can continue."""
    dataset = source["dataset"]
    log = get_logger("bronze", dataset=dataset, batch_id=batch_id)
    started = time.perf_counter()
    src_path = settings.datasets_path / source["relative_path"]

    try:
        validate_readable(src_path, source.get("required_columns", []), source["format"])
        df = read_source(src_path, source["format"])
        out_file = write_parquet(
            df, settings.bronze_path, dataset, settings=settings, ts=ts
        )
        duration = time.perf_counter() - started

        meta = IngestionMetadata(
            dataset=dataset,
            source_system=source["source_system"],
            source_filename=src_path.name,
            source_format=source["format"],
            batch_id=batch_id,
            row_count=len(df),
            column_count=df.shape[1],
            source_checksum=file_sha256(src_path),
            output_checksum=dataframe_sha256(df),
            source_size_bytes=src_path.stat().st_size,
            output_path=str(out_file),
            execution_seconds=round(duration, 3),
        )
        write_metadata(meta, out_file.parent / "_ingestion_metadata.json")

        log.info(
            "Ingested {rows} rows × {cols} cols in {d:.2f}s → {path}",
            rows=len(df), cols=df.shape[1], d=duration, path=out_file.name,
        )
        metrics = StageMetrics(
            stage="bronze", dataset=dataset, batch_id=batch_id,
            rows_read=len(df), rows_written=len(df),
            execution_seconds=round(duration, 3), output_path=str(out_file),
            status="success",
        )
        return metrics, meta

    except IngestionError as exc:
        duration = time.perf_counter() - started
        log.error("Ingestion failed for '{ds}': {e}", ds=dataset, e=exc)
        metrics = StageMetrics(
            stage="bronze", dataset=dataset, batch_id=batch_id,
            execution_seconds=round(duration, 3), status="failed",
            errors=[str(exc)],
        )
        return metrics, None


def run(batch_id: str | None = None, settings: Settings | None = None) -> list[StageMetrics]:
    """Run Bronze ingestion for all registered sources.

    Returns the list of :class:`StageMetrics` (one per dataset).
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    batch_id = batch_id or new_batch_id("BRONZE")
    ts = utc_now()
    log = get_logger("bronze", batch_id=batch_id)

    sources = load_source_registry(settings)
    log.info("Bronze batch {b} — {n} sources", b=batch_id, n=len(sources))

    metrics: list[StageMetrics] = []
    for source in sources:
        m, _ = ingest_one(source, batch_id, ts, settings)
        metrics.append(m)

    ok = sum(1 for m in metrics if m.status == "success")
    total_rows = sum(m.rows_written for m in metrics)
    log.info(
        "Bronze complete — {ok}/{n} datasets, {rows} rows",
        ok=ok, n=len(metrics), rows=total_rows,
    )
    return metrics


if __name__ == "__main__":  # pragma: no cover
    run()
