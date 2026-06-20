"""Unified H5 analyst payload (spec §9)."""

from __future__ import annotations

from typing import Any, Literal  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import BaseModel, Field


class AnalystPayload(BaseModel):
    """Per-ticker unified analyst output — PM + deliberation contract."""

    ticker: str = Field()
    conviction_score: int = Field(ge=-5, le=5, description="-5 strong sell … +5 strong buy")
    stance: Literal["buy", "hold", "sell", "watch"]
    thesis: str = Field(default="")
    risks: str = Field(default="")
    sources: list[str] = Field(default_factory=list)
    fundamentals: str = Field(default="")
    technicals: str = Field(default="")
    headwinds: list[str] = Field(default_factory=list)
    tailwinds: list[str] = Field(default_factory=list)
    bull_case: str = Field(default="")
    bear_case: str = Field(default="")
    price_targets: dict[str, Any] | None = None
    expectations: str = Field(default="")
    fingerprint_news_hash: str = Field(default="")
