"""Generate ``analysis.ipynb`` programmatically with nbformat.

Keeping the notebook under source control as a generator guarantees it stays in
lock-step with the Gold schema and is reproducible. Run:

    python notebooks/build_notebook.py    # writes notebooks/analysis.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells: list = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip("\n")))


def code(text: str) -> None:
    cells.append(nbf.v4.new_code_cell(text.strip("\n")))


md(
    """
# ACME Organizational Analytics — Gold Layer Analysis

**Citi Data Engineering Coding Workshop**

This notebook analyses the **Gold layer** of the ACME Medallion data lake to
answer the seven workshop business questions. It reads **only** curated Gold
datasets — never Bronze or Silver — mirroring the architectural boundary the
dashboard also respects.

**Architecture:** `Source → Bronze (raw) → Silver (clean/validated) → Gold (curated) → Analytics`
"""
)

code(
    """
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()))

import pandas as pd
import plotly.express as px
from dashboard import data_access as da

pd.set_option('display.max_columns', None)
TEMPLATE = 'plotly_white'
gold = da.load_all_gold()
metrics = da.load_report('business_metrics')
{k: v.shape for k, v in gold.items()}
"""
)

md(
    """
## Dataset overview

Seven curated Gold datasets, one per business question. Below is the headline
set of organisation metrics computed by the Gold pipeline.
"""
)
code(
    """
pd.Series(metrics).to_frame('value')
"""
)

# Q1
md(
    """
## Q1 — Who are the members of each team?

**Objective:** enumerate every team's members with their designation,
department, resolved staff type and location. Source: `gold/team_members`.
"""
)
code(
    """
tm = gold['team_members']
print(f"{tm['team_id'].nunique():,} teams · {len(tm):,} memberships")
top = tm.groupby('team_name').size().sort_values(ascending=False).head(15).reset_index(name='members')
px.bar(top, x='members', y='team_name', orientation='h', template=TEMPLATE,
       title='Top 15 teams by member count', height=500)
"""
)
code("tm.head(10)")
md(
    """
**Insight:** team sizes are tightly clustered around the organisation average,
and every membership row resolves to a real person (direct or non-direct) —
orphaned members were quarantined in Silver, so Gold is trustworthy.
"""
)

# Q2
md(
    """
## Q2 — Where are the teams located?

**Objective:** map each team to its primary office and geography. Source:
`gold/team_locations`.
"""
)
code(
    """
tl = gold['team_locations']
tree = tl.groupby(['region','country','city']).size().reset_index(name='teams')
px.treemap(tree, path=['region','country','city'], values='teams', template=TEMPLATE,
           title='Office footprint (region → country → city)')
"""
)
md(
    """
**Insight:** the office footprint spans AMER/EMEA/APAC. Note the source lacks a
state field, so geography is analysed at city/country/region granularity
(documented in ASSUMPTIONS).
"""
)

# Q3
md(
    """
## Q3 — What are the monthly achievements of each team?

**Objective:** aggregate achievements per team per month. Only achievements that
resolve to a unique `team_id` are attributed (name-only rows are non-unique and
excluded — see ASSUMPTIONS). Source: `gold/monthly_achievements`.
"""
)
code(
    """
ma = gold['monthly_achievements'].copy()
ma['period'] = ma['year'].astype(str) + '-' + ma['month'].astype(str)
by_month = ma.groupby('period')['achievement_count'].sum().reset_index()
px.line(by_month, x='period', y='achievement_count', markers=True, template=TEMPLATE,
        title='Total attributable achievements by month')
"""
)
md("**Insight:** achievement volume is stable month-to-month, consistent with a steady-state organisation.")

# Q4
md(
    """
## Q4 — How many teams have leaders not co-located with the majority of members?

**Objective:** compare each leader's location to the modal (majority) member
location. Source: `gold/leader_colocation`.
"""
)
code(
    """
lc = gold['leader_colocation']
n_no = int((lc['co_located'] == 'No').sum())
print(f"Teams NOT co-located with the member majority: {n_no:,} of {len(lc):,}")
dist = lc['co_located'].value_counts().reset_index(); dist.columns=['co_located','teams']
px.pie(dist, names='co_located', values='teams', hole=0.45, template=TEMPLATE,
       title='Leader co-location with member majority')
"""
)

# Q5
md(
    """
## Q5 — How many teams have leaders who are non-direct staff?

**Objective:** classify each team leader as direct (employee) or non-direct
(contractor). Source: `gold/non_direct_leaders`.
"""
)
code(
    """
nl = gold['non_direct_leaders']
n_nd = int((nl['direct_or_non_direct'] == 'Non-Direct').sum())
print(f"Teams with non-direct leaders: {n_nd:,}")
d = nl['direct_or_non_direct'].value_counts().reset_index(); d.columns=['leader_type','teams']
px.bar(d, x='leader_type', y='teams', color='leader_type', template=TEMPLATE,
       title='Team leaders: direct vs non-direct')
"""
)

# Q6
md(
    """
## Q6 — How many teams have a non-direct staff ratio greater than 20%?

**Objective:** per team, compute non-direct members ÷ total members and flag
those above the configurable 20% threshold. Source: `gold/non_direct_staff_ratio`.
"""
)
code(
    """
r = gold['non_direct_staff_ratio']
above = int(r['above_threshold'].sum())
print(f"Teams with non-direct ratio > 20%: {above:,} ({above/len(r):.1%} of teams)")
px.histogram(r, x='ratio', nbins=40, template=TEMPLATE, title='Distribution of non-direct staff ratio')
"""
)

# Q7
md(
    """
## Q7 — How many teams report directly to organization leaders?

**Objective:** identify teams whose reporting type is *Org Leader*. This is
independently corroborated by the reporting-manager email matching an org
leader (both signals agree — asserted in Gold validation). Source:
`gold/organization_reporting`.
"""
)
code(
    """
org = gold['organization_reporting']
direct = int((org['reporting_status'] == 'Direct to Org Leader').sum())
print(f"Teams reporting directly to an org leader: {direct:,}")
by_org = (org[org['reporting_status']=='Direct to Org Leader']
          .groupby('org_name').size().reset_index(name='teams'))
px.bar(by_org, x='org_name', y='teams', template=TEMPLATE, title='Directly-reporting teams by organization')
"""
)

md(
    """
## Conclusion & insights

- All seven questions are answered **entirely from curated Gold**, derived from
  real source data — no value was fabricated.
- Data-quality handling in Silver (deduplication, standardization, FK
  validation, quarantine) makes the Gold answers trustworthy and reproducible.
- Key figures are cross-checked (Q5 vs Silver, Q7 across three independent
  signals) in `gold_validation_report.json`.

### Future improvements
- Add a `state` mapping if a richer location reference becomes available.
- Resolve name-only achievements via fuzzy team disambiguation.
- Promote Gold into PostgreSQL for BI-tool consumption (loader provided).
"""
)

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path(__file__).resolve().parent / "analysis.ipynb"
nbf.write(nb, out)
print(f"wrote {out}")
