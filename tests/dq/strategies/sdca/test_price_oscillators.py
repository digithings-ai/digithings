"""Weekly RSI / MACD and SMA-band z — causal, ISO-week, no lookahead."""

from __future__ import annotations

import datetime as _dt
import math
from datetime import date

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    PRICE_OSCILLATOR_NAMES,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    build_extra_indicators,
    composite_weights_from_params,
)
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    agreement_scaled_blend,
    completed_monthly_closes,
    completed_weekly_closes,
    daily_macd_z,
    daily_rsi_z,
    macd_confluence_z,
    monthly_rsi_z,
    rsi_confluence_z,
    rsi_deadzone_z,
    sma_band_z,
    weekly_macd_z,
    weekly_rsi_z,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 6)) -> pl.Series:
    """Default start is a Monday so ISO weeks line up."""
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


class TestCompletedWeeklyCloses:
    def test_drops_in_progress_iso_week(self) -> None:
        # Mon 6 Jan 2020 … Wed 22 Jan 2020 (week of 20 Jan is incomplete).
        dates = _dates(17)
        close = pl.Series([float(i + 1) for i in range(17)])
        weekly = completed_weekly_closes(dates, close)
        week_ends = weekly["week_end"].to_list()
        assert date(2020, 1, 12) in week_ends  # first full week Sun
        assert date(2020, 1, 19) in week_ends  # second full week Sun
        assert date(2020, 1, 22) not in week_ends  # incomplete Wed

    def test_weekly_close_is_last_daily_of_completed_week(self) -> None:
        dates = _dates(14)
        close = pl.Series([10.0 + i for i in range(14)])
        weekly = completed_weekly_closes(dates, close)
        # Week Mon 6–Sun 12 Jan: last close is day index 6 (value 16.0).
        first = weekly.filter(pl.col("week_end") == date(2020, 1, 12))
        assert first.height == 1
        assert first["close"][0] == pytest.approx(16.0)


class TestRsiDeadzone:
    def test_mid_cycle_maps_to_zero(self) -> None:
        rsi = pl.Series([30.0, 50.0, 80.0, 20.0, 85.0, 100.0])
        z = rsi_deadzone_z(rsi).to_list()
        assert z[0] == pytest.approx(0.0)
        assert z[1] == pytest.approx(0.0)
        assert z[2] == pytest.approx(0.0)
        assert z[3] == pytest.approx(3.0)
        assert z[4] == pytest.approx(-3.0)
        assert z[5] == pytest.approx(-3.0)


