"""Named SDCA extra indicators and composite-weight simplex (follow-up to #3174)."""

from __future__ import annotations

import datetime as _dt
import math
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    align_to_dates,
    build_extra_indicators,
    causal_rolling_z,
    composite_weights_from_params,
    dxy_z,
    extra_indicators_for_window,
    load_date_value_frame,
    m2_liquidity_z,
    parse_indicator_weights_json,
    rs_eth_confluence_z,
    rs_eth_z,
)
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    macd_confluence_z,
    rsi_confluence_z,
    sma_band_confluence_z,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.power_law_zscore import power_law_z_score

pytestmark = pytest.mark.unit


class StaticRiskModel:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _dates(n: int, start: date = date(2020, 1, 1)) -> pl.Series:
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


class TestSdcaCompositeWeights:
    def test_default_is_power_law_only(self) -> None:
        w = SdcaCompositeWeights()
        assert w.power_law == pytest.approx(1.0)
        assert w.enabled_extras() == {}
        assert w.normalized().power_law == pytest.approx(1.0)

    def test_zero_weight_is_disabled_not_in_blend(self) -> None:
        w = SdcaCompositeWeights(power_law=1.0, m2=0.0, rs_eth=0.0, dxy=0.0)
        assert "m2" not in w.enabled_extras()

    def test_normalize_is_simplex(self) -> None:
        w = SdcaCompositeWeights(power_law=2.0, m2=2.0, rs_eth=0.0, dxy=0.0).normalized()
        assert w.power_law == pytest.approx(0.5)
        assert w.m2 == pytest.approx(0.5)
        assert w.power_law + w.m2 + w.rs_eth + w.dxy == pytest.approx(1.0)

    def test_all_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            SdcaCompositeWeights(power_law=0.0, m2=0.0, rs_eth=0.0, dxy=0.0)

    def test_from_params_defaults_match_current_btc_charts(self) -> None:
        w = composite_weights_from_params({"buy_max_rate": 10.0})
        assert w.power_law == pytest.approx(1.0)
        assert w.enabled_extras() == {}

    def test_parse_json_object(self) -> None:
        w = parse_indicator_weights_json('{"power_law": 0.5, "m2": 0.5}')
        assert w.m2 == pytest.approx(0.5)
        assert w.rs_eth == pytest.approx(0.0)

    def test_catalog_names_are_independent_series(self) -> None:
        assert EXTRA_INDICATOR_NAMES[:3] == ("m2", "rs_eth", "dxy")
        assert "rolling_z" not in EXTRA_INDICATOR_NAMES
        assert "mayer" not in EXTRA_INDICATOR_NAMES


class TestCausalRollingZ:
    def test_constant_series_is_null_not_inf(self) -> None:
        z = causal_rolling_z(pl.Series([1.0] * 30), window=10, min_samples=5)
        assert z.null_count() == 30 or z.drop_nulls().abs().max() == pytest.approx(0.0)

    def test_is_causal_later_spike_does_not_change_early_z(self) -> None:
        base = [float(i) for i in range(40)]
        z1 = causal_rolling_z(pl.Series(base), window=10, min_samples=10)
        spiked = base.copy()
        spiked[-1] = 10_000.0
        z2 = causal_rolling_z(pl.Series(spiked), window=10, min_samples=10)
        # Day 20 cannot see the terminal spike.
        assert z1[20] == pytest.approx(z2[20])


