"""Deterministic duplicate detection & removal.

Two kinds of duplicates are handled:

* **Full-row duplicates** — identical across every column.
* **Key duplicates** — same natural/primary key, differing rows.

Both are resolved deterministically (stable sort + keep-first) so re-runs always
produce identical output. Removed rows are returned so the caller can quarantine
them with an appropriate reason.
"""

from __future__ import annotations

import pandas as pd


def split_full_row_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(deduped, removed)`` for exact full-row duplicates (keep first)."""
    dup_mask = df.duplicated(keep="first")
    return df[~dup_mask].copy(), df[dup_mask].copy()


def split_key_duplicates(
    df: pd.DataFrame,
    key: list[str],
    sort_by: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(deduped, removed)`` for duplicate keys.

    A stable sort on ``sort_by`` (defaulting to ``key``) makes "keep first"
    deterministic regardless of input ordering.
    """
    if not key or not all(k in df.columns for k in key):
        return df.copy(), df.iloc[0:0].copy()
    ordered = df.sort_values(by=(sort_by or key), kind="stable", na_position="last")
    dup_mask = ordered.duplicated(subset=key, keep="first")
    deduped = ordered[~dup_mask].sort_index()
    removed = ordered[dup_mask].sort_index()
    return deduped.copy(), removed.copy()
