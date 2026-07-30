# INSTALLATION

## Prerequisites
- Python 3.12 (3.13 also works locally)
- Git
- (Optional) Docker & Docker Compose for the containerised path

## Local install

```bash
git clone <repo> && cd citi-data-engineering
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Provide the dataset

Place the scenario folder under `datasets/` so that this path exists:

```
datasets/data-engineering-sample-teams-scenario/
  employee_directory/employees.csv
  vendor_management/contractor_roster.csv
  project_tracking/{teams.json, team_membership.csv}
  performance_management/monthly_achievements.json
  facilities/locations.csv
  org_structure/organizations.json
```

The path is configured by `DATASETS_DIR` in `.env`.

## Run

```bash
python run_pipeline.py all          # Bronze → Silver → Gold → lineage
pytest                              # 63 tests
streamlit run dashboard/app.py      # http://localhost:8501
```

## Optional: PostgreSQL serving

```bash
# with a running Postgres and DATABASE_URL/POSTGRES_* set in .env
alembic upgrade head
python scripts/load_gold_to_postgres.py
```

## Troubleshooting
- **`ModuleNotFoundError`** — activate the venv / re-run `pip install -r requirements.txt`.
- **Dashboard shows "Gold not found"** — run `python run_pipeline.py all` first.
- **Postgres connection refused** — check `POSTGRES_*` in `.env` or use Docker.
