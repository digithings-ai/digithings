"""Multi-timeframe RSI / MACD / SMA-band confluence family.

Leaf 1 of the SDCA research port from ``claude/sdca-develop-sync`` (DIG-1597).

This leaf is **additive only**. It lands the branch's agreement-scaled
confluence family — the continuous (no dead zone) RSI map, the daily legs,
and the three pairings each of RSI / log-MACD / SMA-band gets from combining
a long-term and a medium-term timeframe — *alongside* develop's existing
dead-zone oscillators.

Two regression nets matter as much as the new behaviour:

* ``TestDevelopApiUnchanged`` pins that ``rsi_deadzone_z``, ``weekly_rsi_z``,
  ``monthly_rsi_z``, ``mtf_rsi_z`` and ``price_oscillator_z_vectors`` still
  behave exactly as they do on develop. Switching the *published* oscillators
  to the continuous map is a separate, separately-measured leaf; if it ever
  lands, it lands with a delta note, not silently here.
* ``TestNoLookAhead`` truncates the input series and pins that every earlier
  value is unchanged. Weekly/monthly legs broadcast completed-period values
  with ``join_asof(..., strategy="backward")``, so a Wednesday must never see
  its week's Friday close. A confluence vote that leaks would look good and be
  worth nothing.

All inputs are deterministic synthetic series — no seeds, no fixtures to
regenerate, so every number below is reproducible from one command:

    PYTHONPATH="$PWD/digiquant/src" python -m pytest \
        tests/dq/strategies/sdca/test_price_oscillators_confluence.py

The two headline measurements this file rests on, both reproducible from that
one command and asserted rather than assumed:

* the calm-then-shock sign flip — crash tail mean z **+2.32** (every bar
  positive), rally tail mean z **-0.02**, over the last 80 bars of a 400-bar
  series;
* the daily MACD rolling window — a single bar perturbed by +50% at distance
  60 moves the final z by **1.5e-02**, at distance 300 by **4.0e-08**, which
  is the gap the `_MACD_DAILY_Z_WINDOW = 90` thresholds sit in.

Both suites were mutation-checked: ten deliberate defects injected into
`price_oscillators.py` (look-ahead `join_asof`, swapped boost/damp, removed
silent-leg passthrough, widened clip, dropped sign flip, widened z-window,
removed magnitude weighting, shifted RSI midpoint, broken null passthrough)
were each caught by at least one test here.
"""

from __future__ import annotations

import datetime as _dt
from datetime import date

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    PRICE_OSCILLATOR_NAMES,
    SdcaCompositeWeights,
)
from digiquant.strategies.sdca.price_oscillators import (
    agreement_scaled_blend,
    daily_macd_z,
    daily_rsi_z,
    macd_confluence_z,
    monthly_macd_confluence_z,
    monthly_macd_z,
    monthly_rsi_confluence_z,
    monthly_rsi_continuous_z,
    price_oscillator_z_vectors,
    rsi_confluence_z,
    rsi_continuous_z,
    rsi_deadzone_z,
    sma_band_confluence_z,
    sma_band_z,
    weekly_macd_z,
    weekly_monthly_macd_confluence_z,
    weekly_monthly_rsi_confluence_z,
    weekly_rsi_continuous_z,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 6)) -> pl.Series:
    """Default start is a Monday so ISO weeks line up."""
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


def _sawtooth(n: int, *, period: int = 40, base: float = 100.0, amp: float = 30.0) -> pl.Series:
    """Deterministic triangle wave — oscillates without a random seed."""
    half = period // 2
    vals: list[float] = []
    for i in range(n):
        phase = i % period
        frac = phase / half if phase < half else (period - phase) / half
        vals.append(base + amp * (frac if phase < half else -frac))
    return pl.Series(vals)


def _falling(n: int, *, start: float = 1000.0, step: float = -3.0) -> pl.Series:
    return pl.Series([start + step * i for i in range(n)])


def _rising(n: int, *, start: float = 1000.0, step: float = 2.0) -> pl.Series:
    return pl.Series([start + step * i for i in range(n)])


