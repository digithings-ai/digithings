"""Unit tests for Phase-1 RS rotation backtest + Nautilus config (#1084)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import polars as pl
import pytest
from digiquant.indicators.rs_ranker import RsRanker, RsRankerConfig
from digiquant.strategies.rotation.backtest import (
    backtest_rs_rotation,
    build_allocation_frame,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _close_frame(dates: list[date], values: np.ndarray) -> pl.DataFrame:
    return pl.DataFrame({"date": dates, "close": [float(v) for v in values]})


def _crypto_pool(n: int = 250) -> dict[str, pl.DataFrame]:
    """Synthetic BTC/ETH/SOL (+ALT) pool with clear leadership rotation."""
    dates = _dates(n)
    t = np.arange(n, dtype=float)
    # First half: BTC leads; second half: ETH leads; SOL drifts down.
    btc = np.concatenate(
        [
            100.0 * (1.0 + 0.005 * t[: n // 2]),
            100.0 * (1.0 + 0.005 * (n // 2 - 1)) * (1.0 + 0.0005 * np.arange(n - n // 2)),
        ]
    )
    eth = np.concatenate(
        [
            100.0 * (1.0 + 0.001 * t[: n // 2]),
            100.0 * (1.0 + 0.001 * (n // 2 - 1)) * (1.0 + 0.006 * np.arange(n - n // 2)),
        ]
    )
    sol = 100.0 * (1.0 - 0.0015 * t)
    alt = 100.0 * (1.0 + 0.0008 * t)
    return {
        "BTC": _close_frame(dates, btc),
        "ETH": _close_frame(dates, eth),
        "SOL": _close_frame(dates, sol),
        "ALT": _close_frame(dates, alt),
    }


class TestRsRotationBacktest:
    def test_reports_vs_equal_weight_and_buy_hold(self) -> None:
        pool = _crypto_pool()
        report = backtest_rs_rotation(
            pool,
            config=RsRankerConfig(lookback_days=60, skip_days=5),
            top_n=1,
            rebalance_every=7,
        )
        assert report.days_total >= 2
        assert report.rebalance_count >= 1
        # Finite returns vs both benchmarks.
        for val in (
            report.rotation_return_pct,
            report.equal_weight_return_pct,
            report.buy_hold_return_pct,
            report.vs_equal_weight_pct,
            report.vs_buy_hold_pct,
        ):
            assert np.isfinite(val)
        assert report.days_invested + report.days_cash == report.days_total

    def test_absolute_strength_gate_moves_to_cash(self) -> None:
        dates = _dates(180)
        t = np.arange(180, dtype=float)
        # Entire pool falling → no qualifiers → cash sleeve.
        pool = {
            "BTC": _close_frame(dates, 100.0 * (1.0 - 0.003 * t)),
            "ETH": _close_frame(dates, 100.0 * (1.0 - 0.002 * t)),
            "SOL": _close_frame(dates, 100.0 * (1.0 - 0.0025 * t)),
        }
        report = backtest_rs_rotation(
            pool,
            config=RsRankerConfig(lookback_days=60, skip_days=5),
            top_n=1,
            rebalance_every=5,
        )
        # After warmup the rotator should spend meaningful time in cash.
        assert report.days_cash > 0
        # Flat-ish cash book vs deep drawdown on always-in EW.
        assert report.rotation_return_pct > report.equal_weight_return_pct

    def test_optional_regime_gate_forces_cash(self) -> None:
        pool = _crypto_pool(n=200)
        n = 200
        # risk_on only on first quarter — rest cash.
        gate = [True] * (n // 4) + [False] * (n - n // 4)
        report = backtest_rs_rotation(
            pool,
            config=RsRankerConfig(lookback_days=60, skip_days=5),
            top_n=1,
            rebalance_every=5,
            risk_on=gate,
        )
        assert report.days_cash > report.days_invested

    def test_build_allocation_respects_risk_on(self) -> None:
        pool = _crypto_pool(n=180)
        ranked = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5)).rank(pool)
        last = ranked["date"].max()
        alloc = build_allocation_frame(
            ranked,
            top_n=1,
            risk_on_by_date={last: False},
        )
        # Last day forced cash; earlier days may still appear.
        assert alloc.filter(pl.col("date") == last).is_empty()


try:
    from nautilus_trader.model.data import BarSpecification, BarType
    from nautilus_trader.model.enums import BarAggregation, PriceType
    from nautilus_trader.model.identifiers import InstrumentId

    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False


@pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
class TestRsRotationNautilusConfig:
    def test_config_and_instantiate(self, tmp_path) -> None:
        from digiquant.strategies.rotation.nautilus_strategy import (
            RsRotationConfig,
            RsRotationStrategy,
        )

        pool = _crypto_pool(n=160)
        ranked = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5)).rank(pool)
        alloc = build_allocation_frame(ranked, top_n=1)
        path = tmp_path / "alloc.parquet"
        alloc.write_parquet(path)

        iid = InstrumentId.from_str("BTC-USD.SIM")
        spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
        bt = BarType(iid, spec)
        cfg = RsRotationConfig(
            instrument_id=iid,
            bar_type=bt,
            instrument_ids_csv="BTC-USD.SIM,ETH-USD.SIM",
            bar_types_csv=f"{bt},{BarType(InstrumentId.from_str('ETH-USD.SIM'), spec)}",
            allocation_path=str(path),
            portfolio_notional=Decimal("10000"),
        )
        strategy = RsRotationStrategy(cfg)
        assert strategy is not None
