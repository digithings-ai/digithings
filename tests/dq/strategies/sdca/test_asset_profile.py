"""Per-asset SDCA profile: generic technicals + plugin extras + cycle windows."""

from __future__ import annotations

import datetime as _dt
import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.history_cache import save_cached
from digiquant.strategies.sdca.asset_profile import (
    BTC_PLUGIN_INDICATOR_NAMES,
    GENERIC_TECHNICAL_NAMES,
    SdcaAssetProfile,
    daily_closes_from_cache,
    daily_closes_from_ohlcv,
    stage_a_search_names,
    technicals_from_ohlcv,
    union_date_range,
)
from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    build_extra_indicators,
)
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    documented_warmup_calendar_days,
    weekly_rsi_z,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.stage_a import CycleOverlapScore, cycle_overlap_score

pytestmark = pytest.mark.unit

_SETTINGS = (
    Path(__file__).resolve().parents[4]
    / "digiquant"
    / "src"
    / "digiquant"
    / "strategies"
    / "settings.json"
)
_ETH_CACHE = Path("data/price-history/ETH-USD.csv")


def _dates(n: int, start: date = date(2020, 1, 6)) -> pl.Series:
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


def _ohlcv_frame(
    ticker: str, n: int, *, start: date = date(2020, 1, 6), seed: int = 1
) -> pl.DataFrame:
    ts = [start + _dt.timedelta(days=i) for i in range(n)]
    close = [100.0 + seed * 0.15 * i + (3.0 if i % 17 == 0 else 0.0) for i in range(n)]
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


def _synthetic_second_asset(n: int = 2500) -> tuple[pl.Series, pl.Series]:
    # Long enough for 90d SMA warmup plus ETH research pins (2018–2022).
    dates = _dates(n, start=date(2016, 1, 1))
    close = pl.Series("close", [80.0 + 0.05 * i + (8.0 if i % 40 == 0 else 0.0) for i in range(n)])
    return dates, close


class TestSdcaOscillatorSpec:
    def test_btc_defaults_are_weekly_14_and_90d_sma(self) -> None:
        spec = SdcaOscillatorSpec()
        assert spec.rsi_length == 14
        assert spec.sma_band_window == 90
        assert spec.macd_fast == 12
        assert spec.macd_slow == 26
        assert spec.macd_signal == 9

    def test_rejects_non_positive_windows(self) -> None:
        with pytest.raises(ValueError):
            SdcaOscillatorSpec(rsi_length=1)


class TestSdcaAssetProfileBtcV1:
    def test_btc_v1_pins_power_law_and_btc_cycle_windows(self) -> None:
        profile = SdcaAssetProfile.btc_v1()
        assert profile.symbol == "BTC-USD"
        assert profile.risk_model == "btc_power_law"
        assert profile.cycle_windows == SdcaCycleWindows.btc_v1()
        assert profile.oscillators.rsi_length == 14
        assert profile.oscillators.sma_band_window == 90
        assert profile.signal_delay_days == 0
        assert set(GENERIC_TECHNICAL_NAMES).issubset(set(profile.extra_indicators))
        assert set(BTC_PLUGIN_INDICATOR_NAMES).issubset(set(profile.extra_indicators))
        assert profile.plugin_extras() == BTC_PLUGIN_INDICATOR_NAMES
        assert profile.generic_technicals() == GENERIC_TECHNICAL_NAMES
        assert stage_a_search_names(profile) == GENERIC_TECHNICAL_NAMES + BTC_PLUGIN_INDICATOR_NAMES

    def test_signal_delay_default_does_not_publish_eth(self) -> None:
        payload = json.loads(_SETTINGS.read_text())
        assert "eth_sdca" not in payload["strategies"]
        assert payload["strategies"]["btc_sdca"]["sdca"]["risk_model"] == "btc_power_law"