def _calm_then_shock(
    shock_step: float, *, n: int = 400, shock: int = 120, base: float = 1000.0
) -> pl.Series:
    """A long calm oscillation, then a sustained linear shock. Exactly ``n`` bars.

    Needed because a *purely linear* series is the wrong probe for
    ``daily_macd_z``. On constant slope the log-MACD gap between the fast and
    slow EMA is itself constant, so the rolling z-score has no momentum signal
    to score and reads off warm-up transients instead — measured, a linear
    decline and a linear rise both come out with a **positive** mean z over the
    last 80 bars (+0.76 vs +1.64), i.e. the sign convention is not even
    recoverable there. Shocking a calm base is what actually exercises
    "momentum unusually low vs its own history".
    """
    vals = [base]
    for i in range(n - shock - 1):
        # deterministic triangle wobble around `base`, no net drift
        wobble = (1 if i % 2 else -1) * (1 - abs((i % 20) - 10) / 10)
        vals.append(base * (1.0 + 0.01 * wobble))
    for _ in range(shock):
        vals.append(vals[-1] + shock_step)
    assert len(vals) == n
    return pl.Series(vals)


@pytest.fixture(scope="module")
def sample() -> tuple[pl.Series, pl.Series]:
    """1400 days (~3.8 years) of sawtooth price.

    Long enough that *every* leg produces real values: the monthly MACD leg
    needs ``slow=26`` completed months (~800 days) before its EMA is even
    defined, so a 700-day series would leave it all-null and every assertion
    against it vacuous.
    """
    n = 1400
    return _dates(n), _sawtooth(n)


class TestRsiContinuousZ:
    """The continuous map: z is 0 only at RSI=50, ramping to +-3 at the extremes."""

    def test_midpoint_is_exactly_zero(self) -> None:
        assert rsi_continuous_z(pl.Series([50.0])).to_list() == [0.0]

    def test_extremes_saturate_at_three(self) -> None:
        z = rsi_continuous_z(pl.Series([20.0, 85.0])).to_list()
        assert z[0] == pytest.approx(3.0)
        assert z[1] == pytest.approx(-3.0)

    def test_beyond_extremes_stays_clipped(self) -> None:
        z = rsi_continuous_z(pl.Series([0.0, 100.0])).to_list()
        assert z[0] == pytest.approx(3.0)
        assert z[1] == pytest.approx(-3.0)

    def test_ordinary_mid_bull_reading_stays_mild(self) -> None:
        """RSI 60 must read near zero — a naive linear map pegs a bull at the floor."""
        z = rsi_continuous_z(pl.Series([60.0])).to_list()[0]
        assert abs(z) < 0.05

    def test_power_curve_is_monotonic_on_both_sides(self) -> None:
        rsi = pl.Series([50.0, 55.0, 65.0, 75.0, 85.0])
        z = rsi_continuous_z(rsi).to_list()
        assert z == sorted(z, reverse=True)  # rising RSI -> falling z
        assert all(z[i] >= z[i + 1] for i in range(len(z) - 1))

    def test_null_passes_through_as_null(self) -> None:
        z = rsi_continuous_z(pl.Series([None, 50.0, None], dtype=pl.Float64)).to_list()
        assert z[0] is None
        assert z[1] == pytest.approx(0.0)
        assert z[2] is None

    def test_dead_zone_no_longer_flattens(self) -> None:
        """The whole point: develop's dead zone read as a flat line mid-cycle."""
        rsi = pl.Series([35.0, 50.0, 65.0, 75.0])
        continuous = rsi_continuous_z(rsi).to_list()
        assert len(set(round(v, 9) for v in continuous)) == 4


