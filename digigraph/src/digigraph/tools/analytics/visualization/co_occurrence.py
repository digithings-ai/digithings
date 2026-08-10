"""Co-occurrence counts for entity columns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _sanitize_node_id


def entity_co_occurrence(
    dataset_path: str | Path,
    entity_columns: list[str],
    min_count: int = 1,
    include_mermaid: bool = True,
) -> dict[str, Any]:
    """
    Co-occurrence of entities (e.g. fromAddress, conversationId). Returns pairs/counts, optional image_path, optional mermaid_source.
    """
    df = load_dataset(dataset_path)
    for c in entity_columns:
        if c not in df.columns:
            return {
                "error": f"Column {c!r} not found",
                "pairs": [],
                "image_path": None,
                "mermaid_source": None,
            }
    df = df.drop_nulls(entity_columns)
    if len(entity_columns) < 2:
        counts = df[entity_columns[0]].value_counts().filter(pl.col("count") >= min_count)
        pairs = [
            {"value": r[0], "count": r[1]}
            for r in zip(counts[entity_columns[0]].to_list(), counts["count"].to_list())
        ]
        return {"pairs": pairs, "image_path": None, "mermaid_source": None}
    a, b = entity_columns[0], entity_columns[1]
    pair_df = (
        df.group_by([a, b])
        .agg(pl.len().alias("count"))
        .filter(pl.col("count") >= min_count)
        .sort("count", descending=True)
    )
    pairs = [
        {"source": r[0], "target": r[1], "count": r[2]}
        for r in zip(pair_df[a].to_list(), pair_df[b].to_list(), pair_df["count"].to_list())
    ][:100]
    mermaid_source = None
    if include_mermaid and pairs:
        lines = ["flowchart LR"]
        for p in pairs[:30]:
            sid = _sanitize_node_id(p["source"])
            tid = _sanitize_node_id(p["target"])
            lines.append(f"    {sid} -->|{p['count']}| {tid}")
        mermaid_source = "\n".join(lines)
    return {"pairs": pairs, "image_path": None, "mermaid_source": mermaid_source}
