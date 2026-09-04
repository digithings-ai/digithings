"""Unit tests for RsRanker (#1084)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from digiquant.indicators.rs_ranker import RsRanker, RsRankerConfig
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _close_frame(dates: list[date], values: np.ndarray) -> pl.DataFrame:
    return pl.DataFrame({"date": dates, "close": [float(v) for v in values]})


def _trending_pool(n: int = 200) -> dict[str, pl.DataFrame]:
    """BTC rises hard & smooth, ETH noisy mild rise, SOL falls — clear risk-adj ranks."""
    dates = _dates(n)
    t = np.arange(n, dtype=float)
    rng = np.random.default_rng(0)
    btc = 100.0 * (1.0 + 0.004 * t)  # strong, smooth
    eth = 100.0 * (1.0 + 0.001 * t) * (1.0 + 0.01 * rng.normal(0, 1, n))
    sol = 100.0 * (1.0 - 0.002 * t) * (1.0 + 0.01 * rng.normal(0, 1, n))
    # Keep closes positive.
    eth = np.maximum(eth, 1.0)
    sol = np.maximum(sol, 1.0)
    return {
        "BTC": _close_frame(dates, btc),
        "ETH": _close_frame(dates, eth),
        "SOL": _close_frame(dates, sol),
    }


class TestRsRankerConfig:
    def test_rejects_bad_lookback(self) -> None:
        with pytest.raises(ValidationError):
            RsRankerConfig(lookback_days=1)


class TestRsRanker:
    def test_ranks_strongest_first_on_multi_asset_pool(self) -> None:
        pool = _trending_pool()
        cfg = RsRankerConfig(lookback_days=60, skip_days=5)
        ranked = RsRanker(cfg).rank(pool)
        assert set(ranked.columns) >= {
            "date",
            "symbol",
            "abs_return",
            "vol",
            "risk_adj",
            "rs_rank",
            "qualifies",
        }
        scored = ranked.drop_nulls(subset=["rs_rank"])
        assert len(scored) > 0
        # Last day: BTC should be rank 1, SOL last (falling).
        last = scored.filter(pl.col("date") == scored["date"].max())
        by_sym = {r["symbol"]: r for r in last.to_dicts()}
        assert by_sym["BTC"]["rs_rank"] == 1
        assert by_sym["SOL"]["rs_rank"] == 3
        assert by_sym["BTC"]["qualifies"] is True
        assert by_sym["SOL"]["qualifies"] is False

    def test_absolute_gate_marks_falling_assets_unqualified(self) -> None:
        pool = _trending_pool()
        ranked = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5)).rank(pool)
        sol = ranked.filter(pl.col("symbol") == "SOL").drop_nulls(subset=["abs_return"])
        assert len(sol) > 0
        assert sol["qualifies"].sum() == 0

    def test_select_top_n_cash_when_none_qualify(self) -> None:
        # All falling.
        dates = _dates(150)
        t = np.arange(150, dtype=float)
        pool = {
            "A": _close_frame(dates, 100.0 * (1.0 - 0.003 * t)),
            "B": _close_frame(dates, 100.0 * (1.0 - 0.002 * t)),
        }
        ranked = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5)).rank(pool)
        picks = RsRanker().select_top_n(ranked, top_n=1, qualifying_only=True)
        assert picks.is_empty()

    def test_select_top_n_equal_weights(self) -> None:
        pool = _trending_pool()
        ranked = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5)).rank(pool)
        picks = RsRanker().select_top_n(ranked, top_n=2, qualifying_only=True)
        last = picks.filter(pl.col("date") == picks["date"].max())
        assert len(last) == 2
        assert abs(last["weight"].sum() - 1.0) < 1e-9
        assert set(last["symbol"].to_list()) == {"BTC", "ETH"}

    def test_long_frame_input_and_parquet_roundtrip(self, tmp_path) -> None:
        pool = _trending_pool(n=160)
        long = pl.concat(
            [
                f.with_columns(pl.lit(sym).alias("symbol")).select(["date", "symbol", "close"])
                for sym, f in pool.items()
            ]
        )
        ranker = RsRanker(RsRankerConfig(lookback_days=60, skip_days=5))
        ranked = ranker.rank(long)
        path = ranker.write_rankings(ranked, tmp_path / "ranks.parquet")
        loaded = RsRanker.load_rankings(path)
        assert loaded.height == ranked.height
        index = RsRanker.ranking_index_by_date(loaded)
        assert len(index) > 0

    def test_stable_ranks_are_deterministic(self) -> None:
        pool = _trending_pool()
        cfg = RsRankerConfig(lookback_days=60, skip_days=5)
        a = RsRanker(cfg).rank(pool)
        b = RsRanker(cfg).rank(pool)
        assert a.select(["date", "symbol", "rs_rank", "qualifies"]).equals(
            b.select(["date", "symbol", "rs_rank", "qualifies"])
        )