class TestWeeklyRsiZ:
    def test_oversold_weekly_rsi_is_positive_z(self) -> None:
        n = 280  # ~40 weeks
        dates = _dates(n)
        # Steady grind down so weekly RSI sits well below 50.
        close = pl.Series([1000.0 - 2.0 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-60:] if v is not None]
        assert tail, "expected weekly RSI z after warmup"
        assert sum(tail) / len(tail) > 0.5

    def test_overbought_weekly_rsi_is_negative_z(self) -> None:
        n = 280
        dates = _dates(n)
        close = pl.Series([100.0 + 2.0 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-60:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) < -0.5

    def test_wednesday_does_not_see_same_week_friday_spike(self) -> None:
        n = 250
        dates = _dates(n)
        # Oscillate so weekly RSI is not already clipped at ±3.
        base = [100.0 + 8.0 * ((i % 20) - 10) for i in range(n)]
        z1 = weekly_rsi_z(dates, pl.Series(base))
        spiked = base.copy()
        # Spike the ISO week-end (Sunday). Wednesday of that week must not see it;
        # the following Monday must.
        sunday = date(2020, 5, 17)
        idx = dates.to_list().index(sunday)
        spiked[idx] = 10_000.0
        z2 = weekly_rsi_z(dates, pl.Series(spiked))
        wednesday = date(2020, 5, 13)
        w_idx = dates.to_list().index(wednesday)
        assert z1[w_idx] is not None
        assert z1[w_idx] == pytest.approx(z2[w_idx])
        next_monday = date(2020, 5, 18)
        m_idx = dates.to_list().index(next_monday)
        assert z1[m_idx] != pytest.approx(z2[m_idx])

    def test_clipped_to_unit_interval(self) -> None:
        n = 200
        dates = _dates(n)
        close = pl.Series([50.0 + i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_mid_bull_rsi_does_not_sit_at_floor_for_entire_bull(self) -> None:
        n = 7 * 160
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [10_000.0 * (1.002**i) * (1.0 + 0.03 * ((i % 40) / 20.0 - 1.0)) for i in range(n)]
        )
        z = weekly_rsi_z(dates, close)
        mid = [v for v in z.to_list()[400:1600] if v is not None]
        assert len(mid) > 200
        floor_days = sum(1 for v in mid if v <= -2.5)
        assert floor_days / len(mid) < 0.25
        assert abs(sum(mid) / len(mid)) < 1.25

    def test_blowoff_rsi_still_votes_rich(self) -> None:
        n = 280
        dates = _dates(n)
        close = pl.Series([100.0 + 8.0 * i for i in range(n)])
        z = weekly_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-40:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) < -1.5


class TestWeeklyMacdZ:
    def test_default_macd_weight_is_zero(self) -> None:
        w = SdcaCompositeWeights()
        assert w.weekly_macd == pytest.approx(0.0)
        assert "weekly_macd" not in w.enabled_extras()

    def test_macd_is_causal_asof_like_rsi(self) -> None:
        n = 800
        dates = _dates(n)
        base = [100.0 + 4.0 * ((i % 30) - 15) for i in range(n)]
        z1 = weekly_macd_z(dates, pl.Series(base))
        spiked = base.copy()
        sunday = date(2021, 6, 13)
        idx = dates.to_list().index(sunday)
        spiked[idx] = 50_000.0
        z2 = weekly_macd_z(dates, pl.Series(spiked))
        wednesday = date(2021, 6, 9)
        w_idx = dates.to_list().index(wednesday)
        assert z1[w_idx] is not None
        assert z1[w_idx] == pytest.approx(z2[w_idx])
        next_monday = date(2021, 6, 14)
        m_idx = dates.to_list().index(next_monday)
        assert z1[m_idx] is not None
        assert z1[m_idx] != pytest.approx(z2[m_idx])

    def test_persistent_log_macd_does_not_renormalize_to_neutral(self) -> None:
        n = 7 * 200
        dates = _dates(n, start=date(2016, 1, 4))
        close = pl.Series([1_000.0 * (1.003**i) for i in range(n)])
        z = weekly_macd_z(dates, close)
        late = [v for v in z.to_list()[-400:] if v is not None]
        assert len(late) > 100
        assert sum(late) / len(late) < -0.5


class TestMonthlyRsiZ:
    def test_drops_in_progress_calendar_month(self) -> None:
        dates = _dates(46, start=date(2020, 1, 1))
        close = pl.Series([float(i + 1) for i in range(46)])
        monthly = completed_monthly_closes(dates, close)
        assert date(2020, 1, 31) in monthly["month_end"].to_list()
        assert date(2020, 2, 15) not in monthly["month_end"].to_list()

    def test_mid_month_does_not_see_same_month_close(self) -> None:
        n = 1400
        dates = _dates(n, start=date(2017, 1, 2))
        base = [100.0 + 8.0 * ((i % 40) - 20) for i in range(n)]
        z1 = monthly_rsi_z(dates, pl.Series(base))
        spiked = base.copy()
        idx = dates.to_list().index(date(2020, 1, 31))
        spiked[idx] = 50_000.0
        z2 = monthly_rsi_z(dates, pl.Series(spiked))
        m_idx = dates.to_list().index(date(2020, 1, 15))
        assert z1[m_idx] is not None
        assert z1[m_idx] == pytest.approx(z2[m_idx])
        f_idx = dates.to_list().index(date(2020, 2, 1))
        assert z1[f_idx] is not None
        assert z1[f_idx] != pytest.approx(z2[f_idx])


class TestDailyRsiZ:
    def test_oversold_daily_rsi_is_positive_z(self) -> None:
        n = 60
        dates = _dates(n)
        close = pl.Series([1000.0 - 5.0 * i for i in range(n)])
        z = daily_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-20:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) > 0.5

    def test_overbought_daily_rsi_is_negative_z(self) -> None:
        n = 60
        dates = _dates(n)
        close = pl.Series([100.0 + 5.0 * i for i in range(n)])
        z = daily_rsi_z(dates, close)
        tail = [v for v in z.to_list()[-20:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) < -0.5

    def test_clipped_to_unit_interval(self) -> None:
        n = 60
        dates = _dates(n)
        close = pl.Series([50.0 + i for i in range(n)])
        z = daily_rsi_z(dates, close)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_no_asof_lag_reacts_to_the_same_day(self) -> None:
        """Unlike weekly/monthly RSI, daily RSI needs no join-asof broadcast."""
        n = 60
        dates = _dates(n)
        base = [100.0 + 4.0 * ((i % 10) - 5) for i in range(n)]
        z1 = daily_rsi_z(dates, pl.Series(base))
        spiked = base.copy()
        spiked[40] = 10_000.0
        z2 = daily_rsi_z(dates, pl.Series(spiked))
        assert z1[40] != pytest.approx(z2[40])


class TestRsiConfluenceZ:
    def test_clipped_to_unit_interval(self) -> None:
        n = 400
        dates = _dates(n)
        close = pl.Series(
            [1000.0 - 0.5 * i + 15.0 * math.sin(i / 5.0) for i in range(n)]
        )
        z = rsi_confluence_z(dates, close, weekly_length=8, daily_length=10)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_matches_agreement_scaled_formula_across_history(self) -> None:
        """Reconstruct the blend independently from the weekly/daily legs.

        Cross-checks both the wiring (weekly + daily are actually combined)
        and the arithmetic (amplify on agreement, damp on disagreement, pass
        through when one leg is at the dead-zone) against real generated
        price data instead of hand-picked edge cases.
        """
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly_length, daily_length = 8, 10
        weekly = weekly_rsi_z(dates, close, length=weekly_length)
        daily = daily_rsi_z(dates, close, length=daily_length)
        confluence = rsi_confluence_z(
            dates, close, weekly_length=weekly_length, daily_length=daily_length
        )

        saw_agreement = saw_disagreement = False
        for w, d, c in zip(weekly.to_list(), daily.to_list(), confluence.to_list(), strict=True):
            if w is None and d is None:
                assert c is None
                continue
            if w is None:
                assert c == pytest.approx(d, abs=1e-9)
                continue
            if d is None:
                assert c == pytest.approx(w, abs=1e-9)
                continue
            base = 0.5 * w + 0.5 * d
            if w == 0.0 or d == 0.0:
                expected = base
            elif (w > 0) == (d > 0):
                frac = min(abs(w), abs(d)) / max(abs(w), abs(d))
                expected = max(-3.0, min(3.0, base * (1.0 + 0.5 * frac)))
                saw_agreement = True
            else:
                expected = max(-3.0, min(3.0, base * 0.5))
                saw_disagreement = True
            assert c == pytest.approx(expected, abs=1e-9)

        assert saw_agreement, "fixture never hit the agreement branch"
        assert saw_disagreement, "fixture never hit the disagreement branch"

    def test_agreement_amplifies_beyond_simple_average(self) -> None:
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly_length, daily_length = 8, 10
        weekly = weekly_rsi_z(dates, close, length=weekly_length).to_list()
        daily = daily_rsi_z(dates, close, length=daily_length).to_list()
        confluence = rsi_confluence_z(
            dates, close, weekly_length=weekly_length, daily_length=daily_length
        ).to_list()
        checked = 0
        for w, d, c in zip(weekly, daily, confluence, strict=True):
            if w is None or d is None or w == 0.0 or d == 0.0:
                continue
            base = 0.5 * w + 0.5 * d
            if (w > 0) == (d > 0) and abs(base) < 2.9:
                assert abs(c) >= abs(base) - 1e-9
                checked += 1
        assert checked > 0, "fixture never produced an unclipped agreement case"

    def test_disagreement_damps_toward_zero(self) -> None:
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly_length, daily_length = 8, 10
        weekly = weekly_rsi_z(dates, close, length=weekly_length).to_list()
        daily = daily_rsi_z(dates, close, length=daily_length).to_list()
        confluence = rsi_confluence_z(
            dates, close, weekly_length=weekly_length, daily_length=daily_length
        ).to_list()
        checked = 0
        for w, d, c in zip(weekly, daily, confluence, strict=True):
            if w is None or d is None or w == 0.0 or d == 0.0:
                continue
            if (w > 0) != (d > 0):
                base = 0.5 * w + 0.5 * d
                assert abs(c) <= abs(base) + 1e-9
                checked += 1
        assert checked > 0, "fixture never produced a disagreement case"

    def test_daily_length_changes_output(self) -> None:
        n = 200
        dates = _dates(n)
        close = pl.Series(
            [1000.0 - 0.3 * i + 20.0 * math.sin(i / 6.0) for i in range(n)]
        )
        z_short = rsi_confluence_z(dates, close, weekly_length=8, daily_length=5).to_list()
        z_long = rsi_confluence_z(dates, close, weekly_length=8, daily_length=30).to_list()
        assert z_short != z_long


class TestOscillatorSpecDailyRsiLength:
    def test_default_matches_rsi_length(self) -> None:
        spec = SdcaOscillatorSpec()
        assert spec.daily_rsi_length == 14

    def test_daily_rsi_length_independent_of_weekly(self) -> None:
        spec = SdcaOscillatorSpec(rsi_length=21, daily_rsi_length=7)
        assert spec.rsi_length == 21
        assert spec.daily_rsi_length == 7


class TestAgreementScaledBlend:
    def test_either_leg_zero_skips_amplify_damp(self) -> None:
        """A silent leg (z == 0) is not a disagreement, so the multiplier
        stays 1.0 -- but the weighted base blend (including the zero) still
        applies, it is not a raw pass-through of the nonzero leg.
        """
        z = agreement_scaled_blend(
            pl.Series([0.0, 2.0]),
            pl.Series([1.5, 0.0]),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="x",
        )
        assert z.to_list() == pytest.approx([0.75, 1.0])

    def test_agreement_amplifies_disagreement_damps(self) -> None:
        agree = agreement_scaled_blend(
            pl.Series([1.0]),
            pl.Series([1.0]),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="x",
        )
        disagree = agreement_scaled_blend(
            pl.Series([1.0]),
            pl.Series([-1.0]),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="x",
        )
        assert agree[0] == pytest.approx(1.5)  # base 1.0 * (1 + 0.5*1.0)
        assert disagree[0] == pytest.approx(0.0)  # base 0.0 * 0.5

    def test_nulls_pass_through(self) -> None:
        z = agreement_scaled_blend(
            pl.Series([None, 1.0], dtype=pl.Float64),
            pl.Series([None, None], dtype=pl.Float64),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="x",
        )
        assert z.to_list() == [None, 1.0]


class TestDailyMacdZ:
    def test_clipped_to_unit_interval(self) -> None:
        n = 300
        dates = _dates(n)
        close = pl.Series([1000.0 + 50.0 * math.sin(i / 9.0) for i in range(n)])
        z = daily_macd_z(dates, close)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_is_causal_no_lookahead(self) -> None:
        n = 300
        dates = _dates(n)
        base = [1000.0 + 50.0 * math.sin(i / 9.0) for i in range(n)]
        z1 = daily_macd_z(dates, pl.Series(base))
        spiked = base.copy()
        spiked[-1] = 50_000.0
        z2 = daily_macd_z(dates, pl.Series(spiked))
        assert z1[100] == pytest.approx(z2[100])
        assert z1[-1] != pytest.approx(z2[-1])

    def test_sharp_dip_against_stable_regime_is_positive_z(self) -> None:
        """A few-months momentum dip inside an otherwise-flat regime should
        register against its own recent history -- exactly the medium-term
        signal a whole-history/weekly-scale leg would miss.
        """
        stable = [1000.0 + 5.0 * math.sin(i / 11.0) for i in range(200)]
        dip = [stable[-1] * (0.985**i) for i in range(1, 40)]
        close = pl.Series(stable + dip)
        dates = _dates(close.len())
        z = daily_macd_z(dates, close, z_window=90, min_samples=30)
        tail = [v for v in z.to_list()[-10:] if v is not None]
        assert tail
        assert sum(tail) / len(tail) > 0.5


class TestMacdConfluenceZ:
    def test_clipped_to_unit_interval(self) -> None:
        n = 400
        dates = _dates(n)
        close = pl.Series([1000.0 - 0.5 * i + 15.0 * math.sin(i / 5.0) for i in range(n)])
        z = macd_confluence_z(dates, close)
        finite = [v for v in z.to_list() if v is not None]
        assert finite
        assert max(finite) <= 3.0 + 1e-9
        assert min(finite) >= -3.0 - 1e-9

    def test_matches_agreement_scaled_formula_across_history(self) -> None:
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly = weekly_macd_z(dates, close)
        daily = daily_macd_z(dates, close)
        confluence = macd_confluence_z(dates, close)

        saw_agreement = saw_disagreement = False
        for w, d, c in zip(weekly.to_list(), daily.to_list(), confluence.to_list(), strict=True):
            if w is None and d is None:
                assert c is None
                continue
            if w is None:
                assert c == pytest.approx(d, abs=1e-9)
                continue
            if d is None:
                assert c == pytest.approx(w, abs=1e-9)
                continue
            base = 0.5 * w + 0.5 * d
            if w == 0.0 or d == 0.0:
                expected = base
            elif (w > 0) == (d > 0):
                frac = min(abs(w), abs(d)) / max(abs(w), abs(d))
                expected = max(-3.0, min(3.0, base * (1.0 + 0.5 * frac)))
                saw_agreement = True
            else:
                expected = max(-3.0, min(3.0, base * 0.5))
                saw_disagreement = True
            assert c == pytest.approx(expected, abs=1e-9)

        assert saw_agreement, "fixture never hit the agreement branch"
        assert saw_disagreement, "fixture never hit the disagreement branch"

    def test_agreement_amplifies_beyond_simple_average(self) -> None:
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly = weekly_macd_z(dates, close).to_list()
        daily = daily_macd_z(dates, close).to_list()
        confluence = macd_confluence_z(dates, close).to_list()
        checked = 0
        for w, d, c in zip(weekly, daily, confluence, strict=True):
            if w is None or d is None or w == 0.0 or d == 0.0:
                continue
            base = 0.5 * w + 0.5 * d
            if (w > 0) == (d > 0) and abs(base) < 2.9:
                assert abs(c) >= abs(base) - 1e-9
                checked += 1
        assert checked > 0, "fixture never produced an unclipped agreement case"

    def test_disagreement_damps_toward_zero(self) -> None:
        n = 500
        dates = _dates(n, start=date(2018, 1, 1))
        close = pl.Series(
            [
                1000.0
                + 800.0 * math.sin(2 * math.pi * i / 140.0)
                + 80.0 * math.sin(2 * math.pi * i / 33.0)
                for i in range(n)
            ]
        )
        weekly = weekly_macd_z(dates, close).to_list()
        daily = daily_macd_z(dates, close).to_list()
        confluence = macd_confluence_z(dates, close).to_list()
        checked = 0
        for w, d, c in zip(weekly, daily, confluence, strict=True):
            if w is None or d is None or w == 0.0 or d == 0.0:
                continue
            if (w > 0) != (d > 0):
                base = 0.5 * w + 0.5 * d
                assert abs(c) <= abs(base) + 1e-9
                checked += 1
        assert checked > 0, "fixture never produced a disagreement case"

    def test_daily_leg_params_change_output(self) -> None:
        n = 300
        dates = _dates(n)
        close = pl.Series([1000.0 - 0.3 * i + 20.0 * math.sin(i / 6.0) for i in range(n)])
        z_short = macd_confluence_z(dates, close, daily_fast=5, daily_slow=10).to_list()
        z_long = macd_confluence_z(dates, close, daily_fast=12, daily_slow=26).to_list()
        assert z_short != z_long


class TestOscillatorSpecDailyMacd:
    def test_default_matches_weekly_fast_slow(self) -> None:
        spec = SdcaOscillatorSpec()
        assert spec.macd_daily_fast == 12
        assert spec.macd_daily_slow == 26

    def test_daily_independent_of_weekly(self) -> None:
        spec = SdcaOscillatorSpec(macd_fast=8, macd_slow=21, macd_daily_fast=5, macd_daily_slow=10)
        assert spec.macd_fast == 8
        assert spec.macd_slow == 21
        assert spec.macd_daily_fast == 5
        assert spec.macd_daily_slow == 10

    def test_daily_slow_must_exceed_daily_fast(self) -> None:
        with pytest.raises(ValueError, match="macd_daily_slow"):
            SdcaOscillatorSpec(macd_daily_fast=10, macd_daily_slow=10)

    def test_daily_min_samples_must_not_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="macd_daily_min_samples"):
            SdcaOscillatorSpec(macd_daily_z_window=10, macd_daily_min_samples=20)


