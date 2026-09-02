"""WP10.4/WP10.5 — shared-cash Nautilus replay + paired shadow comparison.

Isolated challenger/shadow path only. Must never be imported by production
H8/H9 booking, commit writers, or live-trading surfaces.
"""

from __future__ import annotations

from digiquant.dashboard.replay.allocation_comparison import (
    AllocationComparisonReport,
    ComparisonStatus,
    compare_allocation_arms,
    load_shadow_criteria,
    write_comparison_report,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    FillRecord,
    HoldingQuantity,
    HoldingSnapshot,
    InstrumentBarSeries,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    TargetWeight,
    inconclusive_result,
)
from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

__all__ = [
    "AllocationComparisonReport",
    "ComparisonStatus",
    "ExecutionPolicy",
    "FillRecord",
    "HoldingQuantity",
    "HoldingSnapshot",
    "InstrumentBarSeries",
    "OhlcvBar",
    "PortfolioReplayRequest",
    "PortfolioReplayResult",
    "PortfolioReplayStatus",
    "TargetWeight",
    "compare_allocation_arms",
    "inconclusive_result",
    "load_shadow_criteria",
    "run_portfolio_replay_isolated",
    "write_comparison_report",
]
