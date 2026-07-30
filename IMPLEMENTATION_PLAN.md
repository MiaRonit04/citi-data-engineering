# IMPLEMENTATION PLAN

**Project:** ACME Inc. Organizational Analytics Platform
**Architecture:** Medallion Data Lake (Bronze → Silver → Gold) + analytics consumers
**Status of planning inputs:** ✅ Repository inspected · ✅ All 7 datasets profiled ([DATA_PROFILING_REPORT.md](docs/DATA_PROFILING_REPORT.md)) · ✅ Assumptions recorded ([ASSUMPTIONS.md](docs/ASSUMPTIONS.md))

---

## 1. Project Overview

ACME's employee, contractor, team, location, organization and achievement data
live in six disconnected source systems. This platform ingests them into an
immutable **Bronze** raw zone, cleans/standardizes/validates them into a trusted
**Silver** zone, and curates exactly **seven Gold** business datasets that answer
the seven workshop questions. A Streamlit dashboard and a Jupyter notebook
consume **only** Gold. Everything is config-driven, logged, tested and
reproducible.

## 2. Architecture

```
Source Systems (CSV / JSON)  ──► (optional PostgreSQL landing)
        │
        ▼
   Bronze  (raw, immutable, Parquet, partitioned by ingest date, + metadata)
        │
        ▼
   Silver  (clean · standardized · schema-validated · FK-validated · quarantine)
        │
        ▼
   Gold    (exactly 7 curated business datasets + validation + metrics)
        │             │
        ▼             ▼
  Streamlit DB   Jupyter Notebook      (Gold-only consumers)
```

Lineage is tracked end-to-end (`Source → Bronze → Silver → Gold → Analytics`).

## 3. Folder Structure

```
citi-data-engineering/
├── config/            sources.json (source registry), logging/settings
├── datasets/          raw scenario (input, read-only)
├── lakehouse/
│   ├── bronze/        raw Parquet, partitioned + _metadata
│   ├── silver/        cleaned Parquet + _quality
│   ├── gold/          7 curated datasets + _validation
│   └── quarantine/    rejected records with reasons
├── etl/
│   ├── common/        config · logging · exceptions · utils · metadata
│   ├── bronze/        ingest_files · ingest_postgres · bronze_pipeline
│   ├── silver/        schema_validation · data_cleaning · standardization ·
│   │                  relationship_validation · duplicate_detection · silver_pipeline
│   └── gold/          gold_business_questions · gold_pipeline
├── lineage/           lineage builder → lineage.json/md/mmd
├── validation/        pandera schemas + quality metric helpers
├── dashboard/         Streamlit app (pages/)
├── notebooks/         analysis.ipynb
├── db/                SQLAlchemy models + Alembic migrations
├── tests/             pytest suite
├── reports/           generated JSON reports + execution history
├── docs/              all markdown deliverables + mermaid diagrams
├── docker/            Dockerfile + entrypoints
├── scripts/           helper CLIs (profiling, load-to-postgres)
└── run_pipeline.py    orchestrator (bronze|silver|gold|all)
```

## 4. Database Design (serving / metadata)

Normalized star-ish schema in PostgreSQL for the serving copy of Gold plus a
`pipeline_execution` audit table. Dimensions: `dim_location`, `dim_organization`,
`dim_team`, `dim_person`. Facts: `fact_team_membership`, `fact_monthly_achievement`.
Constraints: PKs, FKs, NOT NULL, unique, check (`ratio BETWEEN 0 AND 1`). ER
diagram generated as Mermaid in [docs/ER_DIAGRAM.md]. The Parquet lake remains
the system of record; Postgres load is optional (`scripts/load_gold_to_postgres.py`).

## 5. ETL Architecture

Each layer is a package with **single-responsibility modules** and a
`*_pipeline.py` orchestrator exposing `run()`. Cross-cutting concerns
(config, logging, retry, metadata) live in `etl/common` and are injected, never
duplicated. Every stage is **idempotent** (partition overwrite + deterministic
sorts), **recoverable** (per-dataset try/except, continue-on-failure), and
**observable** (StageMetrics + structured logs).

### 5.1 Bronze strategy
- Driven entirely by `config/sources.json`.
- Pre-ingest validation: file exists, readable, required columns present.
- Read raw **as strings** (no type coercion) → write Parquet partitioned by
  `year=/month=/day=`. **Zero transformation** (immutable source of truth).
- Emit `IngestionMetadata` per dataset (checksums, counts, size, duration).
- One dataset failing does not stop the others.

### 5.2 Silver strategy
Deterministic, reproducible transforms in this order per dataset:
1. **Cleaning** — trim/collapse whitespace, strip invisible unicode, canonical
   casing, NULL-token normalization (`N/A`, `Unknown`, blank → null).
