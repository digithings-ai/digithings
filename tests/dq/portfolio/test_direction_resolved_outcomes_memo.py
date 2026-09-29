"""Collapse the duplicate resolved-outcomes GET across one run (#4617).

Each daily run issued the byte-identical ``list_resolved_outcomes_as_of``
Supabase GET twice — once at research preflight (direction prerequisites) and
once in the portfolio direction phase (shadow calibration). Both paths now
share a run-scoped ``ResolvedOutcomesMemo``: the first reader issues the GET,
the second reuses it.

These tests exercise *both* real paths against one counting client and pin:
exactly one ``forecast_outcomes`` GET, cohort agreement between the paths, and
the preserved #4298 fail-loud / generic-``Exception`` fail-soft semantics.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

import pytest
from digiquant.dashboard.research_retrieval.direction_prerequisites import (
    build_direction_prerequisite_snapshot,
)
from digiquant.portfolio.phases.direction import _direction_node, _load_cutoff_outcomes
from digiquant.research import forecast_outcomes as fo
from digiquant.research.state import PhasePortfolioState, ResearchState

from tests.dq.research.test_forecast_outcome_hash_ingress import (
    _build_outcome,
    _postgrest_numeric_roundtrip,
    _stale_row,
)
from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

CUTOFF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
RUN_DATE = date(2026, 8, 25)


@pytest.fixture(autouse=True)
def _stub_web_grounding_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the tool-only grounding boundary with canned grounding (#3859)."""
    from digiquant.research.testing.simulator import CANNED_TOOL_SEARCH

    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
        lambda **_kwargs: dict(CANNED_TOOL_SEARCH),
    )
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.call_web_search_tool",
        lambda **_kwargs: {
            "summary": str(CANNED_TOOL_SEARCH["summary"]),
            "sources": list(CANNED_TOOL_SEARCH["sources"]),
        },
    )
    monkeypatch.setattr(
        "digiquant.research.data.ai_portfolios.fetch_ai_portfolio_grounding",
        lambda **_kwargs: dict(CANNED_TOOL_SEARCH),
    )


def _healthy_row() -> dict[str, Any]:
    return _postgrest_numeric_roundtrip(fo._outcome_row(_build_outcome()))  # type: ignore[return-value]


def _counting_client(
    canned_reads: dict[str, list[dict[str, Any]]],
) -> tuple[FakeSupabaseClient, list[str]]:
    """Fake client recording each ``forecast_outcomes`` table read (one GET each)."""
    client = FakeSupabaseClient(canned_reads=canned_reads)
    gets: list[str] = []
    real_table = client.table

    def _counting_table(name: str) -> Any:
        if name == fo.OUTCOMES:
            gets.append(name)
        return real_table(name)

    client.table = _counting_table  # type: ignore[method-assign]
    return client, gets


def _state() -> ResearchState:
    return ResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        knowledge_cutoff_at=CUTOFF,
        phase_portfolio=PhasePortfolioState(),
    )


def test_preflight_and_direction_phase_issue_a_single_get() -> None:
    client, gets = _counting_client(canned_reads={fo.OUTCOMES: [_healthy_row()]})
    memo: fo.ResolvedOutcomesMemo = {}
    state = _state()

    snapshot = build_direction_prerequisite_snapshot(
        client=client,
        run_date=RUN_DATE,
        knowledge_cutoff_at=CUTOFF,
        research_state_pin=None,
        resolved_outcomes_memo=memo,
    )
    assert snapshot is not None
    assert snapshot.matured_forecast_outcome_ids
    # Realistic run shape: preflight's snapshot is on state when direction runs.
    state = state.model_copy(
        update={"direction_prerequisite_snapshot": snapshot.model_dump(mode="json")}
    )
    with patch(
        "digiquant.portfolio.phases.direction.run_research_agent",
        side_effect=ValueError("llm offline"),
    ):
        _direction_node(state, client=client, resolved_outcomes_memo=memo)

    assert len(gets) == 1, f"one run must issue one outcomes GET, saw {len(gets)}"

    # The phase cohort agrees with the preflight pin (same answer, not just one GET).
    phase_outcomes = _load_cutoff_outcomes(client=client, state=state, resolved_outcomes_memo=memo)
    assert len(gets) == 1
    assert tuple(sorted(str(o.outcome_id) for o in phase_outcomes)) == tuple(
        sorted(snapshot.matured_forecast_outcome_ids)
    )


def test_memo_hit_returns_an_equal_copy() -> None:
    client, gets = _counting_client(canned_reads={fo.OUTCOMES: [_healthy_row()]})
    memo: fo.ResolvedOutcomesMemo = {}
    state = _state()

    first = _load_cutoff_outcomes(client=client, state=state, resolved_outcomes_memo=memo)
    second = _load_cutoff_outcomes(client=client, state=state, resolved_outcomes_memo=memo)
    assert len(gets) == 1
    assert first == second
    assert first is not second


def test_memo_none_reads_directly_each_time() -> None:
    client, gets = _counting_client(canned_reads={fo.OUTCOMES: [_healthy_row()]})
    state = _state()

    build_direction_prerequisite_snapshot(
        client=client,
        run_date=RUN_DATE,
        knowledge_cutoff_at=CUTOFF,
        research_state_pin=None,
    )
    _load_cutoff_outcomes(client=client, state=state)
    assert len(gets) == 2


def test_integrity_error_propagates_on_both_memoized_paths() -> None:
    client, gets = _counting_client(canned_reads={fo.OUTCOMES: [_stale_row()]})
    memo: fo.ResolvedOutcomesMemo = {}
    state = _state()

    # #4298 fail-loud: never degrade to an empty cohort, on either path.
    with pytest.raises(fo.ForecastOutcomeIntegrityError):
        build_direction_prerequisite_snapshot(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            research_state_pin=None,
            resolved_outcomes_memo=memo,
        )
    with pytest.raises(fo.ForecastOutcomeIntegrityError):
        _load_cutoff_outcomes(client=client, state=state, resolved_outcomes_memo=memo)
    # Integrity failures are never cached: the memo stays empty.
    assert memo == {}


def test_transient_failure_stays_fail_soft_and_uncached() -> None:
    class _BrokenClient:
        def table(self, _name: str) -> object:
            raise RuntimeError("transient backend failure")

    client = _BrokenClient()
    memo: fo.ResolvedOutcomesMemo = {}
    state = _state()

    assert (
        build_direction_prerequisite_snapshot(
            client=client,  # type: ignore[arg-type]
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            research_state_pin=None,
            resolved_outcomes_memo=memo,
        )
        is None
    )
    assert (
        _load_cutoff_outcomes(
            client=client,  # type: ignore[arg-type]
            state=state,
            resolved_outcomes_memo=memo,
        )
        == []
    )
    assert memo == {}
