"""H6 deliberation turn + summary models (spec §10)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DeliberationTurn(BaseModel):
    """One PM↔analyst exchange in the deliberation transcript."""

    role: Literal["pm", "analyst"]
    round_number: int = Field(ge=1)
    message: str = Field()


class DeliberationPmTurn(BaseModel):
    """PM challenge turn or terminal summary."""

    converged: bool = False
    challenge: str = Field(default="")
    accepts_analyst_position: bool = False
    open_questions: list[str] = Field(default_factory=list)
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: int = Field(default=0, ge=-2, le=2)


class DeliberationAnalystTurn(BaseModel):
    """Analyst response turn or terminal summary."""

    converged: bool = False
    response: str = Field(default="")
    revises_payload: bool = False
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: int = Field(default=0, ge=-2, le=2)


class DeliberationSummary(BaseModel):
    """Per-ticker deliberation output feeding H7."""

    ticker: str = Field()
    converged: bool = True
    conclusion: str = Field(default="")
    net_stance: Literal["bullish", "neutral", "bearish"] = "neutral"
    conviction_delta: int = Field(default=0, ge=-2, le=2)
    transcript: list[DeliberationTurn] = Field(default_factory=list)
    carried: bool = False
