# ASSUMPTIONS & DESIGN DECISIONS

Every non-trivial modeling decision is recorded here with its rationale. Data is
**never silently changed** — each rule below is applied explicitly in code and
surfaced in the validation / cleaning reports.

## Identity & staff classification
1. **Direct vs non-direct staff.** A person in `employees.csv` is **direct**
   staff; a person in `contractor_roster.csv` is **non-direct** staff. This is
   the only signal in the data for the direct/non-direct distinction the
   business questions require.
2. **Roster overlap tie-break (562 emails in both).** When a normalized email
   exists in *both* rosters, the person is classified by **team-membership
   context is irrelevant**; globally we treat presence in the contractor roster
   as authoritative for "non-direct" **only when the person is not also an
   active employee**. Concretely: resolve to `employees` first (direct); fall
   back to `contractor_roster` (non-direct). Documented and unit-tested.
3. **Email normalization key.** Emails are matched on a canonical form:
   lowercased, trimmed, internal whitespace removed, `acmeinc` → `acme-inc`
   domain repair, and the underscore/dot separator **unified**
   (`patricia_lane` ≡ `patricia.lane`). Evidence-based choice: profiling three
   strategies showed unifying `_`↔`.` recovers ~522 real team members that
   would otherwise be false orphans (member orphans 4,058 → 3,536) while keeping
   every team leader resolved (0 unresolved). The more aggressive strategy of
   stripping *all* separators was rejected — it merges ~32k distinct identities.
   The original email is always retained alongside the canonical join key for
   lineage.

## Keys & grain
4. **`team_id` is the team grain**, never `team_name`. `team_name` has only 200
   distinct values across 25,000 teams and cannot identify a team.
5. **`team_code` normalization.** Membership `team_code` (`tm006`, `tm-005`) is
   normalized to the canonical `TM-<zero-padded>` form to match `teams.team_id`.
6. **Duplicate `emp_id` (4).** Deterministically de-duplicated keeping the first
   occurrence by stable sort on `(emp_id, hire_date)`; dropped rows are
   quarantined with reason `DUPLICATE_PRIMARY_KEY`.
7. **`LOC-01` conflict (Austin vs Dallas).** The locations dimension has two
   rows for `LOC-01`. We keep the **first** (`Austin`) as canonical and
   quarantine the second (`Dallas`) as `DUPLICATE_LOCATION_CODE`. City for
   `LOC-01` therefore resolves to Austin everywhere downstream.

## Dates & values
8. **Date standardization.** All dates are parsed from any detected format
   (`%Y-%m-%d`, `%m/%d/%Y`, `%d-%b-%Y`, `%Y/%m/%d`, `%B %d, %Y`, `%b %d %Y`,
   long month names) to ISO `YYYY-MM-DD`. Unparseable, non-blank dates are set
   null and counted in the cleaning report (never guessed).
9. **`month` standardization** (`March 2026` → `2026-03`) uses the same engine,
   normalized to `YYYY-MM`.
10. **`allocation_pct` bounds.** Valid range is `[ALLOCATION_MIN, ALLOCATION_MAX]`
    = `[0, 100]` (configurable). Out-of-range values (`120`, `-10`) are **not**
    silently clamped; the membership row is kept but `allocation_pct` is set null
    and flagged `INVALID_ALLOCATION` in the cleaning report, so headcount logic
    is unaffected while the bad metric is not trusted.
11. **`impact_score` mixed type.** Numeric values are coerced to float;
    non-numeric textual values (`Low`, …) are set null for the numeric
    `performance_score` and preserved in an `impact_score_raw` audit column.
12. **`employment_type`** — all six variants map to canonical `Full-Time`
    (direct). This does **not** reclassify anyone as non-direct; roster
    membership (rule 1) is the sole direct/non-direct signal.

## Categorical standardization
13. **Departments** collapse to their 10 canonical Title-Case names.
14. **Locations / countries / regions** are taken as-is from the (cleaned)
    `locations` dimension — they are already canonical there.

## Relationships & quarantine
15. **Orphan team members (3,536).** Membership emails resolving to neither
    roster are quarantined `ORPHAN_MEMBER_EMAIL` and excluded from team headcount.
16. **Invalid `manager_emp_id`.** Manager ids not present in the employee master
    are recorded as `BROKEN_MANAGER_FK` (the employee row is retained; the
    dangling manager reference is nulled for hierarchy safety).
17. **Orphan achievements (5,422).** Achievement rows with neither `team_id` nor
    `team_name` are quarantined `ORPHAN_ACHIEVEMENT`.
18. **Achievements linked only by `team_name`.** Because `team_name` is
    non-unique, such rows **cannot** be attributed to a single team. They are
    excluded from the per-team Gold grain and counted in a documented
    `unresolved_by_name` metric (not dropped from lineage). Only `team_id`-linked
    achievements populate `monthly_achievements` Gold.

## Business rules
19. **Q5 non-direct leader** = a team whose `team_leader_email` resolves to the
    contractor roster (non-direct). 3,937 teams per profiling.
20. **Q6 threshold** = non-direct-member ratio **strictly greater than**
    `NON_DIRECT_RATIO_THRESHOLD` (0.20, configurable).
21. **Q7 reports-to-org-leader** uses `reports_to_type == 'Org Leader'`, which
    profiling confirmed is identical to `reporting_manager_email ∈ org leaders`
    (both = 9,957). We assert this equivalence in Gold validation.

## Environment
22. **Python.** Brief targets 3.12; local Anaconda provides 3.13.5 (fully
    compatible). Docker image pins **3.12** for reproducibility.
23. **PostgreSQL** is provided for a serving/metadata layer and ER modeling, but
    the Medallion lake (Parquet) is the system of record. Gold is additionally
    loadable into Postgres via `scripts/load_gold_to_postgres.py`.