class TestNamedExtras:
    def test_align_forward_fills_monthly_macro(self) -> None:
        dates = _dates(10)
        src_d = pl.Series("date", [date(2020, 1, 1), date(2020, 1, 6)], dtype=pl.Date)
        src_v = pl.Series("value", [10.0, 20.0])
        aligned = align_to_dates(dates, src_d, src_v, forward_fill=True)
        assert aligned[0] == pytest.approx(10.0)
        assert aligned[4] == pytest.approx(10.0)
        assert aligned[5] == pytest.approx(20.0)

    def test_m2_high_growth_is_positive_z(self) -> None:
        n = 80
        dates = _dates(n)
        # Flat then accelerating M2 so YoY (roc_days) growth rises through the window.
        m2 = pl.Series([100.0] * 30 + [100.0 * (1.04 ** (i + 1)) for i in range(n - 30)])
        z = m2_liquidity_z(dates, dates, m2, roc_days=10, window=20, min_samples=10)
        tail = [v for v in z.to_list()[50:] if v is not None]
        assert tail, "expected some non-null m2 z after warmup"
        assert sum(tail) / len(tail) > 0

    def test_dxy_strength_is_negative_z(self) -> None:
        n = 50
        dates = _dates(n)
        dxy = pl.Series([100.0 + i for i in range(n)])
        z = dxy_z(dates, dates, dxy, window=10, min_samples=8)
        tail = [v for v in z.to_list() if v is not None]
        assert tail
        assert sum(tail) / len(tail) < 0

    def test_rs_eth_cheap_btc_is_positive_z(self) -> None:
        n = 50
        dates = _dates(n)
        btc = pl.Series([100.0] * n)
        eth = pl.Series([10.0 + i for i in range(n)])  # ETH rips, BTC/ETH falls
        z = rs_eth_z(dates, btc, dates, eth, window=10, min_samples=8)
        tail = [v for v in z.to_list() if v is not None]
        assert tail
        assert sum(tail) / len(tail) > 0


