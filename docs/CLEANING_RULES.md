# CLEANING RULES

Every rule is deterministic, reproducible, unit-tested, and applied explicitly —
data is **never silently changed**. Implemented in `etl/silver/data_cleaning.py`
(generic) and `etl/silver/data_standardization.py` + `transforms.py`
(dataset-specific). Coercions are counted in `reports/cleaning_summary.json`.

## Generic text cleaning (all string columns)

| Rule | Description | Function |
|------|-------------|----------|
| Unicode NFKC | Normalise visually-identical glyphs | `normalize_unicode` |
| Strip invisibles | Remove zero-width chars; NBSP → space | `strip_invisible` |
| Whitespace | Trim ends, collapse internal runs to one space | `normalize_whitespace` |
| Null tokens | `'', na, n/a, none, null, nil, unknown, unspecified, -, --` → `null` | `to_null_if_token` |

## Standardization rules

| Field(s) | Rule | Example | Function |
|----------|------|---------|----------|
| All dates | Parse ≥10 formats → ISO `YYYY-MM-DD`; unparseable non-blank → null (counted) | `11/18/2016` → `2016-11-18`; `February 10, 2024` → `2024-02-10` | `parse_date` |
| `month` | → `YYYY-MM` | `March 2026` → `2026-03` | `parse_month` |
| Emails | lower, trim, strip spaces, `acmeinc`→`acme-inc`, unify `_`↔`.` | `PATRICIA_LANE@ACME-INC.COM` → `patricia.lane@acme-inc.com` | `canonical_email` |
| `department` | Canonical Title-Case (10 canonical values) | `FINANCE`/`finance` → `Finance` | `canonical_department` |
| `employment_type` | 6 variants → `Full-Time` | `FT`,`FTE`,`Employee` → `Full-Time` | `canonical_employment_type` |
| `team_code` | → `TM-###` (zero-padded) | `tm006`,`tm-5` → `TM-006`,`TM-005` | `canonical_team_code` |
| `allocation_pct` | Coerce int, enforce `[0,100]`; out-of-range → null + flag | `120`,`-10` → null (`INVALID_ALLOCATION`) | `bounded_int` |
| `impact_score` | Numeric coercion; textual (`Low`) → null, raw kept in `impact_score_raw` | `Low` → null | `coerce_numeric` |

## Duplicate rules

| Rule | Scope | Resolution |
|------|-------|-----------|
| Full-row duplicates | all datasets | keep first, quarantine rest (`DUPLICATE_FULL_ROW`) |
| Natural-key duplicates | per `sources.json` `natural_key` | stable sort + keep first (`DUPLICATE_NATURAL_KEY`) |

## Notable domain rules

- **`LOC-01` conflict** (Austin vs Dallas): keep first (Austin), quarantine
  second — see [ASSUMPTIONS](ASSUMPTIONS.md) #7.
- **Broken `manager_emp_id`** (e.g. `EMP-200013`): row kept, manager reference
  nulled, `broken_manager_fk=True` — #16.
- **Orphan members / achievements**: quarantined, never dropped silently — #15, #17.

All the above are covered by tests in `tests/test_cleaning.py` and
`tests/test_standardization.py`.
