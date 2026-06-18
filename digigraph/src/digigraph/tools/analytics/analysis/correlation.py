"""Correlation matrix of numeric columns. Returns matrix dict and optional heatmap image."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.analysis._helpers import _artifacts_dir, _next_filename


def _corr_polars(df: pl.DataFrame) -> dict:
    """Polars-only correlation: build dict of column -> column -> value."""
    cols = df.columns
    out = {c: {} for c in cols}
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            sa = df[a].drop_nulls()
            sb = df[b].drop_nulls()
            if len(sa) != len(sb):
                common = df.select([a, b]).drop_nulls()
                sa = common[a]
                sb = common[b]
            if len(sa) < 2:
                out[a][b] = 0.0
                continue
            mean_a = sa.mean()
            mean_b = sb.mean()
            cov = ((sa - mean_a) * (sb - mean_b)).sum() / (len(sa) - 1)
            std_a = sa.std()
            std_b = sb.std()
            if std_a and std_b:
                out[a][b] = float(cov / (std_a * std_b))
            else:
                out[a][b] = 0.0
    return out


def correlation_matrix(
    dataset_path: str | Path,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Compute correlation matrix of numeric columns. Returns matrix (dict) and optional image_path (heatmap)."""
    df = load_dataset(dataset_path)
    numeric = [c for c in df.columns if df[c].dtype in (pl.Int64, pl.Float64, pl.UInt32)]
    if columns:
        numeric = [c for c in columns if c in numeric]
    if not numeric:
        return {"error": "No numeric columns", "matrix": {}, "image_path": None}
    df = df.select(numeric).drop_nulls()
    if len(df) < 2:
        return {"error": "Not enough rows", "matrix": {}, "image_path": None}
    matrix = _corr_polars(df)
    image_path = None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        pass  # matplotlib optional; correlation matrix still returned
    else:
        arr = [[matrix.get(c1, {}).get(c2, 0) for c2 in numeric] for c1 in numeric]
        out_dir = _artifacts_dir(dataset_path)
        path = _next_filename(out_dir, "corr")
        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(arr, cmap="RdYlBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(numeric)))
        ax.set_yticks(range(len(numeric)))
        ax.set_xticklabels(numeric, rotation=45, ha="right")
        ax.set_yticklabels(numeric)
        plt.colorbar(im, ax=ax)
        plt.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        image_path = str(path)
    return {"matrix": matrix, "image_path": image_path}
