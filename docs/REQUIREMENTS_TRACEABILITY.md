# REQUIREMENTS TRACEABILITY

Maps every mandatory workshop requirement to its implementation. Status: ✅ done.

| Requirement | Implementation | File/Module | Status |
|-------------|----------------|-------------|:------:|
| Medallion architecture (Bronze/Silver/Gold) | Layered lakehouse + pipelines | `etl/bronze`, `etl/silver`, `etl/gold`, `lakehouse/` | ✅ |
| Data profiling before implementation | Evidence-based profiling | `docs/DATA_PROFILING_REPORT.md` | ✅ |
| Implementation plan before code | Plan authored first | `IMPLEMENTATION_PLAN.md` | ✅ |
| Bronze raw & immutable | String-only raw ingest, no transforms | `etl/bronze/ingest_files.py`, `bronze_pipeline.py` | ✅ |
| Bronze partitioning `year/month/day` | Hive partitions | `etl/common/utils.write_parquet` | ✅ |
| Bronze metadata (checksums, counts, size, duration) | `IngestionMetadata` | `etl/common/metadata.py` | ✅ |
| Multi-format support (CSV/JSON/Parquet/PostgreSQL) | Readers + registry | `ingest_files.py`, `ingest_postgres.py`, `config/sources.json` | ✅ |
| Continue-on-failure per dataset | Per-dataset try/except | all `*_pipeline.py` | ✅ |
| Silver cleaning (whitespace/unicode/null tokens/case) | Cleaning primitives | `etl/silver/data_cleaning.py` | ✅ |
| Date standardization → `YYYY-MM-DD` | Multi-format parser | `data_standardization.parse_date` | ✅ |
| String/categorical standardization | Canonical mappers | `data_standardization.py`, `transforms.py` | ✅ |
| Schema validation | Pandera schemas | `etl/silver/schema_validation.py` | ✅ |
| Relationship/FK validation | Cross-dataset resolver | `etl/silver/relationship_validation.py` | ✅ |
| Duplicate detection | Full-row + key dedupe | `etl/silver/duplicate_detection.py` | ✅ |
| Quarantine (never delete) | Annotated rejects | `etl/silver/quarantine.py`, `lakehouse/quarantine/` | ✅ |
| Data-quality metrics JSON | quality/cleaning/validation summaries | `reports/*.json` | ✅ |
| Idempotency | Partition overwrite + deterministic sorts + test | `utils.write_parquet`, `test_config_and_io.py`, `test_gold_business.py` | ✅ |
| Error handling + retry/backoff | Typed exceptions + retry | `exceptions.py`, `utils.retry` | ✅ |
| Gold: exactly 7 datasets | Contract-enforced builders | `etl/gold/gold_business_questions.py`, `gold_pipeline.py` | ✅ |
| Gold answers all 7 questions (no hardcoding) | Derived transformations | `gold_business_questions.py` | ✅ |
| Gold validation + cross-checks | Grain/coverage/cross-signal | `gold_pipeline._validate_gold` | ✅ |
| Business metrics | `business_metrics.json` | `gold_pipeline._business_metrics` | ✅ |
| Data lineage (json/md/mmd) | Lineage builder | `lineage/lineage_builder.py`, `docs/lineage.*` | ✅ |
| Transformation catalog | Documented | `docs/TRANSFORMATIONS.md` | ✅ |
| Structured logging | Loguru, rotating file sink | `etl/common/logging.py`, `logs/` | ✅ |
| Execution history | JSONL ledger | `metadata.append_execution_history`, `reports/execution_history.jsonl` | ✅ |
| Configuration system (no hardcoding) | pydantic-settings + registry | `etl/common/config.py`, `.env.example`, `config/sources.json` | ✅ |
| Independent stage execution | Orchestrator CLI | `run_pipeline.py` | ✅ |
| Streamlit dashboard (Gold-only, 8 pages) | Multipage app | `dashboard/app.py`, `dashboard/data_access.py` | ✅ |
| Plotly visualizations | Charts per page | `dashboard/app.py`, notebook | ✅ |
| Jupyter notebook (Gold-only) | Narrated analysis | `notebooks/analysis.ipynb` | ✅ |
| PostgreSQL + SQLAlchemy + Alembic | ORM + migrations | `db/models/models.py`, `db/migrations/`, `alembic.ini` | ✅ |
| ER diagram (Mermaid) | Serving schema | `docs/ER_DIAGRAM.md` | ✅ |
| Docker + Compose | 3 services | `docker/Dockerfile`, `docker-compose.yml` | ✅ |
| Automated tests (pytest) | 63 tests | `tests/` | ✅ |
| Documentation set | Full docs | `docs/`, `README.md` | ✅ |
| Mermaid architecture / lineage / ER diagrams | 3 diagrams | `ARCHITECTURE.md`, `lineage_graph.mmd`, `ER_DIAGRAM.md` | ✅ |
| Assumptions documented | 23 decisions | `docs/ASSUMPTIONS.md` | ✅ |
| Reproducible from README | One-command run | `README.md`, `run_pipeline.py` | ✅ |
| FastAPI (optional) | Intentionally omitted | — (see README limitations) | ➖ |