class TestSdcaAssetProfileEthResearch:
    def test_eth_research_uses_generic_valuation_and_own_windows(self) -> None:
        profile = SdcaAssetProfile.eth_research_v1()
        assert profile.symbol == "ETH-USD"
        assert profile.risk_model == "generic_valuation"
        assert profile.cycle_windows != SdcaCycleWindows.btc_v1()
        kinds = {w.kind for w in profile.cycle_windows.windows}
        assert CycleKind.PEAK in kinds
        assert CycleKind.TROUGH in kinds
        assert set(profile.extra_indicators) == set(GENERIC_TECHNICAL_NAMES)
        assert "m2" not in profile.extra_indicators
        assert "rs_eth" not in profile.extra_indicators
        assert "dxy" not in profile.extra_indicators
        assert "mvrv" not in profile.extra_indicators
        assert profile.signal_delay_days == 0
        assert stage_a_search_names(profile) == GENERIC_TECHNICAL_NAMES

    def test_rejects_btc_plugin_not_on_allowlist(self) -> None:
        profile = SdcaAssetProfile.eth_research_v1()
        with pytest.raises(ValueError, match="allowlist"):
            profile.ensure_extras_allowed(SdcaCompositeWeights(power_law=1.0, m2=0.5))


class TestDailyClosesFromOhlcv:
    def test_same_code_path_for_two_tickers(self, tmp_path: Path) -> None:
        btc = _ohlcv_frame("BTC-USD", 20, seed=1)
        eth = _ohlcv_frame("ETH-USD", 20, seed=2)
        save_cached("BTC-USD", btc, tmp_path)
        save_cached("ETH-USD", eth, tmp_path)
        btc_dates, btc_close = daily_closes_from_cache("BTC-USD", tmp_path)
        eth_dates, eth_close = daily_closes_from_cache("ETH-USD", tmp_path)
        assert btc_dates.dtype == pl.Date
        assert eth_dates.dtype == pl.Date
        assert btc_dates.len() == eth_dates.len() == 20
        assert btc_close[-1] != pytest.approx(eth_close[-1])
        from_frame = daily_closes_from_ohlcv(btc)
        assert from_frame[0].to_list() == btc_dates.to_list()
        assert from_frame[1].to_list() == btc_close.to_list()

    def test_missing_cache_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no cached price history"):
            daily_closes_from_cache("SOL-USD", tmp_path)


class TestGenericTechnicalsFromAnyOhlcv:
    def test_btc_and_second_asset_share_oscillator_path(self) -> None:
        n = 220
        btc_dates, btc_close = daily_closes_from_ohlcv(_ohlcv_frame("BTC-USD", n, seed=1))
        eth_dates, eth_close = daily_closes_from_ohlcv(_ohlcv_frame("ETH-USD", n, seed=3))
        spec = SdcaOscillatorSpec()
        btc_z = technicals_from_ohlcv(btc_dates, btc_close, spec)
        eth_z = technicals_from_ohlcv(eth_dates, eth_close, spec)
        assert set(btc_z) == set(eth_z) == set(GENERIC_TECHNICAL_NAMES)
        assert len(btc_z["weekly_rsi"]) == n
        assert len(eth_z["sma_band"]) == n
        assert btc_z["weekly_rsi"] != eth_z["weekly_rsi"]

    def test_calibrated_rsi_length_changes_z(self) -> None:
        n = 400
        dates = _dates(n)
        # Chop, then a blow-off: RSI(14) crosses the rich cap before RSI(28).
        close = pl.Series(
            [100.0 + 4.0 * ((i % 20) - 10) for i in range(200)]
            + [100.0 + 5.0 * i for i in range(200)]
        )
        default = weekly_rsi_z(dates, close)
        slower = weekly_rsi_z(dates, close, length=28)
        finite = [
            (float(a), float(b))
            for a, b in zip(default.to_list(), slower.to_list(), strict=True)
            if a is not None and b is not None and a == a and b == b
        ]
        assert len(finite) > 10
        assert any(abs(a - b) > 1e-6 for a, b in finite)

    def test_build_extras_honor_profile_spec_and_allowlist(self) -> None:
        n = 200
        dates, close = daily_closes_from_ohlcv(_ohlcv_frame("ETH-USD", n, seed=4))
        profile = SdcaAssetProfile.eth_research_v1()
        extras = build_extra_indicators(
            dates,
            close,
            SdcaCompositeWeights(power_law=1.0, weekly_rsi=0.4, sma_band=0.2),
            ExtraIndicatorSources(),
            oscillators=profile.oscillators,
            allowlist=profile.extra_indicators,
        )
        # weekly_macd/monthly_rsi/monthly_macd are allowlist-gated only (like
        # weekly_rsi/sma_band), so they're still materialized here for display
        # even though their weight is 0.
        by_name = {e.name: e for e in extras}
        assert set(by_name) == {
            "weekly_rsi",
            "weekly_macd",
            "sma_band",
            "monthly_rsi",
            "monthly_macd",
        }
        assert by_name["weekly_rsi"].enabled
        assert by_name["sma_band"].enabled
        assert not by_name["weekly_macd"].enabled
        assert not by_name["monthly_rsi"].enabled
        assert not by_name["monthly_macd"].enabled


