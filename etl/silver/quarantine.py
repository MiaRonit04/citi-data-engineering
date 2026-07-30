"""Quarantine utilities — rejected records are preserved, never deleted.

Every row removed by cleaning, dedupe or relationship validation is written to
``lakehouse/quarantine/<dataset>/`` as Parquet, annotated with the reason,
pipeline stage, rule violated, batch id and timestamp. This makes every
rejection auditable and recoverable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from etl.common.config import Settings, get_settings
from etl.common.logging import get_logger
from etl.common.utils import utc_now_iso, write_parquet


def quarantine(
    df: pd.DataFrame,
    dataset: str,
    reason: str,
    rule: str,
    batch_id: str,
    *,
    stage: str = "silver",
    settings: Settings | None = None,
) -> int:
    """Persist ``df`` to the quarantine zone with audit annotations.

    Returns the number of quarantined rows. A no-op (returns 0) for empty input.
    """
    if df.empty:
        return 0
    settings = settings or get_settings()
    log = get_logger("silver", dataset=dataset, batch_id=batch_id)

    annotated = df.copy()
    annotated["_quarantine_reason"] = reason
    annotated["_quarantine_rule"] = rule
    annotated["_quarantine_stage"] = stage
    annotated["_quarantine_batch_id"] = batch_id
    annotated["_quarantine_timestamp"] = utc_now_iso()

    # File name keyed by reason so multiple reasons for one dataset coexist.
    safe_reason = reason.lower().replace(" ", "_")
    write_parquet(
        annotated, settings.quarantine_path, dataset,
        settings=settings, partitioned=False, filename=f"{safe_reason}.parquet",
        clear_dir=False,
    )
    log.warning(
        "Quarantined {n} rows from '{ds}' — {reason} ({rule})",
        n=len(annotated), ds=dataset, reason=reason, rule=rule,
    )
    return len(annotated)
