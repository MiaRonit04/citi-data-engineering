# DATA DICTIONARY

Field-level reference for Silver and Gold. Bronze mirrors the raw source columns
verbatim (all string).

## Silver datasets

### `employees`
| Column | Type | Null | Description |
|--------|------|:----:|-------------|
| emp_id | str | no | PK, `EMP-\d+` |
| full_name | str | yes | Cleaned name |
| email | str | yes | Cleaned email |
| email_canonical | str | yes | Canonical join key |
| department | str | yes | Canonical department (10) |
| location_code | str | yes | FK → locations |
| employment_type | str | yes | Canonical `Full-Time` |
| manager_emp_id | str | yes | FK → employees (nulled if broken) |
| hire_date | str | yes | ISO date |
| status | str | yes | Active/Terminated |
| broken_manager_fk | bool | no | True if manager FK was dangling |

### `contractor_roster`
`contractor_id` (PK), `full_name`, `email`, `email_canonical`, `agency`,
`location_code` (FK), `engagement_type`, `start_date`/`end_date` (ISO), `status`
(Active/Ended).

### `team_membership`
`team_code` (FK→teams), `employee_email`, `employee_email_canonical`, `role`,
`allocation_pct` (Int64 0–100, null if invalid), `start_date`/`end_date` (ISO),
`staff_type` (direct/non_direct/unknown).

### `teams`
`team_id` (PK), `team_name`, `team_leader_email`(+`_canonical`), `primary_office`
(FK→locations), `reports_to_type`, `reporting_manager_email`(+`_canonical`),
`formed_date` (ISO), `org_id`/`org_name` (FK→organizations),
`leader_staff_type` (direct/non_direct/unresolved).

### `monthly_achievements`
`month` (YYYY-MM), `title`, `category`, `impact_score` (float, null if textual),
`impact_score_raw` (str, audit), `reported_by`, `team_name`, `team_id`,
`attributable` (bool — resolvable to a unique team_id).

### `locations`
`location_code` (PK), `city`, `country`, `region` (AMER/EMEA/APAC), `timezone`.

### `organizations`
`org_id` (PK), `org_name`, `org_leader_email` (canonical).

## Gold datasets

### `team_members` (Q1)
team_id, team_name, employee_id, employee_name, designation, department, leader,
location, staff_type, status.

### `team_locations` (Q2)
team_id, team_name, primary_office, city, state (null), country, region,
employee_count, leader_location.

### `monthly_achievements` (Q3)
year, month, team_id, team_name, achievement_count, achievement_details,
performance_score.

### `leader_colocation` (Q4)
team_id, leader, leader_location, majority_team_location, co_located (Yes/No).

### `non_direct_leaders` (Q5)
team_id, leader, leader_type, direct_or_non_direct.

### `non_direct_staff_ratio` (Q6)
team_id, total_members, non_direct_members, ratio, above_threshold.

### `organization_reporting` (Q7)
team_id, organization_leader, org_name, reporting_chain, reporting_status.
