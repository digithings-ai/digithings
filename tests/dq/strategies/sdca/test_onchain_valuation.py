"""Unit tests for on-chain SDCA valuation provider (#1086).

No network — frames are synthetic Polars. Verifies MVRV-Z, composite
consumability, and basic-tier fallback when on-chain is unavailable.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.onchain_valuation import (
    ONCHAIN_INDICATOR_NAMES,
    OnChainValuationProvider,
    ValuationTier,
    asset_onchain_coverage,
    build_onchain_composite_z,
    build_onchain_indicator_weights,
    causal_expanding_z,
    mvrv_z_score,
    resolve_sdca_valuation_tier,
)
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 1)) -> pl.Series:
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def _mvrv_frame(n: int = 60) -> pl.DataFrame:
    # Mild cycle: starts rich (~3.5), drifts toward cheap (~0.8).
    values = [3.5 - (2.7 * i / (n - 1)) for i in range(n)]
    return pl.DataFrame({"date": _dates(n), "value": values})


def _asopr_frame(n: int = 60) -> pl.DataFrame:
    values = [1.05 - (0.15 * i / (n - 1)) for i in range(n)]
    return pl.DataFrame({"date": _dates(n), "value": values})


class TestMvrvZ:
    def test_cheap_mvrv_is_positive_z(self) -> None:
        # Long history of high MVRV, then a drop → last z should be + (cheap).
        n = 80
        values = [3.0] * (n - 5) + [0.9, 0.85, 0.8, 0.75, 0.7]
        z = mvrv_z_score(pl.Series("mvrv", values), min_samples=20)
        assert z[-1] is not None
        assert float(z[-1]) > 0.0

    def test_expanding_z_null_until_min_samples(self) -> None:
        values = pl.Series("v", [float(i) for i in range(10)])
        z = causal_expanding_z(values, min_samples=5)
        assert z[:4].null_count() == 4
        assert z[4:].null_count() == 0


class TestOnChainProvider:
    def test_indicator_weights_consumable_by_composite(self) -> None:
        n = 60
        dates = _dates(n)
        frames = {
            "mvrv": _mvrv_frame(n),
            "asopr_24h": _asopr_frame(n),
            "puell_multiple": pl.DataFrame(
                {"date": dates, "value": [1.5 - i * 0.01 for i in range(n)]}
            ),
            "rhodl_ratio": pl.DataFrame(
                {"date": dates, "value": [0.5 - i * 0.002 for i in range(n)]}
            ),
        }
        provider = OnChainValuationProvider(series_frames=frames, min_samples=20)
        indicators = provider.indicator_weights(dates)
        names = {ind.name for ind in indicators}
        assert names == set(ONCHAIN_INDICATOR_NAMES)

        # Price valuation stub + on-chain votes → composite_risk accepts them.
        price_z = pl.Series("valuation", [0.0] * n)
        blend = [
            IndicatorWeight(name="valuation", z=price_z, weight=1.0),
            *indicators,
        ]
        out = compute_composite_risk(blend)
        assert "composite_z" in out.columns and "risk" in out.columns
        # After warmup, risk is finite on most days.
        assert out["risk"].drop_nulls().len() > 20

    def test_blended_valuation_z_skip_missing_series(self) -> None:
        n = 50
        dates = _dates(n)
        # Only MVRV present — blend still emits a series.
        z = build_onchain_composite_z(dates, {"mvrv": _mvrv_frame(n)}, min_samples=15)
        assert z.drop_nulls().len() > 10

    def test_empty_frames_yield_no_indicators(self) -> None:
        dates = _dates(10)
        assert build_onchain_indicator_weights(dates, {}) == []


class TestCoverageAndFallback:
    def test_btc_rich_eth_none(self) -> None:
        assert asset_onchain_coverage("BTC-USD") == "rich"
        assert asset_onchain_coverage("ETH-USD") == "none"
        assert asset_onchain_coverage("SOL-USD") == "none"

    def test_enhanced_when_btc_and_cache(self) -> None:
        n = 50
        dates = _dates(n)
        price = pl.Series("price", [10_000.0 + i * 10 for i in range(n)])
        provider = OnChainValuationProvider(series_frames={"mvrv": _mvrv_frame(n)}, min_samples=15)
        result = resolve_sdca_valuation_tier("BTC-USD", dates=dates, price=price, provider=provider)
        assert result.tier == ValuationTier.ONCHAIN_ENHANCED
        assert len(result.onchain_indicators) >= 1
        assert isinstance(result.risk_model, RollingZRiskModel)

    def test_fallback_when_eth(self) -> None:
        n = 40
        dates = _dates(n)
        price = pl.Series("price", [100.0 + i for i in range(n)])
        provider = OnChainValuationProvider(series_frames={"mvrv": _mvrv_frame(n)}, min_samples=15)
        result = resolve_sdca_valuation_tier("ETH-USD", dates=dates, price=price, provider=provider)
        assert result.tier == ValuationTier.BASIC
        assert result.onchain_indicators == ()
        assert isinstance(result.risk_model, RollingZRiskModel)

    def test_fallback_when_btc_cache_empty(self) -> None:
        n = 40
        dates = _dates(n)
        price = pl.Series("price", [100.0 + i for i in range(n)])
        result = resolve_sdca_valuation_tier(
            "BTC-USD",
            dates=dates,
            price=price,
            provider=OnChainValuationProvider(series_frames={}),
        )
        assert result.tier == ValuationTier.BASIC
        assert "fallback" in result.reason
