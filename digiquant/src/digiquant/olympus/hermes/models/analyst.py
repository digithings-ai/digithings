"""Unified H5 analyst payload (spec §9)."""

from __future__ import annotations

from typing import Any, Literal  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import BaseModel, Field, model_validator


class EvidenceAssessment(BaseModel):
    """Itemized, checkable evidence — ``conviction_score`` is COMPUTED from this (#1672).

    Production data showed the LLM-chosen score collapsing to a single mode (77% of
    decisions at exactly +2). Central tendency cannot be prompted away, so the number
    is taken away from the model: it itemizes evidence, code derives conviction.
    """

    independent_confirming_signals: int = Field(
        ge=0,
        le=5,
        description=(
            "How many INDEPENDENT signal families confirm the thesis today: technicals, "
            "fundamentals, flows/positioning, macro regime, sentiment/news. Count a family "
            "only on concrete evidence cited in this payload — not vibes."
        ),
    )
    contradicting_signals: int = Field(
        ge=0,
        le=5,
        description="Signal families actively CONTRADICTING the thesis today (same families).",
    )
    catalyst_within_horizon: bool = Field(
        description=(
            "True only when a specific, dated/window-bound catalyst inside the thesis "
            "horizon is identified in the thesis text."
        ),
    )
    trend_alignment: Literal["with", "against", "mixed"] = Field(
        description="Is the call with, against, or orthogonal to the prevailing trend?",
    )
    evidence_quality: Literal["high", "medium", "low"] = Field(
        description=(
            "Completeness of today's evidence: 'high' = fresh data across families; "
            "'low' = thin/stale inputs — be honest, this caps conviction."
        ),
    )


def derive_conviction(evidence: EvidenceAssessment, stance: str) -> int:
    """Deterministic conviction from itemized evidence (#1672).

    Magnitude = confirming − contradicting, then capped: no dated catalyst ≤ 3,
    medium evidence quality ≤ 3, low ≤ 2; against-trend −1. High conviction (4–5)
    therefore structurally requires ≥4 confirming families, ≤~1 contradicting, a
    dated catalyst, high-quality evidence, and not fighting the trend — naturally
    scarce. hold/watch clamp to ±1 (a strong view IS a buy/sell stance).
    """
    magnitude = max(0, evidence.independent_confirming_signals - evidence.contradicting_signals)
    if not evidence.catalyst_within_horizon:
        magnitude = min(magnitude, 3)
    if evidence.evidence_quality == "medium":
        magnitude = min(magnitude, 3)
    elif evidence.evidence_quality == "low":
        magnitude = min(magnitude, 2)
    if evidence.trend_alignment == "against":
        magnitude = max(magnitude - 1, 0)
    if stance == "buy":
        return magnitude
    if stance == "sell":
        return -magnitude
    # hold/watch: a residual lean only — sign follows the trend, capped at 1.
    lean = min(magnitude, 1)
    if evidence.trend_alignment == "against":
        return -lean
    if evidence.trend_alignment == "mixed":
        return 0
    return lean


class AnalystPayload(BaseModel):
    """Per-ticker unified analyst output — PM + deliberation contract."""

    ticker: str = Field()
    conviction_score: int = Field(ge=-5, le=5, description="-5 strong sell … +5 strong buy")
    stance: Literal["buy", "hold", "sell", "watch"]
    evidence: EvidenceAssessment | None = Field(
        default=None,
        description=(
            "Itemized evidence assessment — REQUIRED for new analyses; conviction_score "
            "is recomputed from it (the model-provided number is ignored when present)."
        ),
    )

    @model_validator(mode="after")
    def _derive_conviction_from_evidence(self) -> "AnalystPayload":
        """When the evidence block is present, the computed score wins (#1672).

        Legacy payloads (prior docs, carried analyses) lack ``evidence`` and keep
        their stored score — compatibility over purity for old rows.
        """
        if self.evidence is not None:
            object.__setattr__(
                self, "conviction_score", derive_conviction(self.evidence, self.stance)
            )
        return self

    thesis: str = Field(
        default="",
        description=(
            "Full investment thesis: the catalyst(s), the mechanism, the key price / "
            "valuation levels, and the time horizon. Write it complete — never abbreviate "
            "or truncate mid-sentence."
        ),
    )
    risks: str = Field(
        default="",
        description=(
            "What would invalidate this thesis: the main downside scenarios, the level or "
            "signal that proves the call wrong, and the key uncertainties. Always populate — "
            "the PM and risk sizer depend on it."
        ),
    )
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
