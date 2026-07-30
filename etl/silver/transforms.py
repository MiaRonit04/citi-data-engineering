"""Dataset-specific standardization transforms.

Each transform takes a *cleaned* Bronze DataFrame and returns
``(standardized_df, stats)``. ``stats`` records every coercion (date-parse
failures, invalid allocations, non-numeric impact scores …) so the quality
report reflects exactly what changed — nothing is mutated silently.

Transforms compose the generic primitives from :mod:`data_cleaning` and
:mod:`data_standardization`; they contain no IO.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from etl.common.config import get_settings
from etl.silver.data_cleaning import clean_text_columns
from etl.silver.data_standardization import (
    bounded_int,
    canonical_department,
    canonical_email,
    canonical_employment_type,
    canonical_team_code,
    coerce_numeric,
    parse_month,
    standardize_date_series,
)


def _std_dates(df: pd.DataFrame, columns: list[str], stats: dict[str, Any]) -> None:
    """Standardize each date column in place; record parse-failure counts."""
    for col in columns:
        if col in df.columns:
            iso, failed = standardize_date_series(df[col])
            df[col] = iso
            stats.setdefault("date_parse_failures", {})[col] = int(failed.sum())


def transform_employees(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, Any] = {}
    df = clean_text_columns(df)
    df["email_canonical"] = df["email"].map(canonical_email)
    df["department"] = df["department"].map(canonical_department)
    df["employment_type"] = df["employment_type"].map(canonical_employment_type)
    _std_dates(df, ["hire_date"], stats)
    return df, stats


def transform_contractor_roster(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, Any] = {}
    df = clean_text_columns(df)
    df["email_canonical"] = df["email"].map(canonical_email)
    _std_dates(df, ["start_date", "end_date"], stats)
    return df, stats


def transform_team_membership(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, Any] = {}
    settings = get_settings()
    df = clean_text_columns(df)
    df["team_code"] = df["team_code"].map(canonical_team_code)
    df["employee_email_canonical"] = df["employee_email"].map(canonical_email)

    lo, hi = settings.allocation_min, settings.allocation_max
    bounded = df["allocation_pct"].map(lambda v: bounded_int(v, lo, hi))
    df["allocation_pct"] = pd.array([b[0] for b in bounded], dtype="Int64")
    invalid = sum(1 for b in bounded if not b[1])
    stats["invalid_allocation"] = int(invalid)

    _std_dates(df, ["start_date", "end_date"], stats)
    return df, stats


def transform_teams(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, Any] = {}
    df = df.rename(columns={
        "organization.org_id": "org_id",
        "organization.org_name": "org_name",
    })
    df = clean_text_columns(df)
    df["team_leader_email_canonical"] = df["team_leader_email"].map(canonical_email)
    df["reporting_manager_email_canonical"] = df["reporting_manager_email"].map(canonical_email)
    _std_dates(df, ["formed_date"], stats)
    return df, stats


def transform_monthly_achievements(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, Any] = {}
    df = clean_text_columns(df)
    df["month"] = df["month"].map(parse_month)
    df["impact_score_raw"] = df["impact_score"]
    numeric = df["impact_score"].map(coerce_numeric)
    df["impact_score"] = pd.to_numeric(numeric, errors="coerce")
    stats["non_numeric_impact_score"] = int(
        (df["impact_score"].isna() & df["impact_score_raw"].notna()).sum()
    )
    return df, stats


def transform_locations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    return clean_text_columns(df), {}


def transform_organizations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = clean_text_columns(df)
    df["org_leader_email"] = df["org_leader_email"].map(canonical_email)
    return df, {}


TRANSFORMS: dict[str, Callable[[pd.DataFrame], tuple[pd.DataFrame, dict]]] = {
    "employees": transform_employees,
    "contractor_roster": transform_contractor_roster,
    "team_membership": transform_team_membership,
    "teams": transform_teams,
    "monthly_achievements": transform_monthly_achievements,
    "locations": transform_locations,
    "organizations": transform_organizations,
}
