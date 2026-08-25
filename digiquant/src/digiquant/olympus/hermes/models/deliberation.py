"""H6 deliberation turn + summary models (spec §10)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: persisted JSON summary dicts
    Literal,
)

from pydantic import BaseModel, Field


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
    conviction_delta: int = Field(default=0, ge=-2, le=2)


class DeliberationAnalystTurn(BaseModel):
    """Analyst response turn or terminal summary."""

    converged: bool = False
    response: str = Field(default="")
    revises_payload: bool = False
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: int = Field(default=0, ge=-2, le=2)
    # Optional complete replacement ForecastTerms for WP4.4 amendment materialization.
    # Partial nested patches are rejected by materialize/resolve — omit when unchanged.
    forecast_amendment: dict[str, Any] | None = None


CARRY_FINGERPRINT_SKIP = "fingerprint_skip"
CARRY_LLM_FAILURE = "llm_failure"
CarryReason = Literal["fingerprint_skip", "llm_failure"]


class DeliberationSummary(BaseModel):
    """Per-ticker deliberation output feeding H7."""

    ticker: str = Field()
    converged: bool = True
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: int = Field(default=0, ge=-2, le=2)
    transcript: list[DeliberationTurn] = Field(default_factory=list)
    carried: bool = False
    carry_reason: CarryReason | None = Field(
        default=None,
        description=(
            "Why the debate did not run. ``fingerprint_skip`` is the benign quiet-ticker "
            "carry (#925); ``llm_failure`` means the deliberation crashed and no PM "
            "challenge ever executed (#1742). ``carried`` alone cannot tell the two apart, "
            "which is how 31 crashed debates and 4 intentional skips published the same "
            "flag on 2026-07-31."
        ),
    )
    escalated: bool = False
    cap_reason: str | None = None
    # WP4.4 forecast lineage — IDs only on the summary; full artifacts stay on analyst docs.
    base_forecast_id: str | None = None
    amendment_id: str | None = None
    effective_forecast_id: str | None = None
    amendment_outcome: str | None = None
    forecast_degradation: str | None = None
    effective_forecast: dict[str, Any] | None = None


def is_unchallenged_carry(summary: Mapping[str, Any]) -> bool:
    """True when a summary dict carries a stance whose PM challenge never ran (#1742).

    Reads the persisted dict shape rather than the model because every downstream consumer
    (``payloads``, H7, H8 sizing, the published document) sees state as plain JSON.
    """
    return summary.get("carry_reason") == CARRY_LLM_FAILURE