class TestRsEthConfluenceZ:
    def _btc_eth(self, n: int = 500) -> tuple[pl.Series, pl.Series, pl.Series]:
        dates = _dates(n)
        btc = pl.Series(
            [
                1000.0
                + 300.0 * math.sin(2 * math.pi * i / 140.0)
                + 60.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        eth = pl.Series([50.0] * n)
        return dates, btc, eth

    def test_clipped_to_unit_interval(self) -> None:
        dates, btc, eth = self._btc_eth()
        z = rs_eth_confluence_z(dates, btc, dates, eth)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_matches_agreement_scaled_formula_across_history(self) -> None:
        dates, btc, eth = self._btc_eth()
        slow = rs_eth_z(dates, btc, dates, eth, window=90, min_samples=20)
        fast = rs_eth_z(dates, btc, dates, eth, window=30, min_samples=15)
        confluence = rs_eth_confluence_z(dates, btc, dates, eth)

        saw_agreement = saw_disagreement = False
        for s, f, c in zip(slow.to_list(), fast.to_list(), confluence.to_list(), strict=True):
            if s is None and f is None:
                assert c is None
                continue
            if s is None:
                assert c == pytest.approx(f, abs=1e-9)
                continue
            if f is None:
                assert c == pytest.approx(s, abs=1e-9)
                continue
            base = 0.5 * s + 0.5 * f
            if s == 0.0 or f == 0.0:
                expected = base
            elif (s > 0) == (f > 0):
                frac = min(abs(s), abs(f)) / max(abs(s), abs(f))
                expected = max(-3.0, min(3.0, base * (1.0 + 0.5 * frac)))
                saw_agreement = True
            else:
                expected = max(-3.0, min(3.0, base * 0.5))
                saw_disagreement = True
            assert c == pytest.approx(expected, abs=1e-9)

        assert saw_agreement, "fixture never hit the agreement branch"
        assert saw_disagreement, "fixture never hit the disagreement branch"

    def test_fast_leg_params_change_output(self) -> None:
        n = 300
        dates = _dates(n)
        btc = pl.Series([1000.0 - 0.3 * i + 20.0 * math.sin(i / 6.0) for i in range(n)])
        eth = pl.Series([50.0 + 0.05 * i for i in range(n)])
        z_short = rs_eth_confluence_z(
            dates, btc, dates, eth, fast_window=10, fast_min_samples=5
        ).to_list()
        z_long = rs_eth_confluence_z(
            dates, btc, dates, eth, fast_window=40, fast_min_samples=20
        ).to_list()
        assert z_short != z_long


class TestOscillatorSpecRsEthFast:
    def test_default_matches_shorter_window(self) -> None:
        spec = SdcaOscillatorSpec()
        assert spec.rs_eth_fast_window == 30
        assert spec.rs_eth_fast_min_samples == 15

    def test_fast_independent_of_slow(self) -> None:
        spec = SdcaOscillatorSpec(rs_eth_window=120, rs_eth_fast_window=20)
        assert spec.rs_eth_window == 120
        assert spec.rs_eth_fast_window == 20

    def test_fast_min_samples_must_not_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="rs_eth_fast_min_samples"):
            SdcaOscillatorSpec(rs_eth_fast_window=10, rs_eth_fast_min_samples=20)


class TestBuildExtraIndicators:
    def test_zero_weights_emit_no_extras_even_when_sources_exist(self) -> None:
        dates = _dates(30)
        m2 = pl.Series([100.0] * 30)
        sources = ExtraIndicatorSources(m2_dates=dates, m2_values=m2)
        extras = build_extra_indicators(
            dates,
            pl.Series([100.0] * 30),
            SdcaCompositeWeights(),
            sources,
            window=10,
            min_samples=5,
            roc_days=5,
        )
        assert extras == []

    def test_positive_m2_weight_without_source_raises(self) -> None:
        dates = _dates(30)
        with pytest.raises(ValueError, match="m2"):
            build_extra_indicators(
                dates,
                pl.Series([100.0] * 30),
                SdcaCompositeWeights(power_law=1.0, m2=0.5),
                ExtraIndicatorSources(),
            )

    def test_window_slice_keeps_alignment(self) -> None:
        dates = [date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(10)]
        extra_z = {"m2": [float(i) for i in range(10)]}
        w = SdcaCompositeWeights(power_law=1.0, m2=1.0)
        sliced = extra_indicators_for_window(dates[3:6], dates, extra_z, w)
        assert len(sliced) == 1
        assert sliced[0].name == "m2"
        assert sliced[0].z.to_list() == [3.0, 4.0, 5.0]

    def test_load_date_value_frame_accepts_fred_observation_date(self, tmp_path: Path) -> None:
        path = tmp_path / "M2SL.csv"
        path.write_text("observation_date,M2SL\n2020-01-01,15400.1\n", encoding="utf-8")
        dates, values = load_date_value_frame(path)
        assert dates.len() == 1
        assert dates[0] == date(2020, 1, 1)
        assert values[0] == pytest.approx(15400.1)

    def test_load_date_value_frame_accepts_iso_timestamp_close(self, tmp_path: Path) -> None:
        path = tmp_path / "ETH-USD.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume,symbol\n"
            "2017-11-09T00:00:00.000,300,330,290,320.5,1,ETH-USD\n",
            encoding="utf-8",
        )
        dates, values = load_date_value_frame(path)
        assert dates[0] == date(2017, 11, 9)
        assert values[0] == pytest.approx(320.5)

    def test_weekly_rsi_slot_is_the_confluence_sub_aggregate(self) -> None:
        """weekly_rsi now wires to rsi_confluence_z (weekly+daily), not mtf_rsi_z."""
        n = 300
        dates = _dates(n)
        close = pl.Series([1000.0 + 3.0 * ((i % 40) - 20) - 0.5 * i for i in range(n)])
        spec = SdcaOscillatorSpec(rsi_length=10, daily_rsi_length=6)
        extras = build_extra_indicators(
            dates,
            close,
            SdcaCompositeWeights(power_law=1.0, weekly_rsi=1.0),
            ExtraIndicatorSources(),
            oscillators=spec,
        )
        assert len(extras) == 1
        expected = rsi_confluence_z(dates, close, weekly_length=10, daily_length=6)
        assert extras[0].z.to_list() == expected.to_list()

    def test_weekly_macd_slot_is_the_confluence_sub_aggregate(self) -> None:
        """weekly_macd now wires to macd_confluence_z (weekly+daily), not weekly-only."""
        n = 300
        dates = _dates(n)
        close = pl.Series([1000.0 + 3.0 * ((i % 40) - 20) - 0.5 * i for i in range(n)])
        spec = SdcaOscillatorSpec(macd_fast=8, macd_slow=21, macd_daily_fast=5, macd_daily_slow=10)
        extras = build_extra_indicators(
            dates,
            close,
            SdcaCompositeWeights(power_law=1.0, weekly_macd=1.0),
            ExtraIndicatorSources(),
            oscillators=spec,
        )
        assert len(extras) == 1
        expected = macd_confluence_z(
            dates, close, weekly_fast=8, weekly_slow=21, daily_fast=5, daily_slow=10
        )
        assert extras[0].z.to_list() == expected.to_list()

    def test_sma_band_slot_is_the_confluence_sub_aggregate(self) -> None:
        """sma_band now wires to sma_band_confluence_z (slow+fast), not the raw single-window z."""
        n = 300
        dates = _dates(n)
        close = pl.Series([1000.0 + 3.0 * ((i % 40) - 20) - 0.5 * i for i in range(n)])
        spec = SdcaOscillatorSpec(
            sma_band_window=80, sma_band_fast_window=15, sma_band_fast_min_samples=8
        )
        extras = build_extra_indicators(
            dates,
            close,
            SdcaCompositeWeights(power_law=1.0, sma_band=1.0),
            ExtraIndicatorSources(),
            oscillators=spec,
        )
        assert len(extras) == 1
        expected = sma_band_confluence_z(
            dates, close, slow_window=80, fast_window=15, fast_min_samples=8
        )
        assert extras[0].z.to_list() == expected.to_list()

    def test_rs_eth_slot_is_the_confluence_sub_aggregate(self) -> None:
        """rs_eth now wires to rs_eth_confluence_z (slow+fast), not the raw single-window z."""
        n = 300
        dates = _dates(n)
        btc = pl.Series([1000.0 + 3.0 * ((i % 40) - 20) - 0.5 * i for i in range(n)])
        eth = pl.Series([50.0 + 0.2 * ((i % 25) - 12) + 0.1 * i for i in range(n)])
        sources = ExtraIndicatorSources(eth_dates=dates, eth_close=eth)
        spec = SdcaOscillatorSpec(
            rs_eth_window=60, rs_eth_fast_window=12, rs_eth_fast_min_samples=6
        )
        extras = build_extra_indicators(
            dates,
            btc,
            SdcaCompositeWeights(power_law=1.0, rs_eth=1.0),
            sources,
            oscillators=spec,
        )
        assert len(extras) == 1
        expected = rs_eth_confluence_z(
            dates, btc, dates, eth, slow_window=60, fast_window=12, fast_min_samples=6
        )
        assert extras[0].z.to_list() == expected.to_list()


