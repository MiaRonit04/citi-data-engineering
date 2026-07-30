"""Shared pytest fixtures."""

from __future__ import annotations

import pandas as pd
import pytest

from etl.common.config import get_settings
from etl.common.utils import read_latest_parquet


@pytest.fixture(scope="session")
def settings():
    return get_settings()


def _gold_or_skip(name: str):
    s = get_settings()
    try:
        return read_latest_parquet(s.gold_path, name)
    except FileNotFoundError:
        pytest.skip(f"Gold dataset '{name}' not built; run `python run_pipeline.py all` first")


@pytest.fixture
def gold(request):
    """Load a Gold dataset by param, skipping if the pipeline hasn't run."""
    return _gold_or_skip(request.param)
