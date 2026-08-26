"""WP15.1 — strict outcome-learning contracts (#2954).

Red coverage: frozen/extra-forbid, UTC temporal contract, missing core refs,
excluded/no-op without fabricated targets/fills, unavailable attribution needs
reason, causal sizing/timing needs replay artifact, all canonical dispositions
and attribution methods validate without raw dicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.olympus.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    ComponentAttributionReport,
    ComponentEligibility,
    ComponentObservation,
    EpisodeDisposition,
    EvidenceQuality,
    H8TargetLineage,
    H9ExecutionLinks,
    LessonQualityState,
    OutcomeEpisode,
    OutcomeLessonVersion,
    OutcomeQualityCode,
    OutcomeQualityIssue,
    OutcomeTemporalContract,
    RealizedReturnObservation,
    UnavailableReason,
    episode_content_hash,
    episode_version_id,
    lesson_content_hash,
    lesson_version_id,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_HORIZON_END = _TS + timedelta(days=21)
_AVAILABLE = _TS + timedelta(days=22)


def _temporal(**overrides: object) -> OutcomeTemporalContract:
    fields: dict[str, object] = dict(
        effective_at=_TS - timedelta(days=21),
        known_at=_TS - timedelta(days=20),
        recorded_at=_TS,
        horizon_end=_HORIZON_END,
        available_at=_AVAILABLE,
        replay_as_of=_AVAILABLE,
    )
    fields.update(overrides)
    return OutcomeTemporalContract(**fields)


def _realized(**overrides: object) -> RealizedReturnObservation:
    fields: dict[str, object] = dict(
        instrument_return=Decimal("0.042"),
        benchmark_return=Decimal("0.018"),
        active_return=Decimal("0.024"),
        accounting_period_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        contribution_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    fields.update(overrides)
    return RealizedReturnObservation(**fields)


def _episode(**overrides: object) -> OutcomeEpisode:
    forecast_id = UUID("11111111-1111-4111-8111-111111111111")
    outcome_id = UUID("22222222-2222-4222-8222-222222222222")
    fields: dict[str, object] = dict(
        episode_key=f"forecast:{forecast_id}:horizon:21",
        forecast_id=forecast_id,
        outcome_id=outcome_id,
        mandate_id="mandate-daily",
        instrument_id="AAPL",
        horizon_id="h-21s",
        source_run_id="run-2026-08-26",
        evidence_bundle_id=UUID("33333333-3333-4333-8333-333333333333"),
        research_state_version_id=UUID("44444444-4444-4444-8444-444444444444"),
        context_manifest_id=UUID("55555555-5555-4555-8555-555555555555"),
        policy_version_id="policy-v1",
        disposition=EpisodeDisposition.AUTHORIZED,
        temporal=_temporal(),
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
        realized=_realized(),
        expected_cost_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        realized_cost_id=UUID("bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"),
        pre_trade_risk_report_id=UUID("cccccccc-dddd-4eee-8fff-000000000000"),
        component_eligibility=(
            ComponentEligibility(component=AttributionComponent.FORECAST, eligible=True),
            ComponentEligibility(component=AttributionComponent.EXECUTION, eligible=True),
            ComponentEligibility(
                component=AttributionComponent.SIZING,
                eligible=False,
                unavailable_reason=UnavailableReason.MISSING_REPLAY_ARTIFACT,
            ),
        ),
        quality_issues=(),
        supersedes_version_id=None,
    )
    fields.update(overrides)
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
        realized=fields.get("realized"),  # type: ignore[arg-type]
        h8_lineage=fields.get("h8_lineage"),  # type: ignore[arg-type]
        h9_links=fields.get("h9_links"),  # type: ignore[arg-type]
        evidence_bundle_id=fields.get("evidence_bundle_id"),  # type: ignore[arg-type]
        research_state_version_id=fields.get("research_state_version_id"),  # type: ignore[arg-type]
        context_manifest_id=fields.get("context_manifest_id"),  # type: ignore[arg-type]
        policy_version_id=fields.get("policy_version_id"),  # type: ignore[arg-type]
        expected_cost_id=fields.get("expected_cost_id"),  # type: ignore[arg-type]
        realized_cost_id=fields.get("realized_cost_id"),  # type: ignore[arg-type]
        pre_trade_risk_report_id=fields.get("pre_trade_risk_report_id"),  # type: ignore[arg-type]
        component_eligibility=tuple(fields.get("component_eligibility", ())),  # type: ignore[arg-type]
        quality_issues=tuple(fields.get("quality_issues", ())),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "episode_version_id",
        episode_version_id(
            episode_key=str(fields["episode_key"]),
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return OutcomeEpisode(**fields)


def _observation(**overrides: object) -> ComponentObservation:
    fields: dict[str, object] = dict(
        component=AttributionComponent.FORECAST,
        metric="forecast_error_bps",
        value=Decimal("-12.5"),
        unit="bps",
        uncertainty=Decimal("3.0"),
        baseline="point_forecast",
        interval_start=_TS - timedelta(days=21),
        interval_end=_HORIZON_END,
        artifact_ids=(UUID("11111111-1111-4111-8111-111111111111"),),
        evidence_quality=EvidenceQuality.OBSERVED,
        method=AttributionMethod.OBSERVED,
    )
    fields.update(overrides)
    return ComponentObservation(**fields)


# ── Strict / frozen ───────────────────────────────────────────────────────────


def test_models_are_frozen_and_forbid_extra_fields() -> None:
    ep = _episode()
    with pytest.raises(ValidationError, match="extra"):
        OutcomeEpisode.model_validate({**ep.model_dump(), "rogue": True})
    with pytest.raises(ValidationError, match="frozen"):
        ep.disposition = EpisodeDisposition.EXCLUDED  # type: ignore[misc]


def test_temporal_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _temporal(effective_at=datetime(2026, 8, 1))  # noqa: DTZ001


def test_temporal_requires_available_at_gte_horizon_end() -> None:
    with pytest.raises(ValidationError, match="available_at"):
        _temporal(available_at=_HORIZON_END - timedelta(hours=1))


def test_temporal_requires_known_at_lte_available_at() -> None:
    with pytest.raises(ValidationError, match="known_at"):
        _temporal(known_at=_AVAILABLE + timedelta(hours=1))


def test_episode_rejects_missing_core_refs() -> None:
    base = _episode().model_dump()
    for field in (
        "episode_key",
        "forecast_id",
        "outcome_id",
        "mandate_id",
        "instrument_id",
        "horizon_id",
        "source_run_id",
    ):
        payload = {**base, field: "" if field == "episode_key" else None}
        with pytest.raises(ValidationError):
            OutcomeEpisode.model_validate(payload)


# ── Dispositions ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "disposition",
    [
        EpisodeDisposition.AUTHORIZED,
        EpisodeDisposition.EXCLUDED,
        EpisodeDisposition.REJECTED,
        EpisodeDisposition.NO_OP,
    ],
)
def test_all_canonical_dispositions_validate(disposition: EpisodeDisposition) -> None:
    overrides: dict[str, object] = {"disposition": disposition}
    if disposition in (EpisodeDisposition.EXCLUDED, EpisodeDisposition.NO_OP):
        overrides["h8_lineage"] = None
        overrides["h9_links"] = None
        overrides["realized"] = None
    elif disposition == EpisodeDisposition.REJECTED:
        overrides["h9_links"] = None
        overrides["realized"] = None
    ep = _episode(**overrides)
    assert ep.disposition is disposition


def test_excluded_episode_allows_missing_h9_without_fabricated_fill() -> None:
    ep = _episode(
        disposition=EpisodeDisposition.EXCLUDED,
        h8_lineage=None,
        h9_links=None,
        realized=None,
    )
    assert ep.h9_links is None
    assert ep.realized is None


def test_no_op_episode_rejects_fabricated_h9_links() -> None:
    with pytest.raises(ValidationError, match="h9_links"):
        _episode(
            disposition=EpisodeDisposition.NO_OP,
            h8_lineage=None,
            h9_links=H9ExecutionLinks(action_id=UUID("66666666-6666-4666-8666-666666666666")),
            realized=None,
        )


def test_authorized_episode_requires_h9_links() -> None:
    with pytest.raises(ValidationError, match="h9_links"):
        _episode(disposition=EpisodeDisposition.AUTHORIZED, h9_links=None)


# ── Attribution methods ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method",
    [
        AttributionMethod.OBSERVED,
        AttributionMethod.MODEL_ESTIMATE,
        AttributionMethod.COUNTERFACTUAL_REPLAY,
        AttributionMethod.UNAVAILABLE,
    ],
)
def test_all_attribution_methods_validate(method: AttributionMethod) -> None:
    overrides: dict[str, object] = {"method": method}
    if method == AttributionMethod.UNAVAILABLE:
        overrides["value"] = None
        overrides["uncertainty"] = None
        overrides["unavailable_reason"] = UnavailableReason.MISSING_FILL_DATA
    elif method == AttributionMethod.COUNTERFACTUAL_REPLAY:
        overrides["component"] = AttributionComponent.SIZING
        overrides["metric"] = "sizing_pnl_usd"
        overrides["replay_artifact_id"] = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    report = ComponentAttributionReport(
        report_id=UUID("dddddddd-eeee-4fff-8000-111111111111"),
        episode_version_id=_episode().episode_version_id,
        observations=(_observation(**overrides),),
    )
    assert report.observations[0].method is method


def test_unavailable_observation_requires_reason() -> None:
    with pytest.raises(ValidationError, match="unavailable_reason"):
        _observation(
            method=AttributionMethod.UNAVAILABLE,
            value=None,
            uncertainty=None,
        )


def test_counterfactual_replay_requires_replay_artifact() -> None:
    with pytest.raises(ValidationError, match="replay_artifact_id"):
        _observation(
            component=AttributionComponent.SIZING,
            metric="sizing_pnl_usd",
            method=AttributionMethod.COUNTERFACTUAL_REPLAY,
        )


def test_causal_sizing_timing_observed_rejected_without_replay() -> None:
    with pytest.raises(ValidationError, match="counterfactual_replay"):
        _observation(
            component=AttributionComponent.TIMING,
            metric="timing_pnl_usd",
            method=AttributionMethod.OBSERVED,
            value=Decimal("100"),
        )


def test_episode_rejects_mismatched_content_hash() -> None:
    ep = _episode()
    with pytest.raises(ValidationError, match="content_hash"):
        OutcomeEpisode.model_validate({**ep.model_dump(), "content_hash": "f" * 64})


def test_authorized_episode_requires_realized() -> None:
    with pytest.raises(ValidationError, match="realized"):
        _episode(
            disposition=EpisodeDisposition.AUTHORIZED,
            realized=None,
        )


def test_timing_diagnostics_observed_allowed() -> None:
    obs = _observation(
        component=AttributionComponent.TIMING,
        metric="timing_latency_ms",
        method=AttributionMethod.OBSERVED,
        value=Decimal("250"),
        unit="ms",
    )
    assert obs.metric == "timing_latency_ms"


# ── Lessons ───────────────────────────────────────────────────────────────────


def _lesson(**overrides: object) -> OutcomeLessonVersion:
    ep = _episode()
    fields: dict[str, object] = dict(
        compilation_policy_id="lesson-policy-v1",
        compilation_cutoff=_AVAILABLE,
        episode_version_ids=(ep.episode_version_id,),
        report_ids=(UUID("eeeeeeee-ffff-4000-8000-222222222222"),),
        cohort="large_cap_us",
        regime="risk_on",
        horizon_id="h-21s",
        component=AttributionComponent.FORECAST,
        sample_count=42,
        effective_sample_count=38,
        estimate=Decimal("-8.5"),
        uncertainty=Decimal("2.1"),
        prior=Decimal("-10.0"),
        shrinkage=Decimal("0.15"),
        quality_state=LessonQualityState.ADEQUATE,
        recommendation_code="forecast_bias_negative",
        warning_codes=(),
        available_at=_AVAILABLE + timedelta(hours=1),
        supersedes_version_id=None,
    )
    fields.update(overrides)
    content_hash = lesson_content_hash(
        compilation_policy_id=str(fields["compilation_policy_id"]),
        compilation_cutoff=fields["compilation_cutoff"],  # type: ignore[arg-type]
        episode_version_ids=tuple(fields["episode_version_ids"]),  # type: ignore[arg-type]
        report_ids=tuple(fields["report_ids"]),  # type: ignore[arg-type]
        component=fields["component"],  # type: ignore[arg-type]
        estimate=fields["estimate"],  # type: ignore[arg-type]
        uncertainty=fields["uncertainty"],  # type: ignore[arg-type]
        sample_count=int(fields["sample_count"]),  # type: ignore[arg-type]
        effective_sample_count=int(fields["effective_sample_count"]),  # type: ignore[arg-type]
        quality_state=fields["quality_state"],  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "lesson_version_id",
        lesson_version_id(
            compilation_policy_id=str(fields["compilation_policy_id"]),
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return OutcomeLessonVersion(**fields)


def test_lesson_version_is_frozen_with_required_refs() -> None:
    lesson = _lesson()
    assert lesson.sample_count >= lesson.effective_sample_count
    with pytest.raises(ValidationError, match="episode_version_ids"):
        _lesson(episode_version_ids=())


def test_episode_content_hash_stable() -> None:
    ep = _episode()
    assert ep.content_hash == episode_content_hash(
        episode_key=ep.episode_key,
        forecast_id=ep.forecast_id,
        outcome_id=ep.outcome_id,
        mandate_id=ep.mandate_id,
        instrument_id=ep.instrument_id,
        horizon_id=ep.horizon_id,
        source_run_id=ep.source_run_id,
        disposition=ep.disposition,
        temporal=ep.temporal,
        realized=ep.realized,
        h8_lineage=ep.h8_lineage,
        h9_links=ep.h9_links,
        evidence_bundle_id=ep.evidence_bundle_id,
        research_state_version_id=ep.research_state_version_id,
        context_manifest_id=ep.context_manifest_id,
        policy_version_id=ep.policy_version_id,
        expected_cost_id=ep.expected_cost_id,
        realized_cost_id=ep.realized_cost_id,
        pre_trade_risk_report_id=ep.pre_trade_risk_report_id,
        component_eligibility=ep.component_eligibility,
        quality_issues=ep.quality_issues,
    )
    assert len(ep.content_hash) == 64


def test_quality_issue_requires_non_empty_message() -> None:
    with pytest.raises(ValidationError):
        OutcomeQualityIssue(code=OutcomeQualityCode.MISSING_BENCHMARK, message="")


def test_component_eligibility_unavailable_needs_reason() -> None:
    with pytest.raises(ValidationError, match="unavailable_reason"):
        ComponentEligibility(
            component=AttributionComponent.RESIDUAL,
            eligible=False,
        )
