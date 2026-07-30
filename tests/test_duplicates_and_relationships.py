"""Unit tests for duplicate detection and relationship validation."""

from __future__ import annotations

import pandas as pd

from etl.silver.duplicate_detection import (
    split_full_row_duplicates,
    split_key_duplicates,
)
from etl.silver.relationship_validation import validate_relationships


def test_split_full_row_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    kept, removed = split_full_row_duplicates(df)
    assert len(kept) == 2 and len(removed) == 1


def test_split_key_duplicates_keep_first_deterministic():
    df = pd.DataFrame({"id": ["A", "A", "B"], "v": [2, 1, 3]})
    kept, removed = split_key_duplicates(df, ["id"], sort_by=["id", "v"])
    assert sorted(kept["id"]) == ["A", "B"]
    assert len(removed) == 1
    # keep-first after sort by v → the A row with v=1 survives
    assert kept[kept["id"] == "A"]["v"].iloc[0] == 1


def _mini_frames():
    employees = pd.DataFrame({
        "emp_id": ["EMP-1", "EMP-2"],
        "email_canonical": ["a@x.com", "b@x.com"],
        "manager_emp_id": ["EMP-2", "EMP-999"],  # second is a broken FK
    })
    contractors = pd.DataFrame({"contractor_id": ["CTR-1"], "email_canonical": ["c@x.com"]})
    teams = pd.DataFrame({
        "team_id": ["TM-001"],
        "team_leader_email_canonical": ["c@x.com"],   # contractor leader → non_direct
        "primary_office": ["LOC-01"], "org_id": ["ORG-01"],
    })
    membership = pd.DataFrame({
        "team_code": ["TM-001", "TM-001", "TM-999"],   # last is orphan team
        "employee_email_canonical": ["a@x.com", "zzz@x.com", "a@x.com"],  # middle orphan person
    })
    achievements = pd.DataFrame({
        "team_id": ["TM-001", None, None],
        "team_name": ["Alpha", "Alpha", None],   # last is orphan achievement
    })
    locations = pd.DataFrame({"location_code": ["LOC-01"]})
    organizations = pd.DataFrame({"org_id": ["ORG-01"]})
    return {
        "employees": employees, "contractor_roster": contractors, "teams": teams,
        "team_membership": membership, "monthly_achievements": achievements,
        "locations": locations, "organizations": organizations,
    }


def test_relationship_validation_classifies_and_quarantines():
    res = validate_relationships(_mini_frames())

    # Leader resolves to contractor → non_direct
    assert res.metrics["teams"]["leaders_non_direct"] == 1

    # Broken manager FK detected and nulled
    assert res.metrics["employees"]["broken_manager_fk"] == 1
    emp = res.frames["employees"]
    assert emp.loc[emp["emp_id"] == "EMP-2", "manager_emp_id"].isna().all()

    # Orphan team + orphan member quarantined (one each)
    reasons = {a.reason for a in res.quarantine}
    assert "ORPHAN_TEAM_CODE" in reasons
    assert "ORPHAN_MEMBER_EMAIL" in reasons
    assert "ORPHAN_ACHIEVEMENT" in reasons

    # Only the fully-valid membership row survives
    assert len(res.frames["team_membership"]) == 1
    assert res.frames["team_membership"]["staff_type"].iloc[0] == "direct"
