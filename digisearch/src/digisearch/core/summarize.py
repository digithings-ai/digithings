"""Polars-based summarization of search result sets. Bounds context for the LLM."""

from __future__ import annotations

from typing import Any

import polars as pl

# Default sample size and categorical top-k for summary
DEFAULT_SAMPLE_ROWS = 5
DEFAULT_CATEGORICAL_TOP_K = 10


def _results_to_dataframe(results: list[dict[str, Any]]) -> pl.DataFrame:
    """Build a Polars DataFrame from API-style result dicts (content, score, doc_id, rank, metadata)."""
    if not results:
        return pl.DataFrame()

    rows: list[dict[str, Any]] = []
    for r in results:
        row = {
            "chunk_id": r.get("chunk_id"),
            "content": r.get("content", ""),
            "score": r.get("score"),
            "doc_id": r.get("doc_id"),
            "rank": r.get("rank"),
        }
        meta = r.get("metadata") or {}
        for k, v in meta.items():
            if k not in row:
                row[k] = v
        rows.append(row)
    return pl.from_dicts(rows, infer_schema_length=10_000)


def _infer_numeric_cols(df: pl.DataFrame) -> list[str]:
    """Column names that look numeric (int/float)."""
    return [c for c in df.columns if df[c].dtype in (pl.Int64, pl.Float64, pl.UInt32)]


def _infer_datetime_cols(df: pl.DataFrame) -> list[str]:
    """Column names that are datetime."""
    return [c for c in df.columns if df[c].dtype == pl.Datetime]


def _infer_categorical_cols(df: pl.DataFrame, numeric: list[str], dt: list[str]) -> list[str]:
    """Columns we treat as categorical (string or few-unique)."""
    skip = {"content", "doc_id", "rank", "score"} | set(numeric) | set(dt)
    return [c for c in df.columns if c not in skip and df[c].dtype in (pl.Utf8, pl.String, pl.Categorical)]


def summarize_results(
    results: list[dict[str, Any]],
    sample_size: int = DEFAULT_SAMPLE_ROWS,
    categorical_top_k: int = DEFAULT_CATEGORICAL_TOP_K,
    include_text_summary: bool = True,
) -> dict[str, Any]:
    """
    Summarize a list of search result dicts using Polars.

    Returns a structured data_summary (counts, numeric/date stats, categorical top values),
    an optional sample of rows, and an optional short text summary for the model.
    """
    if not results:
        return {
            "data_summary": {"total_rows": 0, "counts": {}, "numeric_stats": {}, "categorical_top": {}},
            "sample": [],
            "text_summary": "0 results.",
        }

    df = _results_to_dataframe(results)
    total = len(df)

    counts: dict[str, int] = {c: int(df[c].null_count()) for c in df.columns}
    # non-null count per column
    counts = {c: total - nulls for c, nulls in counts.items()}

    numeric_cols = _infer_numeric_cols(df)
    datetime_cols = _infer_datetime_cols(df)
    categorical_cols = _infer_categorical_cols(df, numeric_cols, datetime_cols)

    numeric_stats: dict[str, dict[str, Any]] = {}
    for c in numeric_cols:
        s = df[c]
        n = s.drop_nulls()
        if len(n) == 0:
            numeric_stats[c] = {"min": None, "max": None, "mean": None}
        else:
            numeric_stats[c] = {
                "min": n.min(),
                "max": n.max(),
                "mean": float(n.mean()) if n.dtype in (pl.Float64, pl.Float32) else float(n.mean()),
            }

    for c in datetime_cols:
        s = df[c].drop_nulls()
        if len(s) == 0:
            numeric_stats[c] = {"min": None, "max": None}
        else:
            numeric_stats[c] = {"min": str(s.min()), "max": str(s.max())}

    categorical_top: dict[str, list[dict[str, Any]]] = {}
    for c in categorical_cols:
        top = df[c].value_counts().head(categorical_top_k)
        categorical_top[c] = [{"value": str(v), "count": int(cnt)} for v, cnt in zip(top[c], top["count"])]

    data_summary = {
        "total_rows": total,
        "counts": counts,
        "numeric_stats": numeric_stats,
        "categorical_top": categorical_top,
    }

    sample = []
    if sample_size > 0 and total > 0:
        head = df.head(sample_size)
        sample = head.to_dicts()

    text_parts = [f"{total} results."]
    if numeric_stats:
        for col, stats in list(numeric_stats.items())[:5]:
            if stats.get("min") is not None and stats.get("max") is not None:
                text_parts.append(f"{col}: {stats['min']} to {stats['max']}")
    if categorical_top:
        for col, tops in list(categorical_top.items())[:3]:
            if tops:
                frag = "; ".join(f"{t['value']} ({t['count']})" for t in tops[:5])
                text_parts.append(f"{col}: {frag}")
    text_summary = " ".join(text_parts) if include_text_summary else ""

    return {
        "data_summary": data_summary,
        "sample": sample,
        "text_summary": text_summary,
    }
