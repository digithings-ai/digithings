"""Generate Mermaid diagram source from dataset. Client renders with Mermaid.js."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _sanitize_node_id


def generate_mermaid_diagram(
    dataset_path: str | Path,
    diagram_type: str,
    source_column: str | None = None,
    target_column: str | None = None,
    label_column: str | None = None,
) -> dict[str, Any]:
    """
    Generate Mermaid diagram source from dataset columns.
    diagram_type: flowchart | sequence | graph | er | gantt.
    For graph/flowchart: source_column and target_column define edges.
    Returns mermaid_source (string) for client-side Mermaid.js rendering.
    """
    diagram_type = (diagram_type or "graph").strip().lower()
    df = load_dataset(dataset_path)
    if diagram_type in ("graph", "flowchart") and source_column and target_column:
        if source_column not in df.columns or target_column not in df.columns:
            return {"error": f"Missing column {source_column!r} or {target_column!r}", "mermaid_source": None}
        df = df.drop_nulls([source_column, target_column])
        edge_df = df.group_by([source_column, target_column]).agg(pl.len().alias("_w"))
        dir_arrow = "-->"
        prefix = "flowchart LR" if diagram_type == "flowchart" else "graph LR"
        lines = [prefix]
        for r in zip(edge_df[source_column].to_list(), edge_df[target_column].to_list(), edge_df["_w"].to_list()):
            sid = _sanitize_node_id(r[0])
            tid = _sanitize_node_id(r[1])
            w = r[2]
            lines.append(f"    {sid} {dir_arrow}|{w}| {tid}")
        mermaid_source = "\n".join(lines[:80])
        return {"mermaid_source": mermaid_source}
    if diagram_type == "sequence" and source_column and target_column:
        if source_column not in df.columns or target_column not in df.columns:
            return {"error": f"Missing column {source_column!r} or {target_column!r}", "mermaid_source": None}
        df = df.drop_nulls([source_column, target_column])
        lines = ["sequenceDiagram"]
        for row in df.head(30).iter_rows(named=True):
            a = _sanitize_node_id(row.get(source_column, ""))
            b = _sanitize_node_id(row.get(target_column, ""))
            lab = str(row.get(label_column, ""))[:30] if label_column else "message"
            lines.append(f"    {a}->>{b}: {lab}")
        return {"mermaid_source": "\n".join(lines)}
    if diagram_type == "er" and source_column:
        if source_column not in df.columns:
            return {"error": f"Column {source_column!r} not found", "mermaid_source": None}
        lines = ["erDiagram"]
        uniq = df[source_column].drop_nulls().unique().to_list()[:15]
        for u in uniq:
            ent = _sanitize_node_id(u)
            lines.append(f"    {ent} {{")
            lines.append("        string id")
            lines.append("    }")
        return {"mermaid_source": "\n".join(lines)}
    if diagram_type == "gantt" and source_column:
        if source_column not in df.columns:
            return {"error": f"Column {source_column!r} not found", "mermaid_source": None}
        lines = ["gantt", "    title Gantt", "    dateFormat YYYY-MM-DD"]
        for i, row in enumerate(df.head(10).iter_rows(named=True)):
            lab = str(row.get(source_column, f"Task {i}"))[:30]
            lines.append(f"    section S\n    {lab} :a{i}, 2024-01-01, 1d")
        return {"mermaid_source": "\n".join(lines)}
    str_cols = [c for c in df.columns if df[c].dtype in (pl.Utf8, pl.String)][:2]
    if len(str_cols) >= 2:
        return generate_mermaid_diagram(dataset_path, "graph", str_cols[0], str_cols[1])
    return {"error": "Need diagram_type and source_column (and target_column for graph/flowchart)", "mermaid_source": None}