class TestAgreementScaledBlend:
    """Blend two timeframe legs: boost on sign-agreement, damp on conflict."""

    def _blend(self, lv: float | None, mv: float | None) -> float | None:
        out = agreement_scaled_blend(
            pl.Series([lv], dtype=pl.Float64),
            pl.Series([mv], dtype=pl.Float64),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="blend",
        )
        return out.to_list()[0]

    def test_full_agreement_gets_the_full_boost(self) -> None:
        assert self._blend(1.0, 1.0) == pytest.approx(1.5)  # 1.0 * (1 + 0.5)

    def test_partial_agreement_boost_is_magnitude_weighted(self) -> None:
        # base = 1.5, agreement_frac = 1/2 -> multiplier 1.25 -> 1.875
        assert self._blend(2.0, 1.0) == pytest.approx(1.875)

    def test_disagreement_is_damped(self) -> None:
        # base = 0.5, damped to 0.5x -> 0.25
        assert self._blend(2.0, -1.0) == pytest.approx(0.25)

    def test_opposite_legs_cancel_to_zero(self) -> None:
        assert self._blend(1.0, -1.0) == pytest.approx(0.0)

    def test_silent_leg_is_not_a_disagreement(self) -> None:
        assert self._blend(0.0, 2.0) == pytest.approx(1.0)
        assert self._blend(2.0, 0.0) == pytest.approx(1.0)

    def test_null_leg_defers_to_the_other(self) -> None:
        assert self._blend(None, 2.0) == pytest.approx(2.0)
        assert self._blend(2.0, None) == pytest.approx(2.0)

    def test_both_null_stays_null(self) -> None:
        assert self._blend(None, None) is None

    def test_result_is_clipped_to_three(self) -> None:
        assert self._blend(3.0, 3.0) == pytest.approx(3.0)
        assert self._blend(-3.0, -3.0) == pytest.approx(-3.0)

    def test_boost_never_flips_the_sign(self) -> None:
        out = agreement_scaled_blend(
            pl.Series([0.4, -0.4], dtype=pl.Float64),
            pl.Series([0.1, -0.1], dtype=pl.Float64),
            long_term_weight=0.5,
            agreement_boost=1.5,
            disagreement_damp=0.5,
            name="blend",
        ).to_list()
        assert out[0] > 0
        assert out[1] < 0