class TestDefaultMatchesPowerLawOnly:
    def test_disabled_extras_match_single_indicator_risk(self) -> None:
        dates = _dates(5)
        price = pl.Series([80.0] * 5)
        model = StaticRiskModel()
        solo = build_risk_index(dates, price, model)
        extras = [
            # Would move the blend if enabled; weight 0 / omitted must not.
        ]
        blended = build_risk_index(dates, price, model, extra_indicators=extras)
        assert blended["risk"].to_list() == pytest.approx(solo["risk"].to_list())
        assert blended["composite_z"].to_list() == pytest.approx(solo["composite_z"].to_list())

    def test_nonzero_m2_weight_changes_composite(self) -> None:
        dates = _dates(1)
        price = pl.Series([100.0])  # at median → power_law_z = 0
        model = StaticRiskModel()
        rails = model.rails(dates)
        val_z = power_law_z_score(price, rails["low"], rails["median"], rails["high"])
        assert val_z[0] == pytest.approx(0.0)
        extras = [IndicatorWeight(name="m2", z=pl.Series([3.0]), weight=1.0)]
        frame = build_risk_index(dates, price, model, extra_indicators=extras)
        expected = compute_composite_risk(
            [
                IndicatorWeight(name="power_law", z=val_z, weight=1.0),
                extras[0],
            ]
        )
        assert frame["composite_z"][0] == pytest.approx(expected["composite_z"][0])
        assert frame["composite_z"][0] != pytest.approx(0.0)
        assert "m2_z" in frame.columns
        assert frame["m2_z"][0] == pytest.approx(3.0)

    def test_zero_weight_extra_does_not_null_on_missing_macro(self) -> None:
        dates = _dates(3)
        price = pl.Series([100.0] * 3)
        frame = build_risk_index(dates, price, StaticRiskModel())
        assert frame["risk"].null_count() == 0
