"""WP13.3 — Atlas research attention planner wiring (#2926)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from digiquant.olympus.atlas.phases._node_factory import SegmentNodeSpec, build_segment_node
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps, build_triage_node
from digiquant.olympus.atlas.research_attention import (
    OLYMPUS_RESEARCH_ATTENTION_MODE_ENV,
    apply_segment_metric_patch,
    artifact_target_key,
    attention_store_for_run,
    plan_atlas_research_attention,
    reset_attention_stores,
    triage_phase_attention_update,
)
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    DeltaTriageResult,
    PriorContext,
    SegmentPayload,
)
from digiquant.olympus.edit_mode.models import PriorPublished
from digiquant.olympus.research_retrieval.planner import AttentionMode, AttentionRolloutMode
from pydantic import BaseModel

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN = date(2026, 8, 26)
PRIOR = date(2026, 8, 25)


class _BondsSegment(BaseModel):
    segment: str = "bonds"
    date: str = PRIOR.isoformat()
    bias: str = "neutral"
    notes: str = "prior body"


def _prior_bonds_row() -> dict[str, Any]:
    return {
        "date": PRIOR.isoformat(),
        "payload": _BondsSegment().model_dump(mode="json"),
    }


def _state_with_triage(*, price_deltas: dict[str, float] | None = None) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN,
        baseline_date=PRIOR,
        config=AtlasConfigBundle(watchlist=["TLT"]),
        prior_context=PriorContext(latest_segments={"bonds": _prior_bonds_row()}),
        price_deltas=price_deltas or {},
    )
    state.triage = DeltaTriageResult(
        evaluated_at=RUN,
        baseline_date=PRIOR,
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
    return state


def _bonds_spec() -> SegmentNodeSpec:
    return SegmentNodeSpec(
        segment_slug="bonds",
        skill_slug="bonds",
        output_model=_BondsSegment,
        phase_outputs_field="phase4_outputs",
    )


@pytest.fixture(autouse=True)
def _clean_attention_stores() -> None:
    reset_attention_stores()
    yield
    reset_attention_stores()


def test_triage_builds_plan_before_segment_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    node = build_triage_node(TriageDeps(client=FakeSupabaseClient()))
    update = node(_state_with_triage())
    assert update.get("research_attention_plan") is not None
    from digiquant.olympus.research_retrieval.planner import AttentionPlan

    plan = AttentionPlan.model_validate(update["research_attention_plan"])
    assert plan.rollout_mode is AttentionRolloutMode.SHADOW


def test_plan_persists_decisions_to_attention_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    state = _state_with_triage(price_deltas={"TLT": 0.01})
    plan = plan_atlas_research_attention(state)
    assert plan is not None
    from digiquant.olympus.atlas.research_attention import persist_research_attention_plan

    persist_research_attention_plan(state=state, plan=plan)
    store = attention_store_for_run(str(state.run_id))
    persisted = store.load_plan(plan.plan_id)
    assert persisted.plan == plan
    assert store.decision_count_for_plan(plan.plan_id) == len(plan.decisions)
    bonds = next(
        d for d in plan.decisions if d.target_key == artifact_target_key("segment", "bonds")
    )
    assert bonds.mode is AttentionMode.METRIC_PATCH


def _apply_attention_plan(state: AtlasResearchState) -> AtlasResearchState:
    return state.model_copy(update=triage_phase_attention_update(state))


def test_enforce_metric_patch_skips_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "enforce")
    state = _apply_attention_plan(_state_with_triage(price_deltas={"TLT": 0.012}))

    grounding_calls: list[str] = []
    agent_calls: list[str] = []

    def _fake_grounding(**kwargs: Any) -> tuple[None, None, None]:
        grounding_calls.append(kwargs.get("segment", ""))
        return None, None, None

    def _fake_agent(**kwargs: Any) -> _BondsSegment:
        agent_calls.append(kwargs.get("phase_slug", ""))
        return _BondsSegment(date=RUN.isoformat())

    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.build_grounding",
        _fake_grounding,
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
        _fake_agent,
    )

    node = build_segment_node(_bonds_spec())
    update = node(state)
    slot = update["phase4_outputs"]["bonds"]
    assert isinstance(slot.payload, SegmentPayload)
    assert slot.payload.body.get("metric_patch") is True
    assert slot.payload.body.get("structured_price_deltas") == {"TLT": 0.012}
    assert grounding_calls == []
    assert agent_calls == []


def test_shadow_preserves_incumbent_provider_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "shadow")
    state = _apply_attention_plan(_state_with_triage())

    agent_calls: list[str] = []

    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.build_grounding",
        lambda **_: (None, None, None),
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
        lambda **_: agent_calls.append("called") or _BondsSegment(date=RUN.isoformat()),
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.load_skill",
        lambda _slug: "skill",
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory._resolve_segment_edit_mode",
        lambda _state, _segment: "full",
    )

    node = build_segment_node(_bonds_spec())
    node(state)
    assert agent_calls == ["called"]


def test_metric_patch_recompiles_structured_view() -> None:
    state = _state_with_triage(price_deltas={"TLT": -0.004})
    prior = PriorPublished(
        date=PRIOR,
        document_key="bonds",
        payload=_BondsSegment().model_dump(mode="json"),
    )
    slot = apply_segment_metric_patch(state, "bonds", prior)
    assert isinstance(slot.payload, SegmentPayload)
    body = slot.payload.body
    assert body["metric_patch"] is True
    assert body["structured_price_deltas"] == {"TLT": -0.004}
    assert body["date"] == RUN.isoformat()


def test_enforce_carry_skips_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "enforce")
    state = _apply_attention_plan(_state_with_triage(price_deltas={}))

    agent_calls: list[str] = []

    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.build_grounding",
        lambda **_: (None, None, None),
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
        lambda **_: agent_calls.append("called") or _BondsSegment(date=RUN.isoformat()),
    )

    node = build_segment_node(_bonds_spec())
    update = node(state)
    slot = update["phase4_outputs"]["bonds"]
    assert isinstance(slot.payload, Carried)
    assert agent_calls == []


def test_off_mode_skips_plan_and_allows_incumbent_without_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OLYMPUS_RESEARCH_ATTENTION_MODE_ENV, "off")
    state = _state_with_triage()
    assert plan_atlas_research_attention(state) is None
    triage_update = build_triage_node(None)(state)
    assert triage_update.get("research_attention_plan") is None

    agent_calls: list[str] = []
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.build_grounding",
        lambda **_: (None, None, None),
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
        lambda **_: agent_calls.append("called") or _BondsSegment(date=RUN.isoformat()),
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory.load_skill",
        lambda _slug: "skill",
    )
    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases._node_factory._resolve_segment_edit_mode",
        lambda _state, _segment: "full",
    )

    node = build_segment_node(_bonds_spec())
    node(state)
    assert agent_calls == ["called"]