class TestDailyLegs:
    def test_daily_rsi_mid_is_near_zero_on_a_sawtooth(self, sample: tuple) -> None:
        dates, close = sample
        z = daily_rsi_z(dates, close).to_list()
        tail = [v for v in z[-200:] if v is not None]
        assert tail
        assert all(-3.0 <= v <= 3.0 for v in tail)

    def test_daily_rsi_rejects_mismatched_lengths(self, sample: tuple) -> None:
        dates, close = sample
        with pytest.raises(ValueError, match="same length"):
            daily_rsi_z(dates, close[:10])

    def test_daily_macd_has_no_leading_warmup_beyond_its_own(self, sample: tuple) -> None:
        """A rolling z needs its window; it must not need 52 weeks."""
        dates, close = sample
        z = daily_macd_z(dates, close).to_list()
        first = next((i for i, v in enumerate(z) if v is not None), None)
        assert first is not None
        assert first < 120

    def test_daily_macd_is_sign_flipped(self, sample: tuple) -> None:
        """Momentum unusually low vs its own history reads as cheap (+z).

        Measured on a 400-bar calm-then-shock series, sampling the last 80
        bars (inside the shock, outside the rolling window's warmup): a crash
        averages z=+2.32 with every bar positive, a rally averages z=-0.02.
        The crash leg is asserted to clear +1.0 rather than merely >0 so this
        cannot pass on a near-zero signal; the rally side is deliberately not
        pinned to a tight bound, because a sustained rally keeps its own
        lmacd inside the rolling window and re-centres toward zero.
        """
        dates, _ = sample
        dates = dates[:400]
        crash = [
            v for v in daily_macd_z(dates, _calm_then_shock(-9.0)).to_list()[-80:] if v is not None
        ]
        rally = [
            v for v in daily_macd_z(dates, _calm_then_shock(9.0)).to_list()[-80:] if v is not None
        ]
        assert len(crash) == 80 and len(rally) == 80
        crash_mean = sum(crash) / len(crash)
        rally_mean = sum(rally) / len(rally)
        assert crash_mean > 1.0, f"crash leg should read decisively cheap, got {crash_mean}"
        assert all(v > 0 for v in crash), "every bar in the crash tail should be cheap (+z)"
        assert crash_mean > rally_mean, f"{crash_mean} should exceed the rally leg {rally_mean}"

    def test_daily_macd_reads_nothing_on_a_constant_slope_series(self, sample: tuple) -> None:
        """Pins the degeneracy that forces the calm-then-shock construction.

        On a purely linear series the log-MACD gap is constant, so the rolling
        z has no signal to score. Both directions come out positive over the
        last 80 bars — a linear decline does *not* read cheap. If this ever
        starts behaving, the helper above can be simplified; until then it is
        why the sign-flip test must not use a straight line.
        """
        dates, _ = sample
        dates = dates[:400]
        falling = [v for v in daily_macd_z(dates, _falling(400)).to_list()[-80:] if v is not None]
        rising = [v for v in daily_macd_z(dates, _rising(400)).to_list()[-80:] if v is not None]
        assert sum(falling) / len(falling) > 0
        assert sum(rising) / len(rising) > 0

    def test_daily_macd_rejects_mismatched_lengths(self, sample: tuple) -> None:
        dates, close = sample
        with pytest.raises(ValueError, match="same length"):
            daily_macd_z(dates, close[:10])

    def test_daily_macd_z_window_is_ninety_days_of_recent_normal(self, sample: tuple) -> None:
        """Pins the rolling z-window: ~3 months of history, not all of it.

        ``_MACD_DAILY_Z_WINDOW = 90`` is the whole premise of the daily leg —
        "a few-months momentum dip registers against *recent* normal" — so the
        window has to be pinned by a test, not left to a constant nobody reads.

        The EMA underneath is recursive and never fully forgets, so a bar's
        influence decays rather than vanishing at the window edge. Measured on
        a 700-bar sawtooth, perturbing one bar by +50% and reading the final
        z: distance 5 → 4.7e-01, 60 → 1.5e-02, 89 → 9.1e-03, 300 → 4.0e-08.
        The two thresholds below sit in that gap, so the test holds while
        still failing if the window is widened (at z_window=400 a 300-bar-old
        bar falls back inside the window and moves the result far more than
        1e-6).
        """
        dates, close = sample
        dates, close = dates[:700], close[:700]
        baseline = daily_macd_z(dates, close).to_list()[-1]

        def shift_at(distance: int) -> float:
            vals = close.to_list()
            vals[len(vals) - 1 - distance] *= 1.5
            z = daily_macd_z(dates, pl.Series(vals)).to_list()[-1]
            return abs(z - baseline)

        assert shift_at(60) > 1e-2, "a bar inside the window must move the z"
        assert shift_at(300) < 1e-6, "a bar well outside the window must not"


class TestMonthlyMacdZ:
    def test_leading_monthly_leg_is_null_until_the_first_completed_month(
        self, sample: tuple
    ) -> None:
        dates, close = sample
        z = monthly_macd_z(dates, close).to_list()
        assert z[0] is None

    def test_tail_is_bounded(self, sample: tuple) -> None:
        dates, close = sample
        z = [v for v in monthly_macd_z(dates, close).to_list()[-200:] if v is not None]
        assert z
        assert all(-3.0 <= v <= 3.0 for v in z)


