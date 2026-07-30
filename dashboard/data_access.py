"""Gold-only data access for the analytics layer (dashboard + notebook).

This is the **single boundary** through which the analytics layer reads data. It
exposes the seven Gold datasets and the generated JSON reports — and nothing
from Bronze or Silver, enforcing the architectural rule that visualisation
consumes only Gold.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from etl.common.config import get_settings
from etl.common.utils import read_latest_parquet

GOLD_DATASETS = [
    "team_members", "team_locations", "monthly_achievements", "leader_colocation",
    "non_direct_leaders", "non_direct_staff_ratio", "organization_reporting",
]

QUESTION_TITLES = {
    "team_members": "Q1 · Who are the members of each team?",
    "team_locations": "Q2 · Where are the teams located?",
    "monthly_achievements": "Q3 · What are the monthly achievements of each team?",
    "leader_colocation": "Q4 · Teams whose leader is not co-located with the majority",
    "non_direct_leaders": "Q5 · Teams whose leaders are non-direct staff",
    "non_direct_staff_ratio": "Q6 · Teams with a non-direct staff ratio > 20%",
    "organization_reporting": "Q7 · Teams reporting directly to organization leaders",
}


def load_gold(dataset: str) -> pd.DataFrame:
    """Load a single Gold dataset (latest partition)."""
    if dataset not in GOLD_DATASETS:
        raise ValueError(f"'{dataset}' is not a Gold dataset")
    return read_latest_parquet(get_settings().gold_path, dataset)


def load_all_gold() -> dict[str, pd.DataFrame]:
    """Load every Gold dataset keyed by name."""
    return {d: load_gold(d) for d in GOLD_DATASETS}


def load_report(name: str) -> dict:
    """Load a generated JSON report from ``reports/`` (empty dict if absent)."""
    path = get_settings().reports_path / f"{name}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_execution_history() -> pd.DataFrame:
    """Load the pipeline execution-history ledger as a DataFrame."""
    path = get_settings().reports_path / "execution_history.jsonl"
    if not path.exists():
        return pd.DataFrame()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to CSV bytes for download buttons."""
    return df.to_csv(index=False).encode("utf-8")


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to Parquet bytes for download buttons."""
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()


def gold_available() -> bool:
    """True if at least one Gold dataset exists on disk."""
    gold_dir: Path = get_settings().gold_path
    return any((gold_dir / d).exists() for d in GOLD_DATASETS)
