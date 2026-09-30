"""Unit tests for digiquant.data.gloomberb.calculators (130-coverage Task 1).

Pure stdlib math: Black-Scholes (OVME), bond metrics (YAS), Kelly (KELLY).
"""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.unit


def test_black_scholes_call_put_parity() -> None:
    from digiquant.data.gloomberb.calculators import black_scholes_price

    call = black_scholes_price(
        spot=100.0, strike=100.0, rate=0.05, vol=0.2, expiry_years=1.0, kind="call"
    )
    put = black_scholes_price(
        spot=100.0, strike=100.0, rate=0.05, vol=0.2, expiry_years=1.0, kind="put"
    )
    assert call - put == pytest.approx(100.0 - 100.0 * math.exp(-0.05), rel=1e-9)


def test_black_scholes_known_value() -> None:
    from digiquant.data.gloomberb.calculators import black_scholes_price

    call = black_scholes_price(
        spot=100.0, strike=100.0, rate=0.05, vol=0.2, expiry_years=1.0, kind="call"
    )
    assert call == pytest.approx(10.4506, abs=1e-3)


def test_black_scholes_iv_round_trip() -> None:
    from digiquant.data.gloomberb.calculators import (
        black_scholes_iv,
        black_scholes_price,
    )

    price = black_scholes_price(
        spot=100.0, strike=100.0, rate=0.05, vol=0.25, expiry_years=1.0, kind="call"
    )
    assert black_scholes_iv(
        price=price, spot=100.0, strike=100.0, rate=0.05, expiry_years=1.0, kind="call"
    ) == pytest.approx(0.25, rel=1e-6)


def test_bond_metrics_par_bond_prices_at_face() -> None:
    from digiquant.data.gloomberb.calculators import bond_metrics

    out = bond_metrics(coupon=0.05, face=1000.0, ytm=0.05, years=10, freq=2)
    assert set(out) == {"price", "accrued", "duration", "convexity", "dv01"}
    assert out["price"] == pytest.approx(1000.0, rel=1e-9)
    assert out["duration"] > 0.0
    assert out["convexity"] > 0.0
    assert out["dv01"] > 0.0


def test_kelly_rejects_impossible_probability() -> None:
    from digiquant.data.gloomberb.calculators import kelly_fraction

    with pytest.raises(ValueError):
        kelly_fraction(win_prob=1.5, win_loss_ratio=1.0)


def test_kelly_standard_and_clamp() -> None:
    from digiquant.data.gloomberb.calculators import kelly_fraction

    assert kelly_fraction(win_prob=0.6, win_loss_ratio=1.0) == pytest.approx(0.2)
    assert kelly_fraction(win_prob=0.4, win_loss_ratio=1.0) == 0.0
