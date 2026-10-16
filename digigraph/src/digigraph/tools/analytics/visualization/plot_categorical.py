"""Bar or pie chart of categorical column."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename


def plot_categorical(
    dataset_path: str | Path,
    column: str,
    top_n: int = 10,
    kind: str = "bar",
) -> dict[str, Any]:
    """Plot categorical column (bar or pie). Returns image_path and summary."""
    df = load_dataset(dataset_path)
    if column not in df.columns:
        return {"error": f"Column {column!r} not found", "image_path": None, "summary": {}}
    counts = df[column].value_counts().head(top_n)
    labels = counts[column].to_list()
    values = counts["count"].to_list()
    if not labels:
        return {"error": "No data", "image_path": None, "summary": {}}
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {
            "error": "matplotlib not installed",
            "image_path": None,
            "summary": {"unique": len(labels)},
        }
    out_dir = _artifacts_dir(dataset_path)
    path = _next_filename(out_dir, "cat")
    fig, ax = plt.subplots()
    kind = (kind or "bar").strip().lower()
    if kind == "pie":
        ax.pie(values, labels=[str(x)[:20] for x in labels], autopct="%1.0f%%", startangle=90)
    else:
        ax.bar([str(x)[:30] for x in labels], values)
        plt.xticks(rotation=45, ha="right")
    ax.set_title(f"Top {top_n}: {column}")
    plt.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    summary = {
        "unique": len(labels),
        "total": sum(values),
        "top_value": labels[0] if labels else None,
    }
    return {"image_path": str(path), "summary": summary}
