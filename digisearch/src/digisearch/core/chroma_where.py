"""Map structured DigiSearch filters to ChromaDB ``where`` metadata clauses."""

from __future__ import annotations

from typing import Any

_ALLOWED_OPS = frozenset({"eq", "ne", "in", "gt", "ge", "lt", "le"})

# Comma-serialized multi-value fields: Chroma cannot match tag subsets; post-filter only.
_COMMA_TAG_FIELDS = frozenset({"asset_class_tags", "methodology_tags"})


def _chrom_op(op: str) -> str:
    m = {
        "eq": "$eq",
        "ne": "$ne",
        "gt": "$gt",
        "ge": "$gte",
        "lt": "$lt",
        "le": "$lte",
    }
    return m.get(op.lower(), "$eq")


def structured_filters_to_chroma_where(structured: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Build a Chroma ``where`` dict from structured filters [{field, op, value}, ...].

    Chroma supports $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, and logical $and.
    """
    if not structured:
        return None
    clauses: list[dict[str, Any]] = []
    for f in structured:
        if not isinstance(f, dict):
            continue
        field = f.get("field")
        if field is None or str(field).strip() == "":
            continue
        field_s = str(field)
        if field_s in _COMMA_TAG_FIELDS:
            continue
        op = (f.get("op") or "eq").strip().lower()
        value = f.get("value")
        if op == "in":
            if isinstance(value, list):
                vals: list[str | int | float | bool] = []
                for v in value:
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        vals.append(v)
                    else:
                        vals.append(str(v))
                if not vals:
                    continue
                clauses.append({field_s: {"$in": vals}})
            elif isinstance(value, str):
                parts = [p.strip() for p in value.split(",") if p.strip()]
                if not parts:
                    continue
                clauses.append({field_s: {"$in": parts}})
            continue
        if op not in _ALLOWED_OPS or op == "in":
            continue
        if op == "eq":
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                clauses.append({field_s: value})
            else:
                clauses.append({field_s: str(value)})
            continue
        cop = _chrom_op(op)
        if value is None and op == "ne":
            clauses.append({field_s: {"$ne": None}})
            continue
        if isinstance(value, (str, int, float, bool)):
            clauses.append({field_s: {cop: value}})
        else:
            clauses.append({field_s: {cop: str(value)}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
