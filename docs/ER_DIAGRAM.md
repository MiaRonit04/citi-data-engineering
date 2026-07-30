# ENTITY–RELATIONSHIP DIAGRAM

Serving-layer schema (PostgreSQL, `db/models/models.py`). The Parquet Gold layer
is the system of record; this relational model is the optional SQL-serving copy.

```mermaid
erDiagram
    DIM_LOCATION ||--o{ DIM_TEAM : "office"
    DIM_ORGANIZATION ||--o{ DIM_TEAM : "belongs to"
    DIM_TEAM ||--o{ FACT_TEAM_MEMBERSHIP : "has members"
    DIM_TEAM ||--o{ FACT_MONTHLY_ACHIEVEMENT : "has achievements"

    DIM_LOCATION {
        string location_code PK
        string city
        string country
        string region
    }
    DIM_ORGANIZATION {
        string org_id PK
        string org_name
        string org_leader_email
    }
    DIM_TEAM {
        string team_id PK
        string team_name
        string team_leader_email
        string leader_staff_type
        string reports_to_type
        string primary_office FK
        string org_id FK
    }
    FACT_TEAM_MEMBERSHIP {
        int id PK
        string team_id FK
        string employee_id
        string employee_name
        string designation
        string department
        string location
        string staff_type
        string status
    }
    FACT_MONTHLY_ACHIEVEMENT {
        int id PK
        string team_id FK
        string year
        string month
        int achievement_count
        float performance_score
    }
    PIPELINE_EXECUTION {
        string batch_id PK
        string pipeline_name
        string status
        string start_time
        string end_time
        float duration_seconds
        int rows_processed
    }
```

## Constraints

- **PKs:** every table above.
- **FKs:** `dim_team.primary_office → dim_location`, `dim_team.org_id →
  dim_organization`, `fact_*.team_id → dim_team` (all indexed).
- **NOT NULL:** dimension names, fact grain columns.
- **CHECK:** `leader_staff_type ∈ {direct, non_direct, unresolved}`,
  `staff_type ∈ {direct, non_direct, unknown}`, `achievement_count ≥ 0`.

## Migrations

Managed by Alembic (`alembic.ini`, `db/migrations/`). Apply with
`alembic upgrade head`; load Gold with `python scripts/load_gold_to_postgres.py`.
