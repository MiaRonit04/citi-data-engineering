"""ACME Analytics — Streamlit dashboard.

A professional, Gold-only analytics application. Navigation is via the sidebar;
every business page answers exactly one of the seven workshop questions with an
interactive table, a Plotly visualization, a short business summary and CSV /
Parquet downloads. The dashboard never reads Bronze or Silver.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Make the project importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import data_access as da  # noqa: E402

st.set_page_config(page_title="ACME Analytics Platform", page_icon="📊", layout="wide")

PLOTLY_TEMPLATE = "plotly_white"


# ── Cached loaders ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _gold(dataset: str) -> pd.DataFrame:
    return da.load_gold(dataset)


@st.cache_data(show_spinner=False)
def _report(name: str) -> dict:
    return da.load_report(name)


@st.cache_data(show_spinner=False)
def _history() -> pd.DataFrame:
    return da.load_execution_history()


def _download_buttons(df: pd.DataFrame, key: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Download CSV", da.to_csv_bytes(df), f"{key}.csv", "text/csv", key=f"csv_{key}")
    c2.download_button("⬇️ Download Parquet", da.to_parquet_bytes(df), f"{key}.parquet",
                       "application/octet-stream", key=f"pq_{key}")


def _kpi_row(items: list[tuple[str, object]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)


# ── Pages ───────────────────────────────────────────────────────────────────
def page_home() -> None:
    st.title("📊 ACME Organizational Analytics Platform")
    st.caption("Medallion Data Lake · Bronze → Silver → Gold · Gold-only analytics")
    m = _report("business_metrics")
    q = _report("quality_metrics")
    if not m:
        st.warning("No Gold metrics found. Run `python run_pipeline.py all` first.")
        return
    _kpi_row([("Total Employees", f"{m.get('total_employees', 0):,}"),
              ("Total Contractors", f"{m.get('total_contractors', 0):,}"),
              ("Total Teams", f"{m.get('total_teams', 0):,}"),
              ("Org Leaders", m.get("total_org_leaders", 0))])
    _kpi_row([("Locations", m.get("total_locations", 0)),
              ("Departments", m.get("total_departments", 0)),
              ("Monthly Achievements", f"{m.get('total_monthly_achievements', 0):,}"),
              ("Avg Team Size", m.get("avg_team_size", 0))])
    _kpi_row([("Q5 · Non-Direct Leaders", f"{m.get('q5_non_direct_leader_teams', 0):,}"),
              ("Q6 · Teams > 20% Ratio", f"{m.get('q6_teams_above_ratio', 0):,}"),
              ("Q7 · Report to Org Leader", f"{m.get('q7_teams_report_to_org_leader', 0):,}"),
              ("Mean Quality Score", q.get("mean_quality_score", "—"))])
    st.divider()
    st.subheader("Business questions answered by the Gold layer")
    for ds, title in da.QUESTION_TITLES.items():
        st.markdown(f"- **{title}**  ·  `gold/{ds}`")


def page_business() -> None:
    st.title("🧭 Business Analytics")
    st.caption("Each section answers exactly one workshop question, from the Gold layer.")
    _q1_members()
    _q2_locations()
    _q3_achievements()
    _q4_colocation()
    _q5_non_direct_leaders()
    _q6_ratio()
    _q7_org_reporting()


def _q1_members() -> None:
    st.header(da.QUESTION_TITLES["team_members"])
    df = _gold("team_members")
    teams = sorted(df["team_name"].dropna().unique())
    pick = st.selectbox("Filter by team", ["(all)"] + teams, key="q1team")
    view = df if pick == "(all)" else df[df["team_name"] == pick]
    counts = df.groupby("team_name").size().sort_values(ascending=False).head(20).reset_index(name="members")
    fig = px.bar(counts, x="members", y="team_name", orientation="h",
                 title="Top 20 teams by member count", template=PLOTLY_TEMPLATE, height=520)
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(view.head(2000), use_container_width=True, height=320)
    st.info(f"{df['team_id'].nunique():,} teams · {len(df):,} membership rows · "
            f"{(df['staff_type'] == 'non_direct').mean():.1%} non-direct members overall.")
    _download_buttons(view, "team_members")
    st.divider()


def _q2_locations() -> None:
    st.header(da.QUESTION_TITLES["team_locations"])
    df = _gold("team_locations")
    c1, c2 = st.columns(2)
    by_city = df.groupby("city").size().reset_index(name="teams")
    c1.plotly_chart(px.bar(by_city, x="city", y="teams", title="Teams by city",
                           template=PLOTLY_TEMPLATE), use_container_width=True)
    by_country = df.groupby("country").size().reset_index(name="teams")
    c2.plotly_chart(px.pie(by_country, names="country", values="teams", title="Teams by country",
                           template=PLOTLY_TEMPLATE, hole=0.4), use_container_width=True)
    tree = df.groupby(["region", "country", "city"]).size().reset_index(name="teams")
    st.plotly_chart(px.treemap(tree, path=["region", "country", "city"], values="teams",
                               title="Office footprint (region → country → city)",
                               template=PLOTLY_TEMPLATE), use_container_width=True)
    st.dataframe(df.head(2000), use_container_width=True, height=300)
    _download_buttons(df, "team_locations")
    st.divider()


def _q3_achievements() -> None:
    st.header(da.QUESTION_TITLES["monthly_achievements"])
    df = _gold("monthly_achievements")
    df = df.copy()
    df["period"] = df["year"].astype(str) + "-" + df["month"].astype(str)
    by_month = df.groupby("period")["achievement_count"].sum().reset_index()
    st.plotly_chart(px.line(by_month, x="period", y="achievement_count", markers=True,
                            title="Total achievements by month", template=PLOTLY_TEMPLATE),
                    use_container_width=True)
    top = (df.groupby("team_name")["achievement_count"].sum()
           .sort_values(ascending=False).head(15).reset_index())
    st.plotly_chart(px.bar(top, x="achievement_count", y="team_name", orientation="h",
                           title="Top 15 teams by achievements", template=PLOTLY_TEMPLATE, height=500),
                    use_container_width=True)
    st.dataframe(df.drop(columns=["period"]).head(2000), use_container_width=True, height=300)
    st.info(f"{int(df['achievement_count'].sum()):,} attributable achievements across "
            f"{df['team_id'].nunique():,} teams and {df['period'].nunique()} months.")
    _download_buttons(df.drop(columns=["period"]), "monthly_achievements")
    st.divider()


def _q4_colocation() -> None:
    st.header(da.QUESTION_TITLES["leader_colocation"])
    df = _gold("leader_colocation")
    dist = df["co_located"].value_counts().reset_index()
    dist.columns = ["co_located", "teams"]
    c1, c2 = st.columns([1, 2])
    c1.plotly_chart(px.pie(dist, names="co_located", values="teams", hole=0.45,
                           title="Leader co-location", template=PLOTLY_TEMPLATE),
                    use_container_width=True)
    c2.metric("Teams NOT co-located with majority", f"{int((df['co_located'] == 'No').sum()):,}")
    c2.dataframe(df[df["co_located"] == "No"].head(1000), use_container_width=True, height=360)
    _download_buttons(df, "leader_colocation")
    st.divider()


def _q5_non_direct_leaders() -> None:
    st.header(da.QUESTION_TITLES["non_direct_leaders"])
    df = _gold("non_direct_leaders")
    dist = df["direct_or_non_direct"].value_counts().reset_index()
    dist.columns = ["leader_type", "teams"]
    st.plotly_chart(px.bar(dist, x="leader_type", y="teams", color="leader_type",
                           title="Team leaders: direct vs non-direct", template=PLOTLY_TEMPLATE),
                    use_container_width=True)
    st.metric("Teams with non-direct leaders", f"{int((df['direct_or_non_direct'] == 'Non-Direct').sum()):,}")
    st.dataframe(df[df["direct_or_non_direct"] == "Non-Direct"].head(1000), use_container_width=True, height=320)
    _download_buttons(df, "non_direct_leaders")
    st.divider()


def _q6_ratio() -> None:
    st.header(da.QUESTION_TITLES["non_direct_staff_ratio"])
    df = _gold("non_direct_staff_ratio")
    above = int(df["above_threshold"].sum())
    c1, c2 = st.columns([1, 2])
    c1.metric("Teams with ratio > 20%", f"{above:,}")
    c1.metric("Share of all teams", f"{above / max(len(df), 1):.1%}")
    c2.plotly_chart(px.histogram(df, x="ratio", nbins=40, title="Distribution of non-direct staff ratio",
                                 template=PLOTLY_TEMPLATE), use_container_width=True)
    st.dataframe(df.sort_values("ratio", ascending=False).head(1000), use_container_width=True, height=320)
    _download_buttons(df, "non_direct_staff_ratio")
    st.divider()


def _q7_org_reporting() -> None:
    st.header(da.QUESTION_TITLES["organization_reporting"])
    df = _gold("organization_reporting")
    dist = df["reporting_status"].value_counts().reset_index()
    dist.columns = ["reporting_status", "teams"]
    c1, c2 = st.columns([1, 2])
    c1.plotly_chart(px.pie(dist, names="reporting_status", values="teams", hole=0.45,
                           title="Reporting status", template=PLOTLY_TEMPLATE), use_container_width=True)
    by_org = (df[df["reporting_status"] == "Direct to Org Leader"]
              .groupby("org_name").size().reset_index(name="teams"))
    c2.plotly_chart(px.bar(by_org, x="org_name", y="teams", title="Teams reporting directly, by organization",
                           template=PLOTLY_TEMPLATE), use_container_width=True)
    st.metric("Teams reporting directly to an org leader",
              f"{int((df['reporting_status'] == 'Direct to Org Leader').sum()):,}")
    st.dataframe(df.head(1000), use_container_width=True, height=300)
    _download_buttons(df, "organization_reporting")


def page_pipeline_status() -> None:
    st.title("🚦 Pipeline Status")
    summary = _report("pipeline_summary")
    execu = _report("execution_summary")
    if not summary:
        st.warning("No pipeline run recorded yet.")
        return
    _kpi_row([("Status", summary.get("status", "—")),
              ("Duration (s)", summary.get("duration_seconds", "—")),
              ("Rows Processed", f"{summary.get('rows_processed', 0):,}"),
              ("Batch", summary.get("batch_id", "—"))])
    st.subheader("Per-stage")
    st.dataframe(pd.DataFrame(summary.get("per_stage", [])), use_container_width=True)
    st.subheader("Execution history")
    hist = _history()
    if not hist.empty:
        st.dataframe(hist[["batch_id", "pipeline_name", "status", "duration_seconds",
                           "rows_processed", "end_time"]].tail(20), use_container_width=True)
    if execu.get("errors"):
        st.error(execu["errors"])


def page_data_quality() -> None:
    st.title("✅ Data Quality")
    q = _report("quality_metrics")
    if not q:
        st.warning("No quality metrics found.")
        return
    st.metric("Mean quality score", q.get("mean_quality_score", "—"))
    st.metric("Total rejected (quarantined) records", f"{q.get('total_rejected', 0):,}")
    per = pd.DataFrame(q.get("per_dataset", {})).T.reset_index().rename(columns={"index": "dataset"})
    st.dataframe(per, use_container_width=True)
    if "quality_score" in per:
        st.plotly_chart(px.bar(per, x="dataset", y="quality_score", title="Quality score by dataset",
                               template=PLOTLY_TEMPLATE, range_y=[0, 1]), use_container_width=True)
    st.subheader("Cleaning summary")
    st.json(_report("cleaning_summary").get("datasets", {}), expanded=False)
    st.subheader("Validation summary")
    st.json(_report("validation_summary").get("datasets", {}), expanded=False)


def page_metrics() -> None:
    st.title("📈 Pipeline Metrics")
    hist = _history()
    if hist.empty:
        st.warning("No execution history yet.")
        return
    st.plotly_chart(px.line(hist, x="end_time", y="duration_seconds", markers=True,
                            title="Pipeline duration over runs", template=PLOTLY_TEMPLATE),
                    use_container_width=True)
    st.plotly_chart(px.bar(hist, x="end_time", y="rows_processed",
                           title="Rows processed per run", template=PLOTLY_TEMPLATE),
                    use_container_width=True)
    st.dataframe(hist, use_container_width=True)


def page_lineage() -> None:
    st.title("🔗 Data Lineage")
    st.caption("Source → Bronze → Silver → Gold → Analytics")
    mmd_path = Path(__file__).resolve().parents[1] / "docs" / "lineage_graph.mmd"
    if mmd_path.exists():
        st.code(mmd_path.read_text(encoding="utf-8"), language="mermaid")
        st.caption("Rendered Mermaid (paste into any Mermaid viewer, or see docs/lineage.md).")
    lineage = _report("lineage")
    if lineage.get("gold_detail"):
        st.subheader("Gold dataset provenance")
        rows = [{"gold_dataset": k, **{kk: (", ".join(vv) if isinstance(vv, list) else vv)
                                       for kk, vv in v.items()}}
                for k, v in lineage["gold_detail"].items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


def page_documentation() -> None:
    st.title("📚 Documentation")
    docs_dir = Path(__file__).resolve().parents[1] / "docs"
    root = Path(__file__).resolve().parents[1]
    candidates = ["README.md", "IMPLEMENTATION_PLAN.md"]
    doc_files = candidates + sorted(p.name for p in docs_dir.glob("*.md"))
    pick = st.selectbox("Document", doc_files)
    path = (root / pick) if pick in candidates else (docs_dir / pick)
    if path.exists():
        st.markdown(path.read_text(encoding="utf-8"))
    else:
        st.info("Document not found.")


def page_about() -> None:
    st.title("ℹ️ About")
    st.markdown(
        """
        **ACME Organizational Analytics Platform** — built for the Citi Data
        Engineering Coding Workshop.

        - **Architecture:** Medallion Data Lake (Bronze → Silver → Gold)
        - **Storage:** Parquet (snappy), Hive-partitioned by ingest date
        - **Stack:** Python · pandas · pyarrow · DuckDB · Pandera · Pydantic ·
          Loguru · Streamlit · Plotly · PostgreSQL · Docker
        - **Principle:** the analytics layer consumes **only** the Gold layer.

        Run the pipeline with `python run_pipeline.py all`, then refresh.
        """
    )


PAGES = {
    "Home": page_home,
    "Business Analytics": page_business,
    "Pipeline Status": page_pipeline_status,
    "Data Quality": page_data_quality,
    "Pipeline Metrics": page_metrics,
    "Data Lineage": page_lineage,
    "Documentation": page_documentation,
    "About": page_about,
}


def main() -> None:
    st.sidebar.title("ACME Analytics")
    st.sidebar.caption("Gold-layer analytics")
    if not da.gold_available():
        st.sidebar.error("Gold layer not found. Run the pipeline first.")
    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.divider()
    st.sidebar.caption("Bronze/Silver are never queried here.")
    PAGES[choice]()


if __name__ == "__main__":
    main()
else:
    main()
