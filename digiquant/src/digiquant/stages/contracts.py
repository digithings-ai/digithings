"""Stage handoff models for ADR-0030.

Research output is ``ResearchDigest``. Trade-generation output is
``TradeIdeaSnapshot``. Neither type is an ``OrderIntent``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from digiquant.research.segments import digest_briefing_for_portfolio
from digiquant.research.snapshot import DigestPayload
from digiquant.stages.timeframe import ConsensusTimeframe


class StageId(StrEnum):
    RESEARCH = "research"
    INVESTMENT = "investment"
    EXECUTION = "execution"


class Stage2Kind(StrEnum):
    PORTFOLIO = "portfolio"
    TRADE_GENERATION = "trade_generation"


class ResearchDigest(BaseModel):
    """Stage-1 handoff. Briefing fields only, plus producer identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_date: date
    body: str = Field(min_length=1)
    regime_label: str = ""
    source: Literal["digiquant.research", "twelve-x.research"]
    composition_id: Literal["digiquant-baseline", "twelve-x"]


def research_digest_from_digest_payload(
    payload: DigestPayload,
    *,
    composition_id: Literal["digiquant-baseline"] = "digiquant-baseline",
) -> ResearchDigest:
    """Copy the briefing thesis/market already read. Drop every other digest field."""
    brief = digest_briefing_for_portfolio(payload.model_dump(mode="json"))
    if "date" not in brief or "body" not in brief:
        raise ValueError("DigestPayload briefing is missing date or body")
    return ResearchDigest(
        run_date=date.fromisoformat(str(brief["date"])[:10]),
        body=brief["body"],
        regime_label=brief.get("regime_label", ""),
        source="digiquant.research",
        composition_id=composition_id,
    )


class LevelProvenance(StrEnum):
    BROKER_QUOTED = "broker_quoted"
    PMT_BANK_TRADE = "pmt_bank_trade"
    PMT_SEASONALITY_TARGET = "pmt_seasonality_target"
    PMT_POSITION_CLUSTER = "pmt_position_cluster"
    PMT_RETAIL_BOOK = "pmt_retail_book"
    COMPUTED = "computed"
    TECHNICAL = "technical"
    LLM = "llm"


class LevelStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INCOMPLETE = "incomplete"


class TradeIdeaLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    provenance: LevelProvenance
    source_ref: str


class TradeIdeaLevels(BaseModel):
    """Mirrors ``FxTradeLevels`` in ``apps/dashboard/lib/twelve-x/types.ts``."""

    model_config = ConfigDict(extra="forbid")

    entry_low: TradeIdeaLevel | None = None
    entry_high: TradeIdeaLevel | None = None
    stop: TradeIdeaLevel | None = None
    targets: list[TradeIdeaLevel] = Field(default_factory=list)
    risk_reward: float | None = None
    status: LevelStatus


class TradeIdeaSnapshot(BaseModel):
    """Stage-2 trade-generation row. Not an order."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_date: date
    rank: int = Field(ge=1)
    pair: str = Field(min_length=1)
    direction: Literal["long", "short"]
    title: str
    thesis: str
    catalyst: str
    consensus_timeframe: ConsensusTimeframe
    display_timeframe: str | None = None
    levels: TradeIdeaLevels | None = None
    idea_id: str | None = None
    as_of: datetime | None = None


class ExecutionOptInRequired(Exception):
    """Trade ideas are not submittable. A later human-gated issue would opt in."""


def refuse_order_intent(idea: TradeIdeaSnapshot) -> None:
    """Refuse to turn a trade idea into an OrderIntent.

    There is no mapping. Calling this is the execution boundary. It does not
    write a row and it does not read the execution router.
    """
    raise ExecutionOptInRequired(
        "Trade ideas do not become OrderIntent rows. twelve-x does not execute. "
        "Only digiquant.execution may submit, and only after a separate human-gated "
        f"issue. idea_id={idea.idea_id!r} pair={idea.pair!r} rank={idea.rank}"
    )
