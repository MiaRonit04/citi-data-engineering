"""Silver pipeline — turns raw Bronze into clean, trusted, validated datasets.

Per-dataset flow: read Bronze → standardize → detect/remove duplicates →
schema-validate. Then a cross-dataset relationship-validation pass quarantines
orphans/dangling references. Finally every trusted frame is written to Silver
Parquet and quality/cleaning/validation reports are emitted as JSON.

Design guarantees: deterministic (stable sorts), idempotent (partition
overwrite), recoverable (per-dataset isolation), observable (StageMetrics +
structured logs), and fully auditable (quarantine + reports).
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from etl.common.config import Settings, get_settings, load_source_registry
from etl.common.logging import get_logger
from etl.common.metadata import StageMetrics
from etl.common.utils import (
    new_batch_id,
    read_latest_parquet,
    utc_now,
    write_json,
    write_parquet,
)
from etl.silver.duplicate_detection import (
    split_full_row_duplicates,
    split_key_duplicates,
)
from etl.silver.quarantine import quarantine
from etl.silver.relationship_validation import validate_relationships
from etl.silver.schema_validation import validate_schema
from etl.silver.transforms import TRANSFORMS


def _missing_ratio(df: pd.DataFrame) -> float:
    """Fraction of null cells across the whole frame."""
    if df.empty:
        return 0.0
    return float(df.isna().sum().sum()) / float(df.size)


def _quality_score(schema_valid: float, rel_valid: float, dup_ratio: float, missing: float) -> float:
    """Composite 0..1 quality score (higher is better)."""
    return round(
        0.35 * schema_valid + 0.35 * rel_valid + 0.15 * (1 - dup_ratio) + 0.15 * (1 - missing),
        4,
    )


def run(batch_id: str | None = None, settings: Settings | None = None) -> list[StageMetrics]:
    """Execute the Silver stage for every registered dataset."""
    settings = settings or get_settings()
    settings.ensure_directories()
    batch_id = batch_id or new_batch_id("SILVER")
    ts = utc_now()
    log = get_logger("silver", batch_id=batch_id)

    registry = {s["dataset"]: s for s in load_source_registry(settings)}
    metrics: list[StageMetrics] = []
    cleaning_summary: dict[str, Any] = {}
    validation_summary: dict[str, Any] = {}
    quality_metrics: dict[str, Any] = {}

    standardized: dict[str, pd.DataFrame] = {}
    per_dataset_state: dict[str, dict[str, Any]] = {}

    # ── Phase 1: per-dataset standardize + dedupe + schema ──────────────────
    for dataset, source in registry.items():
        started = time.perf_counter()
        state: dict[str, Any] = {"rejected": 0, "rows_in": 0, "dup_removed": 0,
                                 "schema_invalid": 0, "status": "success", "errors": []}
        try:
            bronze = read_latest_parquet(settings.bronze_path, dataset)
            state["rows_in"] = len(bronze)

            transform = TRANSFORMS[dataset]
            df, stats = transform(bronze)
            cleaning_summary[dataset] = stats

            # Duplicates: full-row then natural-key.
            df, full_dups = split_full_row_duplicates(df)
            if not full_dups.empty:
                state["rejected"] += quarantine(
                    full_dups, dataset, "DUPLICATE_FULL_ROW", "identical across all columns",
                    batch_id, settings=settings)
            key = source.get("natural_key", [])
            if key:
                df, key_dups = split_key_duplicates(df, key)
                if not key_dups.empty:
                    state["rejected"] += quarantine(
                        key_dups, dataset, "DUPLICATE_NATURAL_KEY",
                        f"duplicate on {key}", batch_id, settings=settings)
                    state["dup_removed"] += len(key_dups)
            state["dup_removed"] += len(full_dups)

            # Schema validation (post-standardization contract).
            df, invalid, schema_sum = validate_schema(df, dataset)
            validation_summary[dataset] = {"schema": schema_sum}
            if not invalid.empty:
                state["schema_invalid"] = len(invalid)
                state["rejected"] += quarantine(
                    invalid, dataset, "SCHEMA_VIOLATION",
                    "failed Pandera schema", batch_id, settings=settings)

            standardized[dataset] = df.reset_index(drop=True)
            state["execution_seconds"] = round(time.perf_counter() - started, 3)
        except Exception as exc:  # noqa: BLE001 - per-dataset isolation
            log.exception("Silver transform failed for '{ds}'", ds=dataset)
            state.update(status="failed", errors=[str(exc)],
                         execution_seconds=round(time.perf_counter() - started, 3))
        per_dataset_state[dataset] = state

    # ── Phase 2: cross-dataset relationship validation ──────────────────────
    rel = validate_relationships(standardized)
    for action in rel.quarantine:
        n = quarantine(action.rows, action.dataset, action.reason, action.rule,
                       batch_id, settings=settings)
        per_dataset_state[action.dataset]["rejected"] += n
    for ds, m in rel.metrics.items():
        validation_summary.setdefault(ds, {})["relationships"] = m
    trusted = rel.frames

    # ── Phase 3: persist Silver + quality metrics ───────────────────────────
    for dataset, df in trusted.items():
        state = per_dataset_state[dataset]
        out_file = write_parquet(df, settings.silver_path, dataset, settings=settings, ts=ts)

        rows_in = max(state["rows_in"], 1)
        dup_ratio = state["dup_removed"] / rows_in
        schema_valid = 1 - (state["schema_invalid"] / rows_in)
        rel_m = validation_summary.get(dataset, {}).get("relationships", {})
        rel_valid = (rel_m.get("valid_rows", len(df)) / rows_in) if "valid_rows" in rel_m else 1.0
        missing = _missing_ratio(df)
        score = _quality_score(schema_valid, rel_valid, dup_ratio, missing)

        quality_metrics[dataset] = {
            "rows_in": state["rows_in"],
            "rows_out": len(df),
            "rejected": state["rejected"],
            "duplicate_ratio": round(dup_ratio, 4),
            "schema_valid_ratio": round(schema_valid, 4),
            "relationship_valid_ratio": round(rel_valid, 4),
            "missing_ratio": round(missing, 4),
            "quality_score": score,
            "below_threshold": score < settings.quality_min_schema_valid,
        }
        metrics.append(StageMetrics(
            stage="silver", dataset=dataset, batch_id=batch_id,
            rows_read=state["rows_in"], rows_written=len(df),
            rows_rejected=state["rejected"], execution_seconds=state.get("execution_seconds", 0.0),
            output_path=str(out_file), status=state["status"], errors=state["errors"],
        ))
        log.info("Silver '{ds}': {out}/{ins} rows, {rej} rejected, score={s}",
                 ds=dataset, out=len(df), ins=state["rows_in"], rej=state["rejected"], s=score)

    # ── Reports ─────────────────────────────────────────────────────────────
    overall = {
        "batch_id": batch_id,
        "datasets": len(trusted),
        "total_rows_out": int(sum(len(d) for d in trusted.values())),
        "total_rejected": int(sum(s["rejected"] for s in per_dataset_state.values())),
        "mean_quality_score": round(
            sum(q["quality_score"] for q in quality_metrics.values()) / max(len(quality_metrics), 1), 4),
        "per_dataset": quality_metrics,
    }
    write_json(overall, settings.reports_path / "quality_metrics.json")
    write_json({"batch_id": batch_id, "datasets": cleaning_summary},
               settings.reports_path / "cleaning_summary.json")
    write_json({"batch_id": batch_id, "datasets": validation_summary},
               settings.reports_path / "validation_summary.json")

    log.info("Silver complete — {n} datasets, {rej} rejected, mean quality {q}",
             n=len(trusted), rej=overall["total_rejected"], q=overall["mean_quality_score"])
    return metrics


if __name__ == "__main__":  # pragma: no cover
    run()
