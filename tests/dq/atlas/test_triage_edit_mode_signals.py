"""Triage → TriageSignal mapping and resolve_edit_mode integration (Olympus #930 slice A1)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.edit_mode import PriorLoader, PriorPublished, TriageSignal, resolve_edit_mode
from digiquant.olympus.atlas.phases.triage_phase import build_triage_node
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
    DeltaTriageDecision,
    PriorContext,
)
from digiquant.olympus.atlas.triage import evaluate, triage_decision_to_signal
from tests.dq.atlas.test_triage_monthly_phase9 import _delta_state, _quiet_bias_for_all_segments


class _SegmentPriorLoader(PriorLoader):
    """Prior loader keyed by segment slug for triage integration tests."""

    def __init__(self, priors: dict[str, PriorPublished]) -> None:
        self._priors = priors

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        del run_date
        _namespace, slug = artifact_key
        return self._priors.get(slug)


def _macro_prior(*, prior_date: date) -> PriorPublished:
    return PriorPublished(
        date=prior_date,
        document_key="macro",
        payload={"segment": "macro", "bias": "neutral"},
    )


@pytest.mark.unit
class TestTriageDecisionToSignal:
    def test_carry_maps_to_quiet(self) -> None:
        decision = DeltaTriageDecision(
            segment="bonds",
            decision="carry",
            reason="price_quiet",
            tier="high",
        )
        assert triage_decision_to_signal(decision) == TriageSignal(mode="quiet")

    def test_regenerate_maps_to_stale(self) -> None:
        decision = DeltaTriageDecision(
            segment="macro",
            decision="regenerate",
            reason="mandatory_tier",
            tier="mandatory",
        )
        assert triage_decision_to_signal(decision) == TriageSignal(mode="stale")


@pytest.mark.unit
class TestTriageResolvesEditMode:
    def test_quiet_carry_with_prior_resolves_skip(self) -> None:
        run_date = date(2026, 4, 27)
        prior_date = date(2026, 4, 26)
        state = _delta_state(
            run_date,
            prior_date,
            bias_by_segment=_quiet_bias_for_all_segments(),
            price_deltas={"TLT": 0.001, "IEF": 0.001, "SHY": 0.001},
        )
        bonds = next(d for d in evaluate(state).decisions if d.segment == "bonds")
        assert bonds.decision == "carry"

        mode = resolve_edit_mode(
            artifact_key=("segment", "bonds"),
            run_date=run_date,
            prior_loader=_SegmentPriorLoader(
                {"bonds": PriorPublished(date=prior_date, document_key="bonds", payload={})}
            ),
            triage=triage_decision_to_signal(bonds),
        )
        assert mode == "skip"

    def test_stale_regenerate_with_prior_resolves_edit(self) -> None:
        run_date = date(2026, 4, 27)
        prior_date = date(2026, 4, 26)
        state = _delta_state(run_date, prior_date)
        macro = next(d for d in evaluate(state).decisions if d.segment == "macro")
        assert macro.decision == "regenerate"

        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=run_date,
            prior_loader=_SegmentPriorLoader({"macro": _macro_prior(prior_date=prior_date)}),
            triage=triage_decision_to_signal(macro),
        )
        assert mode == "edit"


@pytest.mark.unit
class TestTriageAlwaysOn:
    def test_baseline_run_evaluates_decisions(self) -> None:
        state = AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            data_layer=DataLayerSnapshot(
                price_technicals_latest=date(2026, 4, 25),
                price_technicals_ticker_count=56,
                macro_series_latest=date(2026, 4, 25),
                fallback_used="supabase",
            ),
            prior_context=PriorContext(
                last_snapshots=[
                    {
                        "date": "2026-04-25",
                        "run_type": "delta",
                        "snapshot": {"bias": "neutral", "bias_by_segment": _quiet_bias_for_all_segments()},
                    }
                ]
            ),
            price_deltas={"TLT": 0.001, "IEF": 0.001, "SHY": 0.001},
        )
        result = evaluate(state)
        assert result.decisions
        macro = next(d for d in result.decisions if d.segment == "macro")
        assert macro.decision == "regenerate"

    def test_triage_phase_node_runs_on_baseline(self) -> None:
        state = AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            data_layer=DataLayerSnapshot(
                price_technicals_latest=date(2026, 4, 25),
                price_technicals_ticker_count=56,
                macro_series_latest=date(2026, 4, 25),
                fallback_used="supabase",
            ),
        )
        out = build_triage_node(deps=None)(state)
        assert "triage" in out
        assert out["triage"].decisions
