"""Tests for RSI and BollingerBands indicator classes."""

from __future__ import annotations

import pytest
from digiquant.indicators.oscillators import RSI, BollingerBands


class TestRSI:
    def test_not_initialized_before_length_plus_one(self) -> None:
        rsi = RSI(3)
        rsi.update(10.0)
        assert not rsi.initialized

    def test_constant_rising_is_100(self) -> None:
        rsi = RSI(5)
        for i in range(20):
            rsi.update(float(i))
        assert rsi.initialized
        assert rsi.value == pytest.approx(100.0)

    def test_constant_falling_is_0(self) -> None:
        rsi = RSI(5)
        for i in range(20):
            rsi.update(float(20 - i))
        assert rsi.initialized
        assert rsi.value == pytest.approx(0.0)

    def test_flat_prices_after_move(self) -> None:
        rsi = RSI(14)
        for i in range(20):
            rsi.update(float(i))
        for _ in range(10):
            rsi.update(19.0)
        assert rsi.initialized
        assert rsi.value > 50.0

    def test_no_division_by_zero_on_flat(self) -> None:
        rsi = RSI(3)
        for _ in range(10):
            rsi.update(10.0)
        assert rsi.initialized
        assert rsi.value == pytest.approx(100.0)


class TestBollingerBands:
    def test_not_initialized_before_length(self) -> None:
        bb = BollingerBands(length=3, mult=2.0)
        bb.update(10.0)
        assert not bb.initialized

    def test_symmetric_around_middle(self) -> None:
        bb = BollingerBands(length=5, mult=2.0)
        for v in [10.0, 11.0, 12.0, 11.0, 10.0]:
            bb.update(v)
        assert bb.initialized
        assert bb.upper is not None
        assert bb.lower is not None
        assert bb.middle is not None
        assert bb.upper > bb.middle > bb.lower
        assert bb.upper - bb.middle == pytest.approx(bb.middle - bb.lower, rel=1e-6)

    def test_tight_bands_on_constant_prices(self) -> None:
        bb = BollingerBands(length=5, mult=2.0)
        for _ in range(5):
            bb.update(10.0)
        assert bb.initialized
        assert bb.upper == pytest.approx(10.0)
        assert bb.lower == pytest.approx(10.0)

    def test_ema_basis_type(self) -> None:
        bb_sma = BollingerBands(length=5, mult=2.0, ma_type="SMA")
        bb_ema = BollingerBands(length=5, mult=2.0, ma_type="EMA")
        prices = [10.0, 12.0, 11.0, 13.0, 12.0, 20.0]
        for p in prices:
            bb_sma.update(p)
            bb_ema.update(p)
        assert bb_sma.middle != pytest.approx(bb_ema.middle)

    def test_mult_scales_bands(self) -> None:
        bb1 = BollingerBands(length=5, mult=1.0)
        bb2 = BollingerBands(length=5, mult=2.0)
        for v in [10.0, 12.0, 8.0, 11.0, 9.0]:
            bb1.update(v)
            bb2.update(v)
        assert bb2.upper - bb2.lower == pytest.approx(2 * (bb1.upper - bb1.lower))
