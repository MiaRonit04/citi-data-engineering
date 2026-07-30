"""Unit tests for standardization primitives (dates, emails, categoricals, numerics)."""

from __future__ import annotations

import pandas as pd
import pytest

from etl.silver.data_standardization import (
    bounded_int,
    canonical_department,
    canonical_email,
    canonical_employment_type,
    canonical_team_code,
    coerce_numeric,
    parse_date,
    parse_month,
    standardize_date_series,
)


@pytest.mark.parametrize("raw,expected", [
    ("2018-08-10", "2018-08-10"),
    ("11/18/2016", "2016-11-18"),
    ("22-Jan-2021", "2021-01-22"),
    ("2024/02/01", "2024-02-01"),
    ("February 10, 2024", "2024-02-10"),
    ("12-May-2022", "2022-05-12"),
    ("", None),
    ("not a date", None),
])
def test_parse_date_multiple_formats(raw, expected):
    assert parse_date(raw) == expected


def test_standardize_date_series_flags_failures():
    s = pd.Series(["2020-01-01", "garbage", ""])
    iso, failed = standardize_date_series(s)
    assert iso.tolist() == ["2020-01-01", None, None]
    assert failed.tolist() == [False, True, False]  # blank is not a failure


@pytest.mark.parametrize("raw,expected", [
    ("2026-07", "2026-07"),
    ("March 2026", "2026-03"),
    ("February 2026", "2026-02"),
    ("", None),
])
def test_parse_month(raw, expected):
    assert parse_month(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("  JOHN.DOE@ACME-INC.COM ", "john.doe@acme-inc.com"),
    ("patricia_lane@acme-inc.com", "patricia.lane@acme-inc.com"),  # separator unified
    ("a@acmeinc.com", "a@acme-inc.com"),                            # domain repaired
    ("", None),
])
def test_canonical_email(raw, expected):
    assert canonical_email(raw) == expected


def test_email_unifies_underscore_and_dot():
    assert canonical_email("a_b@x.com") == canonical_email("a.b@x.com")


@pytest.mark.parametrize("raw,expected", [
    ("finance", "Finance"), ("FINANCE", "Finance"),
    ("it operations", "IT Operations"), ("data & analytics", "Data & Analytics"),
])
def test_canonical_department(raw, expected):
    assert canonical_department(raw) == expected


@pytest.mark.parametrize("raw", ["full-time", "FT", "Full Time", "Employee", "FTE", "Full-Time"])
def test_employment_type_collapses_to_full_time(raw):
    assert canonical_employment_type(raw) == "Full-Time"


@pytest.mark.parametrize("raw,expected", [
    ("tm006", "TM-006"), ("tm-5", "TM-005"), ("TM 12", "TM-012"), ("TM-001", "TM-001"),
])
def test_canonical_team_code(raw, expected):
    assert canonical_team_code(raw) == expected


def test_coerce_numeric_handles_text():
    assert coerce_numeric("2.2") == 2.2
    assert coerce_numeric("Low") is None
    assert coerce_numeric("") is None


@pytest.mark.parametrize("raw,ok", [("100", True), ("0", True), ("120", False), ("-10", False), ("Low", False)])
def test_bounded_int_enforces_range(raw, ok):
    value, valid = bounded_int(raw, 0, 100)
    assert valid is ok
    if not ok:
        assert value is None