2. **Standardization** — dates → `YYYY-MM-DD`; month → `YYYY-MM`; emails →
   canonical; departments/employment_type → canonical; numeric coercion with
   bounds (`allocation_pct`, `impact_score`).
3. **Duplicate detection** — full-row + PK-level; losers quarantined.
4. **Schema validation** — Pandera schema per dataset (types, nullability,
   allowed domains, uniqueness).
5. **Relationship validation** — FK resolution (member→person, team→location,
   team→org, achievement→team, manager→employee); orphans quarantined.
6. Write Silver Parquet + `quality_metrics.json`, `cleaning_summary.json`,
   `validation_summary.json`.

### 5.3 Gold strategy
Build **exactly seven** datasets (one per business question) with DuckDB SQL /
pandas over Silver, each with documented transformation + post-build validation
(grain uniqueness, null checks, cross-check totals vs Silver). Emit
`gold_validation_report.json` and `business_metrics.json`.

| Gold dataset | Question |
|--------------|----------|
| `team_members` | Q1 members of each team |
| `team_locations` | Q2 team locations |
| `monthly_achievements` | Q3 monthly achievements per team |
| `leader_colocation` | Q4 leader not co-located with majority |
| `non_direct_leaders` | Q5 non-direct leaders |
| `non_direct_staff_ratio` | Q6 non-direct ratio > 20% |
| `organization_reporting` | Q7 reporting to org leaders |

## 6. Validation Strategy
- **Schema:** Pandera `DataFrameSchema` per Silver dataset.
- **Relationships:** explicit FK resolution with quarantine + counts.
- **Quality metrics:** missing %, duplicate %, schema-valid %, relationship-valid
  %, rejected/accepted, composite quality score vs configurable thresholds.
- **Gold:** grain uniqueness + totals reconciliation against Silver.

## 7. Testing Strategy
`pytest` covering: cleaning functions (whitespace/case/unicode/null tokens),
date & month normalization (all formats), email canonicalization, duplicate
detection, allocation bounds, `team_code` normalization, relationship
resolution, idempotency (run twice → identical Parquet hash), Gold aggregation
correctness (Q5=3,937, Q7=9,957, grain uniqueness), config loading, dashboard &
notebook Gold-loading helpers.

## 8. Dashboard Design
Streamlit multipage: Home (KPIs) · Business Analytics (7 questions, each with
table + Plotly chart + CSV/Parquet download) · Pipeline Status · Data Quality ·
Pipeline Metrics · Data Lineage (mermaid) · Documentation · About. **Reads Gold
only**, auto-discovers latest Gold via `etl.common.utils.read_latest_parquet`.

## 9. Notebook Design
`analysis.ipynb`: intro/architecture → Gold summaries → each business question
(objective, load Gold, analyze, Plotly viz, interpret) → insights/conclusion.
Gold-only.

## 10. Deployment Strategy
Local: `python -m venv`, `pip install -r requirements.txt`, `python run_pipeline.py all`.
Docker: `docker compose up --build` starts Postgres + ETL (one-shot) + dashboard.
All config via `.env`.

## 11. Execution Order (build sequence)
1. Config + scaffold ✅
2. Common layer (config/logging/utils/metadata/exceptions) ✅
3. Bronze
4. Silver (clean → standardize → dedupe → schema → relationships → quarantine)
5. Gold (7 datasets + validation + metrics)
6. Lineage + orchestrator + reports
7. Dashboard + notebook
8. Tests + Docker + DB + docs + self-audit

## 12. Risk Analysis
| Risk | Mitigation |
|------|-----------|
| `team_name` ambiguity corrupts Q3 | Grain on `team_id`; name-only achievements quarantined/counted |
| Non-idempotent reruns | Partition overwrite + deterministic sorts + content-hash test |
| One bad dataset halts pipeline | Per-dataset isolation, continue-on-failure |
| Memory on 200k+ rows | Vectorized pandas; chunked read where needed; Parquet+snappy |
| Hidden dirtiness beyond profiling | Pandera catches schema drift; quarantine is default, not drop |
| Direct/non-direct overlap | Explicit tie-break rule (ASSUMPTIONS #2), unit-tested |

## 13. Assumptions
See [ASSUMPTIONS.md](docs/ASSUMPTIONS.md) — 23 documented decisions.

## 14. Success Criteria
Bronze immutable ✔ · Silver validated ✔ · exactly 7 Gold datasets ✔ · dashboard
& notebook Gold-only ✔ · validation + lineage + quality reports generated ✔ ·
tests pass ✔ · Docker runs ✔ · reproducible ✔ · docs complete ✔.
