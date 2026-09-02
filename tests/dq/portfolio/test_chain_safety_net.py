"""Chain safety net (Pillar 1B).

A failing terminal phase (risk-sizing / publish / materialize) or a graph-level crash must
be recorded and swallowed so the run still reaches the remaining phases + the diagnostics
write — never a hard abort that leaves the dashboard stale.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from digiquant.research import diagnostics
from digiquant.research.graph import ResearchInput
from digiquant.research.phases.preflight import PreflightDeps
from digiquant.research.state import (
    ResearchConfigBundle,
    ResearchState,
    PhasePortfolioState,
    SegmentPayload,
    SegmentSlot,
)
from digiquant.portfolio.chain import (
    ChainDeps,
    _coerce_research_state,
    _record_chain_error,
    _retry_worthy,
    _run_beliefs_fold,
    _run_terminal_phase,
    run_research_then_portfolio,
)

pytestmark = pytest.mark.unit


def _state() -> ResearchState:
    return ResearchState(
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
    _record_chain_error(state, "research", RuntimeError("graph crash"))
    assert state.errors[-1].phase == "chain"
    assert state.errors[-1].node == "research"
    assert "graph crash" in state.errors[-1].message


def test_coerce_research_state_normalizes_langgraph_dict() -> None:
    state = _state()
    state.config = ResearchConfigBundle(preferences={"debate_rounds": 3})
    raw = state.model_dump(mode="json")
    coerced = _coerce_research_state(raw)
    assert isinstance(coerced, ResearchState)
    assert coerced.config.preferences.get("debate_rounds", 1) == 3


def test_coerce_research_state_passthrough_model() -> None:
    state = _state()
    assert _coerce_research_state(state) is state


def test_retry_worthy_when_degraded_and_no_book() -> None:
    # No fresh research + no materialized book → the run should retry (the #726 degraded gate).
    state = _state()
    assert _retry_worthy(state, degraded_pct=50.0) is True


def test_not_retry_worthy_when_book_committed() -> None:
    # #809 (generalized by #1555): a degraded run that COMMITTED a valid sized book must
    # NOT retry — re-running just burns the CI outer-loop's backoff sleeps on a good book.
    # The guard now keys on the commit manifest, not mere materialization.
    state = _state()
    state.phase_portfolio = PhasePortfolioState(
        sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
        commit_manifest={"status": "committed", "source_run_id": str(state.run_id)},
    )
    assert _retry_worthy(state, degraded_pct=50.0) is False


def test_retry_worthy_when_book_materialized_but_uncommitted() -> None:
    # #1555: a book H8 materialized but H9 never committed (coherence fail-closed / silent
    # skip) is NOT durable work — it must retry. This is the exact shape of the 2026-06-26
    # freeze, which the old materialization-only guard wrongly treated as a good book.
    state = _state()
    state.phase_portfolio = PhasePortfolioState(
        sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
        commit_manifest=None,
    )
    assert _retry_worthy(state, degraded_pct=50.0) is True


def test_not_retry_worthy_when_not_degraded() -> None:
    # A run with fresh research is not degraded → never retry, book or not. NOTE this holds
    # even though ``status`` is now "degraded" for exactly this state (no committed book):
    # ``_retry_worthy`` keys on the frozen ``retry_signal``, not on the health verdict (#1736).
    state = _state()
    state.phase1_outputs = {
        "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=state.run_date))
    }
    assert _retry_worthy(state, degraded_pct=50.0) is False
    assert diagnostics.summarize_run(state).status == "degraded"


# ─── #1737: beliefs distillation is optional and must never kill a booked run ───


class _FakeClient:
    """Stand-in for the Supabase client; only its presence matters to the beliefs fold."""


def _chain_deps() -> ChainDeps:
    from digiquant.research.graph import ResearchGraphDeps
    from digiquant.portfolio.graph import PortfolioGraphDeps

    return ChainDeps(
        research=ResearchGraphDeps(
            preflight=PreflightDeps(client=_FakeClient(), config_loader=None)  # type: ignore[arg-type]
        ),
        portfolio=PortfolioGraphDeps(),
    )


def test_beliefs_failure_is_recorded_and_swallowed() -> None:
    # Beliefs distillation is an on-demand backlog fold, not a run deliverable. Before #1737
    # both call sites were bare, so a failure here propagated out of run_research_then_portfolio and
    # killed a run whose book had already committed.
    state = _state()
    with patch(
        "digiquant.portfolio.chain.run_beliefs_distillation_if_triggered",
        side_effect=RuntimeError("beliefs LLM 500"),
    ):
        _run_beliefs_fold(state, _chain_deps(), ResearchInput(run_date=state.run_date))
    assert [(e.phase, e.node) for e in state.errors] == [("chain", "beliefs")]
    assert "beliefs LLM 500" in state.errors[0].message


def test_beliefs_fold_skipped_without_a_client() -> None:
    from digiquant.research.graph import ResearchGraphDeps
    from digiquant.portfolio.graph import PortfolioGraphDeps

    state = _state()
    deps = ChainDeps(
        research=ResearchGraphDeps(preflight=PreflightDeps(client=None, config_loader=None)),  # type: ignore[arg-type]
        portfolio=PortfolioGraphDeps(),
    )
    with patch(
        "digiquant.portfolio.chain.run_beliefs_distillation_if_triggered",
        side_effect=AssertionError("must not be called"),
    ):
        _run_beliefs_fold(state, deps, ResearchInput(run_date=state.run_date))
    assert state.errors == []


# ─── #1733/#1763: a terminating crash must be recorded before the diagnostics write ───


def test_terminating_crash_is_recorded_in_the_diagnostics_row_then_reraised() -> None:
    """A BaseException (job-timeout SIGTERM, SystemExit, KeyboardInterrupt) used to reach the
    ``finally`` diagnostics write with an error-free state — so the row said nothing was
    wrong. Record it first, then re-raise untouched so the exit code is unchanged."""
    written: dict[str, object] = {}

    def _capture(_client, *, state, **_kwargs):
        written["errors"] = [(e.phase, e.node) for e in state.errors]
        written["status"] = diagnostics.summarize_run(state).status
        return None

    from digiquant.portfolio.chain import DiagnosticsDeps

    deps = _chain_deps()
    deps = ChainDeps(
        research=deps.research,
        portfolio=deps.portfolio,
        diagnostics=DiagnosticsDeps(client=_FakeClient(), run_id="r1"),
    )
    with (
        patch("digiquant.portfolio.chain.build_research_graph", side_effect=KeyboardInterrupt),
        patch("digiquant.research.diagnostics.write_row", _capture),
        pytest.raises(KeyboardInterrupt),
    ):
        run_research_then_portfolio(research_input=ResearchInput(run_date=date(2026, 6, 12)), deps=deps)

    assert written["errors"] == [("chain", "terminal")]
    assert written["status"] == "failed"
