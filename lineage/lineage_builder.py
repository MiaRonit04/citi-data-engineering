"""Data-lineage builder.

Emits machine- and human-readable lineage tracing every Gold dataset back
through Silver and Bronze to its originating source system, including the
transformations and business rules applied. Outputs:

* ``docs/lineage.json``       — structured graph (nodes + edges)
* ``docs/lineage.md``         — readable per-dataset lineage tables
* ``docs/lineage_graph.mmd``  — Mermaid flow diagram

The lineage spec is declarative and kept in lock-step with the actual pipeline
transformations (Silver ``transforms.py`` / Gold ``gold_business_questions.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from etl.common.config import Settings, get_settings
from etl.common.logging import get_logger
from etl.common.utils import write_json

# Source system → Bronze dataset (raw, immutable)
SOURCE_TO_BRONZE = {
    "employees": ("employee_directory", "employees.csv"),
    "contractor_roster": ("vendor_management", "contractor_roster.csv"),
    "team_membership": ("project_tracking", "team_membership.csv"),
    "teams": ("project_tracking", "teams.json"),
    "monthly_achievements": ("performance_management", "monthly_achievements.json"),
    "locations": ("facilities", "locations.csv"),
    "organizations": ("org_structure", "organizations.json"),
}

# Silver transformations applied per dataset (summary of transforms.py + validation)
SILVER_TRANSFORMS = {
    "employees": ["text cleaning", "email canonicalization", "department standardization",
                  "employment_type standardization", "hire_date → ISO", "dedupe emp_id",
                  "manager FK validation"],
    "contractor_roster": ["text cleaning", "email canonicalization", "dates → ISO"],
    "team_membership": ["text cleaning", "team_code → TM-###", "email canonicalization",
                        "allocation bounds [0,100]", "dates → ISO", "orphan-member quarantine",
                        "staff_type tagging"],
    "teams": ["flatten organization.*", "text cleaning", "leader/manager email canonicalization",
              "formed_date → ISO", "leader staff-type resolution"],
    "monthly_achievements": ["text cleaning", "month → YYYY-MM", "impact_score numeric coercion",
                             "orphan-achievement quarantine", "team_id attributability"],
    "locations": ["text cleaning", "dedupe location_code (LOC-01 conflict)"],
    "organizations": ["text cleaning", "org_leader_email canonicalization"],
}

# Gold dataset → (question, silver inputs, transformation, business rule)
GOLD_LINEAGE: dict[str, dict[str, Any]] = {
    "team_members": {
        "question": "Q1 — Who are the members of each team?",
        "inputs": ["team_membership", "employees", "contractor_roster", "teams", "locations"],
        "transformation": "membership ⋈ person-master ⋈ teams ⋈ locations",
        "business_rule": "member identity resolved by canonical email; direct-wins tie-break",
    },
    "team_locations": {
        "question": "Q2 — Where are the teams located?",
        "inputs": ["teams", "locations", "team_membership"],
        "transformation": "teams ⋈ locations(primary_office); employee_count from membership",
        "business_rule": "one row per team_id; state absent in source (region provided)",
    },
    "monthly_achievements": {
        "question": "Q3 — Monthly achievements per team",
        "inputs": ["monthly_achievements", "teams"],
        "transformation": "filter attributable (team_id) → group by team_id, year, month",
        "business_rule": "name-only achievements excluded (team_name non-unique)",
    },
    "leader_colocation": {
        "question": "Q4 — Leader not co-located with majority",
        "inputs": ["teams", "team_membership", "employees", "contractor_roster", "locations"],
        "transformation": "compare leader location vs modal member location per team",
        "business_rule": "co-located = leader city == majority member city",
    },
    "non_direct_leaders": {
        "question": "Q5 — Teams with non-direct leaders",
        "inputs": ["teams", "employees", "contractor_roster"],
        "transformation": "leader email resolved to employee (direct) or contractor (non-direct)",
        "business_rule": "non-direct leader = leader email ∈ contractor roster (not an employee)",
    },
    "non_direct_staff_ratio": {
        "question": "Q6 — Non-direct staff ratio > threshold",
        "inputs": ["team_membership", "employees", "contractor_roster"],
        "transformation": "per team: non_direct_members / total_members",
        "business_rule": "flag ratio > NON_DIRECT_RATIO_THRESHOLD (0.20, configurable)",
    },
    "organization_reporting": {
        "question": "Q7 — Teams reporting to org leaders",
        "inputs": ["teams", "organizations"],
        "transformation": "classify reports_to_type; build reporting chain",
        "business_rule": "direct = reports_to_type == 'Org Leader' (== reporting_manager ∈ org leaders)",
    },
}


def build_lineage_document() -> dict[str, Any]:
    """Assemble the structured lineage graph (nodes + edges + gold detail)."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    for dataset, (system, filename) in SOURCE_TO_BRONZE.items():
        nodes.append({"id": f"src:{dataset}", "layer": "source", "label": f"{system}/{filename}"})
        nodes.append({"id": f"bronze:{dataset}", "layer": "bronze", "label": dataset})
        nodes.append({"id": f"silver:{dataset}", "layer": "silver", "label": dataset})
        edges.append({"from": f"src:{dataset}", "to": f"bronze:{dataset}", "transform": "raw ingest (immutable)"})
        edges.append({"from": f"bronze:{dataset}", "to": f"silver:{dataset}",
                      "transform": "; ".join(SILVER_TRANSFORMS.get(dataset, []))})

    for gold, spec in GOLD_LINEAGE.items():
        nodes.append({"id": f"gold:{gold}", "layer": "gold", "label": gold})
        for inp in spec["inputs"]:
            edges.append({"from": f"silver:{inp}", "to": f"gold:{gold}", "transform": spec["transformation"]})
        edges.append({"from": f"gold:{gold}", "to": "analytics:dashboard", "transform": "consume"})
        edges.append({"from": f"gold:{gold}", "to": "analytics:notebook", "transform": "consume"})

    nodes.append({"id": "analytics:dashboard", "layer": "analytics", "label": "Streamlit Dashboard"})
    nodes.append({"id": "analytics:notebook", "layer": "analytics", "label": "Jupyter Notebook"})

    return {"nodes": nodes, "edges": edges, "gold_detail": GOLD_LINEAGE,
            "silver_transforms": SILVER_TRANSFORMS, "source_to_bronze": SOURCE_TO_BRONZE}


