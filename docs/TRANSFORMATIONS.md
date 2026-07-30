# TRANSFORMATION CATALOG

Documents every transformation from raw source to Gold: renamed/derived/dropped
columns, aggregations and business rules. Bronze applies **none** (immutable).

## Bronze → Silver (per dataset)

| Dataset | Renamed | Derived | Standardized |
|---------|---------|---------|--------------|
| employees | — | `email_canonical`, `broken_manager_fk` | department, employment_type, hire_date, email |
| contractor_roster | — | `email_canonical` | start/end dates, email |
| team_membership | — | `employee_email_canonical`, `staff_type` | team_code→`TM-###`, allocation bounds, dates, email |
| teams | `organization.org_id→org_id`, `organization.org_name→org_name` | `team_leader_email_canonical`, `reporting_manager_email_canonical`, `leader_staff_type` | formed_date, emails |
| monthly_achievements | — | `impact_score_raw`, `attributable` | month→`YYYY-MM`, impact_score numeric |
| locations | — | — | text cleaning; dedupe `location_code` |
| organizations | — | — | org_leader_email canonicalized |

## Silver → Gold (per business question)

### `team_members` (Q1)
`team_membership ⋈ person_master(email) ⋈ teams ⋈ locations`.
Derived: member identity (`employee_id`, `employee_name`), `department`,
`location` (city), `leader` (name), `staff_type`. Grain: membership row.

### `team_locations` (Q2)
`teams ⋈ locations(primary_office)`; `employee_count` = COUNT(members) per team;
`leader_location` = leader's city. Grain: `team_id`. `state` = null (not in source).

### `monthly_achievements` (Q3)
Filter `attributable` (real `team_id`) → `GROUP BY team_id, year, month`:
`achievement_count` = COUNT, `achievement_details` = distinct titles (top 5 +N),
`performance_score` = MEAN(impact_score). Grain: `team_id × year × month`.

### `leader_colocation` (Q4)
Per team: `majority_team_location` = MODE(member city); `leader_location` =
leader's city; `co_located` = (leader city == majority). Grain: `team_id`.

### `non_direct_leaders` (Q5)
Map `teams.leader_staff_type` → `Direct`/`Non-Direct`. Business rule: non-direct
leader = leader email resolves to contractor roster. Grain: `team_id`.

### `non_direct_staff_ratio` (Q6)
Per team: `total_members`, `non_direct_members` = COUNT(staff_type='non_direct'),
`ratio` = non_direct/total, `above_threshold` = ratio > `NON_DIRECT_RATIO_THRESHOLD`
(0.20, configurable). Grain: `team_id`.

### `organization_reporting` (Q7)
`reporting_status` = 'Direct to Org Leader' iff `reports_to_type=='Org Leader'`;
`reporting_chain` = `team → manager → org`. Grain: `team_id`.

## Business rules (never hardcoded answers)

Every figure is derived from Silver via DataFrame transformations. Direct vs
non-direct is roster membership (employee=direct, contractor=non-direct) with a
direct-wins tie-break. See [ASSUMPTIONS](ASSUMPTIONS.md) for the full rule set.
