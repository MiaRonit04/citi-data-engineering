"""Integration tests over the built Gold layer and business-question correctness.

These skip automatically if the pipeline output is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from etl.common.config import get_settings
from etl.common.utils import read_latest_parquet
from etl.gold.gold_business_questions import (
    build_non_direct_leaders,
    build_organization_reporting,
)

GRAIN_UNIQUE = {
    "team_locations": "team_id",
    "leader_colocation": "team_id",
    "non_direct_leaders": "team_id",
    "non_direct_staff_ratio": "team_id",
    "organization_reporting": "team_id",
}


def _load(name: str) -> pd.DataFrame:
    try:
        return read_latest_parquet(get_settings().gold_path, name)
    except FileNotFoundError:
        pytest.skip("Gold not built; run `python run_pipeline.py all`")


def _silver() -> dict[str, pd.DataFrame]:
    s = get_settings()
    names = ["employees", "contractor_roster", "team_membership", "teams",
             "monthly_achievements", "locations", "organizations"]
    try:
        return {n: read_latest_parquet(s.silver_path, n) for n in names}
    except FileNotFoundError:
        pytest.skip("Silver not built; run `python run_pipeline.py silver`")


def test_exactly_seven_gold_datasets():
    from dashboard.data_access import GOLD_DATASETS
    s = get_settings()
    present = [d for d in GOLD_DATASETS if (s.gold_path / d).exists()]
    if not present:
        pytest.skip("Gold not built")
    assert len(present) == 7


@pytest.mark.parametrize("name,grain", list(GRAIN_UNIQUE.items()))
def test_grain_uniqueness(name, grain):
    df = _load(name)
    assert df.duplicated(subset=[grain]).sum() == 0


def test_non_direct_ratio_bounds_and_flag():
    df = _load("non_direct_staff_ratio")
    assert df["ratio"].between(0, 1).all()
    threshold = get_settings().non_direct_ratio_threshold
    # flag must equal ratio > threshold exactly
    assert (df["above_threshold"] == (df["ratio"] > threshold)).all()


def test_q7_cross_signal_agreement():
    frames = _silver()
    org = build_organization_reporting(frames)
    org_leaders = set(frames["organizations"]["org_leader_email"])
    by_type = int((frames["teams"]["reports_to_type"].str.strip().str.lower() == "org leader").sum())
    by_manager = int(frames["teams"]["reporting_manager_email_canonical"].isin(org_leaders).sum())
    by_status = int((org["reporting_status"] == "Direct to Org Leader").sum())
    assert by_type == by_manager == by_status


def test_q5_reconciles_with_silver_leader_type():
    frames = _silver()
    gold = build_non_direct_leaders(frames)
    silver_nd = int((frames["teams"]["leader_staff_type"] == "non_direct").sum())
    gold_nd = int((gold["direct_or_non_direct"] == "Non-Direct").sum())
    assert silver_nd == gold_nd


def test_gold_builders_are_deterministic():
    """Building the same Gold dataset twice yields identical output (idempotent)."""
    frames = _silver()
    a = build_non_direct_leaders(frames)
    b = build_non_direct_leaders(frames)
    pd.testing.assert_frame_equal(a, b)
