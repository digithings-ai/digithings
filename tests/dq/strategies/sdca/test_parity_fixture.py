"""Parity fixture (acceptance criterion #1): the full SDCA pipeline — power_law
z-score -> composite risk -> AccumDistCurve -> backtest — reproduces expected
numbers within tolerance on a synthetic, self-consistent rails + price series.

Deliberately synthetic (not BTC data): the BTC-specific RiskModel is issue #1082's
job. This fixture only proves the engine's own math is internally consistent
end-to-end, wiring every sdca submodule together the way a real caller would.
"""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.power_law_zscore import power_law_z_score

pytestmark = pytest.mark.unit


class TestSdcaPipelineParityFixture:
    def test_full_pipeline_end_to_end(self) -> None:
        dates = pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, 5), interval="1d", eager=True)
        # Synthetic rails: constant low/median/high; price walks from cheap -> rich -> cheap.
        low = pl.Series([50.0] * 5)
        median = pl.Series([100.0] * 5)
        high = pl.Series([200.0] * 5)
        price = pl.Series([50.0, 75.0, 100.0, 150.0, 200.0])

        z = power_law_z_score(price, low, median, high)
        # price==low -> z=+3 (max buy); price==high -> z=-3 (max sell); price==median -> z=0
        assert z[0] == pytest.approx(3.0)
        assert z[2] == pytest.approx(0.0)
        assert z[4] == pytest.approx(-3.0)

        composite = compute_composite_risk([IndicatorWeight(name="power_law", z=z, weight=1.0)])
        # composite_z mirrors z exactly (single indicator, weight 1) -> risk is the direct mapping
        assert composite["risk"][0] == pytest.approx(0.0)  # cheap -> max-buy risk
        assert composite["risk"][2] == pytest.approx(50.0)  # median -> neutral
        assert composite["risk"][4] == pytest.approx(100.0)  # rich -> max-sell risk

        curve = AccumDistCurve()
        report, frame = run_backtest(
            dates=dates,
            price=price,
            risk=composite["risk"],
            curve=curve,
            initial_cash=1000.0,
        )

        # day0: risk=0 -> curve rate=10% -> buy $100 of $1000 cash at price 50 -> +2.0 btc
        assert frame["rate"][0] == pytest.approx(10.0)
        assert frame["daily_trade_usd"][0] == pytest.approx(100.0)
        assert frame["asset_units"][0] == pytest.approx(2.0)
        assert frame["cash"][0] == pytest.approx(900.0)

        # day4: risk=100 -> curve rate=-10% -> sells 10% of accumulated holdings
        assert frame["rate"][4] == pytest.approx(-10.0)
        assert report.sell_days >= 1
        assert report.buy_days >= 1

        # report is internally consistent with the frame's final row
        assert report.total_pnl == pytest.approx(frame["portfolio_value"][-1] - 1000.0)
        assert report.total_return_pct == pytest.approx(report.total_pnl / 1000.0 * 100.0)
        assert report.avg_risk == pytest.approx(composite["risk"].mean())