class TestSecondAssetSmoke:
    def test_eth_or_synthetic_builds_risk_via_profile(self) -> None:
        profile = SdcaAssetProfile.eth_research_v1()
        used_cache = False
        if _ETH_CACHE.exists():
            try:
                dates, close = daily_closes_from_cache("ETH-USD", _ETH_CACHE.parent)
                used_cache = dates.len() >= 730
            except ValueError:
                used_cache = False
        if not used_cache:
            dates, close = _synthetic_second_asset()

        def _risk_and_overlap(
            series_dates: pl.Series, series_close: pl.Series
        ) -> tuple[pl.DataFrame, CycleOverlapScore]:
            model = resolve_sdca_risk_model(
                profile.risk_model,
                dates=series_dates,
                price=series_close,
            )
            extras = build_extra_indicators(
                series_dates,
                series_close,
                SdcaCompositeWeights(power_law=1.0, weekly_rsi=0.3, sma_band=0.2),
                ExtraIndicatorSources(),
                oscillators=profile.oscillators,
                allowlist=profile.extra_indicators,
            )
            built = build_risk_index(
                series_dates,
                series_close,
                model,
                extra_indicators=extras,
                power_law_weight=1.0,
            )
            overlap = cycle_overlap_score(
                series_dates.to_list(),
                built["risk"].to_list(),
                profile.cycle_windows,
            )
            return built, overlap

        try:
            frame, score = _risk_and_overlap(dates, close)
        except ValueError:
            # CI cache can exist and still miss ETH research pins (prefix / warmup).
            if not used_cache:
                raise
            used_cache = False
            dates, close = _synthetic_second_asset()
            frame, score = _risk_and_overlap(dates, close)

        if used_cache:
            # Full Coinbase cache, not a 900-day prefix (BTC died Jan 2018).
            assert dates.len() > 900
            assert dates[-1].year >= 2025
        assert frame.height == dates.len()
        assert frame["risk"].null_count() < frame.height
        complete = frame.filter(pl.col("risk").is_not_null())
        assert complete.height > 0
        assert complete["risk"].is_finite().all()
        # Cycle windows are per-asset; overlap scoring must accept ETH pins.
        assert score.trough_days > 0
        assert score.peak_days > 0
        assert not used_cache or profile.symbol == "ETH-USD"


class TestUnionDateRange:
    def test_shared_xlim_does_not_inner_join_to_shorter_asset(self) -> None:
        btc = _dates(2000, start=date(2015, 7, 20))
        eth = _dates(1500, start=date(2017, 11, 9))
        start, end = union_date_range(btc, eth)
        assert start == btc[0]
        assert end == max(btc[-1], eth[-1])
        assert start < eth[0]
        inner_end = min(btc[-1], eth[-1])
        assert end > inner_end


class TestOscillatorWarmupIsLeadingGap:
    def test_weekly_rsi_nulls_are_a_short_leading_gap_not_a_2018_cliff(self) -> None:
        n = 2000
        dates = _dates(n, start=date(2015, 7, 20))
        close = pl.Series([100.0 + 0.05 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        values = z.to_list()
        first_finite = next(i for i, v in enumerate(values) if v is not None and v == v)
        warmup = documented_warmup_calendar_days()
        assert first_finite <= warmup
        assert first_finite < 200
        assert dates[first_finite].year == 2015
        assert values[-1] is not None
        leading_nulls = first_finite
        trailing_finite = sum(1 for v in values[first_finite:] if v is not None and v == v)
        assert trailing_finite == n - leading_nulls
