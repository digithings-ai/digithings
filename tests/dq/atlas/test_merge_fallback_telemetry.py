"""Counted, non-gating telemetry for edit-mode merge fallbacks (#1741).

#1641 replaced the ``edit merge failed`` ``PhaseError`` with a silent fallback to
full-mode regeneration. Correct for run health, but the ``PhaseError`` had been the only
thing that ever recorded the event: production run 30636503352 (2026-07-31) logged three
fallbacks, recorded ``status='ok'``, and listed none of the three in ``err_nodes``. A
segment that paid for a patch call *and* a full regeneration became byte-identical in
``atlas_run_diagnostics`` to one that merged cleanly.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.telemetry import merge_fallback_breakdown

pytestmark = pytest.mark.unit


def _state(**extra: object) -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 7, 31),
        baseline_date=date(2026, 7, 30),
        **extra,  # type: ignore[arg-type]
    )


class TestMergeFallbackBreakdown:
    def test_clean_run_contributes_no_key(self) -> None:
        """Empty ⇒ ``{}`` so the caller can omit the key, like ``circuit_breaker_skips``."""
        assert merge_fallback_breakdown(_state()) == {}

    def test_counts_and_names_the_segments_that_paid_twice(self) -> None:
        state = _state(
            merge_fallbacks={
                "crypto": "ValidationError: funding_rate_bias",
                "alt-sentiment-news": "ValidationError: retail_sentiment_stance",
                "equity": "ValidationError: market_breadth",
            }
        )
        breakdown = merge_fallback_breakdown(state)
        assert breakdown["count"] == 3
        assert list(breakdown["segments"]) == ["alt-sentiment-news", "crypto", "equity"]
        assert breakdown["segments"]["crypto"] == "ValidationError: funding_rate_bias"

    def test_breakdown_is_json_safe(self) -> None:
        """``breakdown`` is a jsonb column — str keys and str/int values only."""
        breakdown = merge_fallback_breakdown(_state(merge_fallbacks={"macro": "MergeError: x"}))
        assert isinstance(breakdown["count"], int)
        assert all(
            isinstance(k, str) and isinstance(v, str) for k, v in breakdown["segments"].items()
        )


class TestMergeFallbacksStateField:
    def test_defaults_to_empty(self) -> None:
        assert _state().merge_fallbacks == {}

    def test_carries_a_reducer_so_parallel_fan_out_does_not_raise(self) -> None:
        """11 sector nodes can fall back in the same superstep.

        Without an ``Annotated`` reducer LangGraph raises
        ``InvalidConcurrentGraphUpdate`` on concurrent writes to one field, which would
        turn a cost-telemetry key into a run-killing defect.
        """
        reducers = [m for m in AtlasResearchState.model_fields["merge_fallbacks"].metadata]
        assert len(reducers) == 1, "merge_fallbacks must carry exactly one reducer"
        reduce = reducers[0]
        assert reduce({"sector-energy": "a"}, {"sector-materials": "b"}) == {
            "sector-energy": "a",
            "sector-materials": "b",
        }
        # Right-wins rather than raising: a duplicate slug is not a wiring bug worth
        # failing a run over, unlike ``_merge_segment_dict``'s collision guard.
        assert reduce({"macro": "a"}, {"macro": "b"}) == {"macro": "b"}
