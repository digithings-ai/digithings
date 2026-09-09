"""User investment profile + asset preferences + pipeline schedule schemas.

Versioned Pydantic v2 models describing a user's investment posture
(risk tolerance, horizon, currency, jurisdiction, ESG, sector exclusions,
experience level), per-user asset preferences (watchlists, custom
universe, ticker / sector exclusions), and workspace pipeline scheduling
(``PipelineSchedule`` + ``ExecutionPolicy``). Consumed by research /
portfolio / execution to constrain idea generation and portfolio construction.

See ``digiquant/docs/profiles/README.md`` for the migration story.
"""

from __future__ import annotations

from digiquant.profiles.asset_preferences import AssetPreferences
from digiquant.profiles.execution_policy import ExecutionPolicy
from digiquant.profiles.investment_profile import InvestmentProfile
from digiquant.profiles.pipeline_schedule import (
    WEEKDAYS,
    DayStageFlags,
    PipelineSchedule,
    WeekdayName,
)

__all__ = [
    "WEEKDAYS",
    "AssetPreferences",
    "DayStageFlags",
    "ExecutionPolicy",
    "InvestmentProfile",
    "PipelineSchedule",
    "WeekdayName",
]
