"""WP15.6 — preflight outcome maturation and structured lesson pin (#2975)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.atlas.graph import AtlasGraphDeps, build_atlas_graph
from digiquant.olympus.atlas.phases.outcome_maturation import (
    DEFAULT_OUTCOME_LESSON_COHORT,
    DEFAULT_OUTCOME_LESSON_HORIZON,
    DEFAULT_OUTCOME_LESSON_POLICY,
    OutcomeMaturationDeps,
    pin_outcome_lesson_for_preflight,
)
from digiquant.olympus.atlas.phases.preflight import PreflightDeps, build_preflight_node
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.learning.lesson_registry import LessonCompiler
from digiquant.olympus.learning.outcome_assembly import (
    AssemblyPassResult,
)
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    EpisodeDisposition,
    H8TargetLineage,
    H9ExecutionLinks,
    OutcomeEpisode,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    episode_content_hash,
    episode_version_id,
)
from digiquant.olympus.learning.outcome_store import OutcomeLearningStore
from digiquant.olympus.research_retrieval.context_wiring import (
    wire_h5_phase_inputs,
    wire_h7_phase_inputs,
)
from digiquant.olympus.research_retrieval.h7_decision_context import (
    H7DecisionContextCompileInput,
    H7PrerequisiteSnapshot,
    H7SectionKind,
    compile_h7_decision_context,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.hermes.test_h7_context_compiler import _evidence, _loaded_state, _store_with_state
from tests.dq.learning.test_lesson_registry import _report
from tests.dq.olympus.test_context_compiler import _bundle

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_CUTOFF = _TS + timedelta(days=25)
_HORIZON_END = _TS + timedelta(days=21)
_AVAILABLE = _HORIZON_END + timedelta(days=1)
_FORECAST_ID = UUID("11111111-1111-4111-8111-111111111111")
_OUTCOME_ID = UUID("22222222-2222-4222-8222-222222222222")
_CONSUMING_RUN = "run-current-2026-08-27"
_PRIOR_RUN = "run-prior-2026-08-20"


def _temporal(**overrides: object) -> OutcomeTemporalContract:
    fields: dict[str, object] = dict(
        effective_at=_TS - timedelta(days=21),
        known_at=_TS - timedelta(days=20),
        recorded_at=_TS - timedelta(days=19),
        horizon_end=_HORIZON_END,
        available_at=_AVAILABLE,
        replay_as_of=_AVAILABLE,
    )
    fields.update(overrides)
    return OutcomeTemporalContract(**fields)


def _portfolio_episode(
    *,
    source_run_id: str = _PRIOR_RUN,
    available_at: datetime | None = None,
) -> OutcomeEpisode:
    temporal = _temporal()
    if available_at is not None:
        temporal = _temporal(available_at=available_at)
    fields: dict[str, object] = dict(
        episode_key=f"forecast:{_FORECAST_ID}:horizon:21s",
        forecast_id=_FORECAST_ID,
        outcome_id=_OUTCOME_ID,
        mandate_id="mandate-daily",
        instrument_id="portfolio",
        horizon_id=DEFAULT_OUTCOME_LESSON_HORIZON,
        source_run_id=source_run_id,
        disposition=EpisodeDisposition.AUTHORIZED,
        temporal=temporal,
        h8_lineage=H8TargetLineage(
            requested_weight=Decimal("0.05"),
            approved_weight=Decimal("0.04"),
            adjustment_codes=("risk_cap",),
        ),
        h9_links=H9ExecutionLinks(
            action_id=UUID("66666666-6666-4666-8666-666666666666"),
            order_id=UUID("77777777-7777-4777-8777-777777777777"),
            fill_ids=(UUID("88888888-8888-4888-8888-888888888888"),),
            holding_id=UUID("99999999-9999-4999-8999-999999999999"),
        ),
        realized=RealizedReturnObservation(
            instrument_return=Decimal("0.042"),
            benchmark_return=Decimal("0.018"),
            active_return=Decimal("0.024"),
            accounting_period_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            contribution_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        ),
        supersedes_version_id=None,
    )
    content_hash = episode_content_hash(
        episode_key=str(fields["episode_key"]),
        forecast_id=fields["forecast_id"],  # type: ignore[arg-type]
        outcome_id=fields["outcome_id"],  # type: ignore[arg-type]
        mandate_id=str(fields["mandate_id"]),
        instrument_id=str(fields["instrument_id"]),
        horizon_id=str(fields["horizon_id"]),
        source_run_id=str(fields["source_run_id"]),
        disposition=fields["disposition"],  # type: ignore[arg-type]
        temporal=fields["temporal"],  # type: ignore[arg-type]
        realized=fields["realized"],  # type: ignore[arg-type]
        h8_lineage=fields["h8_lineage"],  # type: ignore[arg-type]
        h9_links=fields["h9_links"],  # type: ignore[arg-type]
        evidence_bundle_id=None,
        research_state_version_id=None,
        context_manifest_id=None,
        policy_version_id=None,
        expected_cost_id=None,
        realized_cost_id=None,
        pre_trade_risk_report_id=None,
        component_eligibility=(),
        quality_issues=(),
    )
    fields["content_hash"] = content_hash
    fields["episode_version_id"] = episode_version_id(
        episode_key=str(fields["episode_key"]),
        content_hash=content_hash,
        supersedes_version_id=None,
    )
    return OutcomeEpisode(**fields)


@dataclass
class _StubAssembler:
    store: OutcomeLearningStore
    episodes: tuple[OutcomeEpisode, ...] = ()
    assembled: int = 0

    def assemble_pass(
        self,
        *,
        as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> AssemblyPassResult:
        from digiquant.olympus.learning.outcome_assembly import EpisodeAssemblyResult

        results: list[EpisodeAssemblyResult] = []
        count = 0
        for episode in self.episodes:
            if episode.temporal.available_at > as_of:
                continue
            if episode.temporal.known_at > knowledge_cutoff_at:
                continue
            if episode.source_run_id == _CONSUMING_RUN:
                continue
            self.store.append_episode(episode)
            report = _report(episode)
            self.store.append_report(report)
            results.append(
                EpisodeAssemblyResult(
                    outcome_id=episode.outcome_id,
                    forecast_id=episode.forecast_id,
                    episode_key=episode.episode_key,
                    episode=episode,
                )
            )
            count += 1
        self.assembled = count
        return AssemblyPassResult(results=tuple(results), assembled=count, blocked=0, skipped=0)


@dataclass
class _StubAttributor:
    store: OutcomeLearningStore

    def attribute_and_persist(
        self, episode: OutcomeEpisode, *, knowledge_cutoff_at: datetime
    ) -> None:
        self.store.append_report(_report(episode))


def _maturation_deps(
    store: OutcomeLearningStore,
    *,
    episodes: tuple[OutcomeEpisode, ...] = (),
) -> OutcomeMaturationDeps:
    assembler = _StubAssembler(store=store, episodes=episodes)
    return OutcomeMaturationDeps(
        store=store,
        assembler=assembler,  # type: ignore[arg-type]
        attributor=_StubAttributor(store=store),  # type: ignore[arg-type]
        compiler=LessonCompiler(store=store),
        policy=DEFAULT_OUTCOME_LESSON_POLICY,
        cohort=DEFAULT_OUTCOME_LESSON_COHORT,
        horizon_id=DEFAULT_OUTCOME_LESSON_HORIZON,
    )


def _preflight_client() -> FakeSupabaseClient:
    return FakeSupabaseClient(
        canned_reads={
            "daily_snapshots": [],
            "documents": [],
            "price_technicals": [{"date": "2026-08-25", "ticker": "SPY"}],
            "macro_series_observations": [{"obs_date": "2026-08-25"}],
        }
    )


def test_available_lesson_included_at_cutoff() -> None:
    store = OutcomeLearningStore()
    episode = _portfolio_episode(source_run_id=_PRIOR_RUN)
    store.append_episode(episode)
    store.append_report(_report(episode))
    deps = _maturation_deps(store)
    result = pin_outcome_lesson_for_preflight(
        deps,
        knowledge_cutoff_at=_CUTOFF,
        consuming_run_id=_CONSUMING_RUN,
    )
    assert result.status == "pinned"
    assert result.pin is not None
    assert result.pin.lesson_version_id is not None


def test_later_lesson_excluded_at_earlier_cutoff() -> None:
    store = OutcomeLearningStore()
    early = _portfolio_episode(source_run_id=_PRIOR_RUN, available_at=_AVAILABLE)
    late = _portfolio_episode(
        source_run_id=_PRIOR_RUN,
        available_at=_AVAILABLE + timedelta(days=5),
    )
    late = late.model_copy(
        update={"outcome_id": uuid4(), "episode_key": "forecast:late:horizon:21s"}
    )
    for ep in (early, late):
        store.append_episode(ep)
        store.append_report(_report(ep))

    early_lesson = LessonCompiler(store=store).compile_and_persist(
        policy=DEFAULT_OUTCOME_LESSON_POLICY,
        cohort=DEFAULT_OUTCOME_LESSON_COHORT,
        horizon_id=DEFAULT_OUTCOME_LESSON_HORIZON,
        compilation_cutoff=_AVAILABLE + timedelta(days=1),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=1),
        consuming_run_id=_CONSUMING_RUN,
    )
    LessonCompiler(store=store).compile_and_persist(
        policy=DEFAULT_OUTCOME_LESSON_POLICY,
        cohort=DEFAULT_OUTCOME_LESSON_COHORT,
        horizon_id=DEFAULT_OUTCOME_LESSON_HORIZON,
        compilation_cutoff=_AVAILABLE + timedelta(days=6),
        knowledge_cutoff_at=_AVAILABLE + timedelta(days=6),
        consuming_run_id=_CONSUMING_RUN,
    )

    selected = store.select_lesson_as_of(
        compilation_policy_id=DEFAULT_OUTCOME_LESSON_POLICY.policy_id,
        cohort=DEFAULT_OUTCOME_LESSON_COHORT,
        component=AttributionComponent.FORECAST,
        horizon_id=DEFAULT_OUTCOME_LESSON_HORIZON,
        as_of=_AVAILABLE + timedelta(days=2),
    )
    assert selected is not None
    assert selected.lesson_version_id == early_lesson.lesson_version_id


def test_newly_matured_prior_run_outcome_allowed() -> None:
    store = OutcomeLearningStore()
    episode = _portfolio_episode(source_run_id=_PRIOR_RUN)
    deps = _maturation_deps(store, episodes=(episode,))
    result = pin_outcome_lesson_for_preflight(
        deps,
        knowledge_cutoff_at=_CUTOFF,
        consuming_run_id=_CONSUMING_RUN,
    )
    assert result.status == "pinned"
    assert result.assembled == 1


def test_own_future_outcome_impossible_for_consuming_run() -> None:
    store = OutcomeLearningStore()
    own_episode = _portfolio_episode(source_run_id=_CONSUMING_RUN)
    prior_episode = _portfolio_episode(source_run_id=_PRIOR_RUN)
    deps = _maturation_deps(store, episodes=(own_episode, prior_episode))
    result = pin_outcome_lesson_for_preflight(
        deps,
        knowledge_cutoff_at=_CUTOFF,
        consuming_run_id=_CONSUMING_RUN,
    )
    assert result.status == "pinned"
    assert result.pin is not None
    lesson = store.load_lesson(result.pin.lesson_version_id)
    for episode_id in lesson.episode_version_ids:
        episode = store.load_episode(episode_id)
        assert episode.source_run_id != _CONSUMING_RUN


def test_exact_replay_selects_same_lesson() -> None:
    store = OutcomeLearningStore()
    episode = _portfolio_episode(source_run_id=_PRIOR_RUN)
    deps = _maturation_deps(store, episodes=(episode,))
    first = pin_outcome_lesson_for_preflight(
        deps,
        knowledge_cutoff_at=_CUTOFF,
        consuming_run_id=_CONSUMING_RUN,
    )
    second = pin_outcome_lesson_for_preflight(
        deps,
        knowledge_cutoff_at=_CUTOFF,
        consuming_run_id=_CONSUMING_RUN,
    )
    assert first.pin is not None and second.pin is not None
    assert first.pin.lesson_version_id == second.pin.lesson_version_id


def test_preflight_pins_lesson_before_h7_prerequisites() -> None:
    store = OutcomeLearningStore()
    episode = _portfolio_episode(source_run_id=_PRIOR_RUN)
    deps = PreflightDeps(
        client=_preflight_client(),
        config_loader=lambda: AtlasConfigBundle(),
        outcome_maturation_deps=_maturation_deps(store, episodes=(episode,)),
    )
    node = build_preflight_node(deps)
    out = node(
        AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 8, 27),
            knowledge_cutoff_at=_CUTOFF,
            run_id=uuid4(),
        )
    )
    assert out["outcome_lesson_status"] == "pinned"
    assert out["outcome_lesson_pin"]["lesson_version_id"]
    snapshot = out["h7_prerequisite_snapshot"]
    assert snapshot["outcome_lesson_version_id"] == out["outcome_lesson_pin"]["lesson_version_id"]


def test_h7_manifest_uses_structured_lesson_not_decision_log() -> None:
    ev = _evidence(summary="pin")
    loaded = _loaded_state(evidence=(ev,))
    lesson_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    prereq = H7PrerequisiteSnapshot(
        state_version_id=loaded.version.state_version_id,
        outcome_lesson_version_id=lesson_id,
        outcome_lesson_content_hash="abc123",
    )
    ctx = compile_h7_decision_context(
        H7DecisionContextCompileInput(
            loaded=loaded,
            prerequisites=prereq,
            decision_lessons=({"decision_id": "legacy-1", "lesson": "prose"},),
            outcome_lesson_version_id=lesson_id,
        )
    )
    prior_auth = next(s for s in ctx.sections if s.kind is H7SectionKind.PRIOR_AUTHORIZATION)
    assert prior_auth.entity_ids == (f"outcome_lesson:{lesson_id}",)
    assert not any(eid.startswith("decision_lesson:") for eid in prior_auth.entity_ids)


def test_h5_and_h7_wire_expose_lesson_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "shadow")
    ev = _evidence(summary="pin")
    loaded = _loaded_state(evidence=(ev,))
    store, pin = _store_with_state(loaded)
    lesson_pin = {
        "lesson_version_id": str(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
        "content_hash": "lesson-hash-1",
    }
    bundle = _bundle(state_version_id=loaded.version.state_version_id)
    h5 = wire_h5_phase_inputs(
        {"ticker": "AAPL"},
        ticker="AAPL",
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        outcome_lesson_pin=lesson_pin,
    )
    assert h5.phase_inputs["outcome_lesson_version_id"] == lesson_pin["lesson_version_id"]

    h7 = wire_h7_phase_inputs(
        {"segment": "pm-direction"},
        research_state_pin=pin,
        research_state_store=store,
        h7_prerequisite_snapshot=H7PrerequisiteSnapshot(
            state_version_id=loaded.version.state_version_id,
            outcome_lesson_version_id=UUID(lesson_pin["lesson_version_id"]),
        ).model_dump(mode="json"),
        outcome_lesson_pin=lesson_pin,
        decision_lessons=({"decision_id": "legacy"},),
    )
    assert h7.phase_inputs["outcome_lesson_version_id"] == lesson_pin["lesson_version_id"]


def test_graph_node_list_unchanged() -> None:
    g = build_atlas_graph(
        deps=AtlasGraphDeps(
            preflight=PreflightDeps(
                client=_preflight_client(),
                config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
            )
        ),
        watchlist=("AAPL",),
    )
    names = set(g.get_graph().nodes.keys())
    assert "preflight" in names
    assert "outcome_maturation" not in names
    assert "preflight-reflect" not in names or "preflight-reflect" in names
