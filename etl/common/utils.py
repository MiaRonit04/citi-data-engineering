"""Reusable, side-effect-light helpers shared across ETL stages.

Grouped concerns: identifiers, hashing, retry/backoff, filesystem, JSON IO and
partitioned Parquet read/write. Keeping these here prevents duplicated logic in
the Bronze/Silver/Gold pipelines.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import pandas as pd

from etl.common.config import Settings, get_settings
from etl.common.exceptions import TransientError
from etl.common.logging import get_logger

T = TypeVar("T")


# ── Time & identifiers ──────────────────────────────────────────────────────
def utc_now() -> datetime:
    """Timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp string (second precision)."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def new_batch_id(prefix: str = "BATCH") -> str:
    """Generate a unique, sortable batch id, e.g. ``BATCH-20260730-ab12cd34``."""
    return f"{prefix}-{utc_now():%Y%m%d}-{uuid.uuid4().hex[:8]}"


def partition_kwargs(ts: datetime | None = None) -> dict[str, str]:
    """Return Hive-style ``year=/month=/day=`` partition components for ``ts``."""
    ts = ts or utc_now()
    return {"year": f"{ts:%Y}", "month": f"{ts:%m}", "day": f"{ts:%d}"}


# ── Hashing ─────────────────────────────────────────────────────────────────
def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file (constant memory)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def dataframe_sha256(df: pd.DataFrame) -> str:
    """Deterministic content hash of a DataFrame (order-sensitive)."""
    row_hashes = pd.util.hash_pandas_object(df, index=False).values
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()


# ── Retry / backoff ─────────────────────────────────────────────────────────
def retry(
    attempts: int | None = None,
    backoff: float | None = None,
    exceptions: tuple[type[Exception], ...] = (TransientError,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry ``fn`` with exponential backoff on ``exceptions``.

    Attempts / backoff default to the values in :class:`Settings`.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            settings = get_settings()
            max_attempts = attempts or settings.retry_count
            base = backoff if backoff is not None else settings.retry_backoff_seconds
            log = get_logger("retry", dataset=fn.__name__)
            last: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:  # noqa: PERF203 - retry is intentional
                    last = exc
                    if attempt == max_attempts:
                        break
                    delay = base * (2 ** (attempt - 1))
                    log.warning(
                        "Attempt {a}/{m} failed: {e}. Retrying in {d:.1f}s",
                        a=attempt, m=max_attempts, e=exc, d=delay,
                    )
                    time.sleep(delay)
            assert last is not None
            raise last

        return wrapper

    return decorator


# ── Filesystem & JSON ───────────────────────────────────────────────────────
def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if absent; return it."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path)


def write_json(obj: Any, path: Path, *, indent: int = 2) -> Path:
    """Atomically write ``obj`` as pretty JSON to ``path``."""
    path = Path(path)
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent, default=str, ensure_ascii=False)
    tmp.replace(path)
    return path


def read_json(path: Path) -> Any:
    """Load JSON from ``path``."""
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def human_bytes(num: float) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"


# ── Partitioned Parquet IO ──────────────────────────────────────────────────
def write_parquet(
    df: pd.DataFrame,
    base_dir: Path,
    dataset: str,
    *,
    settings: Settings | None = None,
    partitioned: bool = True,
    ts: datetime | None = None,
    filename: str = "data.parquet",
    clear_dir: bool = True,
) -> Path:
    """Write ``df`` to ``base_dir/dataset[/year=/month=/day=]/filename``.

    Idempotent: when ``clear_dir`` is True the target partition directory is
    cleared before writing so a re-run for the same date never accumulates
    duplicate part files. Set ``clear_dir=False`` when a directory legitimately
    holds several files (e.g. quarantine, one Parquet per rejection reason) —
    only the exact ``filename`` is overwritten.
    Returns the path of the written Parquet file.
    """
    settings = settings or get_settings()
    target_dir = Path(base_dir) / dataset
    if partitioned:
        for key, val in partition_kwargs(ts).items():
            target_dir = target_dir / f"{key}={val}"
    ensure_dir(target_dir)

    out_file = target_dir / filename
    if clear_dir:
        # Idempotency: remove any pre-existing part files in this partition.
        for existing in target_dir.glob("*.parquet"):
            existing.unlink()
    elif out_file.exists():
        out_file.unlink()
    df.to_parquet(out_file, engine="pyarrow", compression=settings.parquet_compression, index=False)
    return out_file


def read_latest_parquet(base_dir: Path, dataset: str) -> pd.DataFrame:
    """Read the most recent partition of ``dataset`` under ``base_dir``.

    Works for both partitioned (``year=/month=/day=``) and flat layouts by
    globbing every ``*.parquet`` beneath the dataset directory and, when
    partitioned, selecting the lexicographically latest partition path.
    """
    dataset_dir = Path(base_dir) / dataset
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset '{dataset}' not found under {base_dir}")
    files = sorted(dataset_dir.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files for dataset '{dataset}' under {dataset_dir}")
    # Latest partition = deepest/last path when Hive-partitioned.
    latest_partition = files[-1].parent
    part_files = sorted(latest_partition.glob("*.parquet"))
    return pd.concat((pd.read_parquet(f) for f in part_files), ignore_index=True)


def dir_size_bytes(path: Path) -> int:
    """Total size of every file beneath ``path`` (0 if missing)."""
    p = Path(path)
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def batched(iterable: Iterable[T], size: int) -> Iterable[list[T]]:
    """Yield successive ``size``-length lists from ``iterable``."""
    batch: list[T] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
