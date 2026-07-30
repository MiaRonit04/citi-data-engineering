# DATA PROFILING REPORT

**Project:** ACME Inc. — Organizational Analytics Platform (Citi Data Engineering Workshop)
**Scenario:** `data-engineering-sample-teams-scenario`
**Profiled with:** pandas 2.2.3 / pyarrow 19.0.0
**Purpose:** Establish ground truth about the raw source systems *before* any pipeline code is written. All cleaning, standardization and validation rules downstream are inferred from the facts recorded here — none are hardcoded blindly.

> This report is **evidence-based**: every figure below was produced by scanning the actual raw files, not assumed.

---

## 1. Source Systems Overview

Seven raw datasets arrive from **six disconnected source systems**:

| # | Source System | Dataset | File | Format | Rows | Cols |
|---|---------------|---------|------|--------|-----:|-----:|
| 1 | `employee_directory` | employees | `employees.csv` | CSV | 200,004 | 9 |
| 2 | `vendor_management` | contractor_roster | `contractor_roster.csv` | CSV | 50,000 | 9 |
| 3 | `project_tracking` | team_membership | `team_membership.csv` | CSV | 244,202 | 6 |
| 4 | `project_tracking` | teams | `teams.json` | JSON (array) | 25,000 | 9 (nested) |
| 5 | `performance_management` | monthly_achievements | `monthly_achievements.json` | JSON (array) | 184,226 | 7 |
| 6 | `facilities` | locations | `locations.csv` | CSV | 10 | 5 |
| 7 | `org_structure` | organizations | `organizations.json` | JSON (array) | 6 | 3 |

**Total raw records:** ~703,448 across 7 datasets (~95 MB uncompressed).

---

## 2. Per-Dataset Profiles

### 2.1 `employees` (direct staff master) — 200,004 rows
| Column | Unique | Blank/Null | Notes |
|--------|-------:|-----------:|-------|
| `emp_id` | 200,000 | 0 | **Candidate PK** — but **4 duplicate ids** + 4 fully-duplicated rows. |
| `full_name` | 115,228 | 0 | Non-unique (namesakes). |
| `email` | 154,256 | 0 | **Not unique** — casing/format variants collapse many identities. |
| `department` | 31 | 0 | Only **10 real departments**; 21 are case variants (`finance`, `FINANCE`, `Finance`, `It Operations`…). |
| `location_code` | 10 | **9,954** | FK → `locations`; ~5% missing. |
| `employment_type` | 6 | 0 | All six (`Full-Time`, `Full Time`, `FT`, `Employee`, `full-time`, `FTE`) mean the same thing → **direct/full-time**. |
| `manager_emp_id` | 98,608 | 12 | Self-referencing FK; contains **invalid ids** (e.g. `EMP-200013`, out of range). |
| `hire_date` | 19,026 | 4,017 | **≥4 date formats** (`2018-08-10`, `11/18/2016`, `12-May-2022`, …). |
| `status` | 2 | 0 | `Active` / `Terminated`. |

### 2.2 `contractor_roster` (non-direct staff master) — 50,000 rows
| Column | Unique | Blank/Null | Notes |
|--------|-------:|-----------:|-------|
| `contractor_id` | 50,000 | 0 | Clean PK (no dups). |
| `email` | 48,924 | 0 | Near-unique; format variants exist. |
| `agency` | 5 | 0 | BlueWave, TalentBridge, NorthPeak, Apex, Vertical. |
| `location_code` | 10 | 4,057 | FK → `locations`. |
| `engagement_type` | 7 | 0 | `C2C`, `contractor`, `Contractor`, `Temp`, `1099`, `Consultant`, `Vendor` → all **non-direct**. |
| `start_date` / `end_date` | — | 924 / 42,721 | Multi-format incl. long form `February 10, 2024`. |
| `status` | 2 | 0 | `Active` / `Ended`. |

### 2.3 `team_membership` (person ↔ team bridge) — 244,202 rows
| Column | Unique | Blank/Null | Notes |
|--------|-------:|-----------:|-------|
| `team_code` | 25,000 | 0 | FK → `teams.team_id`; **casing/padding drift** (`tm-005`, `tm006`). |
| `employee_email` | 154,426 | 0 | FK → person; **leading/trailing spaces** (`  jeffrey_lowe@… `). |
| `role` | 5 | 0 | `Team Lead`, `Contributor`, `Individual Contributor`, `Member`, `SME`. |
| `allocation_pct` | 5 | 0 | **Invalid values present**: `120`, `-10` (outside 0–100). |
| `start_date` | 9,896 | 4,779 | Multi-format. |
| `end_date` | 4,377 | 223,097 | Mostly null = still active (expected). |
| — | — | — | 6 fully-duplicated rows; 3,536 emails resolve to **neither** roster (orphans). |

### 2.4 `teams` (team master) — 25,000 rows
| Column | Unique | Null | Notes |
|--------|-------:|-----:|-------|
| `team_id` | 25,000 | 0 | **Clean PK.** |
| `team_name` | **200** | 0 | ⚠️ **Non-unique** — 25,000 teams share only 200 names → name alone cannot identify a team. |
| `team_leader_email` | 22,986 | 0 | 21,277 resolve to employees, **3,937 to contractors**, 0 unresolved. |
| `primary_office` | 9 | 0 | FK → `locations`. |
| `reports_to_type` | 5 | 0 | `Org Leader` (9,957), `VP Direct Report`, `Department Manager`, `Director`, `Senior Manager`. |
| `reporting_manager_email` | 13,994 | 0 | For `Org Leader` rows this is always an org-leader email. |
| `formed_date` | 10,318 | 0 | Multi-format incl. `February 05, 2021`. |
| `organization.org_id` / `.org_name` | 6 / 6 | 0 | Nested; FK → `organizations`. |

