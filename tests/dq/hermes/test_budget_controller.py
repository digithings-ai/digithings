from __future__ import annotations

import pytest

from digiquant.olympus.hermes.budget_controller import (
    RegimeAssessment,
    cross_sectional_dispersion,
)


@pytest.mark.unit
def test_regime_assessment_defaults() -> None:
    a = RegimeAssessment(regime="neutral")
    assert a.regime == "neutral"
    assert a.vix_state is None and a.return_dispersion is None and a.note == ""


@pytest.mark.unit
def test_cross_sectional_dispersion_population_stdev() -> None:
    # stdev of {0.02, -0.02, 0.02, -0.02} (population) == 0.02
    out = cross_sectional_dispersion({"A": 0.02, "B": -0.02, "C": 0.02, "D": -0.02})
    assert out == pytest.approx(0.02, abs=1e-9)


@pytest.mark.unit
def test_cross_sectional_dispersion_insufficient_data_is_none() -> None:
    assert cross_sectional_dispersion({}) is None
    assert cross_sectional_dispersion({"A": 0.01}) is None
