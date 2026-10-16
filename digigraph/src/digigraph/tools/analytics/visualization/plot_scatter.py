"""Scatter plot x vs y."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename


def plot_scatter(
    dataset_path: str | Path,
    x_column: str,
    y_column: str,
    color_by: str | None = None,
) -> dict[str, Any]:
    """Scatter plot of x_column vs y_column; optional color_by. Returns image_path and summary."""
    df = load_dataset(dataset_path)
    for c in [x_column, y_column]:
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "image_path": None, "summary": {}}
    if color_by and color_by not in df.columns:
        return {"error": f"Column {color_by!r} not found", "image_path": None, "summary": {}}
    df = df.drop_nulls([x_column, y_column])
    if len(df) == 0:
        return {"error": "No non-null rows for x/y", "image_path": None, "summary": {}}
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"error": "matplotlib not installed", "image_path": None, "summary": {"n": len(df)}}
    out_dir = _artifacts_dir(dataset_path)
    path = _next_filename(out_dir, "scatter")
    fig, ax = plt.subplots()
    x = df[x_column].to_list()
    y = df[y_column].to_list()
    if color_by:
        ax.scatter(x, y, c=[hash(str(v)) % 2**24 for v in df[color_by].to_list()], alpha=0.6, s=20)
    else:
        ax.scatter(x, y, alpha=0.6, s=20)
    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    ax.set_title(f"Scatter: {x_column} vs {y_column}")
    plt.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    summary = {"n": len(df), "x_min": min(x), "x_max": max(x), "y_min": min(y), "y_max": max(y)}
    return {"image_path": str(path), "summary": summary}
