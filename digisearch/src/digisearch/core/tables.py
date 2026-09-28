"""Generic in-memory table ops for API rows (Polars-backed, no service deps).

One implementation for post-retrieval work: structured filter, sort,
group/count, time window, id->display enrichment, term-coverage scoring.
Source adapters (Zammad, future APIs) fetch rows; everything after that
uses these helpers. RAG-hit helpers in ``summarize.py`` delegate here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

_ALLOWED_OPS = frozenset({"eq", "ne", "in", "gt", "ge", "lt", "le"})


class FilterClause(BaseModel):
    """One structured filter clause (same schema as orchestrator `filters`)."""

    field: str
    op: str = "eq"
    value: Any = None


class OrderClause(BaseModel):
    """One sort key: field + direction."""

    field: str
    direction: str = Field(default="desc", pattern="^(asc|desc)$")


def cell(row: dict[str, Any], field: str) -> Any:
    """Flat-field access with `metadata` fallback (serves ticket rows and RAG hits)."""
    if field in row:
        return row[field]
    meta = row.get("metadata")
    if isinstance(meta, dict) and field in meta:
        return meta[field]
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _in_values(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v).strip().lower() for v in value if v is not None and str(v).strip()}
    if isinstance(value, str):
        return {p.strip().lower() for p in value.split(",") if p.strip()}
    return {str(value).lower()}


def _compare(op: str, current: Any, value: Any) -> bool:
    if op == "eq":
        if isinstance(value, bool):
            return bool(current) is value
        if (
            isinstance(current, (int, float))
            and not isinstance(current, bool)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            return float(current) == float(value)
        return str(current) == str(value)
    if op == "ne":
        return not _compare("eq", current, value)
    if op == "in":
        if current is None:
            return False
        cur = {p.strip().lower() for p in str(current).split(",") if p.strip()}
        return bool(cur & _in_values(value))
    if current is None:
        return False
    cur_dt, val_dt = _as_datetime(current), _as_datetime(value)
    if cur_dt is not None and val_dt is not None:
        if op == "gt":
            return cur_dt > val_dt
        if op == "ge":
            return cur_dt >= val_dt
        if op == "lt":
            return cur_dt < val_dt
        return cur_dt <= val_dt
    cur_n, val_n = _as_number(current), _as_number(value)
    if cur_n is None or val_n is None:
        return False
    return {
        "gt": cur_n > val_n,
        "ge": cur_n >= val_n,
        "lt": cur_n < val_n,
        "le": cur_n <= val_n,
    }[op]


def matches_filters(row: dict[str, Any], filters: list[FilterClause] | None) -> bool:
    """True when *row* satisfies every clause (AND). Unknown ops are skipped."""
    for clause in filters or []:
        op = (clause.op or "eq").strip().lower()
        if op not in _ALLOWED_OPS:
            continue
        if not _compare(op, cell(row, clause.field), clause.value):
            return False
    return True


def apply_filters(
    rows: list[dict[str, Any]], filters: list[FilterClause] | None
) -> list[dict[str, Any]]:
    """Return the rows matching all filter clauses (AND), order preserved."""
    if not filters:
        return list(rows)
    return [row for row in rows if matches_filters(row, filters)]


def _sort_key(value: Any) -> tuple[int, str, float]:
    dt = _as_datetime(value)
    if dt is not None:
        return (1, dt.isoformat(), 0.0)
    num = _as_number(value)
    if num is not None:
        return (1, "", num)
    if value is None or str(value) == "None":
        return (0, "", 0.0)
    return (1, str(value), 0.0)


def order_rows(rows: list[dict[str, Any]], order: list[OrderClause]) -> list[dict[str, Any]]:
    """Multi-key stable sort; nulls last in both directions."""
    out = list(rows)
    for clause in reversed(order):
        reverse = clause.direction == "desc"
        out = sorted(
            out,
            key=lambda row: _sort_key(cell(row, clause.field)),
            reverse=reverse,
        )
        if not reverse:
            out = [r for r in out if _sort_key(cell(r, clause.field))[0] == 1] + [
                r for r in out if _sort_key(cell(r, clause.field))[0] == 0
            ]
    return out


def to_dataframe(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Polars frame from arbitrary flat rows (all values kept as given)."""
    if not rows:
        return pl.DataFrame()
    return pl.from_dicts(rows, infer_schema_length=10_000)


def group_count(rows: list[dict[str, Any]], by: str, top_n: int = 10) -> list[dict[str, Any]]:
    """Count rows per distinct value of *by*, most frequent first."""
    if not rows:
        return []
    flat = [{"_g": str(cell(r, by) if cell(r, by) is not None else "unknown")} for r in rows]
    counts = to_dataframe(flat)["_g"].value_counts()
    top = counts.sort(by=["count", "_g"], descending=[True, False]).head(max(1, top_n))
    return [{"value": str(v), "count": int(c)} for v, c in zip(top["_g"], top["count"])]


def window(
    rows: list[dict[str, Any]],
    field: str,
    *,
    since_days: int | None = None,
    until_days: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Keep rows whose *field* datetime falls in [now-since_days, now-1*until_days]."""
    if since_days is None and until_days is None:
        return list(rows)
    ref = now or datetime.now(timezone.utc)
    out = []
    for row in rows:
        stamp = _as_datetime(cell(row, field))
        if stamp is None:
            continue
        if since_days is not None and stamp < ref - timedelta(days=since_days):
            continue
        if until_days is not None and stamp > ref - timedelta(days=until_days):
            continue
        out.append(row)
    return out


def enrich_rows(
    rows: list[dict[str, Any]],
    field: str,
    lookup: Mapping[Any, str],
    *,
    display_field: str | None = None,
    missing: str = "unknown",
) -> list[dict[str, Any]]:
    """Copy rows adding `<field>_display` from *lookup* (never mutates input)."""
    target = display_field or f"{field}_display"
    out = []
    for row in rows:
        copy = dict(row)
        copy[target] = lookup.get(cell(row, field), lookup.get(str(cell(row, field)), missing))
        out.append(copy)
    return out


def coverage_score(text: str, terms: list[str]) -> float:
    """Fraction of *terms* occurring as case-insensitive substrings of *text*."""
    if not terms:
        return 0.0
    hay = (text or "").lower()
    return sum(1 for t in terms if t.lower() in hay) / len(terms)


def numeric_stats(df: pl.DataFrame, cols: list[str]) -> dict[str, dict[str, Any]]:
    """Min/max/mean per numeric column (shared with summarize.py)."""
    stats: dict[str, dict[str, Any]] = {}
    for col in cols:
        series = df[col].drop_nulls()
        if len(series) == 0:
            stats[col] = {"min": None, "max": None, "mean": None}
        else:
            stats[col] = {"min": series.min(), "max": series.max(), "mean": float(series.mean())}
    return stats


def categorical_top(
    df: pl.DataFrame, cols: list[str], top_k: int = 10
) -> dict[str, list[dict[str, Any]]]:
    """Top values per categorical column (shared with summarize.py)."""
    result: dict[str, list[dict[str, Any]]] = {}
    for col in cols:
        counts = df[col].value_counts()
        top = counts.sort(by=["count", col], descending=[True, False]).head(top_k)
        result[col] = [{"value": str(v), "count": int(c)} for v, c in zip(top[col], top["count"])]
    return result
