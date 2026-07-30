"""Gold pipeline — build, validate and persist exactly seven business datasets.

Loads the trusted Silver frames, materialises each Gold dataset via the builders
in :mod:`gold_business_questions`, runs post-build validation (correct count,
grain uniqueness, null checks, cross-checks against Silver), writes Parquet, and
emits ``gold_validation_report.json`` + ``business_metrics.json``.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from etl.common.config import Settings, get_settings
from etl.common.exceptions import GoldValidationError
from etl.common.logging import get_logger
from etl.common.metadata import StageMetrics
from etl.common.utils import (
    new_batch_id,
    read_latest_parquet,
    utc_now,
    write_json,
    write_parquet,
)
from etl.gold.gold_business_questions import GOLD_BUILDERS, build_person_master

SILVER_DATASETS = [
    "employees", "contractor_roster", "team_membership", "teams",
    "monthly_achievements", "locations", "organizations",
]
EXPECTED_GOLD_COUNT = 7


def load_silver_frames(settings: Settings) -> dict[str, pd.DataFrame]:
    """Load every Silver dataset into memory keyed by name."""
    return {d: read_latest_parquet(settings.silver_path, d) for d in SILVER_DATASETS}


def _validate_gold(name: str, df: pd.DataFrame, grain: str | None,
                   frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Post-build checks for one Gold dataset; returns a validation record."""
    checks: dict[str, Any] = {"rows": len(df), "passed": True, "issues": []}
    if df.empty:
        checks["passed"] = False
        checks["issues"].append("empty dataset")
    if grain:
        dups = int(df.duplicated(subset=[grain]).sum())
        checks["grain_unique"] = dups == 0
        checks["duplicate_grain_rows"] = dups
        if dups:
            checks["passed"] = False
            checks["issues"].append(f"{dups} duplicate rows on grain '{grain}'")

    # Cross-checks vs Silver totals.
    n_teams = frames["teams"]["team_id"].nunique()
    if name in {"team_locations", "leader_colocation", "non_direct_leaders", "organization_reporting"}:
        checks["covers_all_teams"] = len(df) == n_teams
        if len(df) != n_teams:
            checks["issues"].append(f"expected {n_teams} teams, got {len(df)}")

    # Q7 independent cross-signal: reports_to_type=='Org Leader' must equal
    # reporting_manager_email ∈ organization leaders (ASSUMPTIONS #21).
    if name == "organization_reporting":
        org_leaders = set(frames["organizations"]["org_leader_email"])
        by_type = int((frames["teams"]["reports_to_type"].str.strip().str.lower() == "org leader").sum())
        by_manager = int(frames["teams"]["reporting_manager_email_canonical"].isin(org_leaders).sum())
        by_status = int((df["reporting_status"] == "Direct to Org Leader").sum())
        checks["q7_cross_signal_agrees"] = by_type == by_manager == by_status
        checks["q7_counts"] = {"by_reports_to_type": by_type,
                               "by_reporting_manager": by_manager, "by_status": by_status}
        if not checks["q7_cross_signal_agrees"]:
            checks["passed"] = False
            checks["issues"].append("Q7 cross-signal disagreement")

    # Q5 reconciliation against Silver leader classification.
    if name == "non_direct_leaders":
        silver_nd = int((frames["teams"]["leader_staff_type"] == "non_direct").sum())
        gold_nd = int((df["direct_or_non_direct"] == "Non-Direct").sum())
        checks["q5_reconciles_with_silver"] = silver_nd == gold_nd
        if silver_nd != gold_nd:
            checks["passed"] = False
            checks["issues"].append(f"Q5 mismatch: silver {silver_nd} vs gold {gold_nd}")
    return checks


