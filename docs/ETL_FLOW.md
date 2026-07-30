# ETL FLOW

## Execution order

```mermaid
flowchart LR
    subgraph Bronze
        b1[validate readable] --> b2[read raw as string] --> b3[write partitioned parquet] --> b4[emit ingestion metadata]
    end
    subgraph Silver
        s1[read latest bronze] --> s2[standardize + clean] --> s3[dedupe] --> s4[schema validate] --> s5[relationship validate] --> s6[write silver + quality reports]
    end
    subgraph Gold
        g1[load silver frames] --> g2[build 7 datasets] --> g3[validate grain/cross-signals] --> g4[write gold + business metrics]
    end
    Bronze --> Silver --> Gold --> L[lineage] --> R[reports/execution summary]
```

## Commands

| Goal | Command |
|------|---------|
| Full pipeline | `python run_pipeline.py all` |
| Bronze only | `python run_pipeline.py bronze` |
| Silver only | `python run_pipeline.py silver` |
| Gold only | `python run_pipeline.py gold` |
| Lineage only | `python run_pipeline.py lineage` |

## Guarantees per stage

- **Idempotent** — partition overwrite + deterministic sorts; re-run → identical output.
- **Recoverable** — per-dataset try/except; one failure does not abort the batch.
- **Observable** — `StageMetrics` per dataset, structured logs, execution history.
- **Traceable** — every rejected row quarantined with reason; full lineage emitted.

## Error handling

Malformed/missing files, unreadable schemas and DB blips are caught per dataset;
transient failures retry with exponential backoff (`etl/common/utils.retry`).
Fatal configuration errors stop early with a clear message.
