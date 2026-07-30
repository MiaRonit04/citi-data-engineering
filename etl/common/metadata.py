"""Metadata & observability models plus a lightweight metadata store.

These Pydantic models are the contract for what every stage records: ingestion
provenance, per-dataset metrics and end-to-end execution history. They are
serialised to JSON under ``reports/`` and ``lakehouse/**/_metadata`` so the
dashboard, notebook and auditors can trace exactly what happened.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from etl.common.utils import utc_now_iso, write_json

Stage = Literal["bronze", "silver", "gold"]
Status = Literal["success", "partial", "failed", "skipped"]


class IngestionMetadata(BaseModel):
    """Provenance captured for a single Bronze ingestion."""

    dataset: str
    source_system: str
    source_filename: str
    source_format: str
    batch_id: str
    load_timestamp: str = Field(default_factory=utc_now_iso)
    row_count: int
    column_count: int
    source_checksum: str
    output_checksum: str
    source_size_bytes: int
    output_path: str
    schema_version: str = "v1"
    execution_seconds: float
    status: Status = "success"
    warnings: list[str] = Field(default_factory=list)


class StageMetrics(BaseModel):
    """Operational metrics emitted by any stage for one dataset."""

    stage: Stage
    dataset: str
    batch_id: str
    rows_read: int = 0
    rows_written: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    validation_failures: int = 0
    retry_attempts: int = 0
    execution_seconds: float = 0.0
    output_path: str = ""
    status: Status = "success"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PipelineExecution(BaseModel):
    """End-to-end record of one pipeline run (any subset of stages)."""

    pipeline_name: str
    batch_id: str
    start_time: str
    end_time: str
    duration_seconds: float
    stages_run: list[str]
    datasets_processed: list[str]
    rows_processed: int
    status: Status
    stage_metrics: list[StageMetrics] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    output_locations: dict[str, str] = Field(default_factory=dict)


def append_execution_history(execution: PipelineExecution, reports_dir: Path) -> Path:
    """Append ``execution`` to the JSONL execution-history ledger."""
    history_file = Path(reports_dir) / "execution_history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as fh:
        fh.write(execution.model_dump_json() + "\n")
    return history_file


def write_metadata(model: BaseModel, path: Path) -> Path:
    """Serialise any metadata model to pretty JSON at ``path``."""
    return write_json(model.model_dump(), path)


def dump_models(models: list[BaseModel]) -> list[dict[str, Any]]:
    """Convert a list of Pydantic models to plain dicts (for aggregate reports)."""
    return [m.model_dump() for m in models]
