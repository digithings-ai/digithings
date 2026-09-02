"""Unit tests for AttentionPlan daily graph publish wiring (#2622)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.phases.publish_phase import PublishDeps, build_publish_node
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DeltaTriageDecision,
    DeltaTriageResult,
    FocusRosterEntry,
    PhaseHermesState,
)
from digiquant.dashboard.attention_plan_graph import (
    OLYMPUS_PLANNER_MODE_ENV,
    maybe_publish_attention_plan_shadow,
    planner_mode_from_env,
)
from digiquant.dashboard.attention_plan_io import ATTENTION_PLAN_DOCUMENT_KEY

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN = date(2026, 8, 25)


def _state_with_triage() -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=RUN,
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    state.triage = DeltaTriageResult(
        evaluated_at=RUN,
        baseline_date=date(2026, 8, 24),
        decisions=[
            DeltaTriageDecision(
                segment="macro",
                decision="regenerate",
                reason="mandatory",
                tier="mandatory",
            ),
            DeltaTriageDecision(
                segment="bonds",
                decision="carry",
                reason="below_threshold",
                tier="high",
            ),
        ],
    )
    state.phase_hermes = PhaseHermesState(
        focus_roster=[
            FocusRosterEntry(ticker="AAPL", roster_reason="held"),
            FocusRosterEntry(ticker="MSFT", roster_reason="momentum"),
        ]
    )
    return state


def test_planner_mode_from_env_defaults_to_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OLYMPUS_PLANNER_MODE_ENV, raising=False)
    assert planner_mode_from_env() == "shadow"
    monkeypatch.setenv(OLYMPUS_PLANNER_MODE_ENV, "off")
    assert planner_mode_from_env() == "off"
    monkeypatch.setenv(OLYMPUS_PLANNER_MODE_ENV, "enforce")
    assert planner_mode_from_env() == "shadow"


def test_maybe_publish_skips_without_triage() -> None:
    client = FakeSupabaseClient()
    state = AtlasResearchState(
        run_type="baseline",
        run_date=RUN,
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    assert maybe_publish_attention_plan_shadow(client=client, state=state) is None
    assert client.store.get("documents", []) == []


def test_maybe_publish_skips_when_planner_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_PLANNER_MODE_ENV, "off")
    client = FakeSupabaseClient()
    assert maybe_publish_attention_plan_shadow(client=client, state=_state_with_triage()) is None
    assert client.store.get("documents", []) == []


def test_maybe_publish_upserts_attention_plan() -> None:
    client = FakeSupabaseClient()
    artifact = maybe_publish_attention_plan_shadow(client=client, state=_state_with_triage())
    assert artifact is not None
    assert artifact.document_key == ATTENTION_PLAN_DOCUMENT_KEY
    rows = client.store["documents"]
    assert len(rows) == 1
    row = rows[0]
    assert row["document_key"] == ATTENTION_PLAN_DOCUMENT_KEY
    assert row["category"] == "planner"
    assert row["run_type"] == "baseline"
    assert row["payload"]["plan"]["h4_roster"] == ["AAPL", "MSFT"]
    assert len(row["payload"]["plan"]["decisions"]) == 2


def test_publish_phase_includes_attention_plan_when_triage_present() -> None:
    client = FakeSupabaseClient()
    state = _state_with_triage()
    result = build_publish_node(PublishDeps(client=client))(state)
    keys = {row["document_key"] for row in client.store["documents"]}
    assert ATTENTION_PLAN_DOCUMENT_KEY in keys
    assert any(a.document_key == ATTENTION_PLAN_DOCUMENT_KEY for a in result["published"])
