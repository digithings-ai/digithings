"""Pure calculators for the gloomberb OVME/YAS/KELLY tools (130-coverage Task 1).

Stdlib ``math`` only — no transport, no I/O. European Black-Scholes via the
``math.erf`` normal CDF, par-bond analytics, and the Kelly fraction.
"""

from __future__ import annotations

import math
from typing import Literal

_IV_MAX_ITERATIONS = 200


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(
    *,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    expiry_years: float,
    kind: Literal["call", "put"],
) -> float:
    """European Black-Scholes price. Raises ``ValueError`` on bad inputs."""
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if spot <= 0.0:
        raise ValueError(f"spot must be positive, got {spot}")
    if strike <= 0.0:
        raise ValueError(f"strike must be positive, got {strike}")
    if vol <= 0.0:
        raise ValueError(f"vol must be positive, got {vol}")
    if expiry_years <= 0.0:
        raise ValueError(f"expiry_years must be positive, got {expiry_years}")

    sqrt_t = math.sqrt(expiry_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * expiry_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    discount = math.exp(-rate * expiry_years)
    if kind == "call":
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def black_scholes_iv(
    *,
    price: float,
    spot: float,
    strike: float,
    rate: float,
    expiry_years: float,
    kind: Literal["call", "put"],
) -> float:
    """Implied vol via bisection (capped at 200 iterations).

    Raises ``ValueError`` when the price is outside arbitrage bounds or the
    bisection does not converge.
    """
    if price <= 0.0:
        raise ValueError(f"price must be positive, got {price}")

    low = 1e-6
    high = 10.0
    if (
        black_scholes_price(
            spot=spot,
            strike=strike,
            rate=rate,
            vol=high,
            expiry_years=expiry_years,
            kind=kind,
        )
        < price
    ):
        raise ValueError(f"price {price} exceeds model range (arbitrage bound)")

    mid = 0.0
    for _ in range(_IV_MAX_ITERATIONS):
        mid = 0.5 * (low + high)
        model = black_scholes_price(
            spot=spot,
            strike=strike,
            rate=rate,
            vol=mid,
            expiry_years=expiry_years,
            kind=kind,
        )
        if abs(model - price) < 1e-12:
            return mid
        if model < price:
            low = mid
        else:
            high = mid
    if high - low > 1e-9:
        raise ValueError(f"IV bisection did not converge for price {price}")
    return mid


def bond_metrics(
    *,
    coupon: float,
    face: float,
    ytm: float,
    years: float,
    freq: int,
) -> dict[str, float]:
    """Bond analytics: price, accrued, duration, convexity, dv01.

    ``accrued`` is 0.0 — settlement is assumed exactly on a coupon date, so
    the dirty price equals the clean price. ``duration`` is the modified
    duration in years; ``convexity`` is in years squared.
    """
    if face <= 0.0:
        raise ValueError(f"face must be positive, got {face}")
    if years <= 0.0:
        raise ValueError(f"years must be positive, got {years}")
    if freq < 1:
        raise ValueError(f"freq must be a positive integer, got {freq}")
    if coupon < 0.0:
        raise ValueError(f"coupon must be non-negative, got {coupon}")

    periods = int(round(years * freq))
    if periods < 1:
        raise ValueError(f"years * freq must cover at least one period, got {years * freq}")
    y = ytm / freq
    payment = coupon * face / freq

    def _discount(t: int) -> float:
        return (1.0 + y) ** -t

    if y == 0.0:
        price = payment * periods + face
        pv_weights = [payment] * periods
        pv_face = face
    else:
        pv_weights = [payment * _discount(t) for t in range(1, periods + 1)]
        pv_face = face * _discount(periods)
        price = sum(pv_weights) + pv_face

    macaulay_periods = (
        sum(t * pv for t, pv in enumerate(pv_weights, start=1)) + periods * pv_face
    ) / price
    macaulay_years = macaulay_periods / freq
    modified = macaulay_years / (1.0 + y)
    convexity = (
        (
            sum(t * (t + 1) * pv for t, pv in enumerate(pv_weights, start=1))
            + periods * (periods + 1) * pv_face
        )
        / price
        / ((1.0 + y) ** 2)
        / (freq * freq)
    )
    dv01 = modified * price * 0.0001
    return {
        "price": price,
        "accrued": 0.0,
        "duration": modified,
        "convexity": convexity,
        "dv01": dv01,
    }


def kelly_fraction(*, win_prob: float, win_loss_ratio: float) -> float:
    """Kelly fraction ``p - (1 - p) / b`` clamped at 0.0 from below.

    Raises ``ValueError`` when ``win_prob`` is outside [0, 1] or
    ``win_loss_ratio`` is not positive.
    """
    if not 0.0 <= win_prob <= 1.0:
        raise ValueError(f"win_prob must be within [0, 1], got {win_prob}")
    if win_loss_ratio <= 0.0:
        raise ValueError(f"win_loss_ratio must be positive, got {win_loss_ratio}")
    return max(0.0, win_prob - (1.0 - win_prob) / win_loss_ratio)
