"""Phase B web research branch (#4064): grounding models + retrieve seam."""

# score:allow untyped any
# PEP 562 lazy exports resolve dynamically typed module attributes; Any is the honest annotation.

from importlib import import_module
from typing import Any

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
    "grounded_answer",
    "live_search",
    "structured_synthesis",
    "verify_grounding",
]

_LAZY_EXPORTS: dict[str, str] = {
    "grounded_answer": "digisearch.web.answer",
    "structured_synthesis": "digisearch.web.structured",
    "verify_grounding": "digisearch.web.structured",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_path), name)
