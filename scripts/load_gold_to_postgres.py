"""Load the Gold (and supporting Silver dimensions) into PostgreSQL.

Optional serving step: the Parquet lake remains the system of record. This
creates the schema (via SQLAlchemy metadata) and bulk-loads dimensions and
facts, so BI tools can query Gold over SQL.

    python scripts/load_gold_to_postgres.py

Fails gracefully with a clear message if the database is unreachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.common.config import get_settings  # noqa: E402
from etl.common.logging import get_logger  # noqa: E402
from etl.common.utils import read_latest_parquet  # noqa: E402
from db.models.models import Base, get_engine  # noqa: E402

log = get_logger("db-load")


def _load_frames():
    s = get_settings()
    silver = {n: read_latest_parquet(s.silver_path, n) for n in ["locations", "organizations", "teams"]}
    gold = {n: read_latest_parquet(s.gold_path, n) for n in ["team_members", "monthly_achievements"]}
    return silver, gold


def main() -> int:
    settings = get_settings()
    try:
        engine = get_engine()
        with engine.connect() as _:
            pass
    except Exception as exc:  # noqa: BLE001
        log.error("Cannot connect to PostgreSQL at {url}: {e}",
                  url=settings.sqlalchemy_url.split('@')[-1], e=exc)
        return 1

    log.info("Creating schema (if absent)…")
    Base.metadata.create_all(engine)

    silver, gold = _load_frames()

    dim_location = silver["locations"][["location_code", "city", "country", "region"]].drop_duplicates("location_code")
    dim_org = silver["organizations"][["org_id", "org_name", "org_leader_email"]]
    dim_team = silver["teams"][[
        "team_id", "team_name", "team_leader_email", "leader_staff_type",
        "reports_to_type", "primary_office", "org_id",
    ]].copy()

    fact_membership = gold["team_members"].rename(columns={"location": "location"})[[
        "team_id", "employee_id", "employee_name", "designation",
        "department", "location", "staff_type", "status",
    ]].copy()

    fact_ach = gold["monthly_achievements"][[
        "team_id", "year", "month", "achievement_count", "performance_score",
    ]].copy()

    # Load order respects FK dependencies; replace for idempotency.
    plan = [
        ("dim_location", dim_location), ("dim_organization", dim_org), ("dim_team", dim_team),
        ("fact_team_membership", fact_membership), ("fact_monthly_achievement", fact_ach),
    ]
    with engine.begin() as conn:
        # Truncate facts first, then dims (reverse FK order).
        for table in ["fact_monthly_achievement", "fact_team_membership", "dim_team",
                      "dim_organization", "dim_location"]:
            conn.exec_driver_sql(f"TRUNCATE TABLE {table} CASCADE")
        for table, df in plan:
            df.to_sql(table, conn, if_exists="append", index=False, chunksize=10_000, method="multi")
            log.info("Loaded {n} rows into {t}", n=len(df), t=table)

    log.info("Gold successfully served to PostgreSQL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
