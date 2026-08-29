"""H7 PM direction memo — direction + conviction rank only (spec §11.2).

WP4.5 (#2660): each roster row may carry a typed ``ForecastReference`` bound
deterministically from the current effective-forecast map — never from LLM IDs.
"""

from __future__ import annotations

from datetime import date
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
    Mapping,
)
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FORECAST_UNAVAILABLE = "forecast_unavailable"


class ForecastReference(BaseModel):
    """Audit pointer from an H7 ticker decision to one effective forecast.

    Identity fields are filled by H7 post-processing from the run's effective
    forecast map. Models must not invent these UUIDs. Missing lineage yields
    null IDs plus ``degradation_reason`` — never fabricated identifiers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_forecast_id: UUID | None = None
    base_forecast_id: UUID | None = None
    amendment_id: UUID | None = None
    ticker: str = Field(min_length=1)
    degradation_reason: str | None = None

    @model_validator(mode="after")
    def _ids_or_explicit_degradation(self) -> ForecastReference:
        has_eff = self.effective_forecast_id is not None
        has_base = self.base_forecast_id is not None
        if has_eff != has_base:
            raise ValueError(
                "effective_forecast_id and base_forecast_id must both be set or both None"
            )
        if not has_eff and not self.degradation_reason:
            raise ValueError("missing forecast lineage requires degradation_reason")
        return self


class TickerDirection(BaseModel):
    """Per-ticker direction and ordinal conviction — no weights."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field()
    direction: Literal["long", "flat"]
    conviction_rank: int = Field(ge=1, description="Ordinal rank across roster; 1 = highest")
    narrative: str | None = None
    forecast_reference: ForecastReference | None = Field(
        default=None,
        description=(
            "Authoritative effective-forecast pointer attached after H7 LLM output; "
            "post-bind always set (degraded when lineage is missing)."
        ),
    )

    @model_validator(mode="after")
    def _forecast_reference_ticker_matches(self) -> TickerDirection:
        ref = self.forecast_reference
        if ref is not None and ref.ticker != self.ticker:
            raise ValueError("forecast_reference.ticker must match decision ticker")
        return self


class PMDirectionMemo(BaseModel):
    """H7 output — consumed by H8 risk sizing; must not carry weight fields."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    date: date
    roster: list[TickerDirection] = Field(default_factory=list)
    memo: str | None = None


def _parse_uuid(raw: object) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return UUID(raw.strip())
        except ValueError:
            return None
    return None


def forecast_reference_from_lineage(
    *,
    ticker: str,
    effective_forecast_id: UUID | None,
    base_forecast_id: UUID | None,
    amendment_id: UUID | None = None,
    degradation_reason: str | None = None,
) -> ForecastReference:
    """Build a ForecastReference; incomplete IDs become explicit degraded (never invent UUIDs)."""
    if effective_forecast_id is not None and base_forecast_id is not None:
        return ForecastReference(
            effective_forecast_id=effective_forecast_id,
            base_forecast_id=base_forecast_id,
            amendment_id=amendment_id,
            ticker=ticker,
            degradation_reason=degradation_reason,
        )
    return ForecastReference(
        effective_forecast_id=None,
        base_forecast_id=None,
        amendment_id=None,
        ticker=ticker,
        degradation_reason=degradation_reason or _FORECAST_UNAVAILABLE,
    )


def _lineage_from_summary(
    summary: Mapping[str, Any],
) -> tuple[UUID | None, UUID | None, UUID | None, str | None]:
    """Extract IDs from flat H6 fields or nested ``effective_forecast``; never invent UUIDs."""
    eff = _parse_uuid(summary.get("effective_forecast_id"))
    base = _parse_uuid(summary.get("base_forecast_id"))
    amend = _parse_uuid(summary.get("amendment_id"))
    degradation = summary.get("forecast_degradation") or summary.get("degradation_reason")
    if not isinstance(degradation, str) or not degradation.strip():
        degradation = None
    else:
        degradation = degradation.strip()

    nested = summary.get("effective_forecast")
    if isinstance(nested, dict):
        if eff is None:
            eff = _parse_uuid(nested.get("effective_id") or nested.get("effective_forecast_id"))
        if base is None:
            base = _parse_uuid(nested.get("base_forecast_id"))
        if amend is None:
            amend = _parse_uuid(nested.get("amendment_id"))
        nested_deg = nested.get("degradation_reason")
        if degradation is None and isinstance(nested_deg, str) and nested_deg.strip():
            degradation = nested_deg.strip()

    if eff is None or base is None:
        return None, None, None, degradation
    return eff, base, amend, degradation


def bind_forecast_references(
    memo: PMDirectionMemo,
    *,
    deliberation_by_ticker: Mapping[str, Mapping[str, Any]],
) -> PMDirectionMemo:
    """Attach authoritative ForecastReference per roster row from current lineage.

    Overwrites any model-supplied or prior-memo references. Missing lineage yields
    an explicit degraded reference (null IDs + reason) — never fabricated UUIDs.
    Direction and conviction_rank are preserved unchanged.
    """
    roster: list[TickerDirection] = []
    for row in memo.roster:
        summary = deliberation_by_ticker.get(row.ticker) or {}
        eff, base, amend, degradation = _lineage_from_summary(summary)
        ref = forecast_reference_from_lineage(
            ticker=row.ticker,
            effective_forecast_id=eff,
            base_forecast_id=base,
            amendment_id=amend,
            degradation_reason=degradation,
        )
        roster.append(row.model_copy(update={"forecast_reference": ref}))
    return memo.model_copy(update={"roster": roster})


__all__ = [
    "ForecastReference",
    "PMDirectionMemo",
    "TickerDirection",
    "bind_forecast_references",
    "forecast_reference_from_lineage",
]
