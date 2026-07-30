"""Business-logic builders for the seven Gold datasets.

Each ``build_*`` function takes the dict of trusted **Silver** frames and returns
a single curated DataFrame answering exactly one business question. All logic is
derived from data — no answer is hardcoded — and every transformation is
documented in ``docs/TRANSFORMATIONS.md``.

A shared :func:`build_person_master` resolves each team member / leader email to
a single identity with a **direct-wins** tie-break (see ASSUMPTIONS #1–#2).
"""

from __future__ import annotations

import pandas as pd

from etl.common.config import get_settings

# ── Shared dimensions ───────────────────────────────────────────────────────
def build_location_lookup(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """``location_code → city, country, region`` (canonical, de-duplicated)."""
    loc = frames["locations"][["location_code", "city", "country", "region"]].copy()
    return loc.drop_duplicates(subset=["location_code"], keep="first")


def build_person_master(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Unified person dimension across direct (employee) and non-direct (contractor).

    Columns: ``email_canonical, person_id, person_name, department,
    location_code, staff_type, status``. When an email exists in both rosters,
    the **direct** (employee) record wins (ASSUMPTIONS #2).
    """
    emp = frames["employees"]
    ctr = frames["contractor_roster"]
    loc = build_location_lookup(frames)

    emp_people = pd.DataFrame({
        "email_canonical": emp["email_canonical"],
        "person_id": emp["emp_id"],
        "person_name": emp["full_name"],
        "department": emp["department"],
        "location_code": emp["location_code"],
        "staff_type": "direct",
        "status": emp["status"],
    })
    ctr_people = pd.DataFrame({
        "email_canonical": ctr["email_canonical"],
        "person_id": ctr["contractor_id"],
        "person_name": ctr["full_name"],
        "department": pd.NA,             # contractors have no ACME department
        "location_code": ctr["location_code"],
        "staff_type": "non_direct",
        "status": ctr["status"],
    })
    # direct first so keep='first' implements direct-wins on email collisions.
    people = pd.concat([emp_people, ctr_people], ignore_index=True)
    people = people.dropna(subset=["email_canonical"])
    people = people.drop_duplicates(subset=["email_canonical"], keep="first")
    people = people.merge(loc[["location_code", "city"]], on="location_code", how="left")
    return people.rename(columns={"city": "location_city"})


def _members_enriched(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """team_membership joined to person master + team (the base for Q1/Q4/Q6)."""
    tm = frames["team_membership"].drop(columns=["staff_type"], errors="ignore")
    people = build_person_master(frames)  # authoritative staff_type (direct-wins)
    teams = frames["teams"]
    merged = tm.merge(
        people, left_on="employee_email_canonical", right_on="email_canonical", how="left"
    )
    merged = merged.merge(
        teams[["team_id", "team_name", "team_leader_email_canonical", "primary_office"]],
        left_on="team_code", right_on="team_id", how="left",
    )
    return merged


# ── Q1: team_members ────────────────────────────────────────────────────────
def build_team_members(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q1 — Who are the members of each team?"""
    m = _members_enriched(frames)
    people = build_person_master(frames).set_index("email_canonical")
    leader_name = frames["teams"].set_index("team_id")["team_leader_email_canonical"].to_dict()

    out = pd.DataFrame({
        "team_id": m["team_id"],
        "team_name": m["team_name"],
        "employee_id": m["person_id"],
        "employee_name": m["person_name"],
        "designation": m["role"],
        "department": m["department"],
        "leader": m["team_leader_email_canonical"].map(
            lambda e: people["person_name"].get(e) if pd.notna(e) else None),
        "location": m["location_city"],
        "staff_type": m["staff_type"],
        "status": m["status"],
    })
    return out.dropna(subset=["team_id"]).sort_values(["team_id", "employee_id"]).reset_index(drop=True)


# ── Q2: team_locations ──────────────────────────────────────────────────────
def build_team_locations(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q2 — Where are the teams located?"""
    teams = frames["teams"]
    loc = build_location_lookup(frames)
    people = build_person_master(frames).set_index("email_canonical")
    m = _members_enriched(frames)

    emp_count = m.groupby("team_id", dropna=True).size().rename("employee_count")
    out = teams.merge(loc, left_on="primary_office", right_on="location_code", how="left")
    out = out.merge(emp_count, left_on="team_id", right_index=True, how="left")
    out["leader_location"] = out["team_leader_email_canonical"].map(
        lambda e: people["location_city"].get(e) if pd.notna(e) else None)

    result = pd.DataFrame({
        "team_id": out["team_id"],
        "team_name": out["team_name"],
        "primary_office": out["primary_office"],
        "city": out["city"],
        # Source has no state granularity; region is the coarsest available.
        "state": pd.NA,
        "country": out["country"],
        "region": out["region"],
        "employee_count": out["employee_count"].fillna(0).astype(int),
        "leader_location": out["leader_location"],
    })
    return result.sort_values("team_id").reset_index(drop=True)


# ── Q3: monthly_achievements ────────────────────────────────────────────────
def build_monthly_achievements(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q3 — Monthly achievements for every team (attributable by team_id only)."""
    ach = frames["monthly_achievements"]
    teams = frames["teams"][["team_id", "team_name"]]
    attributable = ach[ach["attributable"] == True].copy()  # noqa: E712
    attributable["year"] = attributable["month"].str.slice(0, 4)
    attributable["month_num"] = attributable["month"].str.slice(5, 7)

    def _details(titles: pd.Series) -> str:
        uniq = list(dict.fromkeys(titles.dropna()))
        head = "; ".join(uniq[:5])
        return head + (f" (+{len(uniq) - 5} more)" if len(uniq) > 5 else "")

    grouped = (
        attributable.groupby(["team_id", "year", "month_num"])
        .agg(
            achievement_count=("title", "size"),
            achievement_details=("title", _details),
            performance_score=("impact_score", "mean"),
        )
        .reset_index()
    )
    grouped = grouped.merge(teams, on="team_id", how="left")
    grouped["performance_score"] = grouped["performance_score"].round(3)
    return (
        grouped.rename(columns={"month_num": "month"})[
            ["year", "month", "team_id", "team_name",
             "achievement_count", "achievement_details", "performance_score"]
        ]
        .sort_values(["team_id", "year", "month"]).reset_index(drop=True)
    )


# ── Q4: leader_colocation ───────────────────────────────────────────────────
def build_leader_colocation(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q4 — Teams whose leader is not co-located with the member majority."""
    m = _members_enriched(frames)
    teams = frames["teams"]
    people = build_person_master(frames).set_index("email_canonical")

    # Majority (modal) member location per team.
    def _mode(s: pd.Series):
        s = s.dropna()
        return s.mode().iloc[0] if not s.empty else None

    majority = m.groupby("team_id")["location_city"].agg(_mode).rename("majority_location")
    out = teams[["team_id", "team_leader_email_canonical"]].copy()
    out["leader_location"] = out["team_leader_email_canonical"].map(
        lambda e: people["location_city"].get(e) if pd.notna(e) else None)
    out = out.merge(majority, left_on="team_id", right_index=True, how="left")
    out["co_located"] = out.apply(
        lambda r: "Yes" if (pd.notna(r["leader_location"]) and r["leader_location"] == r["majority_location"])
        else "No", axis=1)

    return pd.DataFrame({
        "team_id": out["team_id"],
        "leader": out["team_leader_email_canonical"],
        "leader_location": out["leader_location"],
        "majority_team_location": out["majority_location"],
        "co_located": out["co_located"],
    }).sort_values("team_id").reset_index(drop=True)


# ── Q5: non_direct_leaders ──────────────────────────────────────────────────
def build_non_direct_leaders(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q5 — Teams whose leaders are non-direct staff."""
    teams = frames["teams"]
    out = pd.DataFrame({
        "team_id": teams["team_id"],
        "leader": teams["team_leader_email_canonical"],
        "leader_type": teams["leader_staff_type"],
        "direct_or_non_direct": teams["leader_staff_type"].map(
            {"direct": "Direct", "non_direct": "Non-Direct"}).fillna("Unresolved"),
    })
    return out.sort_values("team_id").reset_index(drop=True)


# ── Q6: non_direct_staff_ratio ──────────────────────────────────────────────
def build_non_direct_staff_ratio(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q6 — Per-team non-direct staff ratio and whether it exceeds the threshold."""
    threshold = get_settings().non_direct_ratio_threshold
    tm = frames["team_membership"]
    grp = tm.groupby("team_code")["staff_type"]
    total = grp.size().rename("total_members")
    non_direct = grp.apply(lambda s: (s == "non_direct").sum()).rename("non_direct_members")
    out = pd.concat([total, non_direct], axis=1).reset_index()
    out["ratio"] = (out["non_direct_members"] / out["total_members"]).round(4)
    out["above_threshold"] = out["ratio"] > threshold
    return out.rename(columns={"team_code": "team_id"}).sort_values("team_id").reset_index(drop=True)


# ── Q7: organization_reporting ──────────────────────────────────────────────
def build_organization_reporting(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Q7 — Teams reporting directly to organization leaders."""
    teams = frames["teams"]
    orgs = frames["organizations"].set_index("org_id")["org_leader_email"].to_dict()
    reports_direct = teams["reports_to_type"].str.strip().str.lower() == "org leader"

    out = pd.DataFrame({
        "team_id": teams["team_id"],
        "organization_leader": teams["reporting_manager_email_canonical"],
        "org_name": teams["org_name"],
        "reporting_chain": teams.apply(
            lambda r: f"{r['team_id']} → {r['reporting_manager_email']} → {r['org_name']}", axis=1),
        "reporting_status": reports_direct.map({True: "Direct to Org Leader", False: "Indirect"}),
    })
    return out.sort_values("team_id").reset_index(drop=True)


# Registry: dataset name → (builder, question text, grain key)
GOLD_BUILDERS = {
    "team_members": (build_team_members, "Q1 — Who are the members of each team?", None),
    "team_locations": (build_team_locations, "Q2 — Where are the teams located?", "team_id"),
    "monthly_achievements": (build_monthly_achievements, "Q3 — Monthly achievements per team", None),
    "leader_colocation": (build_leader_colocation, "Q4 — Leader not co-located with majority", "team_id"),
    "non_direct_leaders": (build_non_direct_leaders, "Q5 — Teams with non-direct leaders", "team_id"),
    "non_direct_staff_ratio": (build_non_direct_staff_ratio, "Q6 — Non-direct staff ratio > threshold", "team_id"),
    "organization_reporting": (build_organization_reporting, "Q7 — Teams reporting to org leaders", "team_id"),
}
