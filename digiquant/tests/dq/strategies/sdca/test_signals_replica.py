"""Tests for the Railway signals-app replica composite (UI-spec reimplementation).

Every vote builder carries ASSUMPTION[Sn] tags (see signals_replica.py and the
challenger spec); these tests pin the documented behavior, not production parity.
"""

from __future__ import annotations

import math
import random

import polars as pl
import pytest

from digiquant.strategies.sdca import signals_replica as replica


def _gbm_prices(n: int, seed: int = 0) -> pl.Series:
    rng = random.Random(seed)
    prices = [100.0]
    for _ in range(1, n):
        prices.append(prices[-1] * math.exp(0.0008 + 0.02 * (rng.random() * 2 - 1)))
    return pl.Series("price", prices)


def _ratio_series(n: int, base: float, seed: int = 1) -> pl.Series:
    rng = random.Random(seed)
    return pl.Series("v", [base * math.exp(0.15 * (rng.random() * 2 - 1)) for _ in range(n)])


def _dates(n: int) -> pl.Series:
    import datetime

    start = datetime.date(2020, 1, 1)
    return pl.Series("date", [start + datetime.timedelta(days=i) for i in range(n)])


def test_votes_bounded_named_and_full_length() -> None:
    n = 400
    dates, prices = _dates(n), _gbm_prices(n)
    votes = {
        "tail_curvature": replica.tail_curvature_z(
            prices, tail_window=30, z_window=20, min_samples=5
        ),
        "sharpe": replica.sharpe_z(prices, window=20, min_samples=5, ema_half_life=7.0),
        "cost_basis": replica.cost_basis_ratio_z(
            dates, dates, _ratio_series(n, 1.5), window=20, min_samples=5, ema_half_life=3.0
        ),
        "onchain": replica.onchain_composite_z(
            dates,
            {
                k: (dates, _ratio_series(n, 1.0 + 0.1 * i, seed=10 + i))
                for i, k in enumerate(replica.ONCHAIN_LEGS)
            },
            window=20,
            min_samples=5,
            ema_half_life=3.0,
        ),
    }
    assert set(votes) == set(replica.REPLICA_VOTE_NAMES)
    for name, vote in votes.items():
        assert len(vote) == n, name
        assert vote.name == name
        finite = vote.drop_nulls()
        assert len(finite) > n // 2, name
        assert finite.is_between(-3.0, 3.0).all(), name


def test_tail_curvature_is_causal() -> None:
    prices = _gbm_prices(200)
    full = replica.tail_curvature_z(prices, tail_window=30, z_window=20, min_samples=5)
    prefix = replica.tail_curvature_z(prices[:120], tail_window=30, z_window=20, min_samples=5)
    assert full[:120].equals(prefix)


def test_sharpe_is_causal() -> None:
    prices = _gbm_prices(200)
    full = replica.sharpe_z(prices, window=20, min_samples=5, ema_half_life=7.0)
    prefix = replica.sharpe_z(prices[:120], window=20, min_samples=5, ema_half_life=7.0)
    assert full[:120].equals(prefix)


def test_composite_is_equal_weight_mean_with_risk_map() -> None:
    n = 60
    votes = {name: pl.Series(name, [1.0] * n) for name in replica.REPLICA_VOTE_NAMES}
    out = replica.build_replica_composite(votes)
    assert out["composite_z"].to_list() == pytest.approx([1.0] * n)
    assert out["risk"].to_list() == pytest.approx([50.0 - 50.0 / 3.0] * n)


def test_composite_null_rule_and_missing_vote_rejected() -> None:
    n = 20
    votes = {name: pl.Series(name, [0.5] * n) for name in replica.REPLICA_VOTE_NAMES}
    votes["sharpe"][5] = None
    out = replica.build_replica_composite(votes)
    assert out["composite_z"][5] is None
    assert out["risk"][5] is None
    with pytest.raises(ValueError, match="missing replica votes"):
        replica.build_replica_composite({k: v for k, v in votes.items() if k != "sharpe"})
