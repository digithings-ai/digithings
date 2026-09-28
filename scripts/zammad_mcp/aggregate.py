"""Windowed aggregation over fetched ticket rows (generic tables lib + Zammad semantics)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

try:  # Stack container + dev: reuse the generic Task 1 table ops.
    from digisearch.core.tables import enrich_rows, group_count
except ImportError:  # Slim zammad-mcp image ships only mcp+httpx (no polars/digisearch).
    enrich_rows = None  # type: ignore[assignment]
    group_count = None  # type: ignore[assignment]

AUTOMATION_OWNERS = frozenset({"jirasync@sitaas.de", "-", "auto"})
CLOSED_TYPE_NAMES = frozenset({"closed", "merged"})

GROUP_KEYS = {"customer": "customer_id", "owner": "owner_id"}
VALID_GROUP_BYS = frozenset({"customer", "owner", "state", "group", "priority", "title"})
VALID_METRICS = frozenset({"count", "open_count", "closed_count"})


def _fallback_cell(row: dict[str, Any], field: str) -> Any:
    if field in row:
        return row[field]
    meta = row.get("metadata")
    if isinstance(meta, dict) and field in meta:
        return meta[field]
    return None


def _fallback_group_count(
    rows: list[dict[str, Any]], by: str, top_n: int = 10
) -> list[dict[str, Any]]:
    """Count rows per distinct value of *by*, most frequent first (no polars)."""
    if not rows:
        return []
    counts: Counter[str] = Counter(
        str(_fallback_cell(row, by) if _fallback_cell(row, by) is not None else "unknown")
        for row in rows
    )
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "count": count} for value, count in ordered[: max(1, top_n)]]


def _fallback_enrich_rows(
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
        cell = _fallback_cell(row, field)
        copy[target] = lookup.get(cell, lookup.get(str(cell), missing))
        out.append(copy)
    return out


if enrich_rows is None or group_count is None:  # pragma: no cover - slim image only
    enrich_rows = _fallback_enrich_rows  # type: ignore[no-redef]
    group_count = _fallback_group_count  # type: ignore[no-redef]


def _is_closed(row: dict[str, Any], state_types: dict[str, int]) -> bool:
    """True when the row's state type is a closed type (closed/merged ids).

    Derives the category from the cached ``{lower_name: type_id}`` mapping, so
    custom states (e.g. ``geloest von Dev``, an open-type state) classify by
    their type — never by matching the state *named* ``open``.
    """
    type_id = row.get("state_type_id")
    if not isinstance(type_id, int):
        state = row.get("state")
        if isinstance(state, dict):
            state = state.get("name")
        type_id = state_types.get(str(state or "").strip().lower())
        if not isinstance(type_id, int):
            return str(state or "").strip().lower() in CLOSED_TYPE_NAMES
    closed_ids = {state_types.get(name) for name in CLOSED_TYPE_NAMES}
    closed_ids.discard(None)
    return type_id in closed_ids


def aggregate(
    rows: list[dict[str, Any]],
    *,
    group_by: str,
    metric: str = "count",
    top_n: int = 5,
    state_types: dict[str, int] | None = None,
    owner_names: Mapping[Any, str] | None = None,
) -> list[dict[str, Any]]:
    """Group rows and count; metric filters open/closed via state types."""
    if group_by not in VALID_GROUP_BYS:
        raise ValueError(f"group_by must be one of {sorted(VALID_GROUP_BYS)}")
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}")
    state_types = state_types or {}
    rows = list(rows)
    if metric in ("open_count", "closed_count"):
        want_closed = metric == "closed_count"
        rows = [row for row in rows if _is_closed(row, state_types) is want_closed]
    key = GROUP_KEYS.get(group_by, group_by)
    if group_by in GROUP_KEYS and rows and not any(key in row for row in rows):
        # Live search rows carry display fields (customer/owner strings) rather
        # than *_id keys — group by those instead of bucketing as "unknown".
        key = group_by
    if group_by == "owner":
        rows = [row for row in rows if str(row.get("owner") or "") not in AUTOMATION_OWNERS]
    ranked = group_count(rows, by=key, top_n=top_n)
    if group_by == "owner" and owner_names:
        # Ranked values are strings (group_count str()-ifies); normalize lookup
        # keys so integer ids still resolve instead of degrading to "?".
        names = {str(raw): display for raw, display in owner_names.items()}
        ranked = enrich_rows(ranked, "value", names, display_field="name", missing="?")
        ranked = [
            entry for entry in ranked if str(entry.get("name") or "") not in AUTOMATION_OWNERS
        ]
    return ranked
