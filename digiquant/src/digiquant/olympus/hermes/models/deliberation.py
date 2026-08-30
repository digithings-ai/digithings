"""H6 deliberation turn + summary models (spec §10)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Annotated,
    Any,  # score:allow untyped any — scored-lint suppression: persisted JSON summary dicts
    Literal,
)

from pydantic import BaseModel, BeforeValidator, Field

CONVICTION_DELTA_MIN = -2
CONVICTION_DELTA_MAX = 2


def _clamp_conviction_delta(value: object) -> object:
    """Bound LLM ``conviction_delta`` to the H6 contract instead of rejecting the turn.

    House GHA 33426508863 failed ``DeliberationAnalystTurn`` at ``input_value=-3``
    (``ge=-2``). A -3 is a max-bearish revision; clamp, don't drop the debate.
    ``bool`` is excluded because it subclasses ``int``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    if value < CONVICTION_DELTA_MIN:
        return CONVICTION_DELTA_MIN
    if value > CONVICTION_DELTA_MAX:
        return CONVICTION_DELTA_MAX
    return value


ConvictionDelta = Annotated[int, BeforeValidator(_clamp_conviction_delta)]

MissingFactSourceKind = Literal[
    "analyst",
    "digest",
    "macro",
    "equity",
    "institutional",
    "altdata",
    "sectors",
]


class MissingFactProposal(BaseModel):
    """PM-named exact missing fact H6 may supplement once (#2908 / WP11.4)."""

    claim_id: str = Field(
        min_length=1,
        description="Evidence or bundle ID from the H5 base bundle being challenged.",
    )
    question: str = Field(
        min_length=1,
        description="The single factual question the supplement must answer.",
    )
    source_kind: MissingFactSourceKind = Field(
        description="Blinded retrieval target — never generic web search.",
    )
    reason: str = Field(
        min_length=1,
        description="Why the named fact is required for this challenge.",
    )


class DeliberationTurn(BaseModel):
    """One PM↔analyst exchange in the deliberation transcript."""

    role: Literal["pm", "analyst"]
    round_number: int = Field(ge=1)
    message: str = Field()


class DeliberationPmTurn(BaseModel):
    """PM challenge turn or terminal summary."""

    converged: bool = False
    challenge: str = Field(
        default="",
        description=(
            "The specific, substantive challenge you raised this turn (sizing, correlation "
            "with the book, catalyst timing, or downside). Required before converging — "
            "never empty on a convergence turn."
        ),
    )
    accepts_analyst_position: bool = False
    open_questions: list[str] = Field(default_factory=list)
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = Field(
        default="neutral",
        description="Your explicit directional call after the debate — choose, don't default.",
    )
    conviction_delta: ConvictionDelta = Field(default=0, ge=-2, le=2)
    # WP11.4 — at most one validated missing-fact supplement per deliberation.
    missing_fact: MissingFactProposal | None = Field(
        default=None,
        description=(
            "Optional named missing fact for a bounded evidence amendment. Omit when "
            "the H5 base bundle is sufficient; never request broad re-grounding."
        ),
    )


class DeliberationAnalystTurn(BaseModel):
    """Analyst response turn or terminal summary."""

    converged: bool = False
    response: str = Field(default="")
    revises_payload: bool = False
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: ConvictionDelta = Field(default=0, ge=-2, le=2)
    # Optional complete replacement ForecastTerms for WP4.4 amendment materialization.
    # Partial nested patches are rejected by materialize/resolve — omit when unchanged.
    forecast_amendment: dict[str, Any] | None = None


CARRY_FINGERPRINT_SKIP = "fingerprint_skip"
CARRY_LLM_FAILURE = "llm_failure"
CARRY_LOW_VALUE = "low_value_carry"
CARRY_ATTENTION = "attention_carry"
CarryReason = Literal["fingerprint_skip", "llm_failure", "low_value_carry"]


class DeliberationSummary(BaseModel):
    """Per-ticker deliberation output feeding H7."""

    ticker: str = Field()
    converged: bool = True
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: ConvictionDelta = Field(default=0, ge=-2, le=2)
    transcript: list[DeliberationTurn] = Field(default_factory=list)
    carried: bool = False
    carry_reason: CarryReason | None = Field(
        default=None,
        description=(
            "Why the debate did not run. ``fingerprint_skip`` is the benign quiet-ticker "
            "carry (#925); ``llm_failure`` means the deliberation crashed and no PM "
            "challenge ever executed (#1742); ``low_value_carry`` is WP11.3 deterministic "
            "selection (#2902). ``carried`` alone cannot tell these apart."
        ),
    )
    escalated: bool = False
    cap_reason: str | None = None
    # WP11.3 — every H6 run/carry records one selection reason (+ optional full dump).
    selection_reason: str | None = Field(
        default=None,
        description="Primary H6SelectionReason code for this run/carry (#2902).",
    )
    h6_selection: dict[str, Any] | None = Field(
        default=None,
        description="Optional H6Selection dump (shadow/enforce audit; never prompt input).",
    )
    # WP4.4 forecast lineage — IDs + optional full amendment dump for H9 registry (#2663).
    base_forecast_id: str | None = None
    amendment_id: str | None = None
    effective_forecast_id: str | None = None
    amendment_outcome: str | None = None
    forecast_degradation: str | None = None
    effective_forecast: dict[str, Any] | None = None
    forecast_amendment: dict[str, Any] | None = None
    # WP11.4 — evidence amendment lineage (distinct from forecast amendment above).
    base_bundle_id: str | None = Field(
        default=None,
        description="Immutable H5 base bundle ID for this ticker.",
    )
    missing_fact_request_id: str | None = None
    evidence_amendment_id: str | None = None
    evidence_amendment_outcome: str | None = Field(
        default=None,
        description=(
            "Outcome of the bounded missing-fact supplement: accepted, invalid_request, "
            "policy_exhausted, retrieval_failed, blinded_source, or none."
        ),
    )
    evidence_amendment_failure_reason: str | None = None


def is_unchallenged_carry(summary: Mapping[str, Any]) -> bool:
    """True when a summary dict carries a stance whose PM challenge never ran (#1742).

    Reads the persisted dict shape rather than the model because every downstream consumer
    (``payloads``, H7, H8 sizing, the published document) sees state as plain JSON.
    """
    return summary.get("carry_reason") == CARRY_LLM_FAILURE
