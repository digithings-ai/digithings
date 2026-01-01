"""Per-turn timing/cost accounting for the Phase B web research branch (#4064).

Pure accounting: nothing in this module reads the wall clock — callers measure
with ``time.perf_counter`` and pass integer milliseconds in. ``estimate_cost``
is advisory-only (OSS web search has no metered dollar cost): ``total`` must
never gate routing on its own; gates also consult stage-ms, and when
``breakdown["llm_calls"] > 0`` they consult digillm telemetry for LLM spend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from digisearch.web.grounding_models import TurnCost, TurnUsage

__all__ = ["StageTimer", "estimate_cost", "finalize_usage", "record_stage", "start_clock"]


@dataclass
class StageTimer:
    """Mutable integer-millisecond accumulator, one entry per recorded stage."""

    stages: dict[str, int] = field(default_factory=dict)


def start_clock() -> StageTimer:
    """Return an empty timer; callers advance it via :func:`record_stage`."""
    return StageTimer()


def record_stage(timer: StageTimer, name: str, ms: int) -> None:
    """Add *ms* to stage *name* (repeated names accumulate)."""
    timer.stages[name] = timer.stages.get(name, 0) + ms


def finalize_usage(
    timer: StageTimer,
    *,
    searches: int = 0,
    pages_fetched: int = 0,
    pages_cited: int = 0,
    llm_calls: int = 0,
) -> TurnUsage:
    """Build the landed :class:`TurnUsage` from *timer* plus turn counters.

    ``total_ms`` is the sum of every recorded stage. Pure: reads no clock.
    """
    return TurnUsage(
        searches=searches,
        pages_fetched=pages_fetched,
        pages_cited=pages_cited,
        llm_calls=llm_calls,
        search_ms=timer.stages.get("search_ms", 0),
        fetch_ms=timer.stages.get("fetch_ms", 0),
        rerank_ms=timer.stages.get("rerank_ms", 0),
        synthesis_ms=timer.stages.get("synthesis_ms", 0),
        total_ms=sum(timer.stages.values()),
    )


def estimate_cost(*, searches: int, pages_fetched: int, llm_calls: int) -> TurnCost:
    """Advisory OSS cost for one web research turn (never a routing gate alone).

    ``total`` stays ``0.0`` — the OSS path has no metered per-call dollar cost;
    LLM spend is metered in digillm telemetry and is deliberately not folded in.
    """
    return TurnCost(
        total=0.0,
        provider="web-oss",
        breakdown={
            "searches": searches,
            "pages_fetched": pages_fetched,
            "llm_calls": llm_calls,
        },
        note="oss-synthesis; llm spend metered in digillm telemetry, not here",
    )
