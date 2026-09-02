"""Round Stage A weights and shrink Stage B curve params (de-overfit)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.regularize import (
    regularize_curve_shape,
    regularize_weights,
)

pytestmark = pytest.mark.unit


class TestRegularizeWeights:
    def test_rounds_to_tenths_and_renormalizes(self) -> None:
        raw = SdcaCompositeWeights(valuation=0.37, weekly_rsi=0.33, sma_band=0.22)
        out = regularize_weights(raw, step=0.1)
        # 0.37→0.4, 0.33→0.3, 0.22→0.2 (sum 0.9) then renormalize.
        assert out.valuation == pytest.approx(0.4 / 0.9)
        assert out.weekly_rsi == pytest.approx(0.3 / 0.9)
        assert out.sma_band == pytest.approx(0.2 / 0.9)
        assert out.weekly_macd == pytest.approx(0.0)
        assert out.valuation + out.weekly_rsi + out.sma_band == pytest.approx(1.0)

    def test_zero_stays_zero(self) -> None:
        raw = SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.0, weekly_macd=0.0)
        out = regularize_weights(raw, step=0.1)
        assert out.weekly_rsi == pytest.approx(0.0)
        assert out.weekly_macd == pytest.approx(0.0)
        assert out.valuation == pytest.approx(1.0)

    def test_step_five_hundredths(self) -> None:
        raw = SdcaCompositeWeights(valuation=0.42, weekly_rsi=0.38)
        out = regularize_weights(raw, step=0.05)
        assert out.valuation == pytest.approx(0.4 / 0.8)
        assert out.weekly_rsi == pytest.approx(0.4 / 0.8)


class TestRegularizeCurve:
    def test_shrinks_max_rates_keeps_knees(self) -> None:
        shape = SdcaCurveShape(
            buy_max_rate=20.0,
            buy_knee_risk=35.0,
            sell_knee_risk=80.0,
            sell_max_rate=18.0,
            buy_curvature=1.0,
            sell_curvature=2.0,
        )
        out = regularize_curve_shape(shape, rate_scale=0.7)
        assert out.buy_max_rate == pytest.approx(14.0)
        assert out.sell_max_rate == pytest.approx(12.6)
        # 6.0 * 0.7 would be 4.1999… without rounding to one decimal.
        tiny = regularize_curve_shape(
            SdcaCurveShape(
                buy_max_rate=6.0,
                buy_knee_risk=35.0,
                sell_knee_risk=80.0,
                sell_max_rate=6.0,
                buy_curvature=1.0,
                sell_curvature=2.0,
            )
        )
        assert tiny.buy_max_rate == pytest.approx(4.2)
        assert tiny.sell_max_rate == pytest.approx(4.2)
        assert out.buy_knee_risk == pytest.approx(35.0)
        assert out.sell_knee_risk == pytest.approx(80.0)
        assert out.buy_curvature == pytest.approx(1.0)
        assert out.sell_curvature == pytest.approx(2.0)
