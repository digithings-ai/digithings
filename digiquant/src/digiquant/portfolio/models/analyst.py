"""Unified analyst payload (spec §9)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Annotated,
    Any,
    Literal,
)

from pydantic import BaseModel, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from digiquant.portfolio.models.forecast import ForecastAssessment, ForecastTerms

# The one universe both evidence counts are drawn from (#4585). Every family is
# itemized once, on the confirming side or the contradicting side — never both.
_EVIDENCE_FAMILIES = (
    "technicals",
    "fundamentals",
    "flows/positioning",
    "macro regime",
    "sentiment/news",
)
_MAX_EVIDENCE_FAMILIES = len(_EVIDENCE_FAMILIES)
_FAMILY_SUM_ERROR = (
    "confirming + contradicting signals must be <= 5 "
    f"(the five signal families: {', '.join(_EVIDENCE_FAMILIES)})"
)


class EvidenceAssessment(BaseModel):
    """Itemized, checkable evidence — ``conviction_score`` is COMPUTED from this (#1672).

    Production data showed the LLM-chosen score collapsing to a single mode (77% of
    decisions at exactly +2). Central tendency cannot be prompted away, so the number
    is taken away from the model: it itemizes evidence, code derives conviction.

    Both counts are measured against **your own call** (the ``stance`` you declare),
    not against the market thesis the vehicle is mapped to — the same frame
    ``trend_alignment`` already uses. The analyst may legitimately disagree with the
    thesis it carries, and when it does, the families contradicting that thesis are
    the families *confirming* the call. Counting against the thesis instead makes the
    derived score meaningless whenever the two disagree.
    """

    independent_confirming_signals: int = Field(
        ge=0,
        le=5,
        description=(
            "How many INDEPENDENT signal families confirm YOUR CALL (your stated stance) "
            "today: technicals, fundamentals, flows/positioning, macro regime, "
            "sentiment/news. Count a family only on concrete evidence cited in this "
            "payload — not vibes. Count against your call, not against the market thesis "
            "you are mapped to: if you would sell a bullish thesis, the bearish families "
            "are the ones confirming your call."
        ),
    )
    contradicting_signals: int = Field(
        ge=0,
        le=5,
        description="Signal families actively CONTRADICTING YOUR CALL today (same families).",
    )
    catalyst_within_horizon: bool = Field(
        description=(
            "True only when a specific, dated/window-bound catalyst inside your call's "
            "horizon is identified in this payload's thesis text."
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

    @model_validator(mode="after")
    def _enforce_single_family_universe(self) -> "EvidenceAssessment":
        """The two counts are disjoint halves of one five-family universe (#4585).

        Both fields are ``le=5`` independently, which alone lets a payload assign
        up to ten family slots — ``analyst/IBIT`` 2026-09-22 stored ``4 + 4``, eight
        families over five. Reject rather than clamp: clamping would silently
        rewrite the model's itemization, so persisted overcounts are instead
        repaired on read by :func:`repair_legacy_evidence_counts`.
        """
        total = self.independent_confirming_signals + self.contradicting_signals
        if total > _MAX_EVIDENCE_FAMILIES:
            raise ValueError(_FAMILY_SUM_ERROR)
        return self


def repair_evidence_counts(confirming: int, contradicting: int) -> tuple[int, int]:
    """Net-preserving repair of a legacy ``(confirming, contradicting)`` pair (#4585).

    A pair that already fits the five-family universe (``sum <= 5``) is returned
    unchanged. An overcount is rebalanced while preserving the net
    ``confirming - contradicting`` — so a repaired legacy row still derives the same
    ``conviction_score`` — using the canonical reduction::

        4+4 -> 2+2   3+3 -> 2+2   5+2 -> 4+1   5+1 -> 4+0
        2+5 -> 1+4   4+3 -> 3+2   3+2 -> 3+2   0+0 -> 0+0
    """
    if confirming + contradicting <= _MAX_EVIDENCE_FAMILIES:
        return confirming, contradicting
    net = confirming - contradicting
    if net >= 0:
        contradicting = min(contradicting, (_MAX_EVIDENCE_FAMILIES - net) // 2)
        confirming = contradicting + net
    else:
        confirming = min(confirming, (_MAX_EVIDENCE_FAMILIES + net) // 2)
        contradicting = confirming - net
    return confirming, contradicting


def repair_legacy_evidence_counts(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return *body* with an overcounted ``evidence`` pair repaired (#4585).

    Called only where a **persisted/prior** analyst body is re-validated (skip
    carry, metric patch, edit fallback) so a legacy overcounted row still carries
    instead of degrading. Fresh LLM output is validated strictly — a bad
    generation must be rejected and retried, never silently rewritten. A body with
    no evidence block, or evidence fields that are not counts, is returned as a
    shallow copy unchanged.
    """
    evidence = body.get("evidence")
    if not isinstance(evidence, Mapping):
        return dict(body)
    confirming = evidence.get("independent_confirming_signals")
    contradicting = evidence.get("contradicting_signals")
    if isinstance(confirming, bool) or isinstance(contradicting, bool):
        return dict(body)
    if not isinstance(confirming, int) or not isinstance(contradicting, int):
        return dict(body)
    repaired = repair_evidence_counts(confirming, contradicting)
    if repaired == (confirming, contradicting):
        return dict(body)
    return {
        **body,
        "evidence": {
            **evidence,
            "independent_confirming_signals": repaired[0],
            "contradicting_signals": repaired[1],
        },
    }


def derive_conviction(evidence: EvidenceAssessment, stance: str) -> int:
    """Deterministic conviction from itemized evidence (#1672).

    Magnitude = confirming − contradicting, then capped: no dated catalyst ≤ 3,
    medium evidence quality ≤ 3, low ≤ 2; against-trend −1. High conviction (4–5)
    therefore structurally requires ≥4 confirming families, ≤~1 contradicting, a
    dated catalyst, high-quality evidence, and not fighting the trend — naturally
    scarce. hold/watch clamp to ±1 (a strong view IS a buy/sell stance).

    Both counts are relative to the stated call (see :class:`EvidenceAssessment`), so
    ``magnitude`` is support for *that* call and the sign flip for ``sell`` is
    coherent: a sell whose own call is confirmed by 5 families is −5, not 0. A call
    whose own evidence is balanced derives 0 — a directional stance at 0 is a weak
    call, not a missing one.
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
    # Optional WP4.2 typed economics (#2637). Never derived from conviction_score
    # or price_targets — materializers (Task 4.3+) must populate explicitly.
    forecast: ForecastTerms | None = Field(
        default=None,
        description=(
            "Typed ForecastTerms when present. Legacy conviction_score / price_targets "
            "remain for compatibility and must not synthesize this field."
        ),
    )
    # Deterministic WP4.3 materializer output (#2649). Excluded from LLM JSON schema
    # so the model cannot invent identity / provenance fields.
    forecast_assessment: Annotated[ForecastAssessment | None, SkipJsonSchema()] = Field(
        default=None,
        description=(
            "Immutable ForecastAssessment produced by analyst materialization. "
            "Never LLM-authored; SkipJsonSchema keeps it out of the provider schema."
        ),
    )
