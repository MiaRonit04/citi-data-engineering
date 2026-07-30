# DEPLOYMENT

## Local (venv)
See [INSTALLATION.md](INSTALLATION.md). One command runs everything:
`python run_pipeline.py all`.

## Docker Compose
```bash
docker compose up --build
```
Starts three services:
| Service | Role | Port |
|---------|------|------|
| `postgres` | serving / metadata DB (healthchecked) | 5432 |
| `etl` | one-shot full pipeline, then exits | — |
| `dashboard` | Streamlit (starts after ETL succeeds) | 8501 |

Shared named volumes (`lakehouse`, `reports`, `logs`) let the dashboard read what
the ETL produced. Datasets are mounted read-only. All config via `.env`.

## Environment profiles
`APP_ENV = development | testing | production`. Override any setting via
environment variables (12-factor). Secrets (`POSTGRES_PASSWORD`, `DATABASE_URL`)
are never committed — `.env` is git-ignored.

## Cloud readiness
Storage paths are abstracted through `Settings`; pointing `BRONZE_DIR`/…/`GOLD_DIR`
at a mounted object store (S3/ADLS/GCS via `s3fs`/`adlfs`/`gcsfs`) requires no
code change. The stateless ETL container is schedulable on ECS/Cloud Run/AKS;
Postgres maps to RDS/Cloud SQL.

## CI suggestion
`pip install -r requirements.txt && pytest` on every push; optionally run
`python run_pipeline.py all` against a sample to smoke-test the DAG.

## Operational notes
- Logs rotate at 20 MB, retained 14 days (`logs/`).
- Each run appends to `reports/execution_history.jsonl` for audit.
- Re-runs are idempotent; safe to retry after a transient failure.