class TestSmaBandZ:
    def test_below_slow_sma_is_positive_z(self) -> None:
        n = 150
        dates = _dates(n)
        # Flat then a crash: close sits below the 90d SMA.
        close = pl.Series([100.0] * 90 + [60.0] * 60)
        z = sma_band_z(dates, close, window=90, min_samples=30)
        # Right after the crash the SMA has not yet followed; the tail has.
        after = [v for v in z.to_list()[90:110] if v is not None]
        assert after
        assert sum(after) / len(after) > 1.0

    def test_above_slow_sma_is_negative_z(self) -> None:
        n = 150
        dates = _dates(n)
        close = pl.Series([100.0] * 90 + [160.0] * 60)
        z = sma_band_z(dates, close, window=90, min_samples=30)
        after = [v for v in z.to_list()[90:110] if v is not None]
        assert after
        assert sum(after) / len(after) < -1.0

    def test_is_causal(self) -> None:
        n = 120
        dates = _dates(n)
        base = [100.0] * n
        z1 = sma_band_z(dates, pl.Series(base), window=90, min_samples=30)
        spiked = base.copy()
        spiked[-1] = 400.0
        z2 = sma_band_z(dates, pl.Series(spiked), window=90, min_samples=30)
        assert z1[100] == pytest.approx(z2[100])


