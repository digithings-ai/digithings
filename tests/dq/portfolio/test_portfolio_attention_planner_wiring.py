"""WP13.4 — Hermes research attention planner wiring (#2930)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from unittest.mock import patch

import pytest
from digiquant.research.research_attention import (
    OLYMPUS_RESEARCH_ATTENTION_MODE_ENV,
    attention_store_for_run,
    reset_attention_stores,
)
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.portfolio.models.analyst import AnalystPayload
from digiquant.portfolio.phases.h4_opportunity_screener import build_h4_opportunity_screener
from digiquant.portfolio.phases.portfolio_common import run_asset_analyst_llm
from digiquant.portfolio.research_attention import (
    h4_phase_attention_update,
    plan_hermes_research_attention,
    research_attention_h5_enforce_path,
    research_attention_h6_enforce_path,
    resolve_h6_attention_decision,
)
from digiquant.dashboard.research_retrieval.planner import (
    AttentionMode,
    AttentionPlan,
    AttentionRolloutMode,
)

pytestmark = pytest.mark.unit

RUN = date(2026, 8, 26)
PRIOR = date(2026, 8, 25)


def _prior_analyst(ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "stance": "hold",
        "conviction_score": 1,
        "thesis": "prior thesis",
        "risks": "none",
        "sources": [],
        "forecast": {
            "horizon_sessions": 21,
            "half_life_sessions": 10,
            "bear_return": "-0.05",
            "base_return": "0.01",
            "bull_return": "0.08",
            "bear_probability": "0.25",
            "base_probability": "0.50",
            "bull_probability": "0.25",
            "thesis_valid_probability": "0.55",
            "raw_uncertainty": "low",
            "evidence_ids": ["ev-1"],
            "counter_evidence_ids": [],
            "assumptions": ["stable"],
            "invalidation_rules": [],
        },
    }


def _state_with_roster(*, price_deltas: dict[str, float] | None = None) -> AtlasResearchState:
    roster = [
        FocusRosterEntry(ticker="SPY", roster_reason="held"),
        FocusRosterEntry(ticker="QQQ", roster_reason="technical"),
    ]
    return AtlasResearchState(
        run_type="delta",
        run_date=RUN,
        baseline_date=PRIOR,
        config=AtlasConfigBundle(watchlist=["SPY", "QQQ", "IWM"]),
        prior_context=PriorContext(
            prior_book=[{"ticker": "SPY", "weight_pct": 10.0}],
            prior_analyst_by_ticker={"SPY": _prior_analyst("SPY"), "QQQ": _prior_analyst("QQQ")},
        ),
        price_deltas=price_deltas or {},
        phase_hermes=PhaseHermesState(focus_roster=roster),
    )


@pytest.fixture(autouse=True)
def _clean_attention_stores() -> None:
    reset_attention_stores()
    yield
    reset_attention_stores()


def test_h4_builds_plan_after_roster_without_mutating_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    state = _state_with_roster(price_deltas={"SPY": 0.001})
    roster_before = [e.model_dump(mode="json") for e in state.phase_hermes.focus_roster]
    update = h4_phase_attention_update(state)
    assert update.get("hermes_research_attention_plan") is not None
    plan = AttentionPlan.model_validate(update["hermes_research_attention_plan"])
    assert plan.rollout_mode is AttentionRolloutMode.SHADOW
    assert {d.target_key for d in plan.decisions} == {"SPY", "QQQ"}
    roster_after = [e.model_dump(mode="json") for e in state.phase_hermes.focus_roster]
    assert roster_before == roster_after


def test_plan_persists_to_attention_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    state = _state_with_roster()
    update = h4_phase_attention_update(state)
    plan = AttentionPlan.model_validate(update["hermes_research_attention_plan"])
    store = attention_store_for_run(str(state.run_id))
    persisted = store.load_plan(plan.plan_id)
    assert persisted.plan == plan


def test_off_mode_skips_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "off")
    state = _state_with_roster()
    assert plan_hermes_research_attention(state) is None
    assert h4_phase_attention_update(state) == {}


def test_h6_resolves_after_h5_features(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "enforce")
    state = _state_with_roster(price_deltas={"SPY": 0.05})
    update = h4_phase_attention_update(state)
    state = state.model_copy(update=update)
    analyst = {
        "ticker": "SPY",
        "stance": "buy",
        "conviction_score": 4,
        "forecast": {
            "raw_uncertainty": "high",
            "counter_evidence_ids": ["c1"],
            "invalidation_rules": [],
            "stance": "buy",
            "conviction_score": 4,
            "price_anchors": [],
        },
    }
    decision = resolve_h6_attention_decision(state, "SPY", analyst)
    assert decision is not None
    assert decision.mode is AttentionMode.CHALLENGE
    assert research_attention_h6_enforce_path(state, "SPY", analyst) == "challenge"


def test_enforce_h5_carry_skips_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "enforce")
    roster = [
        FocusRosterEntry(
            ticker="XYZ",
            roster_reason="thesis_mapped",
            linked_market_thesis_id="demo-thesis",
        )
    ]
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN,
        config=AtlasConfigBundle(watchlist=["XYZ"]),
        prior_context=PriorContext(prior_analyst_by_ticker={"XYZ": _prior_analyst("XYZ")}),
        phase_hermes=PhaseHermesState(focus_roster=roster),
    )
    update = h4_phase_attention_update(state)
    state = state.model_copy(update=update)
    assert research_attention_h5_enforce_path(state, ticker="XYZ") == "carry"

    agent_calls: list[str] = []

    def _fail_agent(**kwargs: Any) -> AnalystPayload:
        agent_calls.append("called")
        return AnalystPayload.model_validate(_prior_analyst("SPY"))

    with patch(
        "digiquant.portfolio.phases.portfolio_common.run_research_agent",
        side_effect=_fail_agent,
    ):
        payload, _doc, _errors, _bundle = run_asset_analyst_llm(
            state=state,
            ticker="XYZ",
            roster_entry={
                "ticker": "XYZ",
                "roster_reason": "thesis_mapped",
                "linked_market_thesis_id": "demo-thesis",
            },
            phase_slug="test-h5",
        )
    assert payload is not None
    assert agent_calls == []


def test_graph_node_order_unchanged() -> None:
    from digiquant.portfolio.graph import build_hermes_phases_thesis

    phases = build_hermes_phases_thesis(watchlist=["SPY"], held={"SPY"})
    names = [p.name for p in phases]
    assert names.index("hermes_h4_opportunity_screener") < names.index("hermes_h5_asset_analyst")
    assert names.index("hermes_h5_asset_analyst") < names.index("hermes_h6_deliberation")
    assert len(names) == len(set(names))


def test_h4_node_plans_without_changing_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN,
        config=AtlasConfigBundle(watchlist=["SPY", "QQQ", "IWM"]),
        prior_context=PriorContext(prior_book=[{"ticker": "SPY", "weight_pct": 5.0}]),
    )
    node = build_h4_opportunity_screener().nodes[0].run
    off_env = "off"
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, off_env)
    reset_attention_stores()
    off_update = node(state.model_copy())
    off_roster = json.dumps(
        [e.model_dump(mode="json") for e in off_update["phase_hermes"].focus_roster],
        sort_keys=True,
    )
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    reset_attention_stores()
    shadow_update = node(state.model_copy())
    shadow_roster = json.dumps(
        [e.model_dump(mode="json") for e in shadow_update["phase_hermes"].focus_roster],
        sort_keys=True,
    )
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "enforce")
    reset_attention_stores()
    enforce_update = node(state.model_copy())
    enforce_roster = json.dumps(
        [e.model_dump(mode="json") for e in enforce_update["phase_hermes"].focus_roster],
        sort_keys=True,
    )
    assert off_roster == shadow_roster == enforce_roster
    assert enforce_update.get("hermes_research_attention_plan") is not None
