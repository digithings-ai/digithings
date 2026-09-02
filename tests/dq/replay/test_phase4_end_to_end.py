"""Integration 4.1 — Phase 4 governed learning/replay golden fixture (#3015).

Proves episodes → lessons → replay → comparison → gate → human decision
deterministically without production activation.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.dashboard.learning.outcome_models import (
    AttributionComponent,
    AttributionMethod,
    EpisodeDisposition,
)
from digiquant.dashboard.replay.comparison import (
    REQUIRED_METRIC_GROUPS,
    ComparisonReportStatus,
    EvidenceMode,
    MetricGroupId,
)
from digiquant.dashboard.replay.governance import CriterionOutcome
from digiquant.dashboard.replay.governance_models import (
    GovernanceDecisionKind,
    PolicyGovernanceDecision,
)
from digiquant.dashboard.replay.models import PortfolioReplayStatus
from digiquant.dashboard.replay.walk_forward import WalkForwardBuildStatus
from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

from tests.dq.conftest import SKIP_NATIVE_CRASH
from tests.dq.replay.phase4_e2e_fixtures import (
    _NUMERIC_TOLERANCE,
    phase4_replay_request,
    run_phase4_composition,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_PRODUCTION_GUARD_PATHS = (
    _REPO / "digiquant/src/digiquant/olympus/hermes/chain.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/h9_commit_run.py",
)


def test_phase4_golden_closed_loop() -> None:
    """Full Phase 4 release gates in one reproducible fixture."""
    first = run_phase4_composition(apply_correction=True)
    second = run_phase4_composition(apply_correction=True)

    # --- Accounting gate: reconciled before learning ---
    first_pass = first["first_pass"]
    assert first_pass.assembled >= 1
    authorized = [
        r.episode
        for r in first_pass.results
        if r.episode is not None and r.episode.disposition is EpisodeDisposition.AUTHORIZED
    ]
    assert authorized, "expected at least one authorized episode with accounting links"
    for episode in authorized:
        assert episode.realized is not None
        assert episode.realized.accounting_period_id is not None
        assert episode.realized.benchmark_return is not None
        assert episode.realized.instrument_return is not None

    dispositions = {r.episode.disposition for r in first_pass.results if r.episode is not None}
    assert EpisodeDisposition.EXCLUDED in dispositions
    assert EpisodeDisposition.NO_OP in dispositions
    assert EpisodeDisposition.AUTHORIZED in dispositions

    # One visible episode per logical key at early cutoff.
    early_keys = {ep.episode_key for ep in first["episodes_visible_early"]}
    assert len(early_keys) == len(first["episodes_visible_early"])

    # Correction supersedes without changing historical replay manifest.
    first_aapl = first["first_aapl"]
    correction = first["correction_episode"]
    assert first_aapl is not None
    assert correction is not None
    assert correction.supersedes_version_id == first_aapl.episode_version_id
    historical = first["store"].select_episode_as_of(
        episode_key=first_aapl.episode_key,
        as_of=first["cutoff_early"],
        knowledge_cutoff_at=first["cutoff_early"],
    )
    assert historical is not None
    assert historical.episode_version_id == first_aapl.episode_version_id
    assert historical.realized is not None
    assert historical.realized.benchmark_return == Decimal("0.018")
    assert first["manifest"].manifest_content_hash == second["manifest"].manifest_content_hash

    # Observed vs counterfactual attribution distinction.
    report = first["store"].latest_report_for_episode(first_aapl.episode_version_id)
    assert report is not None
    forecast_obs = [o for o in report.observations if o.component is AttributionComponent.FORECAST]
    assert forecast_obs
    assert all(o.method is not AttributionMethod.COUNTERFACTUAL_REPLAY for o in forecast_obs)
    sizing_obs = [o for o in report.observations if o.component is AttributionComponent.SIZING]
    if sizing_obs:
        assert all(o.method is not AttributionMethod.COUNTERFACTUAL_REPLAY for o in sizing_obs)

    # Later lesson pin excludes early-only compile at late cutoff.
    assert first["lesson_early"] is not None
    assert first["lesson_late"] is not None
    assert first["lesson_early"].lesson_version_id != first["lesson_late"].lesson_version_id
    assert first["pin_early"].status == "pinned"
    assert first["pin_late"].status == "pinned"
    assert first["pin_early"].pin is not None
    assert first["pin_late"].pin is not None
    assert first["pin_early"].pin.lesson_version_id == first["lesson_early"].lesson_version_id
    assert first["pin_late"].pin.lesson_version_id == first["lesson_late"].lesson_version_id

    # Identical arm manifest + shared-cash replay evidence (mocked deterministic results).
    pair = first["pair"]
    assert pair.shared_manifest.manifest_content_hash == first["manifest"].manifest_content_hash
    assert pair.incumbent.manifest_content_hash == pair.challenger.manifest_content_hash
    inc = first["inc_result"]
    ch = first["ch_result"]
    assert inc.status is PortfolioReplayStatus.OK
    assert ch.status is PortfolioReplayStatus.OK
    assert inc.starting_cash == ch.starting_cash
    assert len(inc.holdings) >= 2
    assert {h.ticker for h in inc.holdings} >= {"AAPL", "MSFT"}

    # Walk-forward: no train/eval leakage when folds build successfully.
    wf = first["walk_forward"]
    if wf["build"].status is WalkForwardBuildStatus.OK and wf["plan"] is not None:
        train = set(wf["plan"].train_episode_keys)
        eval_ = set(wf["plan"].eval_episode_keys)
        assert not (train & eval_)

    # All metric groups present or explicitly unavailable.
    cmp_report = first["report"]
    assert cmp_report.status is ComparisonReportStatus.COMPLETE
    present = {g.group_id for g in cmp_report.metric_groups}
    assert present == REQUIRED_METRIC_GROUPS
    tail_group = next(g for g in cmp_report.metric_groups if g.group_id is MetricGroupId.RISK)
    assert tail_group.metrics
    for group in cmp_report.metric_groups:
        for metric in group.metrics:
            if metric.availability.value == "available":
                assert metric.evidence_mode in EvidenceMode
            else:
                assert metric.unavailable_reason

    # Gate outcomes: eligible, ineligible, insufficient.
    assert first["eval_eligible"].eligible_for_human_review is True
    assert first["eval_ineligible"].eligible_for_human_review is False
    assert "accounting_breach_visible" in first["eval_ineligible"].blockers
    assert first["eval_insufficient"].eligible_for_human_review is False
    assert first["eval_insufficient"].criterion_results
    assert first["eval_insufficient"].criterion_results[0].outcome is CriterionOutcome.INSUFFICIENT

    # Human approval records only — no activation side effects.
    decision = first["decision"]
    assert decision is not None
    assert decision.decision_kind is GovernanceDecisionKind.APPROVE
    assert "activate" not in PolicyGovernanceDecision.model_fields
    # Gate persistence stores manifest/pair evidence only — never activates production.
    assert first["replay_store"].manifest_count() == 1

    # Rerun: identical hashes and tolerance-bounded numbers.
    assert first["report"].report_content_hash == second["report"].report_content_hash
    assert first["report"].report_content_hash == first["rerun_report_hash"]
    assert first["inc_result"].result_content_hash == second["inc_result"].result_content_hash
    assert first["inc_result"].result_content_hash == first["rerun_inc_hash"]
    if first["inc_result"].ending_nav is not None and second["inc_result"].ending_nav is not None:
        delta = abs(first["inc_result"].ending_nav - second["inc_result"].ending_nav)
        assert delta <= _NUMERIC_TOLERANCE


def test_phase4_composition_is_byte_stable() -> None:
    a = run_phase4_composition(apply_correction=False)
    b = run_phase4_composition(apply_correction=False)
    assert a["report"].report_content_hash == b["report"].report_content_hash
    assert a["manifest"].manifest_content_hash == b["manifest"].manifest_content_hash
    assert a["lesson_early"].content_hash == b["lesson_early"].content_hash  # type: ignore[union-attr]


@SKIP_NATIVE_CRASH
def test_phase4_shared_cash_nautilus_engine(tmp_path: Path) -> None:
    """Real one-account multi-instrument engine — skipped on Linux CI (#42)."""
    req = phase4_replay_request(request_id="phase4-nautilus")
    a = run_portfolio_replay_isolated(req, work_dir=tmp_path / "a")
    b = run_portfolio_replay_isolated(req, work_dir=tmp_path / "b")
    assert a.status is PortfolioReplayStatus.OK
    assert b.status is PortfolioReplayStatus.OK
    assert a.result_content_hash == b.result_content_hash
    assert a.ending_nav is not None and b.ending_nav is not None
    assert abs(a.ending_nav - b.ending_nav) <= _NUMERIC_TOLERANCE
    assert a.total_commission is not None and a.total_commission > 0