class TestRsiConfluenceFamily:
    def test_weekly_confluence_matches_its_two_legs(self, sample: tuple) -> None:
        dates, close = sample
        expected = agreement_scaled_blend(
            weekly_rsi_continuous_z(dates, close),
            daily_rsi_z(dates, close),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="weekly_rsi",
        ).to_list()
        assert rsi_confluence_z(dates, close).to_list() == expected

    def test_monthly_confluence_swaps_the_long_term_leg_to_months(self, sample: tuple) -> None:
        dates, close = sample
        got = monthly_rsi_confluence_z(dates, close)
        assert got.name == "monthly_rsi"
        tail = [v for v in got.to_list()[-200:] if v is not None]
        assert tail
        assert all(-3.0 <= v <= 3.0 for v in tail)

    def test_weekly_monthly_pairing_uses_no_daily_leg(self, sample: tuple) -> None:
        dates, close = sample
        expected = agreement_scaled_blend(
            monthly_rsi_continuous_z(dates, close),
            weekly_rsi_continuous_z(dates, close),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="weekly_monthly_rsi",
        ).to_list()
        assert weekly_monthly_rsi_confluence_z(dates, close).to_list() == expected

    def test_all_three_pairings_differ_on_a_sawtooth(self, sample: tuple) -> None:
        dates, close = sample
        weekly_daily = rsi_confluence_z(dates, close).to_list()
        monthly_daily = monthly_rsi_confluence_z(dates, close).to_list()
        weekly_monthly = weekly_monthly_rsi_confluence_z(dates, close).to_list()
        assert weekly_daily != monthly_daily
        assert weekly_daily != weekly_monthly
        assert monthly_daily != weekly_monthly


class TestMacdConfluenceFamily:
    def test_weekly_confluence_matches_its_two_legs(self, sample: tuple) -> None:
        dates, close = sample
        expected = agreement_scaled_blend(
            weekly_macd_z(dates, close),
            daily_macd_z(dates, close),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="weekly_macd",
        ).to_list()
        assert macd_confluence_z(dates, close).to_list() == expected

    def test_monthly_and_weekly_monthly_pairings_are_distinct(self, sample: tuple) -> None:
        dates, close = sample
        monthly_daily = monthly_macd_confluence_z(dates, close).to_list()
        weekly_monthly = weekly_monthly_macd_confluence_z(dates, close).to_list()
        assert monthly_daily != weekly_monthly

    def test_weekly_macd_confluence_is_not_the_bare_weekly_leg(self, sample: tuple) -> None:
        dates, close = sample
        assert macd_confluence_z(dates, close).to_list() != weekly_macd_z(dates, close).to_list()


class TestSmaBandConfluence:
    def test_separates_timeframes_by_window_length_alone(self, sample: tuple) -> None:
        dates, close = sample
        expected = agreement_scaled_blend(
            sma_band_z(dates, close),
            sma_band_z(dates, close, window=20, min_samples=10),
            long_term_weight=0.5,
            agreement_boost=0.5,
            disagreement_damp=0.5,
            name="sma_band",
        ).to_list()
        assert sma_band_confluence_z(dates, close).to_list() == expected

    def test_fast_leg_reports_before_the_slow_leg_does(self, sample: tuple) -> None:
        """The fast leg (min_samples=10) sets the first report, not the slow leg (30).

        Index 9, not 10: ``rolling_mean(min_samples=10)`` is defined on the
        10th observation, which is index 9 zero-based. Asserted against the
        slow leg's own 29 so the test proves *which* leg reports first rather
        than just pinning a magic number.
        """
        from digiquant.strategies.sdca.price_oscillators import _SMA_BAND_MIN_SAMPLES

        dates, close = sample
        z = sma_band_confluence_z(dates, close).to_list()
        first = next((i for i, v in enumerate(z) if v is not None), None)
        assert first == 10 - 1
        assert first < _SMA_BAND_MIN_SAMPLES - 1


