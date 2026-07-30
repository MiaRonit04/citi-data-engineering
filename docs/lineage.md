# DATA LINEAGE

End-to-end lineage: **Source → Bronze → Silver → Gold → Analytics**.
Bronze is immutable; Silver applies documented cleaning/validation; Gold
curates exactly seven business datasets consumed only by the analytics layer.

## Gold dataset provenance

### `team_members` — Q1 — Who are the members of each team?

- **Silver inputs:** team_membership, employees, contractor_roster, teams, locations
- **Transformation:** membership ⋈ person-master ⋈ teams ⋈ locations
- **Business rule:** member identity resolved by canonical email; direct-wins tie-break

### `team_locations` — Q2 — Where are the teams located?

- **Silver inputs:** teams, locations, team_membership
- **Transformation:** teams ⋈ locations(primary_office); employee_count from membership
- **Business rule:** one row per team_id; state absent in source (region provided)

### `monthly_achievements` — Q3 — Monthly achievements per team

- **Silver inputs:** monthly_achievements, teams
- **Transformation:** filter attributable (team_id) → group by team_id, year, month
- **Business rule:** name-only achievements excluded (team_name non-unique)

### `leader_colocation` — Q4 — Leader not co-located with majority

- **Silver inputs:** teams, team_membership, employees, contractor_roster, locations
- **Transformation:** compare leader location vs modal member location per team
- **Business rule:** co-located = leader city == majority member city

### `non_direct_leaders` — Q5 — Teams with non-direct leaders

- **Silver inputs:** teams, employees, contractor_roster
- **Transformation:** leader email resolved to employee (direct) or contractor (non-direct)
- **Business rule:** non-direct leader = leader email ∈ contractor roster (not an employee)

### `non_direct_staff_ratio` — Q6 — Non-direct staff ratio > threshold

- **Silver inputs:** team_membership, employees, contractor_roster
- **Transformation:** per team: non_direct_members / total_members
- **Business rule:** flag ratio > NON_DIRECT_RATIO_THRESHOLD (0.20, configurable)

### `organization_reporting` — Q7 — Teams reporting to org leaders

- **Silver inputs:** teams, organizations
- **Transformation:** classify reports_to_type; build reporting chain
- **Business rule:** direct = reports_to_type == 'Org Leader' (== reporting_manager ∈ org leaders)

## Silver transformations (Bronze → Silver)

- **employees:** text cleaning; email canonicalization; department standardization; employment_type standardization; hire_date → ISO; dedupe emp_id; manager FK validation
- **contractor_roster:** text cleaning; email canonicalization; dates → ISO
- **team_membership:** text cleaning; team_code → TM-###; email canonicalization; allocation bounds [0,100]; dates → ISO; orphan-member quarantine; staff_type tagging
- **teams:** flatten organization.*; text cleaning; leader/manager email canonicalization; formed_date → ISO; leader staff-type resolution
- **monthly_achievements:** text cleaning; month → YYYY-MM; impact_score numeric coercion; orphan-achievement quarantine; team_id attributability
- **locations:** text cleaning; dedupe location_code (LOC-01 conflict)
- **organizations:** text cleaning; org_leader_email canonicalization
