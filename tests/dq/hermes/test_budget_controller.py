from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from digiquant.olympus.hermes.budget_controller import (
    RegimeAssessment,
    assess_budget,
    budget_for,
    classify_regime,
    cross_sectional_dispersion,
)


@pytest.mark.unit
def test_regime_assessment_defaults() -> None:
    a = RegimeAssessment(regime="neutral")
    assert a.regime == "neutral"
    assert a.vix_state is None and a.return_dispersion is None and a.note == ""


@pytest.mark.unit
def test_cross_sectional_dispersion_population_stdev() -> None:
    # Non-degenerate input (a quiet name + a mover): pstdev({0.0, 0.04}) == 0.02
    # (mean 0.02, deviations ±0.02). Distinct magnitudes, so this catches a
    # mean-abs-deviation or sample-stdev mix-up, not just a constant-input pass.
    out = cross_sectional_dispersion({"A": 0.0, "B": 0.04})
    assert out == pytest.approx(0.02, abs=1e-9)


@pytest.mark.unit
def test_cross_sectional_dispersion_insufficient_data_is_none() -> None:
    assert cross_sectional_dispersion({}) is None
    assert cross_sectional_dispersion({"A": 0.01}) is None


@pytest.mark.unit
class TestClassifyRegime:
    def test_backwardation_is_stress(self) -> None:
        a = classify_regime(
            vix_state="backwardation",
            vix_ratio=1.1,
            pct_above_50dma=70.0,
            return_dispersion=0.02,
        )
        assert a.regime == "stress"  # backwardation dominates even with wide dispersion

    def test_weak_breadth_is_stress(self) -> None:
        a = classify_regime(
            vix_state="contango",
            vix_ratio=0.9,
            pct_above_50dma=30.0,
            return_dispersion=0.005,
        )
        assert a.regime == "stress"

    def test_wide_dispersion_is_dispersion(self) -> None:
        a = classify_regime(
            vix_state="contango",
            vix_ratio=0.9,
            pct_above_50dma=65.0,
            return_dispersion=0.02,
        )
        assert a.regime == "dispersion"

    def test_calm_is_neutral(self) -> None:
        a = classify_regime(
            vix_state="contango",
            vix_ratio=0.95,
            pct_above_50dma=55.0,
            return_dispersion=0.005,
        )
        assert a.regime == "neutral"

    def test_all_signals_none_is_neutral(self) -> None:
        a = classify_regime(
            vix_state=None, vix_ratio=None, pct_above_50dma=None, return_dispersion=None
        )
        assert a.regime == "neutral"


@pytest.mark.unit
class TestBudgetFor:
    def test_stress_tightens_below_cap(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="stress"), static_cap=20)
        assert b == 10 and b <= 20
        assert floor == 0

    def test_stress_respects_floor(self) -> None:
        b, _ = budget_for(RegimeAssessment(regime="stress"), static_cap=4)
        assert b == 3  # STRESS_FLOOR, not round(4*0.5)=2

    def test_neutral_equals_cap(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="neutral"), static_cap=20)
        assert b == 20 and floor == 1

    def test_dispersion_keeps_cap_raises_explore_floor(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="dispersion"), static_cap=20)
        assert b == 20  # never exceeds cap (cost-safe)
        assert floor == 5  # round(20*0.25)

    def test_no_cap_configured_stays_uncapped(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="neutral"), static_cap=0)
        assert b == 0  # 0 == "no cap" downstream
        assert floor == 1

    def test_budget_never_exceeds_cap_any_regime(self) -> None:
        for regime in ("stress", "neutral", "dispersion"):
            b, _ = budget_for(RegimeAssessment(regime=regime), static_cap=12)
            assert b <= 12


def _state(price_deltas: dict[str, float]) -> SimpleNamespace:
    return SimpleNamespace(price_deltas=price_deltas, run_date=date(2026, 6, 25))


@pytest.mark.unit
class TestAssessBudget:
    def test_none_client_falls_back_to_static(self) -> None:
        b, floor, a = assess_budget(_state({"A": 0.01, "B": -0.01}), None, static_cap=20)
        assert (b, floor) == (20, 1) and a is None

    def test_reader_error_falls_back_to_static(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**_kw: object) -> dict:
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_vix_term_structure", boom
        )
        b, floor, a = assess_budget(_state({"A": 0.01}), object(), static_cap=15)
        assert (b, floor) == (15, 1) and a is None

    def test_stress_signals_tighten_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_vix_term_structure",
            lambda **_k: {"state": "backwardation", "ratio": 1.2},
        )
        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_market_breadth",
            lambda **_k: {"pct_above_50dma": 35.0, "universe_size": 50},
        )
        b, floor, a = assess_budget(_state({"A": 0.001, "B": -0.001}), object(), static_cap=20)
        assert a is not None and a.regime == "stress"
        assert b == 10 and floor == 0
