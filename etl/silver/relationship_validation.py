"""Referential-integrity validation across standardized Silver datasets.

Runs after per-dataset cleaning/standardization but before Silver is persisted,
so orphaned / dangling rows are quarantined rather than written as trusted data.

Relationships enforced
----------------------
* ``team_membership.team_code``   → ``teams.team_id``            (orphan team)
* ``team_membership.employee_email`` → employee **or** contractor (orphan member)
* ``teams.primary_office``        → ``locations.location_code``  (flag only)
* ``teams.org_id``                → ``organizations.org_id``     (flag only)
* ``employees.manager_emp_id``    → ``employees.emp_id``         (null dangling)
* ``monthly_achievements.team_id``→ ``teams.team_id``            (orphan achievement)

The function is pure w.r.t. IO — it returns the filtered frames plus a list of
``QuarantineAction`` describing what to reject and why, which the pipeline then
persists via :mod:`etl.silver.quarantine`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class QuarantineAction:
    """A set of rows to quarantine with its reason/rule."""

    dataset: str
    rows: pd.DataFrame
    reason: str
    rule: str


@dataclass
class RelationshipResult:
    """Outcome of relationship validation."""

    frames: dict[str, pd.DataFrame]
    quarantine: list[QuarantineAction] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _person_index(frames: dict[str, pd.DataFrame]) -> tuple[set[str], set[str]]:
    """Return ``(direct_emails, non_direct_emails)`` canonical-email sets."""
    emp = frames.get("employees", pd.DataFrame())
    ctr = frames.get("contractor_roster", pd.DataFrame())
    direct = set(emp["email_canonical"].dropna()) if "email_canonical" in emp else set()
    non_direct = set(ctr["email_canonical"].dropna()) if "email_canonical" in ctr else set()
    return direct, non_direct


def validate_relationships(frames: dict[str, pd.DataFrame]) -> RelationshipResult:
    """Validate FKs and return filtered frames + quarantine actions + metrics."""
    frames = {k: v.copy() for k, v in frames.items()}
    actions: list[QuarantineAction] = []
    metrics: dict[str, Any] = {}

    direct_emails, non_direct_emails = _person_index(frames)
    all_people = direct_emails | non_direct_emails
    team_ids = set(frames["teams"]["team_id"]) if "teams" in frames else set()
    location_codes = set(frames["locations"]["location_code"]) if "locations" in frames else set()
    org_ids = set(frames["organizations"]["org_id"]) if "organizations" in frames else set()

    # ── team_membership: team FK + person FK ────────────────────────────────
    if "team_membership" in frames:
        tm = frames["team_membership"]
        orphan_team = ~tm["team_code"].isin(team_ids)
        orphan_person = ~tm["employee_email_canonical"].isin(all_people)

        if orphan_team.any():
            actions.append(QuarantineAction(
                "team_membership", tm[orphan_team], "ORPHAN_TEAM_CODE",
                "team_membership.team_code ∉ teams.team_id"))
        # Person orphans are only those with a resolvable team (avoid double count).
        person_only = orphan_person & ~orphan_team
        if person_only.any():
            actions.append(QuarantineAction(
                "team_membership", tm[person_only], "ORPHAN_MEMBER_EMAIL",
                "team_membership.employee_email ∉ employees ∪ contractors"))

        keep = ~(orphan_team | orphan_person)
        surviving = tm[keep].copy()
        # Tag each surviving member as direct / non-direct (rule: direct wins).
        surviving["staff_type"] = surviving["employee_email_canonical"].map(
            lambda e: "direct" if e in direct_emails else ("non_direct" if e in non_direct_emails else "unknown")
        )
        frames["team_membership"] = surviving
        metrics["team_membership"] = {
            "input_rows": int(len(tm)),
            "orphan_team_code": int(orphan_team.sum()),
            "orphan_member_email": int(person_only.sum()),
            "valid_rows": int(len(surviving)),
        }

    # ── teams: leader resolution + office/org flags ─────────────────────────
    if "teams" in frames:
        teams = frames["teams"]
        teams["leader_staff_type"] = teams["team_leader_email_canonical"].map(
            lambda e: "direct" if e in direct_emails else ("non_direct" if e in non_direct_emails else "unresolved")
        )
        bad_office = ~teams["primary_office"].isin(location_codes) & teams["primary_office"].notna()
        bad_org = ~teams["org_id"].isin(org_ids) & teams["org_id"].notna()
        frames["teams"] = teams
        metrics["teams"] = {
            "input_rows": int(len(teams)),
            "leaders_direct": int((teams["leader_staff_type"] == "direct").sum()),
            "leaders_non_direct": int((teams["leader_staff_type"] == "non_direct").sum()),
            "leaders_unresolved": int((teams["leader_staff_type"] == "unresolved").sum()),
            "invalid_primary_office": int(bad_office.sum()),
            "invalid_org_id": int(bad_org.sum()),
        }

    # ── employees: dangling manager FK → null + flag ────────────────────────
    if "employees" in frames:
        emp = frames["employees"]
        emp_ids = set(emp["emp_id"])
        dangling = emp["manager_emp_id"].notna() & ~emp["manager_emp_id"].isin(emp_ids)
        emp["broken_manager_fk"] = dangling
        emp.loc[dangling, "manager_emp_id"] = None
        frames["employees"] = emp
        metrics["employees"] = {"broken_manager_fk": int(dangling.sum())}

    # ── achievements: team linkage ──────────────────────────────────────────
    if "monthly_achievements" in frames:
        ach = frames["monthly_achievements"]
        has_id = ach["team_id"].notna()
        has_name = ach["team_name"].notna()
        orphan = ~has_id & ~has_name
        if orphan.any():
            actions.append(QuarantineAction(
                "monthly_achievements", ach[orphan], "ORPHAN_ACHIEVEMENT",
                "achievement has neither team_id nor team_name"))
        # Rows resolvable to a real team_id are 'attributable'; name-only are not.
        valid_id = has_id & ach["team_id"].isin(team_ids)
        surviving = ach[~orphan].copy()
        surviving["attributable"] = valid_id[~orphan].values
        frames["monthly_achievements"] = surviving
        metrics["monthly_achievements"] = {
            "input_rows": int(len(ach)),
            "orphan": int(orphan.sum()),
            "attributable_by_team_id": int(valid_id.sum()),
            "name_only_unresolved": int((~has_id & has_name).sum()),
        }

    return RelationshipResult(frames=frames, quarantine=actions, metrics=metrics)
