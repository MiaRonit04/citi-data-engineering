"""Schema validation with Pandera.

Each Silver dataset has a declarative :class:`DataFrameSchema` describing the
*post-standardization* contract: column presence, dtype, nullability, value
domains and uniqueness. Validation runs in **lazy** mode so all violations are
collected at once; failing rows are separated (for quarantine) rather than
aborting the run.
"""

from __future__ import annotations

import pandas as pd

try:  # pandera >= 0.20 splits the pandas backend into its own namespace
    import pandera.pandas as pa
    from pandera.pandas import Check, Column, DataFrameSchema
except Exception:  # pragma: no cover - fallback for older pandera
    import pandera as pa
    from pandera import Check, Column, DataFrameSchema

from etl.common.logging import get_logger

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
_ISO_MONTH = r"^\d{4}-\d{2}$"
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _nullable_str(pattern: str | None = None, **kw) -> Column:
    checks = [Check.str_matches(pattern)] if pattern else None
    return Column(str, checks=checks, nullable=True, required=True, **kw)


# ── Per-dataset Silver schemas ──────────────────────────────────────────────
SILVER_SCHEMAS: dict[str, DataFrameSchema] = {
    "locations": DataFrameSchema(
        {
            "location_code": Column(str, Check.str_matches(r"^LOC-\d{2}$"), nullable=False, unique=True),
            "city": Column(str, nullable=False),
            "country": Column(str, nullable=False),
            "region": Column(str, Check.isin(["AMER", "EMEA", "APAC"]), nullable=False),
            "timezone": Column(str, nullable=True),
        },
        strict=False, coerce=True,
    ),
    "organizations": DataFrameSchema(
        {
            "org_id": Column(str, Check.str_matches(r"^ORG-\d{2}$"), nullable=False, unique=True),
            "org_name": Column(str, nullable=False),
            "org_leader_email": Column(str, Check.str_matches(_EMAIL), nullable=False),
        },
        strict=False, coerce=True,
    ),
    "employees": DataFrameSchema(
        {
            "emp_id": Column(str, Check.str_matches(r"^EMP-\d+$"), nullable=False, unique=True),
            "full_name": Column(str, nullable=True),
            "email": Column(str, Check.str_matches(_EMAIL), nullable=True),
            "email_canonical": Column(str, nullable=True),
            "department": Column(str, nullable=True),
            "location_code": Column(str, nullable=True),
            "employment_type": Column(str, nullable=True),
            "manager_emp_id": Column(str, nullable=True),
            "hire_date": _nullable_str(_ISO_DATE),
            "status": Column(str, Check.isin(["Active", "Terminated"]), nullable=True),
        },
        strict=False, coerce=True,
    ),
    "contractor_roster": DataFrameSchema(
        {
            "contractor_id": Column(str, Check.str_matches(r"^CTR-\d+$"), nullable=False, unique=True),
            "email": Column(str, Check.str_matches(_EMAIL), nullable=True),
            "email_canonical": Column(str, nullable=True),
            "agency": Column(str, nullable=True),
            "location_code": Column(str, nullable=True),
            "engagement_type": Column(str, nullable=True),
            "start_date": _nullable_str(_ISO_DATE),
            "end_date": _nullable_str(_ISO_DATE),
            "status": Column(str, Check.isin(["Active", "Ended"]), nullable=True),
        },
        strict=False, coerce=True,
    ),
    "teams": DataFrameSchema(
        {
            "team_id": Column(str, Check.str_matches(r"^TM-\d+$"), nullable=False, unique=True),
            "team_name": Column(str, nullable=False),
            "team_leader_email": Column(str, nullable=True),
            "team_leader_email_canonical": Column(str, nullable=True),
            "primary_office": Column(str, nullable=True),
            "reports_to_type": Column(str, nullable=True),
            "reporting_manager_email": Column(str, nullable=True),
            "reporting_manager_email_canonical": Column(str, nullable=True),
            "formed_date": _nullable_str(_ISO_DATE),
            "org_id": Column(str, nullable=True),
            "org_name": Column(str, nullable=True),
        },
        strict=False, coerce=True,
    ),
    "team_membership": DataFrameSchema(
        {
            "team_code": Column(str, Check.str_matches(r"^TM-\d+$"), nullable=True),
            "employee_email": Column(str, nullable=True),
            "employee_email_canonical": Column(str, nullable=True),
            "role": Column(str, nullable=True),
            "allocation_pct": Column("Int64", Check.in_range(0, 100), nullable=True),
            "start_date": _nullable_str(_ISO_DATE),
            "end_date": _nullable_str(_ISO_DATE),
        },
        strict=False, coerce=True,
    ),
    "monthly_achievements": DataFrameSchema(
        {
            "month": Column(str, Check.str_matches(_ISO_MONTH), nullable=False),
            "title": Column(str, nullable=False),
            "category": Column(str, nullable=False),
            "impact_score": Column(float, Check.ge(0), nullable=True),
            "impact_score_raw": Column(str, nullable=True),
            "reported_by": Column(str, nullable=True),
            "team_name": Column(str, nullable=True),
            "team_id": Column(str, nullable=True),
        },
        strict=False, coerce=True,
    ),
}


def validate_schema(
    df: pd.DataFrame, dataset: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Validate ``df`` against the Silver schema for ``dataset``.

    Returns ``(valid_df, invalid_df, summary)``. Rows implicated in any failure
    case are moved to ``invalid_df`` so the pipeline can quarantine them; the
    remainder is returned as ``valid_df``. If no schema is registered the input
    passes through unchanged.
    """
    log = get_logger("silver", dataset=dataset)
    schema = SILVER_SCHEMAS.get(dataset)
    if schema is None:
        return df.copy(), df.iloc[0:0].copy(), {"validated": False, "reason": "no_schema"}

    try:
        validated = schema.validate(df, lazy=True)
        summary = {
            "validated": True, "passed": True,
            "rows": len(df), "invalid_rows": 0, "failure_cases": 0,
        }
        return validated, df.iloc[0:0].copy(), summary
    except pa.errors.SchemaErrors as err:
        failures = err.failure_cases
        bad_index = (
            pd.to_numeric(failures["index"], errors="coerce").dropna().astype(int).unique()
            if "index" in failures else []
        )
        bad_index = [i for i in bad_index if i in df.index]
        invalid_df = df.loc[bad_index].copy()
        valid_df = df.drop(index=bad_index).copy()
        # Compact summary of what failed, by check.
        by_check = (
            failures.groupby(["column", "check"]).size().reset_index(name="count")
            if len(failures) else pd.DataFrame()
        )
        summary = {
            "validated": True, "passed": False,
            "rows": len(df), "invalid_rows": len(invalid_df),
            "failure_cases": int(len(failures)),
            "failures_by_check": by_check.to_dict(orient="records"),
        }
        log.warning(
            "Schema '{ds}': {fc} failure cases across {ir} rows",
            ds=dataset, fc=len(failures), ir=len(invalid_df),
        )
        return valid_df, invalid_df, summary