def run(batch_id: str | None = None, settings: Settings | None = None) -> list[StageMetrics]:
    """Build and validate all seven Gold datasets."""
    settings = settings or get_settings()
    settings.ensure_directories()
    batch_id = batch_id or new_batch_id("GOLD")
    ts = utc_now()
    log = get_logger("gold", batch_id=batch_id)

    frames = load_silver_frames(settings)
    metrics: list[StageMetrics] = []
    validation: dict[str, Any] = {}
    built: dict[str, pd.DataFrame] = {}

    for name, (builder, question, grain) in GOLD_BUILDERS.items():
        started = time.perf_counter()
        try:
            df = builder(frames)
            out_file = write_parquet(df, settings.gold_path, name, settings=settings, ts=ts)
            checks = _validate_gold(name, df, grain, frames)
            checks["question"] = question
            validation[name] = checks
            built[name] = df
            metrics.append(StageMetrics(
                stage="gold", dataset=name, batch_id=batch_id,
                rows_written=len(df), execution_seconds=round(time.perf_counter() - started, 3),
                output_path=str(out_file),
                status="success" if checks["passed"] else "partial",
            ))
            log.info("Gold '{n}' built: {r} rows ({q})", n=name, r=len(df), q=question)
        except Exception as exc:  # noqa: BLE001 - isolate per dataset
            log.exception("Gold build failed for '{n}'", n=name)
            validation[name] = {"passed": False, "issues": [str(exc)]}
            metrics.append(StageMetrics(
                stage="gold", dataset=name, batch_id=batch_id, status="failed",
                errors=[str(exc)], execution_seconds=round(time.perf_counter() - started, 3)))

    # Enforce the "exactly seven" contract.
    if len(built) != EXPECTED_GOLD_COUNT:
        raise GoldValidationError(
            f"Expected exactly {EXPECTED_GOLD_COUNT} Gold datasets, built {len(built)}")

    business_metrics = _business_metrics(frames, built)
    validation["_summary"] = {
        "gold_dataset_count": len(built),
        "expected_count": EXPECTED_GOLD_COUNT,
        "all_passed": all(v.get("passed", False) for k, v in validation.items() if not k.startswith("_")),
    }
    write_json({"batch_id": batch_id, "datasets": validation},
               settings.reports_path / "gold_validation_report.json")
    write_json({"batch_id": batch_id, **business_metrics},
               settings.reports_path / "business_metrics.json")

    log.info("Gold complete — {n}/7 datasets, all_passed={p}",
             n=len(built), p=validation["_summary"]["all_passed"])
    return metrics


def _business_metrics(frames: dict[str, pd.DataFrame], gold: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Compute the headline organisation metrics for the dashboard/notebook."""
    people = build_person_master(frames)
    ratio = gold["non_direct_staff_ratio"]
    coloc = gold["leader_colocation"]
    team_sizes = gold["team_members"].groupby("team_id").size()

    return {
        "total_employees": int(frames["employees"]["emp_id"].nunique()),
        "total_contractors": int(frames["contractor_roster"]["contractor_id"].nunique()),
        "total_people_resolved": int(len(people)),
        "total_teams": int(frames["teams"]["team_id"].nunique()),
        "total_leaders": int(frames["teams"]["team_leader_email_canonical"].nunique()),
        "total_org_leaders": int(frames["organizations"]["org_leader_email"].nunique()),
        "total_locations": int(frames["locations"]["location_code"].nunique()),
        "total_departments": int(frames["employees"]["department"].nunique()),
        "total_monthly_achievements": int(gold["monthly_achievements"]["achievement_count"].sum()),
        "avg_team_size": round(float(team_sizes.mean()), 2) if not team_sizes.empty else 0.0,
        "largest_team_size": int(team_sizes.max()) if not team_sizes.empty else 0,
        "smallest_team_size": int(team_sizes.min()) if not team_sizes.empty else 0,
        # Business-question answers:
        "q4_non_colocated_teams": int((coloc["co_located"] == "No").sum()),
        "q4_colocated_teams": int((coloc["co_located"] == "Yes").sum()),
        "q5_non_direct_leader_teams": int((gold["non_direct_leaders"]["direct_or_non_direct"] == "Non-Direct").sum()),
        "q6_teams_above_ratio": int(ratio["above_threshold"].sum()),
        "q7_teams_report_to_org_leader": int((gold["organization_reporting"]["reporting_status"] == "Direct to Org Leader").sum()),
    }


if __name__ == "__main__":  # pragma: no cover
    run()