class TestNoLookAhead:
    """Truncate the future away; every earlier value must be unchanged."""

    @pytest.mark.parametrize(
        "fn",
        [
            weekly_rsi_continuous_z,
            monthly_rsi_continuous_z,
            daily_rsi_z,
            daily_macd_z,
            monthly_macd_z,
            rsi_confluence_z,
            monthly_rsi_confluence_z,
            weekly_monthly_rsi_confluence_z,
            macd_confluence_z,
            monthly_macd_confluence_z,
            weekly_monthly_macd_confluence_z,
            sma_band_confluence_z,
        ],
        ids=lambda f: f.__name__,
    )
    def test_truncating_the_tail_changes_nothing_earlier(self, fn, sample: tuple) -> None:
        dates, close = sample
        full = fn(dates, close).to_list()
        cut = 1000
        truncated = fn(dates[:cut], close[:cut]).to_list()
        assert len(truncated) == cut

        # Non-vacuity guard. The monthly MACD leg needs 26 completed months
        # before it reports anything at all (measured: first non-null at day
        # 784) and the monthly RSI leg at day 419, so an earlier draft's
        # cut=400 compared null against null for both and proved nothing.
        # A cut that leaves a leg all-null fails here instead of passing
        # silently.
        compared = [v for v in full[:cut] if v is not None]
        assert compared, (
            f"{fn.__name__} is null for every day before the cut, so this "
            f"comparison is vacuous — raise cut or lengthen the fixture"
        )

        for i in range(cut):
            a, b = full[i], truncated[i]
            if a is None or b is None:
                assert a is None and b is None, f"{fn.__name__} diverged at {i}"
            else:
                assert a == pytest.approx(b), f"{fn.__name__} leaked at day {i}"

    def test_a_mid_week_date_never_sees_its_week_close(self) -> None:
        """Wednesday 2020-01-08 must carry the week ending 2020-01-05's z, or null."""
        dates = _dates(20)
        close = pl.Series([100.0] * 6 + [500.0] + [100.0] * 13)
        weekly = weekly_rsi_continuous_z(dates, close).to_list()
        # Days 0-5 belong to the week ending 2020-01-05 (close 100.0); day 6 is
        # the 500.0 spike inside the *next*, still-incomplete week.
        assert weekly[:6] == [None] * 6
        assert all(v is None for v in weekly[:13])


#: The seven weight fields develop published, in develop's order, with develop's
#: defaults. Later leaves of the DIG-1597 port may add *dormant* research-only
#: fields; nothing in this port may rename, reorder or re-default these.
_PUBLISHED_WEIGHT_DEFAULTS: dict[str, float] = {
    "valuation": 1.0,
    "m2": 0.0,
    "rs_eth": 0.0,
    "dxy": 0.0,
    "weekly_rsi": 0.0,
    "weekly_macd": 0.0,
    "sma_band": 0.0,
}


class TestDevelopApiUnchanged:
    """This leaf must not disturb what develop already publishes."""

    def test_rsi_deadzone_still_flattens_the_mid_cycle(self) -> None:
        z = rsi_deadzone_z(pl.Series([30.0, 50.0, 80.0])).to_list()
        assert z == [0.0, 0.0, 0.0]

    def test_published_weight_fields_are_unchanged(self) -> None:
        """The published weights keep develop's names, order and defaults."""
        fields = SdcaCompositeWeights.model_fields
        assert [name for name in fields if name in _PUBLISHED_WEIGHT_DEFAULTS] == list(
            _PUBLISHED_WEIGHT_DEFAULTS
        )
        for name, default in _PUBLISHED_WEIGHT_DEFAULTS.items():
            assert fields[name].default == default, name

    def test_any_added_weight_field_is_dormant(self) -> None:
        """`valuation` stays the only non-zero default.

        This is what makes an additive leaf safe: a research-only field can only
        join the model at 0.0, so it cannot shift a published composite risk
        vector unless a caller explicitly asks for it by weight.
        """
        nonzero = {
            name
            for name, field in SdcaCompositeWeights.model_fields.items()
            if field.default != 0.0
        }
        assert nonzero == {"valuation"}

    def test_deferred_branch_renames_stay_deferred(self) -> None:
        """The branch's oscillator-weight and valuation-rename rewires are not here.

        Landing them needs an `SdcaOscillatorSpec` expansion, so they are a
        separate, separately-measured leaf rather than a side effect of a port.
        """
        fields = set(SdcaCompositeWeights.model_fields)
        assert "monthly_rsi" not in fields
        assert "weekly_monthly_rsi" not in fields
        assert "valuation" in fields  # valuation -> power_law is deferred

    def test_generic_oscillator_vector_shape_is_unchanged(self, sample: tuple) -> None:
        dates, close = sample
        vectors = price_oscillator_z_vectors(dates, close)
        assert set(vectors) == set(PRICE_OSCILLATOR_NAMES)
        assert len(PRICE_OSCILLATOR_NAMES) == 3
