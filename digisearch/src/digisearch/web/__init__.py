"""Phase B web research branch (#4064): grounding models + retrieve seam."""

from digisearch.web.grounding_models import (
    EFFORT_PRESETS,
    Confidence,
    EffortMode,
    FieldGrounding,
    GroundingCitation,
    StructuredSynthesis,
    TurnCost,
    TurnUsage,
    WebResearchConfig,
    WebResearchError,
)
from digisearch.web.retrieve import FetchedPage, fetch_pages, live_search

__all__ = [
    "EFFORT_PRESETS",
    "Confidence",
    "EffortMode",
    "FetchedPage",
    "FieldGrounding",
    "GroundingCitation",
    "StructuredSynthesis",
    "TurnCost",
    "TurnUsage",
    "WebResearchConfig",
    "WebResearchError",
    "fetch_pages",
    "live_search",
]
