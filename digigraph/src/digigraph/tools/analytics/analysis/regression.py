"""Simple linear regression y ~ x. Returns coefficients, R², equation; optional residual plot."""

from __future__ import annotations

from pathlib import Path
from typing import Any


from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.analysis._helpers import _artifacts_dir, _next_filename


def simple_regression(
    dataset_path: str | Path,
    x_column: str,
    y_column: str,
) -> dict[str, Any]:
    """Simple linear regression y ~ x. Returns slope, intercept, R², equation; optional image_path (residual plot)."""
    df = load_dataset(dataset_path)
    for c in (x_column, y_column):
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "slope": None, "intercept": None, "r_squared": None, "equation": None, "image_path": None}
    df = df.select([x_column, y_column]).drop_nulls()
    if len(df) < 3:
        return {"error": "Need at least 3 points", "slope": None, "intercept": None, "r_squared": None, "equation": None, "image_path": None}
    x = df[x_column]
    y = df[y_column]
    n = len(x)
    mean_x = x.mean()
    mean_y = y.mean()
    cov = ((x - mean_x) * (y - mean_y)).sum() / n
    var_x = ((x - mean_x) ** 2).sum() / n
    if var_x == 0:
        return {"error": "Constant x", "slope": None, "intercept": None, "r_squared": None, "equation": None, "image_path": None}
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    y_pred = slope * x + intercept
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - mean_y) ** 2).sum()
    r_squared = float(1 - ss_res / ss_tot) if ss_tot else 0.0
    equation = f"y = {slope:.4f} * x + {intercept:.4f}"
    image_path = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        pass
    else:
        out_dir = _artifacts_dir(dataset_path)
        path = _next_filename(out_dir, "regress")
        fig, ax = plt.subplots()
        ax.scatter(x.to_list(), y.to_list(), alpha=0.6, label="data")
        x_min, x_max = x.min(), x.max()
        ax.plot([x_min, x_max], [float(slope * x_min + intercept), float(slope * x_max + intercept)], "r-", label="fit")
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.set_title(f"Regression R²={r_squared:.3f}")
        ax.legend()
        plt.tight_layout()
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        image_path = str(path)
    return {"slope": float(slope), "intercept": float(intercept), "r_squared": r_squared, "equation": equation, "image_path": image_path}
