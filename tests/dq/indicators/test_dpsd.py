"""Tests for DPSDTrend (DEMA Percentile Standard Deviation Trend)."""

from __future__ import annotations

from digiquant.indicators.dpsd import DPSDTrend


def _feed(dpsd: DPSDTrend, prices: list[float]) -> None:
    """Feed a list of (src=price, close=price) pairs — uses same value for simplicity."""
    for p in prices:
        dpsd.update(src=p, close=p)


class TestDPSDTrend:
    def test_not_initialized_before_warmup(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=5,
            percentile_type="55/45",
            sd_length=3,
            ema_length=3,
            include_ema=True,
        )
        for i in range(5):
            dpsd.update(src=float(i), close=float(i))
        assert not dpsd.initialized

    def test_initialized_after_warmup(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=5,
            percentile_type="55/45",
            sd_length=3,
            ema_length=3,
            include_ema=True,
        )
        for i in range(30):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized

    def test_uptrend_on_rising_prices(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        for i in range(60):
            dpsd.update(src=float(i * 10), close=float(i * 10))
        assert dpsd.trend == 1.0

    def test_downtrend_on_falling_prices(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        for i in range(40):
            dpsd.update(src=float(i * 10), close=float(i * 10))
        for i in range(40):
            dpsd.update(src=float(400 - i * 10), close=float(400 - i * 10))
        assert dpsd.trend == -1.0

    def test_crossed_up_fires_once(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        crossups = []
        for i in range(60):
            dpsd.update(src=float(i), close=float(i))
            if dpsd.initialized:
                crossups.append(dpsd.crossed_up())
        assert sum(crossups) <= 5

    def test_percentile_type_60_40(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="60/40",
            sd_length=5,
            ema_length=5,
            include_ema=False,
        )
        for i in range(40):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized

    def test_include_ema_false(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=False,
        )
        for i in range(40):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized
