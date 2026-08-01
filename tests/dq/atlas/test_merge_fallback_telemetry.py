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
from digiquant.olympus.atlas import diagnostics
from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.telemetry import MERGE_FALLBACK_KEY, merge_fallback_breakdown

pytestmark = pytest.mark.unit


def _state(**extra: object) -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 7, 31),
        baseline_date=date(2026, 7, 30),
        **extra,  # type: ignore[arg-type]
    )


_THREE_FALLBACKS = {
    "crypto": "ValidationError: funding_rate_bias",
    "alt-sentiment-news": "ValidationError: retail_sentiment_stance",
    "equity": "ValidationError: market_breadth",
}


class TestMergeFallbackBreakdown:
    def test_clean_run_contributes_no_key(self) -> None:
        """Empty ⇒ ``{}`` so no key is written, like ``circuit_breaker_skips``."""
        assert merge_fallback_breakdown(_state()) == {}

    def test_counts_and_names_the_segments_that_paid_twice(self) -> None:
        """The 07-31 shape: three fallbacks, run recorded ``ok``, none in ``err_nodes``."""
        fragment = merge_fallback_breakdown(_state(merge_fallbacks=_THREE_FALLBACKS))
        assert set(fragment) == {MERGE_FALLBACK_KEY}
        entry = fragment[MERGE_FALLBACK_KEY]
        assert entry["count"] == 3
        assert list(entry["segments"]) == ["alt-sentiment-news", "crypto", "equity"]
        assert entry["segments"]["crypto"] == "ValidationError: funding_rate_bias"

    def test_breakdown_is_json_safe(self) -> None:
        """``breakdown`` is a jsonb column — str keys and str/int values only."""
        entry = merge_fallback_breakdown(_state(merge_fallbacks={"macro": "MergeError: x"}))[
            MERGE_FALLBACK_KEY
        ]
        assert isinstance(entry["count"], int)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in entry["segments"].items())

    def test_contributor_does_not_mutate_state(self) -> None:
        state = _state(merge_fallbacks=dict(_THREE_FALLBACKS))
        merge_fallback_breakdown(state)
        assert state.merge_fallbacks == _THREE_FALLBACKS


class TestSeamRegistration:
    def test_registered_with_the_diagnostics_seam(self) -> None:
        """Importing the module must be enough — nothing else calls the contributor.

        ``phases/_node_factory.py`` imports ``telemetry`` for exactly this side effect, so
        the key reaches ``atlas_run_diagnostics.breakdown`` on a real run.
        """
        assert merge_fallback_breakdown in diagnostics._BREAKDOWN_CONTRIBUTORS

    def test_summarize_run_projects_the_key(self) -> None:
        state = _state(merge_fallbacks=_THREE_FALLBACKS)
        breakdown = diagnostics.summarize_run(state).breakdown
        assert breakdown[MERGE_FALLBACK_KEY]["count"] == 3

    def test_summarize_run_omits_the_key_on_a_clean_run(self) -> None:
        assert MERGE_FALLBACK_KEY not in diagnostics.summarize_run(_state()).breakdown

    def test_the_key_does_not_gate_status_or_retry(self) -> None:
        """Non-gating by construction: only the counter differs between these two runs."""
        clean = diagnostics.summarize_run(_state())
        fell_back = diagnostics.summarize_run(_state(merge_fallbacks=_THREE_FALLBACKS))
        assert fell_back.status == clean.status
        assert fell_back.retry_signal == clean.retry_signal


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