class TestCatalogWiring:
    def test_price_oscillators_listed_and_default_off(self) -> None:
        assert PRICE_OSCILLATOR_NAMES == ("weekly_rsi", "weekly_macd", "sma_band")
        assert set(PRICE_OSCILLATOR_NAMES).issubset(set(EXTRA_INDICATOR_NAMES))
        w = SdcaCompositeWeights()
        assert w.valuation == pytest.approx(1.0)
        assert w.enabled_extras() == {}

    def test_zero_weight_skips_oscillators(self) -> None:
        dates = _dates(30)
        extras = build_extra_indicators(
            dates,
            pl.Series([100.0] * 30),
            SdcaCompositeWeights(),
            ExtraIndicatorSources(),
        )
        assert extras == []

    def test_positive_weekly_rsi_weight_emits_series(self) -> None:
        n = 200
        dates = _dates(n)
        extras = build_extra_indicators(
            dates,
            pl.Series([100.0 + 0.2 * i for i in range(n)]),
            SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.4),
            ExtraIndicatorSources(),
            window=20,
            min_samples=10,
        )
        names = [e.name for e in extras]
        assert names == ["weekly_rsi"]
        assert extras[0].z.len() == n

    def test_from_params_defaults_keep_btc_charts(self) -> None:
        w = composite_weights_from_params({"buy_max_rate": 10.0})
        assert w.weekly_rsi == pytest.approx(0.0)
        assert w.weekly_macd == pytest.approx(0.0)
        assert w.sma_band == pytest.approx(0.0)
        assert w.enabled_extras() == {}
