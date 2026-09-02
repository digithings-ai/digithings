"""WP7 follow-up #2808 — never invent USD when portfolio currency is unset."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from digiquant.portfolio.h9_cost_evidence import (
    build_cost_bundles_for_commit,
    investor_currency_from_state,
)
from digiquant.portfolio.risk_policy import resolve_risk_policy
from digiquant.research import cost_liquidity_registry as clr
from digiquant.research.state import ResearchConfigBundle, ResearchState

from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_RUN_DATE = date(2026, 8, 25)
_TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
_COMMIT_ID = UUID("bbbbbbbb-2222-4222-8222-222222222222")


def _state(*, preferences: dict | None = None, with_policy: bool = False) -> ResearchState:
    state = ResearchState(
        run_id=uuid4(),
        run_type="delta",
        run_date=_RUN_DATE,
        baseline_date=date(2026, 8, 22),
        knowledge_cutoff_at=_TS,
        config=ResearchConfigBundle(preferences=preferences or {}),
    )
    if with_policy:
        from digiquant.research.state import PhasePortfolioState

        state.phase_portfolio = PhasePortfolioState(
            risk_policy=_policy().model_dump(mode="json"),
        )
    return state


def _policy():
    return resolve_risk_policy({}, effective_at=_TS, source_run_id="run-currency").policy


class TestInvestorCurrencyFromState:
    def test_missing_prefs_returns_none_not_usd(self) -> None:
        assert investor_currency_from_state(_state()) is None

    def test_blank_currency_returns_none(self) -> None:
        assert investor_currency_from_state(_state(preferences={"currency": "  "})) is None
        assert investor_currency_from_state(_state(preferences={"currency": "US"})) is None

    def test_explicit_currency_uppercased(self) -> None:
        assert (
            investor_currency_from_state(_state(preferences={"investor_currency": "eur"})) == "EUR"
        )
        assert investor_currency_from_state(_state(preferences={"currency": "GBP"})) == "GBP"


class TestMissingCurrencyFailSoft:
    def test_build_bundles_skips_without_inventing_usd(self) -> None:
        client = FakeSupabaseClient()
        bundles = build_cost_bundles_for_commit(
            client=client,
            state=_state(),
            commit_id=_COMMIT_ID,
            policy=_policy(),
        )
        assert bundles == []

    def test_persist_estimates_degrades_currency_missing(self) -> None:
        client = FakeSupabaseClient()
        result = clr.persist_action_cost_estimates_for_commit(
            client=client,
            state=_state(with_policy=True),
            commit_id=_COMMIT_ID,
        )
        assert result.degraded_reason == "currency_missing"
        assert result.estimates_written == 0
        assert client.store.get(clr.ACTION_COST_ESTIMATES, []) == []

    def test_resolve_outcomes_skips_without_currency(self) -> None:
        client = FakeSupabaseClient()
        result = clr.resolve_realized_action_cost_outcomes_from_state(
            client=client,
            state=_state(),
        )
        assert result.resolved == 0
        assert result.pending == 0
        assert client.store.get(clr.ACTION_COST_OUTCOMES, []) == []
