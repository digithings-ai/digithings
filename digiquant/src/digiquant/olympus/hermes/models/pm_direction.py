"""H7 PM direction memo — direction + conviction rank only (spec §11.2)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TickerDirection(BaseModel):
    """Per-ticker direction and ordinal conviction — no weights."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field()
    direction: Literal["long", "flat"]
    conviction_rank: int = Field(ge=1, description="Ordinal rank across roster; 1 = highest")
    narrative: str | None = Field(default=None, max_length=2000)


class PMDirectionMemo(BaseModel):
    """H7 output — consumed by H8 risk sizing; must not carry weight fields."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    date: date
    roster: list[TickerDirection] = Field(default_factory=list)
    memo: str | None = Field(default=None, max_length=8000)


__all__ = ["PMDirectionMemo", "TickerDirection"]
