"""Cluster rows by numeric columns. Returns cluster labels and per-cluster summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset


def cluster_metadata(
    dataset_path: str | Path,
    numeric_columns: list[str],
    n_clusters: int = 3,
) -> dict[str, Any]:
    """
    Cluster rows by numeric columns. Returns cluster label per row and summary per cluster.
    Uses sklearn KMeans if available; otherwise simple binning by first component.
    """
    df = load_dataset(dataset_path)
    cols = [c for c in numeric_columns if c in df.columns]
    if not cols:
        return {"error": "No valid numeric columns", "labels": [], "summary": {}}
    df = df.select(cols).drop_nulls()
    if len(df) < n_clusters:
        return {"error": "Fewer rows than n_clusters", "labels": [], "summary": {}}
    try:
        from sklearn.cluster import KMeans
        X = df.to_numpy()
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        labels_list = [int(x) for x in labels]
    except ImportError:
        col = cols[0]
        lo, hi = df[col].min(), df[col].max()
        span = (hi - lo) / n_clusters if hi != lo else 1
        labels_list = []
        for v in df[col].to_list():
            lab = int((v - lo) / span) if span else 0
            labels_list.append(min(lab, n_clusters - 1))
    df = df.with_columns(pl.Series("_cluster", labels_list))
    summary = {}
    for c in range(n_clusters):
        sub = df.filter(pl.col("_cluster") == c)
        summary[str(c)] = {"count": len(sub), "columns": {col: {"mean": sub[col].mean(), "min": sub[col].min(), "max": sub[col].max()} for col in cols}}
    return {"labels": labels_list, "summary": summary, "n_clusters": n_clusters}
