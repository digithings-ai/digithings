"""Plot distribution of a column (histogram, kde, or box)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename


def plot_distribution(
    dataset_path: str | Path,
    column: str,
    kind: str = "histogram",
) -> dict[str, Any]:
    """Plot distribution of a column (histogram, kde, or box). Returns image_path and summary."""
    df = load_dataset(dataset_path)
    if column not in df.columns:
        return {"error": f"Column {column!r} not found", "image_path": None, "summary": {}}
    s = df[column].drop_nulls()
    if len(s) == 0:
        return {"error": "No non-null values", "image_path": None, "summary": {}}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"error": "matplotlib not installed", "image_path": None, "summary": {"count": len(s)}}
    out_dir = _artifacts_dir(dataset_path)
    path = _next_filename(out_dir, "dist")
    fig, ax = plt.subplots()
    kind = (kind or "histogram").strip().lower()
    if kind == "histogram":
        ax.hist(s.to_list(), bins=min(50, max(10, len(s) // 5)), edgecolor="gray", alpha=0.8)
    elif kind == "kde":
        try:
            ser = pl.Series(s)
            ax.hist(s.to_list(), bins=50, density=True, alpha=0.5, label="hist")
            s_sorted = ser.sort()
            ax.plot(s_sorted.to_list(), [0.0] * len(s_sorted), "k-", linewidth=0.5)
        except Exception:
            ax.hist(s.to_list(), bins=50, alpha=0.8)
    elif kind == "box":
        ax.boxplot(s.to_list())
    else:
        ax.hist(s.to_list(), bins=min(50, max(10, len(s) // 5)), edgecolor="gray", alpha=0.8)
    ax.set_title(f"Distribution of {column}")
    ax.set_ylabel("count" if kind != "kde" else "density")
    plt.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    summary = {"count": len(s), "min": s.min(), "max": s.max()}
    if s.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
        summary["mean"] = s.mean()
    return {"image_path": str(path), "summary": summary}
