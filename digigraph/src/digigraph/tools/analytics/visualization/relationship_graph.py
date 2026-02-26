"""Build graph from source to target column."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename, _sanitize_node_id


def build_relationship_graph(
    dataset_path: str | Path,
    source_column: str,
    target_column: str,
    weight_column: str | None = None,
    layout: str = "force",
    include_mermaid: bool = True,
) -> dict[str, Any]:
    """
    Build a graph from source_column -> target_column. Returns graph (nodes, edges), optional image_path, optional mermaid_source.
    """
    df = load_dataset(dataset_path)
    for c in (source_column, target_column):
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "graph": None, "image_path": None, "mermaid_source": None}
    if weight_column and weight_column not in df.columns:
        return {"error": f"Column {weight_column!r} not found", "graph": None, "image_path": None, "mermaid_source": None}
    df = df.drop_nulls([source_column, target_column])
    if len(df) == 0:
        return {"error": "No edges after dropping nulls", "graph": {"nodes": [], "edges": []}, "image_path": None, "mermaid_source": None}
    if weight_column:
        edges_df = df.group_by([source_column, target_column]).agg(pl.col(weight_column).sum().alias("weight"))
    else:
        edges_df = df.group_by([source_column, target_column]).agg(pl.len().alias("weight"))
    nodes = list(set(edges_df[source_column].to_list() + edges_df[target_column].to_list()))
    edges = [
        {"source": r[0], "target": r[1], "weight": r[2]}
        for r in zip(edges_df[source_column].to_list(), edges_df[target_column].to_list(), edges_df["weight"].to_list())
    ]
    graph = {"nodes": [{"id": n} for n in nodes], "edges": edges}
    image_path = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError:
        pass
    else:
        G = nx.DiGraph()
        for n in nodes:
            G.add_node(n)
        for e in edges:
            G.add_edge(e["source"], e["target"], weight=e["weight"])
        out_dir = _artifacts_dir(dataset_path)
        path = _next_filename(out_dir, "graph")
        fig, ax = plt.subplots(figsize=(8, 6))
        pos = nx.spring_layout(G, k=0.5, iterations=50) if layout == "force" else nx.shell_layout(G)
        nx.draw(G, pos, ax=ax, with_labels=True, font_size=6, node_size=200, arrows=True)
        plt.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        image_path = str(path)
    mermaid_source = None
    if include_mermaid:
        lines = ["flowchart LR"]
        seen = set()
        for e in edges[:100]:
            sid = _sanitize_node_id(e["source"])
            tid = _sanitize_node_id(e["target"])
            key = (sid, tid)
            if key not in seen:
                seen.add(key)
                w = e.get("weight", "")
                if w:
                    lines.append(f'    {sid} -->|{w}| {tid}')
                else:
                    lines.append(f"    {sid} --> {tid}")
        mermaid_source = "\n".join(lines)
    return {"graph": graph, "image_path": image_path, "mermaid_source": mermaid_source}
