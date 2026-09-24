"""WP11.3 — deterministic deliberation selection from decision-value features (#2902)."""

from __future__ import annotations

import pytest
from digiquant.dashboard.research_retrieval.planner import (
    DeliberationAction,
    DeliberationDecisionFeatures,
    DeliberationSelection,
    DeliberationSelectionMode,
    DeliberationSelectionReason,
    build_deliberation_decision_features,
    resolve_deliberation_selection_mode,
    select_h6,
)

pytestmark = pytest.mark.unit


def _features(**overrides: object) -> DeliberationDecisionFeatures:
    base: dict[str, object] = {
        "ticker": "AAPL",
        "roster_reason": "held",
        "held": True,
        "weight_pct": 1.0,
        "stance": "hold",
        "prior_stance": "hold",
        "conviction_score": 1,
        "raw_uncertainty": "low",
        "has_evidence_conflict": False,
        "counter_evidence_count": 0,
        "invalidation_risk": False,
        "evidence_bundle_id": None,
        "price_delta_abs": 0.001,
        "stance_changed": False,
    }
    base.update(overrides)
    return DeliberationDecisionFeatures.model_validate(base)


class TestH6SelectionConditions:
    def test_decision_boundary_selects(self) -> None:
        sel = select_h6(_features(stance="buy", prior_stance="hold", stance_changed=True))
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.DECISION_BOUNDARY
        assert sel.budget.min_rounds >= 2
        assert sel.budget.max_provider_calls > 0

    def test_conflict_selects(self) -> None:
        sel = select_h6(_features(has_evidence_conflict=True, counter_evidence_count=2))
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.CONFLICT

    def test_uncertainty_selects(self) -> None:
        sel = select_h6(_features(raw_uncertainty="high", weight_pct=4.0))
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.UNCERTAINTY

    def test_invalidation_risk_selects(self) -> None:
        sel = select_h6(_features(invalidation_risk=True))
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.INVALIDATION_RISK

    def test_material_selects(self) -> None:
        sel = select_h6(_features(weight_pct=8.0, held=True))
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.MATERIAL

    def test_exploration_selects(self) -> None:
        sel = select_h6(
            _features(
                roster_reason="technical",
                held=False,
                weight_pct=0.0,
                stance="buy",
            )
        )
        assert sel.action is DeliberationAction.SELECT
        assert sel.reason is DeliberationSelectionReason.EXPLORATION

    def test_low_value_carries_with_zero_budget(self) -> None:
        sel = select_h6(_features())
        assert sel.action is DeliberationAction.CARRY
        assert sel.reason is DeliberationSelectionReason.LOW_VALUE_CARRY
        assert sel.budget.max_provider_calls == 0
        assert sel.budget.min_rounds == 0

    def test_primary_reason_priority_invalidation_over_conflict(self) -> None:
        sel = select_h6(
            _features(
                invalidation_risk=True,
                has_evidence_conflict=True,
                stance_changed=True,
            )
        )
        assert sel.reason is DeliberationSelectionReason.INVALIDATION_RISK

    def test_selection_is_deterministic(self) -> None:
        feats = _features(has_evidence_conflict=True, evidence_bundle_id="bundle-1")
        assert select_h6(feats) == select_h6(feats)


class TestH6SelectionMode:
    def test_default_mode_is_shadow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_H6_SELECTION_MODE", raising=False)
        assert resolve_deliberation_selection_mode() is DeliberationSelectionMode.SHADOW

    def test_unknown_mode_falls_back_to_shadow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_H6_SELECTION_MODE", "bogus")
        assert resolve_deliberation_selection_mode() is DeliberationSelectionMode.SHADOW

    def test_enforce_and_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_H6_SELECTION_MODE", "enforce")
        assert resolve_deliberation_selection_mode() is DeliberationSelectionMode.ENFORCE
        monkeypatch.setenv("DIGIQUANT_H6_SELECTION_MODE", "off")
        assert resolve_deliberation_selection_mode() is DeliberationSelectionMode.OFF


class TestBuildFeatures:
    def test_build_from_analyst_and_bundle_id(self) -> None:
        feats = build_deliberation_decision_features(
            ticker="msft",
            roster_reason="held",
            held=True,
            weight_pct=5.5,
            analyst={
                "stance": "buy",
                "conviction_score": 3,
                "forecast_assessment": {
                    "raw_uncertainty": "medium",
                    "counter_evidence_ids": ["e1"],
                    "invalidation_rules": ["break support"],
                },
            },
            prior_analyst={"stance": "hold"},
            price_delta=0.03,
            evidence_bundle_id="11111111-1111-1111-1111-111111111111",
            has_evidence_conflict=True,
            invalidation_risk=False,
        )
        assert feats.ticker == "MSFT"
        assert feats.stance_changed is True
        assert feats.counter_evidence_count == 1
        assert feats.has_evidence_conflict is True
        assert feats.evidence_bundle_id == "11111111-1111-1111-1111-111111111111"
        # Materiality stays on the typed feature record for selection only.
        assert feats.weight_pct == pytest.approx(5.5)

    def test_deliberation_selection_model_round_trip(self) -> None:
        sel = select_h6(_features(has_evidence_conflict=True))
        assert isinstance(sel, DeliberationSelection)
        again = DeliberationSelection.model_validate(sel.model_dump(mode="json"))
        assert again == sel
