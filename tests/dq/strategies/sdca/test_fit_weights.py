"""Stage A MCP helper: profile → cached OHLCV → weights + regularize."""

from __future__ import annotations

import datetime as _dt
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.history_cache import save_cached
from digiquant.strategies.sdca.asset_profile import SdcaAssetProfile
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.fit_weights import (
    fit_sdca_weights_from_cache,
    resolve_sdca_profile,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec

pytestmark = pytest.mark.unit


def _ohlcv(ticker: str, n: int, *, start: date) -> pl.DataFrame:
    ts = [start + _dt.timedelta(days=i) for i in range(n)]
    close = [100.0 + 0.2 * i for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": ts,
            "open": close,
            "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close],
            "close": close,
            "volume": [1.0] * n,
            "symbol": [ticker] * n,
        }
    ).select(list(OHLCV_COLUMNS))


def _research_profile() -> SdcaAssetProfile:
    start = date(2020, 1, 1)
    return SdcaAssetProfile(
        symbol="ETH-USD",
        risk_model="rolling_z",
        oscillators=SdcaOscillatorSpec(sma_band_window=20, sma_band_min_samples=10),
        cycle_windows=SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 25),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 25),
                ),
            )
        ),
        extra_indicators=("weekly_rsi", "weekly_macd", "sma_band"),
    )


class TestResolveProfile:
    def test_named_btc_and_eth(self) -> None:
        assert resolve_sdca_profile("btc_v1").symbol == "BTC-USD"
        assert resolve_sdca_profile("eth_research_v1").risk_model == "generic_valuation"

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown sdca profile"):
            resolve_sdca_profile("not_a_profile")

    def test_profile_json_roundtrip(self) -> None:
        raw = _research_profile().model_dump_json()
        loaded = resolve_sdca_profile("btc_v1", profile_json=raw)
        assert loaded.symbol == "ETH-USD"
        assert loaded.risk_model == "rolling_z"


class TestFitSdcaWeightsFromCache:
    def test_missing_cache_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no cached price history"):
            fit_sdca_weights_from_cache(_research_profile(), cache_dir=tmp_path)

    def test_fits_and_regularizes(self, tmp_path: Path) -> None:
        save_cached("ETH-USD", _ohlcv("ETH-USD", 220, start=date(2020, 1, 1)), tmp_path)
        out = tmp_path / "weights.json"
        result = fit_sdca_weights_from_cache(
            _research_profile(),
            cache_dir=tmp_path,
            output_path=out,
            profile_name="eth_research_v1",
            rolling_window=10,
        )
        assert result.symbol == "ETH-USD"
        assert result.num_evaluations > 0
        assert result.weights["valuation"] >= 0.0
        assert abs(sum(result.regularized_weights.values()) - 1.0) < 1e-9
        assert "weekly_rsi_weight" in result.regularized_weight_params
        assert Path(result.path or "").exists()
        assert "weekly_rsi" in result.weights