def render_markdown(doc: dict[str, Any]) -> str:
    """Render human-readable lineage markdown."""
    lines = ["# DATA LINEAGE", "",
             "End-to-end lineage: **Source → Bronze → Silver → Gold → Analytics**.",
             "Bronze is immutable; Silver applies documented cleaning/validation; Gold",
             "curates exactly seven business datasets consumed only by the analytics layer.",
             "", "## Gold dataset provenance", ""]
    for gold, spec in doc["gold_detail"].items():
        lines += [f"### `{gold}` — {spec['question']}", "",
                  f"- **Silver inputs:** {', '.join(spec['inputs'])}",
                  f"- **Transformation:** {spec['transformation']}",
                  f"- **Business rule:** {spec['business_rule']}", ""]
    lines += ["## Silver transformations (Bronze → Silver)", ""]
    for ds, ts in doc["silver_transforms"].items():
        lines.append(f"- **{ds}:** {'; '.join(ts)}")
    return "\n".join(lines) + "\n"


def render_mermaid(doc: dict[str, Any]) -> str:
    """Render a Mermaid flow diagram of the lineage graph (layered)."""
    lines = ["flowchart LR"]
    layer_titles = {"source": "Source Systems", "bronze": "Bronze", "silver": "Silver",
                    "gold": "Gold", "analytics": "Analytics"}
    by_layer: dict[str, list[dict[str, str]]] = {}
    for n in doc["nodes"]:
        by_layer.setdefault(n["layer"], []).append(n)

    def _nid(node_id: str) -> str:
        return node_id.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")

    for layer, title in layer_titles.items():
        lines.append(f"  subgraph {layer}[\"{title}\"]")
        for n in by_layer.get(layer, []):
            lines.append(f"    {_nid(n['id'])}[\"{n['label']}\"]")
        lines.append("  end")
    seen: set[tuple[str, str]] = set()
    for e in doc["edges"]:
        key = (e["from"], e["to"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {_nid(e['from'])} --> {_nid(e['to'])}")
    return "\n".join(lines) + "\n"


def run(settings: Settings | None = None) -> dict[str, Path]:
    """Build and write all lineage artefacts. Returns the written paths."""
    settings = settings or get_settings()
    log = get_logger("lineage")
    docs_dir = Path(settings.config_path).parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    doc = build_lineage_document()
    json_path = write_json(doc, docs_dir / "lineage.json")
    md_path = docs_dir / "lineage.md"
    md_path.write_text(render_markdown(doc), encoding="utf-8")
    mmd_path = docs_dir / "lineage_graph.mmd"
    mmd_path.write_text(render_mermaid(doc), encoding="utf-8")

    # Also copy the structured graph into reports/ for the dashboard.
    write_json(doc, settings.reports_path / "lineage.json")

    log.info("Lineage written: {j}, {m}, {g}", j=json_path.name, m=md_path.name, g=mmd_path.name)
    return {"json": json_path, "md": md_path, "mmd": mmd_path}


if __name__ == "__main__":  # pragma: no cover
    run()
