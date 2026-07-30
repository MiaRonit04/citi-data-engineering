# SCHEMA RULES

Declarative Silver schemas are defined with **Pandera** in
`etl/silver/schema_validation.py` and applied post-standardization in lazy mode
(all violations collected; failing rows quarantined, batch continues).

## Common conventions

- Dates validated against `^\d{4}-\d{2}-\d{2}$` (post-standardization ISO).
- Month validated against `^\d{4}-\d{2}$`.
- Emails validated against `^[^@\s]+@[^@\s]+\.[^@\s]+$`.
- `strict=False` (unexpected columns tolerated but reported), `coerce=True`.

## Per-dataset contracts

### `locations`
`location_code` `LOC-\d{2}` **unique, not null** · `city`, `country` not null ·
`region ∈ {AMER, EMEA, APAC}`.

### `organizations`
`org_id` `ORG-\d{2}` unique not null · `org_name` not null ·
`org_leader_email` email, not null.

### `employees`
`emp_id` `EMP-\d+` **unique not null** · `email`/`email_canonical` nullable ·
`hire_date` ISO nullable · `status ∈ {Active, Terminated}`.

### `contractor_roster`
`contractor_id` `CTR-\d+` unique not null · `start_date`/`end_date` ISO nullable ·
`status ∈ {Active, Ended}`.

### `teams`
`team_id` `TM-\d+` **unique not null** · `team_name` not null ·
leader/manager canonical emails nullable · `formed_date` ISO nullable ·
`org_id`, `org_name` nullable.

### `team_membership`
`team_code` `TM-\d+` nullable · canonical email nullable ·
**`allocation_pct` Int64 in `[0,100]`** · dates ISO nullable.

### `monthly_achievements`
`month` `YYYY-MM` not null · `title`, `category` not null ·
`impact_score` float ≥ 0 nullable · `impact_score_raw` string nullable ·
`team_id`, `team_name` nullable.

## Schema drift

Because `strict=False`, unexpected columns do not fail the batch but are visible
in `validation_summary.json`. Missing required columns are caught earlier, in
Bronze pre-ingest validation (`etl/bronze/ingest_files.py::validate_readable`).
