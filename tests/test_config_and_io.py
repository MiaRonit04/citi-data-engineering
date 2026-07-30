"""Tests for configuration loading and Parquet IO idempotency."""

from __future__ import annotations

import pandas as pd

from etl.common.config import get_settings, load_source_registry
from etl.common.utils import dataframe_sha256, new_batch_id, write_parquet


def test_settings_load_and_paths_absolute():
    s = get_settings()
    assert s.bronze_path.is_absolute()
    assert 0 <= s.non_direct_ratio_threshold <= 1
    assert s.allocation_min < s.allocation_max


def test_source_registry_has_seven_sources():
    sources = load_source_registry()
    assert len(sources) == 7
    names = {s["dataset"] for s in sources}
    assert {"employees", "teams", "organizations"} <= names


def test_sqlalchemy_url_derived():
    s = get_settings()
    url = s.sqlalchemy_url
    assert url.startswith("postgresql+psycopg2://")


def test_batch_id_unique_and_prefixed():
    a, b = new_batch_id("X"), new_batch_id("X")
    assert a != b and a.startswith("X-")


def test_write_parquet_idempotent(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    p1 = write_parquet(df, tmp_path, "ds", partitioned=False)
    h1 = dataframe_sha256(pd.read_parquet(p1))
    p2 = write_parquet(df, tmp_path, "ds", partitioned=False)  # rewrite
    # Only one file remains; content identical → idempotent.
    assert p1 == p2
    assert len(list((tmp_path / "ds").glob("*.parquet"))) == 1
    assert dataframe_sha256(pd.read_parquet(p2)) == h1
