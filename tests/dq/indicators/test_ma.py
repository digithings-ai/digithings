"""Tests for bar-by-bar moving average classes."""

from __future__ import annotations

import pytest
from digiquant.indicators.ma import WilderMA, SMA, EMA, WMA, HMA, DEMA, VWMA, make_ma


class TestWilderMA:
    def test_not_initialized_before_enough_bars(self) -> None:
        rma = WilderMA(3)
        rma.update(10.0)
        rma.update(11.0)
        assert not rma.initialized
        assert rma.value is None

    def test_initialized_after_length_bars(self) -> None:
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        assert rma.initialized

    def test_first_value_is_sma_seed(self) -> None:
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        assert rma.value == pytest.approx(11.0)

    def test_subsequent_update(self) -> None:
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        rma.update(13.0)
        assert rma.value == pytest.approx(11.0 + (1 / 3) * (13.0 - 11.0))


class TestSMA:
    def test_not_initialized_before_length(self) -> None:
        sma = SMA(3)
        sma.update(1.0)
        assert not sma.initialized

    def test_value_after_length_bars(self) -> None:
        sma = SMA(3)
        for v in [1.0, 2.0, 3.0]:
            sma.update(v)
        assert sma.value == pytest.approx(2.0)

    def test_rolling_window(self) -> None:
        sma = SMA(3)
        for v in [1.0, 2.0, 3.0, 4.0]:
            sma.update(v)
        assert sma.value == pytest.approx(3.0)


class TestEMA:
    def test_not_initialized_before_length(self) -> None:
        ema = EMA(3)
        ema.update(10.0)
        assert not ema.initialized

    def test_initialized_at_length(self) -> None:
        ema = EMA(3)
        for v in [10.0, 11.0, 12.0]:
            ema.update(v)
        assert ema.initialized

    def test_alpha_formula(self) -> None:
        ema = EMA(3)
        for v in [10.0, 11.0, 12.0]:
            ema.update(v)
        assert ema.value == pytest.approx(11.0)
        ema.update(14.0)
        assert ema.value == pytest.approx(12.5)


class TestWMA:
    def test_weighted_average(self) -> None:
        wma = WMA(3)
        for v in [1.0, 2.0, 3.0]:
            wma.update(v)
        assert wma.value == pytest.approx(14 / 6)

    def test_rolling(self) -> None:
        wma = WMA(3)
        for v in [1.0, 2.0, 3.0, 4.0]:
            wma.update(v)
        assert wma.value == pytest.approx(20 / 6)


class TestDEMA:
    def test_needs_2x_length_bars(self) -> None:
        dema = DEMA(3)
        for v in range(4):
            dema.update(float(v))
        assert not dema.initialized

    def test_initialized_after_2x_length(self) -> None:
        dema = DEMA(3)
        for v in range(6):
            dema.update(float(v))
        assert dema.initialized

    def test_formula_dema_equals_2ema_minus_ema_ema(self) -> None:
        dema = DEMA(3)
        ema1 = EMA(3)
        ema2 = EMA(3)
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        for p in prices:
            dema.update(p)
            ema1.update(p)
            if ema1.initialized:
                ema2.update(ema1.value)
        if dema.initialized and ema1.initialized and ema2.initialized:
            assert dema.value == pytest.approx(2 * ema1.value - ema2.value)


class TestHMA:
    def test_initialized_eventually(self) -> None:
        hma = HMA(9)
        for i in range(30):
            hma.update(float(i))
        assert hma.initialized

    def test_not_initialized_too_early(self) -> None:
        hma = HMA(9)
        for i in range(5):
            hma.update(float(i))
        assert not hma.initialized


class TestVWMA:
    def test_volume_weighted(self) -> None:
        vwma = VWMA(2)
        vwma.update(price=10.0, volume=100.0)
        vwma.update(price=20.0, volume=200.0)
        assert vwma.value == pytest.approx(5000 / 300)

    def test_not_initialized_before_length(self) -> None:
        vwma = VWMA(3)
        vwma.update(price=10.0, volume=100.0)
        assert not vwma.initialized


class TestMakeMa:
    def test_returns_correct_types(self) -> None:
        assert isinstance(make_ma("SMA", 5), SMA)
        assert isinstance(make_ma("EMA", 5), EMA)
        assert isinstance(make_ma("RMA", 5), WilderMA)
        assert isinstance(make_ma("WMA", 5), WMA)
        assert isinstance(make_ma("HMA", 5), HMA)
        assert isinstance(make_ma("DEMA", 5), DEMA)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown MA type"):
            make_ma("UNKNOWN", 5)
