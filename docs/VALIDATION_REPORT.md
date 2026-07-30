# VALIDATION REPORT

Two validation layers run in Silver, plus a post-build validation in Gold.
Machine-readable output: `reports/validation_summary.json` and
`reports/gold_validation_report.json`.

## 1. Schema validation (Pandera)

Every Silver dataset is validated against a declarative `DataFrameSchema`
(`etl/silver/schema_validation.py`) checking column presence, dtype,
nullability, value domains, patterns and uniqueness. Result for the current run:

| Dataset | Schema passed | Invalid rows quarantined |
|---------|:-------------:|-------------------------:|
| employees | ✅ | 0 |
| contractor_roster | ✅ | 0 |
| team_membership | ✅ | 0 |
| teams | ✅ | 0 |
| monthly_achievements | ✅ | 0 |
| locations | ✅ | 0 |
| organizations | ✅ | 0 |

All rows pass schema **after** standardization, confirming the cleaning rules
successfully coerce the raw data into the declared contract.

## 2. Relationship (referential-integrity) validation

`etl/silver/relationship_validation.py` resolves every foreign key and
quarantines orphans:

| Relationship | Result |
|--------------|--------|
| `team_membership.team_code → teams.team_id` | 0 orphan team codes |
| `team_membership.employee_email → person` | **3,536** orphan members quarantined |
| `teams.primary_office → locations` | 0 invalid |
| `teams.org_id → organizations` | 0 invalid |
| `teams.team_leader_email → person` | 21,277 direct · **3,723 non-direct** · 0 unresolved |
| `employees.manager_emp_id → employees.emp_id` | **6,042** dangling → nulled + flagged |
| `monthly_achievements.team_id → teams` | 123,525 attributable · 55,269 name-only (unresolvable) · 5,414 orphan |

## 3. Gold validation

`etl/gold/gold_pipeline.py` validates each Gold dataset after building it:

- **Exactly 7 datasets** produced (contract enforced — build fails otherwise). ✅
- **Grain uniqueness:** `team_locations`, `leader_colocation`, `non_direct_leaders`,
  `non_direct_staff_ratio`, `organization_reporting` all unique on `team_id`. ✅
- **Coverage:** the five team-grain datasets each cover all 25,000 teams. ✅
- **Q7 cross-signal:** `reports_to_type == 'Org Leader'` (9,957) ==
  `reporting_manager ∈ org leaders` (9,957) == `reporting_status` count (9,957). ✅
- **Q5 reconciliation:** Gold non-direct-leader count == Silver leader
  classification (3,723). ✅
- **Ratio bounds:** every `non_direct_staff_ratio.ratio ∈ [0,1]`; `above_threshold`
  equals `ratio > 0.20` exactly. ✅

**`all_passed = true`** in `gold_validation_report.json`.