### 2.5 `monthly_achievements` — 184,226 rows
| Column | Unique | Null | Notes |
|--------|-------:|-----:|-------|
| `month` | 12 | 0 | **Two formats**: `2026-07` and `March 2026`. Range Feb–Jul 2026. |
| `title` | 354 | 0 | Free-text achievement titles. |
| `category` | 5 | 0 | Customer Impact, Innovation, Cost Savings, Delivery, Process Improvement. |
| `impact_score` | 94 | 14,876 | **Mixed type** — numeric (`2.2`) and categorical (`Low`) interleaved. |
| `reported_by` | 13,983 | 0 | Reporter email. |
| `team_name` | 4,108 | **106,804** | Non-unique linkage key. |
| `team_id` | 24,829 | **60,693** | Preferred linkage key; **5,422 rows have neither `team_id` nor `team_name`** (orphans). |

### 2.6 `locations` — 10 rows
Clean dimension **except `LOC-01` appears twice** → `Austin` **and** `Dallas` (duplicate location code with conflicting city). Columns: `location_code, city, country, region, timezone`.

### 2.7 `organizations` — 6 rows
Clean. `org_id, org_name, org_leader_email`. The six org-leader emails are the anchor for Question 7.

---

## 3. Candidate Keys & Relationships (inferred)

```
organizations(org_id)  ◄──────────────┐  teams.organization.org_id
locations(location_code) ◄────────────┤  employees.location_code
        ▲   ▲                          ├  contractor_roster.location_code
        │   └──────────────────────────┤  teams.primary_office
employees(emp_id) ──self──► manager_emp_id
        ▲                              │
        │ (by email)                   │
team_membership(team_code, employee_email)
        │ team_code ─────────────────► teams(team_id)
        │ employee_email ────► employees.email  OR  contractor_roster.email
teams.team_leader_email ─────► employees.email  OR  contractor_roster.email
teams.reporting_manager_email (Org Leader rows) ─► organizations.org_leader_email
monthly_achievements.team_id ─────► teams(team_id)      [preferred]
monthly_achievements.team_name ───► teams(team_name)    [ambiguous, non-unique]
```

**Direct vs non-direct staff** is defined by *which roster an email resolves to*: `employees` ⇒ **direct**, `contractor_roster` ⇒ **non-direct**. Email overlap between the two rosters = **562** (tie-break rule required — see ASSUMPTIONS).

---

## 4. Data-Quality Issues Detected (drives Silver rules)

| Category | Evidence | Silver treatment |
|----------|----------|------------------|
| Duplicate ids / rows | 4 dup `emp_id`, 6 dup membership rows, `LOC-01` conflict | Dedupe deterministically; quarantine conflicts |
| Case inconsistency | `department` 31→10, `employment_type` 6→1, email casing | Canonical casing / mapping |
| Whitespace | padded `employee_email` | strip + collapse whitespace |
| Multi-format dates | ≥4 formats across 4 date columns | Parse → `YYYY-MM-DD` |
| Mixed-type numeric | `impact_score` mixes `Low` with floats | Coerce to numeric, keep textual in audit |
| Out-of-range values | `allocation_pct` `120`, `-10` | Flag/quarantine per business bounds |
| Missing values | `location_code` 9,954; `impact_score` 14,876; `hire_date` 4,017 | Impute-none policy; mark `Unknown` where categorical |
| Broken FKs | `manager_emp_id=EMP-200013`; 3,536 orphan members | Quarantine with reason |
| Key drift | `team_code` `tm006` vs `TM-006` | Normalize to canonical `TM-###` |
| Non-unique business key | `team_name` (200 for 25k teams) | Use `team_id` as grain; document limitation |
| Orphan facts | 5,422 achievements with no team linkage | Quarantine |

---

## 5. Business-Question Feasibility (all answerable from real data)

| Q | Question | Derivable from | Early signal |
|---|----------|----------------|--------------|
| 1 | Members of each team | `team_membership` ⋈ `employees`/`contractors` ⋈ `teams` | 25,000 teams |
| 2 | Team locations | `teams.primary_office` ⋈ `locations` | 9 offices |
| 3 | Monthly achievements per team | `monthly_achievements` (via `team_id`) | 12 months, 5 categories |
| 4 | Leader not co-located w/ majority | leader loc vs modal member loc | needs member-location join |
| 5 | Teams w/ non-direct leaders | leader email ∈ contractor roster | **3,937 teams** |
| 6 | Non-direct staff ratio > 20% | contractors ÷ members per team | derived per team |
| 7 | Teams reporting to org leaders | `reports_to_type='Org Leader'` (== reporting-mgr ∈ org leaders) | **9,957 teams** (two signals agree) |

---

## 6. Conclusion

The scenario is intentionally dirty and multi-format, exercising every cleaning
and validation concern in the workshop brief. All seven business questions are
answerable **entirely from the provided data**; no value needs to be fabricated.
Key modeling decisions (direct/non-direct tie-break, `team_name` ambiguity,
achievement orphan handling, `LOC-01` conflict) are documented in
[`ASSUMPTIONS.md`](ASSUMPTIONS.md) and enforced — never silently applied — in the
Silver and Gold layers.
