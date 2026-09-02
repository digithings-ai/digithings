"""Strict Pydantic contract for ``position_events`` compatibility rows (#2494).

The public ``position_events`` table is a display projection — not part of the append-only
portfolio ledger — but rows still hit PostgREST with enum CHECK constraints on ``event`` and
``book_source``. Hand-built dicts have produced silent typos and 23514 violations (#628,
#1005, #1383); this model validates at construction so mistakes fail before the write.

Only the authoritative ledger path (:func:`execute_at_open.build_events_from_paper_fills`)
constructs these today. Prose-era builders remain dict-based until migration 070 cutover
deletes them.

T0 (#5-T0): ``workspace_id`` is NOT NULL as of migration 097. The house pipeline is the
only producer today, so the field defaults to :func:`house_workspace_id`; overlay /
multi-workspace writers (T4) will pass an explicit id.
"""

from __future__ import annotations

from typing import Any, Literal  # score:allow validated JSON metadata boundary
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.tenancy import house_workspace_id

PositionEventKind = Literal["OPEN", "EXIT", "HOLD", "TRIM", "ADD"]
PositionEventBookSource = Literal["legacy", "authoritative"]


class PositionEventRow(BaseModel):
    """One ``position_events`` upsert row from the authoritative ledger projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Execution session date (ISO-8601 calendar date).",
    )
    ticker: str = Field(min_length=1, max_length=20)
    event: PositionEventKind
    weight_pct: float | None = None
    prev_weight_pct: float | None = None
    price: float | None = None
    reason: str = Field(min_length=1)
    thesis_id: str | None = None
    book_source: PositionEventBookSource
    workspace_id: UUID = Field(default_factory=house_workspace_id)

    def to_postgrest_row(self) -> dict[str, Any]:
        """Dump for PostgREST upsert — UUID serialized as str for the wire."""
        data = self.model_dump(mode="python")
        data["workspace_id"] = str(self.workspace_id)
        return data


__all__ = [
    "PositionEventBookSource",
    "PositionEventKind",
    "PositionEventRow",
]
