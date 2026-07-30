# USER GUIDE

## Running the pipeline
`python run_pipeline.py [all|bronze|silver|gold|lineage]`. Outputs go to
`lakehouse/` and `reports/`. Re-running is safe (idempotent).

## Reading the outputs
| Artefact | Location |
|----------|----------|
| Curated Gold datasets | `lakehouse/gold/<dataset>/…/data.parquet` |
| Quarantined records | `lakehouse/quarantine/<dataset>/<reason>.parquet` |
| Quality metrics | `reports/quality_metrics.json` |
| Validation summaries | `reports/validation_summary.json`, `reports/gold_validation_report.json` |
| Business answers | `reports/business_metrics.json` |
| Lineage | `docs/lineage.md`, `docs/lineage_graph.mmd`, `reports/lineage.json` |
| Run history | `reports/execution_history.jsonl` |

## Dashboard
`streamlit run dashboard/app.py`. Sidebar pages:
- **Home** — KPI overview.
- **Business Analytics** — the 7 questions, each with table, chart, downloads.
- **Pipeline Status / Metrics** — run status, history, durations.
- **Data Quality** — scores, quarantine, cleaning/validation summaries.
- **Data Lineage** — Mermaid graph + Gold provenance.
- **Documentation / About**.

## Notebook
Open `notebooks/analysis.ipynb` (regenerate via `python notebooks/build_notebook.py`).
It walks through all seven questions using Gold data only.

## Configuration
All behaviour is controlled by `.env` (paths, retries, compression, quality
thresholds, business rules like `NON_DIRECT_RATIO_THRESHOLD`). Never edit code to
change a path or threshold.

## Adding a new source
Add an entry to `config/sources.json` (dataset, source_system, relative_path,
format, natural_key, required_columns) — Bronze picks it up automatically.
