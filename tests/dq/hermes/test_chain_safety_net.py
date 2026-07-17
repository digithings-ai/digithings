"""Chain safety net (Pillar 1B).

A failing terminal phase (risk-sizing / publish / materialize) or a graph-level crash must
be recorded and swallowed so the run still reaches the remaining phases + the diagnostics
write — never a hard abort that leaves the dashboard stale.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    PhaseHermesState,
    SegmentPayload,
    SegmentSlot,
)
from digiquant.olympus.hermes.chain import (
    _coerce_atlas_state,
    _record_chain_error,
    _retry_worthy,
    _run_terminal_phase,
)

pytestmark = pytest.mark.unit


def _state() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta", run_date=date(2026, 6, 12), baseline_date=date(2026, 6, 9)
    )


def test_terminal_phase_none_deps_is_noop() -> None:
    state = _state()
    assert _run_terminal_phase(None, lambda _d: None, state, "publish") is state
    assert state.errors == []


def test_terminal_phase_swallows_failure_and_records_error() -> None:
    state = _state()

    def _boom(_deps):
        raise RuntimeError("publish exploded")

    out = _run_terminal_phase(object(), _boom, state, "publish")
    assert out is state  # last-good state returned, not raised
    # Chain-level errors are marked phase="chain" (node = which stage) so the diagnostics
    # gate can distinguish them from node-level errors.
    assert [(e.phase, e.node) for e in state.errors] == [("chain", "publish")]
    assert "publish exploded" in state.errors[0].message


def test_record_chain_error_appends_phase_error() -> None:
    state = _state()
    _record_chain_error(state, "atlas", RuntimeError("graph crash"))
    assert state.errors[-1].phase == "chain"
    assert state.errors[-1].node == "atlas"
    assert "graph crash" in state.errors[-1].message


def test_coerce_atlas_state_normalizes_langgraph_dict() -> None:
    state = _state()
    state.config = AtlasConfigBundle(preferences={"debate_rounds": 3})
    raw = state.model_dump(mode="json")
    coerced = _coerce_atlas_state(raw)
    assert isinstance(coerced, AtlasResearchState)
    assert coerced.config.preferences.get("debate_rounds", 1) == 3


def test_coerce_atlas_state_passthrough_model() -> None:
    state = _state()
    assert _coerce_atlas_state(state) is state


def test_retry_worthy_when_degraded_and_no_book() -> None:
    # No fresh research + no materialized book → the run should retry (the #726 degraded gate).
    state = _state()
    assert _retry_worthy(state, degraded_pct=50.0) is True


def test_not_retry_worthy_when_book_committed() -> None:
    # #809 (generalized by #1555): a degraded run that COMMITTED a valid sized book must
    # NOT retry — re-running just burns the CI outer-loop's backoff sleeps on a good book.
    # The guard now keys on the commit manifest, not mere materialization.
    state = _state()
    state.phase_hermes = PhaseHermesState(
        sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
        commit_manifest={"status": "committed", "source_run_id": str(state.run_id)},
    )
    assert _retry_worthy(state, degraded_pct=50.0) is False


def test_retry_worthy_when_book_materialized_but_uncommitted() -> None:
    # #1555: a book H8 materialized but H9 never committed (coherence fail-closed / silent
    # skip) is NOT durable work — it must retry. This is the exact shape of the 2026-06-26
    # freeze, which the old materialization-only guard wrongly treated as a good book.
    state = _state()
    state.phase_hermes = PhaseHermesState(
        sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
        commit_manifest=None,
    )
    assert _retry_worthy(state, degraded_pct=50.0) is True


def test_not_retry_worthy_when_not_degraded() -> None:
    # A run with fresh research is not degraded → never retry, book or not.
    state = _state()
    state.phase1_outputs = {
        "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=state.run_date))
    }
    assert _retry_worthy(state, degraded_pct=50.0) is False
