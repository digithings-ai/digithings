"""Apply structured metadata filters to chunk metadata (stub / post-filter)."""

from __future__ import annotations

from typing import Any

_ALLOWED = frozenset({"eq", "ne", "in", "gt", "ge", "lt", "le"})


def _coerce_compare_num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _values_for_in(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v).strip().lower() for v in value if v is not None and str(v).strip()}
    if isinstance(value, str):
        return {p.strip().lower() for p in value.split(",") if p.strip()}
    return {str(value).lower()}


def chunk_metadata_matches(structured: list[dict[str, Any]] | None, meta: dict[str, Any] | None) -> bool:
    """Return True if *meta* satisfies all structured filter clauses (AND)."""
    if not structured:
        return True
    m = meta or {}
    for f in structured:
        if not isinstance(f, dict):
            continue
        field = f.get("field")
        if field is None:
            continue
        fs = str(field)
        op = (f.get("op") or "eq").strip().lower()
        value = f.get("value")
        current = m.get(fs)
        if op == "in":
            allowed = _values_for_in(value)
            if current is None:
                return False
            cur_parts = {p.strip().lower() for p in str(current).split(",") if p.strip()}
            if not (allowed & cur_parts):
                return False
            continue
        if op not in _ALLOWED:
            continue
        if op == "eq":
            if isinstance(value, bool):
                if bool(current) is not value:
                    return False
            elif current != value and str(current) != str(value):
                return False
            continue
        if op == "ne":
            if current == value or str(current) == str(value):
                return False
            continue
        cv = _coerce_compare_num(current)
        tv = _coerce_compare_num(value)
        if cv is None or tv is None:
            return False
        if op == "gt" and not (cv > tv):
            return False
        if op == "ge" and not (cv >= tv):
            return False
        if op == "lt" and not (cv < tv):
            return False
        if op == "le" and not (cv <= tv):
            return False
    return True
