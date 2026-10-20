"""Swappable digiquant stage handoffs (ADR-0030).

Adapters live in ``digiquant.stages.adapters`` and are imported from there.
"""

from digiquant.stages.contracts import (
    ExecutionOptInRequired,
    LevelProvenance,
    LevelStatus,
    ResearchDigest,
    Stage2Kind,
    StageId,
    TradeIdeaLevel,
    TradeIdeaLevels,
    TradeIdeaSnapshot,
    refuse_order_intent,
    research_digest_from_digest_payload,
)
from digiquant.stages.timeframe import (
    ConsensusTimeframe,
    TimeframeContractError,
    split_timeframe,
)

__all__ = [
    "ConsensusTimeframe",
    "ExecutionOptInRequired",
    "LevelProvenance",
    "LevelStatus",
    "ResearchDigest",
    "Stage2Kind",
    "StageId",
    "TimeframeContractError",
    "TradeIdeaLevel",
    "TradeIdeaLevels",
    "TradeIdeaSnapshot",
    "refuse_order_intent",
    "research_digest_from_digest_payload",
    "split_timeframe",
]
