"""File readers for Bronze ingestion.

Bronze reads raw data **exactly as received** — every column is read as a string
so nothing is coerced, reformatted, or lost. JSON is flattened one level (for the
nested ``teams.organization`` object) but values are otherwise untouched.

Adding a new format is a matter of registering a reader in ``_READERS``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pandas as pd

from etl.common.exceptions import IngestionError
from etl.common.logging import get_logger


def _read_csv_raw(path: Path) -> pd.DataFrame:
    """Read a CSV with *no* type inference — all values remain raw strings."""
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,   # do not turn '', 'NA' into NaN — Bronze is verbatim
        na_filter=False,
        encoding="utf-8",
    )


def _read_json_raw(path: Path) -> pd.DataFrame:
    """Read a JSON array, flattening one level of nesting; values kept as-is."""
    with Path(path).open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise IngestionError(f"Expected a JSON array in {path}, got {type(payload).__name__}")
    # json_normalize flattens nested objects (e.g. organization.org_id) but keeps
    # scalar values verbatim. Cast everything to string to preserve rawness.
    df = pd.json_normalize(payload)
    return df.astype("string").astype(object).where(df.notna(), None)


_READERS: dict[str, Callable[[Path], pd.DataFrame]] = {
    "csv": _read_csv_raw,
    "json": _read_json_raw,
}


def read_source(path: Path, fmt: str) -> pd.DataFrame:
    """Dispatch to the correct raw reader for ``fmt``.

    Raises
    ------
    IngestionError
        If the format is unsupported or the file cannot be parsed.
    """
    log = get_logger("bronze", dataset=path.stem)
    reader = _READERS.get(fmt.lower())
    if reader is None:
        raise IngestionError(f"Unsupported source format '{fmt}' for {path}")
    try:
        df = reader(path)
    except IngestionError:
        raise
    except Exception as exc:  # noqa: BLE001 - convert any read error to typed error
        raise IngestionError(f"Failed to read {path} as {fmt}: {exc}") from exc
    log.debug("Read {rows} raw rows from {path}", rows=len(df), path=path.name)
    return df


def validate_readable(path: Path, required_columns: list[str], fmt: str) -> list[str]:
    """Pre-ingest checks. Returns a list of warnings (empty ⇒ all good).

    Verifies the file exists, is non-empty and readable, and that every
    ``required_columns`` entry is present. Missing required columns raise, since
    a structurally broken source cannot be ingested; softer issues are warnings.
    """
    warnings: list[str] = []
    if not path.exists():
        raise IngestionError(f"Source file does not exist: {path}")
    if path.stat().st_size == 0:
        raise IngestionError(f"Source file is empty: {path}")

    # Peek at the header only (cheap) to confirm required columns exist.
    if fmt.lower() == "csv":
        header = pd.read_csv(path, nrows=0).columns.tolist()
    else:
        with Path(path).open(encoding="utf-8") as fh:
            first = json.load(fh)
        header = list(pd.json_normalize(first[:1]).columns) if first else []

    missing = [c for c in required_columns if c not in header]
    if missing:
        raise IngestionError(f"{path.name} missing required columns: {missing}")
    return warnings
