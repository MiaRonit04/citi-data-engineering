# ACME Organizational Analytics Platform

> Enterprise-grade **Medallion Data Lake** built for the **Citi Data Engineering Coding Workshop**.
> Ingests six disconnected source systems, cleans and validates them, and curates
> **exactly seven Gold datasets** that answer the seven workshop business questions —
> served through a Streamlit dashboard and a Jupyter notebook that consume **only** Gold.

---

## 1. Problem statement

ACME Inc.'s employee, contractor, team, location, organisation and achievement
data live in six disconnected systems, in inconsistent formats. The business
needs a centralised analytics platform to answer seven questions about team
composition, location, achievements, leadership and reporting structure.

## 2. The seven business questions (answered by Gold)

| # | Question | Gold dataset | Answer* |
|---|----------|--------------|--------:|
| 1 | Who are the members of each team? | `team_members` | 25,000 teams · 240,660 memberships |
| 2 | Where are the teams located? | `team_locations` | 9 offices, 3 regions |
| 3 | Monthly achievements of each team? | `monthly_achievements` | 123,525 attributable achievements |
| 4 | Teams whose leader is not co-located with the majority? | `leader_colocation` | **17,513** teams |
| 5 | Teams whose leaders are non-direct staff? | `non_direct_leaders` | **3,723** teams |
| 6 | Teams with non-direct staff ratio > 20%? | `non_direct_staff_ratio` | **9,337** teams |
| 7 | Teams reporting directly to org leaders? | `organization_reporting` | **9,957** teams |

\*Figures from the current run (`reports/business_metrics.json`); reproducible from the raw data.

## 3. Architecture

```
Source Systems (CSV / JSON)  ──►  [optional PostgreSQL landing]
        │
        ▼
   Bronze  — raw, immutable, Parquet, partitioned by ingest date + metadata
        │
        ▼
   Silver  — cleaned · standardized · schema-validated · FK-validated · quarantine
        │
        ▼
   Gold    — exactly 7 curated business datasets + validation + metrics
        │                    │
        ▼                    ▼
  Streamlit Dashboard   Jupyter Notebook        (Gold-only consumers)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/lineage_graph.mmd](docs/lineage_graph.mmd).

## 4. Technology stack

Python 3.12 · pandas · pyarrow · DuckDB · **Pandera** (schema validation) ·
**Pydantic / pydantic-settings** (typed config) · **Loguru** (structured logging) ·
Parquet (snappy) · Streamlit + Plotly · PostgreSQL + SQLAlchemy + Alembic ·
Pytest · Docker / Docker Compose · Mermaid.

## 5. Repository structure

```
config/        source registry (sources.json)          etl/common/   config·logging·utils·metadata·exceptions
datasets/      raw scenario (input, read-only)          etl/bronze/   raw ingestion
lakehouse/     bronze · silver · gold · quarantine      etl/silver/   clean·standardize·validate·quarantine
reports/       generated JSON reports + history         etl/gold/     7 business datasets + validation
lineage/       lineage builder → json/md/mmd            dashboard/    Streamlit app (Gold-only)
db/            SQLAlchemy models + Alembic              notebooks/    analysis.ipynb (Gold-only)
tests/         pytest suite (63 tests)                  docker/       Dockerfile
docs/          full documentation set                   run_pipeline.py  orchestrator CLI
```

## 6. Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # adjust if needed
# place the scenario under datasets/ (see .env DATASETS_DIR)
python run_pipeline.py all                # Bronze → Silver → Gold → lineage
streamlit run dashboard/app.py            # open http://localhost:8501
```

Run individual stages: `python run_pipeline.py bronze|silver|gold|lineage`.

## 7. Quick start (Docker)

```bash
docker compose up --build
# postgres + one-shot ETL + dashboard on http://localhost:8501
```

## 8. Running the pipeline

Each stage is independently executable, **idempotent** (re-running yields
identical output) and **recoverable** (one bad dataset never aborts the batch).
Outputs land in `lakehouse/` and machine-readable reports in `reports/`
(`quality_metrics.json`, `validation_summary.json`, `gold_validation_report.json`,
`business_metrics.json`, `lineage.json`, `execution_history.jsonl`, …).

## 9. Dashboard & notebook

- **Dashboard** (`dashboard/app.py`): Home · Business Analytics (7 questions) ·
  Pipeline Status · Data Quality · Pipeline Metrics · Data Lineage ·
  Documentation · About. Each question has an interactive table, Plotly chart and
  CSV/Parquet download.
- **Notebook** (`notebooks/analysis.ipynb`): narrated analysis of all seven
  questions. Regenerate with `python notebooks/build_notebook.py`.

Both read **only** the Gold layer, via `dashboard/data_access.py`.

## 10. Testing

```bash
pytest            # 63 tests: cleaning, standardization, dedupe, relationships,
                  # idempotency, Gold aggregations, config/IO
```

See [docs/TESTING.md](docs/TESTING.md).

## 11. Documentation

Architecture, data dictionary, profiling, cleaning rules, schema rules,
validation & quality reports, transformations, lineage, ER diagram, ETL flow,
installation, user guide, deployment, assumptions, requirements traceability and
a completion checklist all live in [`docs/`](docs/) (index in
[docs/README.md](docs/README.md)).

## 12. Known limitations

- `team_name` is non-unique (200 names / 25,000 teams); achievements linked only
  by name cannot be uniquely attributed and are excluded from the per-team grain
  (documented in [ASSUMPTIONS](docs/ASSUMPTIONS.md)).
- The source has no *state* field; geography is at city/country/region grain.
- FastAPI is intentionally **not** implemented (optional in the brief; focus is
  the data platform).

## 13. Future improvements

Fuzzy team disambiguation for name-only achievements · richer location reference
with states · incremental/CDC ingestion with watermarks · cloud object-store
backend (S3/ADLS/GCS) behind the existing path abstraction.
