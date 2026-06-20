"""Read-through cache for preflight-hydrated research rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes

@dataclass
class ResearchCache:
    """Preflight snapshot used before bounded Supabase reads."""

    latest_segments: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_snapshots: list[dict[str, Any]] = field(default_factory=list)

    def get_document(
        self,
        document_key: str,
        *,
        as_of_date: date,
        run_date: date,
    ) -> dict[str, Any] | None:
        """Return a cached documents row when it satisfies *as_of_date* semantics."""
        row = self.latest_segments.get(document_key)
        if not isinstance(row, dict):
            return None
        row_date = _parse_row_date(row.get("date"))
        if row_date is None:
            return None
        if as_of_date == run_date:
            if row_date < run_date:
                return row
            return None
        if row_date == as_of_date or row_date < as_of_date:
            return row
        return None

    def get_digest(self, *, as_of_date: date, run_date: date) -> dict[str, Any] | None:
        """Return a cached ``daily_snapshots`` row when available."""
        for row in self.last_snapshots:
            if not isinstance(row, dict):
                continue
            row_date = _parse_row_date(row.get("date"))
            if row_date is None:
                continue
            if as_of_date == run_date:
                if row_date < run_date:
                    return row
                continue
            if row_date == as_of_date or row_date < as_of_date:
                return row
        return None


def _parse_row_date(raw: Any) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
