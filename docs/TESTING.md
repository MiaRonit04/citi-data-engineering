# TESTING

## Run
```bash
pytest                 # 63 tests, ~1s
pytest --cov=etl       # with coverage
```

## Suite

| File | Coverage |
|------|----------|
| `test_cleaning.py` | whitespace, invisible chars, null tokens, title-case, column cleaning |
| `test_standardization.py` | date parsing (all formats), month, email canonicalization + separator unification, department, employment_type, team_code, numeric coercion, allocation bounds |
| `test_duplicates_and_relationships.py` | full-row & key dedupe determinism; FK resolution, staff-type classification, broken-manager nulling, orphan quarantine |
| `test_gold_business.py` | exactly-7 contract, grain uniqueness, ratio bounds/flag, **Q7 cross-signal**, **Q5 reconciliation**, builder determinism (idempotency) |
| `test_config_and_io.py` | settings/paths, source registry, DB URL, batch id, Parquet write idempotency |

## What the tests assert about correctness

- Every observed date format normalises to ISO; unparseable values become null,
  not guesses.
- `allocation_pct` values `120`/`-10` are rejected (not clamped).
- `impact_score = 'Low'` coerces to null with the raw value preserved.
- Orphan members/achievements and dangling manager FKs are quarantined/flagged.
- **Q7 = 9,957** across three independent signals; **Q5** Gold == Silver.
- Building a Gold dataset twice yields byte-identical output (idempotency).

Integration tests skip gracefully if the pipeline output is absent, so the unit
suite runs anywhere.
