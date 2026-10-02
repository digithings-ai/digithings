"""Gold per-indicator z-window fitting harness — metric + grid completeness (#4804).

Plan-19 Task 1 (amended by Plan-19 **Ruling 1**). The harness fits every WIRED
gold indicator's shipped z-function over a FROZEN parameter grid and scores it
with the in-sample metric

    ``separation = mean(z | trough windows) - mean(z | peak windows)``

against the pinned ``SdcaCycleWindows.gold_v1()`` pins. **Positive = the z votes
CHEAP at bottoms**, which is the convention every shipped z already uses
(``composite_risk.py:57`` maps ``+z`` to ``buy``, and the shipped Stage-A
objective is algebraically ``+(50/3) * separation``). ``abs()`` is FORBIDDEN on
this metric: it would reward a leg that votes backwards.

Three contracts are pinned here:

1. **The metric is exact, signed, and never absolute.** ``separation`` on a
   synthetic z whose peak/trough means are known comes back as the exact
   difference, and a MIRRORED z comes back at exactly the negated separation.
   ``None`` z is skipped, never zero-filled, and a one-sided calendar (peak days
   but no trough days — the hy_oas/ig_oas case, whose staged CSVs start
   2023-09-30 while the last trough window ends 2022-12-05) yields
   ``separation=None`` plus a REASON, never a silent zero and never a raise.

2. **The shares come from the RAW z, per side.** ``peak_negative_share`` and
   ``trough_positive_share`` are counted off the raw vectors, so a dead-zone
   oscillator that sits at exactly ``0.0`` reads ``0.0`` on the dead side — the
   old single ``sign_share`` aggregate was NOT recoverable as ``1 - x`` (a
   dead-zone leg would read a perfect ``1.0`` for a vote it never cast).
   ``zero_z_share`` records how much of the scored window sits exactly at zero.

3. **The grid is complete and dispatch-only.** Every wired indicator named by
   the plan has a non-empty grid of the frozen shape, every grid row's params
   are accepted by the SHIPPED signature, and ``build_z`` returns exactly what
   the shipped z-function returns (call-with-a-param, never reimplement math).

Plus the DEGENERATE-PASS gate: a row whose pass rests on a side whose mean never
leaves the ±0.06 dead zone is flagged ``degenerate``; an indicator whose every
scored row is degenerate AND whose best separation is strictly positive is a
``degenerate_pass`` — listed separately, never a keep without an owner look.

Not vacuous: the one-sided case fails the scoring tests, the abs-guard fails on
any ``abs()`` of the metric, and the dispatch test compares against the shipped
function's own output rather than a restated copy.
"""

from __future__ import annotations

import importlib.util
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from digiquant.strategies.sdca.cycle_windows import (
    CycleKind,
    CycleWindow,
    SdcaCycleWindows,
)
from digiquant.strategies.sdca.indicator_catalog import (
    ExtraIndicatorSources,
    gdx_gld_z,
    m2_liquidity_z,
    uup_z,
)
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    price_oscillator_z_vectors,
)

pytestmark = pytest.mark.unit

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "fit_gold_indicators.py"
)

HALF_WINDOW_DAYS = 45
CALENDAR_DAYS = 700
# Long enough for every frozen window (1260 needs a full warm-up fill) so the
# dispatch test proves a real z comes out, not just a non-raising call.
DISPATCH_DAYS = 1500
LATE_SOURCE_DAYS = 60


def _load_fitter() -> Any:
    spec = importlib.util.spec_from_file_location("fit_gold_indicators", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _window(name: str, kind: CycleKind, pin: date) -> CycleWindow:
    return CycleWindow(
        name=name,
        kind=kind,
        start=pin - timedelta(days=HALF_WINDOW_DAYS),
        end=pin + timedelta(days=HALF_WINDOW_DAYS),
    )


def _calendar(days: int = CALENDAR_DAYS) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(days)]


def _windows() -> SdcaCycleWindows:
    """One peak pin and two trough pins, all fully inside the synthetic calendar."""
    return SdcaCycleWindows(
        windows=(
            _window("p1", CycleKind.PEAK, date(2020, 3, 1)),
            _window("t1", CycleKind.TROUGH, date(2020, 9, 1)),
            _window("t2", CycleKind.TROUGH, date(2021, 2, 15)),
        )
    )


def _window_days(windows: SdcaCycleWindows, dates: list[date]) -> dict[CycleKind, list[int]]:
    out: dict[CycleKind, list[int]] = {CycleKind.PEAK: [], CycleKind.TROUGH: []}
    for i, day in enumerate(dates):
        kind = windows.kind_on(day)
        if kind is not None:
            out[kind].append(i)
    return out


def _two_level_z(
    dates: list[date],
    windows: SdcaCycleWindows,
    *,
    peak: float,
    trough: float,
) -> list[float | None]:
    z: list[float | None] = []
    for day in dates:
        kind = windows.kind_on(day)
        z.append(peak if kind is CycleKind.PEAK else trough if kind is CycleKind.TROUGH else 0.0)
    return z


def _dead_zone_z(
    dates: list[date],
    windows: SdcaCycleWindows,
    *,
    peak: float,
) -> list[float | None]:
    """The dead-zone oscillator shape: real z at the tops, EXACTLY 0.0 at the troughs.

    This is the shape that made ``1 - sign_share`` invalid: the dead side never
    votes, so an aggregate read would report a perfect agreement it never cast.
    """
    z: list[float | None] = []
    for day in dates:
        kind = windows.kind_on(day)
        z.append(peak if kind is CycleKind.PEAK else 0.0 if kind is CycleKind.TROUGH else 0.0)
    return z


def _mirror(z: list[float | None]) -> list[float | None]:
    return [None if v is None else -v for v in z]


# --------------------------------------------------------------------------- #
# 1. The frozen metric (Ruling 1: trough - peak, cheap-at-bottoms positive)
# --------------------------------------------------------------------------- #


def test_separation_is_exact_on_a_synthetic_z() -> None:
    """Known peak/trough means -> the exact difference (1.0 - (-2.0) = +3.0)."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    scored = _window_days(windows, dates)

    score = fitter.separation(dates, _two_level_z(dates, windows, peak=-2.0, trough=1.0), windows)

    assert score.separation == pytest.approx(3.0)
    assert score.mean_peak_z == pytest.approx(-2.0)
    assert score.mean_trough_z == pytest.approx(1.0)
    assert score.peak_days == len(scored[CycleKind.PEAK])
    assert score.trough_days == len(scored[CycleKind.TROUGH])
    assert score.scored_days == len(scored[CycleKind.PEAK]) + len(scored[CycleKind.TROUGH])
    assert score.coverage == pytest.approx(1.0)
    # Raw-z shares: every peak day is below zero, every trough day above.
    assert score.peak_negative_share == pytest.approx(1.0)
    assert score.trough_positive_share == pytest.approx(1.0)
    assert score.zero_z_share == pytest.approx(0.0)
    assert score.degenerate is False
    assert score.reason is None


def test_separation_sign_convention_positive_is_cheap_at_bottoms() -> None:
    """Ruling 1: +separation = cheap at bottoms; rich-at-tops scores negative."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()

    cheap = fitter.separation(dates, _two_level_z(dates, windows, peak=-1.0, trough=2.0), windows)
    rich = fitter.separation(dates, _two_level_z(dates, windows, peak=2.0, trough=-1.0), windows)

    assert cheap.separation == pytest.approx(3.0)
    assert cheap.peak_negative_share == pytest.approx(1.0)
    assert cheap.trough_positive_share == pytest.approx(1.0)
    assert rich.separation == pytest.approx(-3.0)
    assert rich.peak_negative_share == pytest.approx(0.0)
    assert rich.trough_positive_share == pytest.approx(0.0)


def test_separation_never_absorbs_the_sign() -> None:
    """The abs() guard: a mirrored z scores the exact NEGATION, never |separation|."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    cheap = _two_level_z(dates, windows, peak=-1.0, trough=2.0)

    good = fitter.separation(dates, cheap, windows)
    anti = fitter.separation(dates, _mirror(cheap), windows)

    assert good.separation == pytest.approx(3.0)
    assert anti.separation == pytest.approx(-3.0)
    assert anti.separation == pytest.approx(-float(good.separation))
    # A loud anti-correlated leg is NOT rescued by its magnitude.
    strong = fitter.separation(dates, _two_level_z(dates, windows, peak=5.0, trough=-5.0), windows)
    assert strong.separation < 0.0
    assert abs(strong.separation) == pytest.approx(10.0)
    # ...and the mirror of it is the only positive reading of the same magnitude.
    assert fitter.separation(
        dates, _mirror(_two_level_z(dates, windows, peak=5.0, trough=-5.0)), windows
    ).separation == pytest.approx(10.0)


def test_sign_shares_come_from_raw_z_not_one_minus_the_aggregate() -> None:
    """A dead side reads 0.0 on BOTH shares; ``1 - x`` would have read a perfect 1.0."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    scored = _window_days(windows, dates)

    score = fitter.separation(dates, _dead_zone_z(dates, windows, peak=1.5), windows)

    assert score.separation == pytest.approx(-1.5)
    assert score.mean_trough_z == pytest.approx(0.0)
    assert score.peak_negative_share == pytest.approx(0.0)
    assert score.trough_positive_share == pytest.approx(0.0)
    assert score.zero_z_share == pytest.approx(
        len(scored[CycleKind.TROUGH])
        / (len(scored[CycleKind.PEAK]) + len(scored[CycleKind.TROUGH]))
    )
    # One side never leaves the dead zone -> the pass rests on the other side alone.
    assert score.degenerate is True


def test_degenerate_row_flags_a_dead_side_pass_and_only_that() -> None:
    """One side inside ±0.06 -> degenerate; both sides outside it -> not."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()

    dead = fitter.separation(dates, _dead_zone_z(dates, windows, peak=-1.5), windows)
    live = fitter.separation(dates, _two_level_z(dates, windows, peak=-1.5, trough=0.6), windows)

    # cheap at the bottoms, dead zone at the tops: a one-sided pass.
    assert dead.separation == pytest.approx(1.5)
    assert dead.degenerate is True
    # both sides carry a real opinion -> not degenerate, whatever the threshold.
    assert live.separation == pytest.approx(2.1)
    assert live.degenerate is False
    # The threshold is inclusive at 0.06 and exclusive just past it.
    assert fitter.row_is_degenerate(separation=0.6, mean_peak_z=-0.06, mean_trough_z=2.0) is True
    assert fitter.row_is_degenerate(separation=0.6, mean_peak_z=-0.0601, mean_trough_z=2.0) is False
    # An unscored row has no pass to rest on -> never degenerate.
    assert fitter.row_is_degenerate(separation=None, mean_peak_z=None, mean_trough_z=None) is False
    assert fitter.row_is_degenerate(separation=0.6, mean_peak_z=None, mean_trough_z=0.0) is False


def test_degenerate_verdict_lists_a_positive_dead_zone_pass_separately() -> None:
    """DEGENERATE-PASS = every scored row dead-side AND best separation strictly > 0."""
    fitter = _load_fitter()

    dead_pass = [
        _row(fitter, window_days=105, separation=0.44, mean_peak_z=-0.44, mean_trough_z=0.0),
        _row(fitter, window_days=154, separation=0.14, mean_peak_z=-0.14, mean_trough_z=0.0),
    ]
    assert fitter.degenerate_verdict(dead_pass) == (True, True)

    # Degenerate but not a pass: every row dead-side, best separation exactly 0.0.
    flat = [_row(fitter, window_days=90, separation=0.0, mean_peak_z=0.0, mean_trough_z=0.0)]
    assert fitter.degenerate_verdict(flat) == (True, False)

    # Degenerate but not a pass: dead-side rows whose best separation is negative.
    losing = [_row(fitter, window_days=90, separation=-0.02, mean_peak_z=-0.02, mean_trough_z=0.05)]
    assert fitter.degenerate_verdict(losing) == (True, False)

    # One live row anywhere in the grid clears the indicator-level flag.
    mixed = dead_pass + [
        _row(fitter, window_days=378, separation=-3.1, mean_peak_z=-1.96, mean_trough_z=1.15)
    ]
    assert fitter.degenerate_verdict(mixed) == (False, False)

    # Nothing scored (hy_oas / ig_oas) -> no flag at all, never a fake degenerate.
    assert fitter.degenerate_verdict([]) == (False, False)
    assert fitter.degenerate_verdict(
        [_row(fitter, window_days=90, separation=None, mean_peak_z=None, mean_trough_z=None)]
    ) == (False, False)


def test_separation_ignores_null_z_and_reports_coverage() -> None:
    """A null z is skipped (never zero-filled) and shows up as coverage < 1."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    scored = _window_days(windows, dates)
    peak_kept = scored[CycleKind.PEAK][::2]
    z = _two_level_z(dates, windows, peak=-2.0, trough=1.0)
    for i in peak_kept:
        z[i] = None

    score = fitter.separation(dates, z, windows)

    total = len(scored[CycleKind.PEAK]) + len(scored[CycleKind.TROUGH])
    assert score.peak_days == len(scored[CycleKind.PEAK]) - len(peak_kept)
    assert score.separation == pytest.approx(3.0)
    assert score.scored_days == total - len(peak_kept)
    assert score.coverage == pytest.approx((total - len(peak_kept)) / total)
    assert score.coverage < 1.0


def test_separation_without_any_valid_z_is_none_with_a_reason() -> None:
    """All-null z -> separation None + reason, not a raise and not a fake 0.0."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()

    score = fitter.separation(dates, [None] * len(dates), windows)

    assert score.separation is None
    assert score.reason is not None and "valid z" in score.reason
    assert score.scored_days == 0
    assert score.coverage == 0.0
    assert score.degenerate is False
    assert score.peak_negative_share is None
    assert score.trough_positive_share is None
    assert score.zero_z_share is None


def test_one_sided_calendar_is_empty_with_a_reason_not_a_silent_skip() -> None:
    """The hy_oas/ig_oas shape: peak days but zero trough days -> unscorable.

    The staged credit CSVs start 2023-09-30 and the last gold_v1 trough window
    ends 2022-12-05, so hy/ig can only ever see the current-top window.
    """
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    scored = _window_days(windows, dates)
    z: list[float | None] = [None] * len(dates)
    for i in scored[CycleKind.PEAK]:
        z[i] = 2.0

    score = fitter.separation(dates, z, windows)

    assert score.peak_days == len(scored[CycleKind.PEAK])
    assert score.trough_days == 0
    assert score.separation is None
    assert score.reason is not None and "trough" in score.reason
    assert score.degenerate is False


def test_separation_rejects_misaligned_lengths() -> None:
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    with pytest.raises(ValueError, match="same length"):
        fitter.separation(dates, [0.0] * (len(dates) - 1), windows)


# --------------------------------------------------------------------------- #
# 2. Grid completeness (frozen shapes, no silent skips)
# --------------------------------------------------------------------------- #

EXPECTED_GRID_ROWS: dict[str, int] = {
    "uup": 7,
    "real_rate": 7,
    "gvz": 7,
    "hy_oas": 7,
    "ig_oas": 7,
    "breakeven_5y": 7,
    "nfci": 7,
    "gdx_gld": 7,
    "gld_slv": 7,
    "m2": 16,
    "walcl": 16,
    "weekly_rsi": 2,
    "weekly_macd": 4,
    "sma_band": 6,
}


def test_every_wired_indicator_has_a_grid_and_the_grid_set_is_frozen() -> None:
    fitter = _load_fitter()
    assert set(fitter.FITTED_INDICATORS) == set(EXPECTED_GRID_ROWS)
    for name in fitter.FITTED_INDICATORS:
        grid = fitter.indicator_grid(name)
        assert grid, f"{name} has an empty grid"
        assert len(grid) == EXPECTED_GRID_ROWS[name], name
    # hy/ig are IN the fitted set (listed with a reason), never dropped.
    assert "hy_oas" in fitter.FITTED_INDICATORS
    assert "ig_oas" in fitter.FITTED_INDICATORS


def test_unknown_indicator_has_no_grid() -> None:
    fitter = _load_fitter()
    assert fitter.indicator_grid("rs_eth") == ()
    with pytest.raises(ValueError, match="no grid"):
        fitter.build_z("rs_eth", {"window": 90}, pl.Series([1], dtype=pl.Int32), None, None)  # type: ignore[arg-type]


def test_frozen_level_and_roc_grid_values() -> None:
    fitter = _load_fitter()
    assert tuple(fitter.LEVEL_WINDOWS) == (90, 180, 270, 378, 504, 756, 1260)
    assert tuple(fitter.ROC_DAYS) == (90, 180, 365, 730)
    assert tuple(fitter.ROC_WINDOWS) == (180, 378, 756, 1260)

    level = fitter.indicator_grid("nfci")
    assert [p.params["window"] for p in level] == list(fitter.LEVEL_WINDOWS)
    assert {p.window_days for p in level} == set(fitter.LEVEL_WINDOWS)

    roc = fitter.indicator_grid("m2")
    assert sorted({(p.params["roc_days"], p.params["window"]) for p in roc}) == sorted(
        (r, w) for r in fitter.ROC_DAYS for w in fitter.ROC_WINDOWS
    )
    assert all(p.window_days in fitter.ROC_WINDOWS for p in roc)


def test_oscillator_grid_params_are_real_spec_fields() -> None:
    """Every oscillator param is a SdcaOscillatorSpec field (no invented math)."""
    fitter = _load_fitter()
    fields = set(SdcaOscillatorSpec.model_fields)
    for name in ("weekly_rsi", "weekly_macd", "sma_band"):
        for point in fitter.indicator_grid(name):
            assert set(point.params) <= fields, (name, point.params)
            SdcaOscillatorSpec(**point.params)  # validates slow > fast, min <= window


def test_oscillator_windows_use_the_verified_spec_fields() -> None:
    """The frozen named sets, mapped onto the fields the spec actually has."""
    fitter = _load_fitter()

    rsi = fitter.indicator_grid("weekly_rsi")
    assert [p.params["rsi_length"] for p in rsi] == [14, 21]
    # weekly_rsi has no window knob: its calendar footprint IS the rsi_length.
    assert [p.window_days for p in rsi] == [
        (14 + 1) * 7,
        (21 + 1) * 7,
    ]

    macd = fitter.indicator_grid("weekly_macd")
    assert [(p.params["macd_fast"], p.params["macd_slow"]) for p in macd] == [
        (12, 26),
        (12, 26),
        (8, 34),
        (8, 34),
    ]
    assert [p.params["macd_z_window"] for p in macd] == [90, 378, 90, 378]

    sma = fitter.indicator_grid("sma_band")
    assert [p.params["sma_band_window"] for p in sma] == [200, 200, 378, 378, 1000, 1000]
    assert [p.params["sma_band_min_samples"] for p in sma] == [30, 60, 30, 60, 30, 60]
    assert [p.window_days for p in sma] == [200, 200, 378, 378, 1000, 1000]


# --------------------------------------------------------------------------- #
# 3. Dispatch: build_z calls the shipped z-functions, it does not restate them
# --------------------------------------------------------------------------- #


def _synthetic_series(days: int) -> tuple[list[date], list[float], list[float], list[float]]:
    """Deterministic macro series + a GLD close + two sibling closes."""
    dates = _calendar(days)
    macro = [
        100.0 + 0.05 * i + 3.0 * math.sin(2.0 * math.pi * i / 180.0) + 0.01 * i * (i % 7)
        for i in range(days)
    ]
    price = [50.0 + 0.03 * i + 2.0 * math.cos(2.0 * math.pi * i / 240.0) for i in range(days)]
    gdx = [0.6 * p * (1.0 + 0.1 * math.sin(2.0 * math.pi * i / 300.0)) for i, p in enumerate(price)]
    slv = [
        0.24 * p * (1.0 + 0.05 * math.cos(2.0 * math.pi * i / 200.0)) for i, p in enumerate(price)
    ]
    return dates, macro, price, gdx, slv


def _synthetic_sources(
    dates: list[date],
    macro: list[float],
    gdx: list[float],
    slv: list[float],
    *,
    late_start: date | None = None,
) -> ExtraIndicatorSources:
    """Every source pair filled from one deterministic synthetic series.

    ``late_start`` mirrors the staged-credit-CSV shape: hy_oas/ig_oas then see
    only the tail of the calendar, so the pinned trough windows fall outside
    their data.
    """

    def pair(values: list[float]) -> tuple[pl.Series, pl.Series]:
        return (
            pl.Series("d", dates, dtype=pl.Date),
            pl.Series("v", values, dtype=pl.Float64),
        )

    src_dates, src_values = pair(macro)
    gdx_dates, gdx_close = pair(gdx)
    slv_dates, slv_close = pair(slv)
    hy_dates, hy_values = src_dates, src_values
    if late_start is not None:
        keep = [i for i, d in enumerate(dates) if d >= late_start]
        hy_dates = pl.Series("d", [dates[i] for i in keep], dtype=pl.Date)
        hy_values = pl.Series("v", [macro[i] for i in keep], dtype=pl.Float64)
    return ExtraIndicatorSources(
        m2_dates=src_dates,
        m2_values=src_values,
        uup_dates=src_dates,
        uup_close=src_values,
        gvz_dates=src_dates,
        gvz_values=src_values,
        walcl_dates=src_dates,
        walcl_values=src_values,
        hy_oas_dates=hy_dates,
        hy_oas_values=hy_values,
        ig_oas_dates=hy_dates,
        ig_oas_values=hy_values,
        breakeven_5y_dates=src_dates,
        breakeven_5y_values=src_values,
        nfci_dates=src_dates,
        nfci_values=src_values,
        gdx_dates=gdx_dates,
        gdx_close=gdx_close,
        slv_dates=slv_dates,
        slv_close=slv_close,
        real_rate_dates=src_dates,
        real_rate_values=src_values,
    )


def _dispatch_inputs() -> tuple[list[date], pl.Series, pl.Series, ExtraIndicatorSources]:
    dates, macro, price, gdx, slv = _synthetic_series(DISPATCH_DAYS)
    sources = _synthetic_sources(dates, macro, gdx, slv)
    return (
        dates,
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("price", price, dtype=pl.Float64),
        sources,
    )


def test_build_z_returns_exactly_what_the_shipped_z_functions_return() -> None:
    """No reimplementation: level-z, roc-z, ratio-z and oscillator legs delegate."""
    fitter = _load_fitter()
    _, date_s, price_s, sources = _dispatch_inputs()

    level = next(p for p in fitter.indicator_grid("uup") if p.params["window"] == 378)
    assert (
        fitter.build_z("uup", level.params, date_s, price_s, sources)
        == uup_z(date_s, sources.uup_dates, sources.uup_close, window=378).to_list()
    )

    roc = next(
        p for p in fitter.indicator_grid("m2") if p.params == {"roc_days": 365, "window": 378}
    )
    assert (
        fitter.build_z("m2", roc.params, date_s, price_s, sources)
        == m2_liquidity_z(
            date_s, sources.m2_dates, sources.m2_values, roc_days=365, window=378
        ).to_list()
    )

    ratio = next(p for p in fitter.indicator_grid("gdx_gld") if p.params["window"] == 756)
    assert (
        fitter.build_z("gdx_gld", ratio.params, date_s, price_s, sources)
        == gdx_gld_z(date_s, price_s, sources.gdx_dates, sources.gdx_close, window=756).to_list()
    )

    osc = fitter.indicator_grid("weekly_rsi")[1]
    vectors = price_oscillator_z_vectors(
        date_s, price_s, oscillators=SdcaOscillatorSpec(**osc.params)
    )
    assert (
        fitter.build_z("weekly_rsi", osc.params, date_s, price_s, sources) == vectors["weekly_rsi"]
    )


def test_every_grid_row_of_every_indicator_produces_a_real_z() -> None:
    """Every frozen row is dispatchable and yields non-null z — no dead rows."""
    fitter = _load_fitter()
    dates, date_s, price_s, sources = _dispatch_inputs()

    for name in fitter.FITTED_INDICATORS:
        for point in fitter.indicator_grid(name):
            z = fitter.build_z(name, point.params, date_s, price_s, sources)
            assert len(z) == len(dates), name
            assert any(v is not None for v in z), (name, point.params)


# --------------------------------------------------------------------------- #
# 4. fit_indicator + the frozen medium/long band selection
# --------------------------------------------------------------------------- #


def _dispatch_windows() -> SdcaCycleWindows:
    """Peaks/troughs spread so both the <=378 and >=504 bands are populated."""
    return SdcaCycleWindows(
        windows=(
            _window("p_2008", CycleKind.PEAK, date(2020, 3, 1)),
            _window("t_2011", CycleKind.TROUGH, date(2020, 9, 1)),
            _window("p_2020", CycleKind.PEAK, date(2021, 2, 15)),
            _window("t_2022", CycleKind.TROUGH, date(2022, 10, 21)),
            _window("p_2026", CycleKind.PEAK, date(2024, 2, 1)),
        )
    )


def _late_windows() -> SdcaCycleWindows:
    """Only a peak window inside the late source's span; every trough ends before it."""
    return SdcaCycleWindows(
        windows=(
            _window("old_trough", CycleKind.TROUGH, date(2021, 2, 15)),
            _window("late_peak", CycleKind.PEAK, _calendar(DISPATCH_DAYS)[-1] - timedelta(days=10)),
        )
    )


def test_fit_indicator_scores_every_grid_row_and_picks_the_best() -> None:
    fitter = _load_fitter()
    dates, date_s, price_s, sources = _dispatch_inputs()

    fits = fitter.fit_indicator("nfci", dates, date_s, price_s, sources, _dispatch_windows())

    assert len(fits.rows) == EXPECTED_GRID_ROWS["nfci"]
    assert all(row.separation is not None for row in fits.rows)
    assert fits.status == "scored"
    assert fits.reason is None
    assert fits.best_overall is not None
    assert fits.best_overall.separation == max(
        row.separation for row in fits.rows if row.separation is not None
    )
    assert fits.best_medium is not None and fits.best_medium.window_days <= 378
    assert fits.best_long is not None and fits.best_long.window_days >= 504
    # nfci carries a real opinion on both sides here -> never flagged degenerate.
    assert fits.degenerate is False
    assert fits.degenerate_pass is False
    # the stored row flag is exactly the derivation from the row's own means
    for row in fits.rows:
        assert row.degenerate == fitter.row_is_degenerate(
            separation=row.separation,
            mean_peak_z=row.mean_peak_z,
            mean_trough_z=row.mean_trough_z,
        )
        assert fitter.degenerate_verdict(fits.rows) == (fits.degenerate, fits.degenerate_pass)


def test_fit_indicator_flags_the_dead_zone_oscillator_but_never_a_zero_pass() -> None:
    """The log-MACD dead band sits at z == 0 on the synthetic calendar.

    Every scored row is degenerate, yet the best separation is exactly 0.0 — so
    it is a DEGENERATE indicator and NOT a degenerate PASS (strict ``> 0``).
    """
    fitter = _load_fitter()
    dates, date_s, price_s, sources = _dispatch_inputs()

    fits = fitter.fit_indicator("weekly_macd", dates, date_s, price_s, sources, _dispatch_windows())

    assert fits.status == "scored"
    assert fits.degenerate is True
    assert fits.degenerate_pass is False
    assert all(row.degenerate for row in fits.rows)
    assert fits.best_overall is not None
    assert fits.best_overall.separation == pytest.approx(0.0)
    # the raw-z shares are what expose it: the dead side casts no vote at all
    assert fits.best_overall.zero_z_share is not None
    assert fits.best_overall.zero_z_share > 0.5


def test_fit_indicator_on_a_late_source_reports_empty_with_a_reason() -> None:
    """hy/ig shape end to end: late source -> unscoreable + reason, never a raise."""
    fitter = _load_fitter()
    dates = _calendar(DISPATCH_DAYS)
    macro, gdx, slv, _ = _synthetic_series(DISPATCH_DAYS)[1:]
    sources = _synthetic_sources(
        dates, macro, gdx, slv, late_start=dates[-1] - timedelta(days=LATE_SOURCE_DAYS)
    )
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", list(gdx), dtype=pl.Float64)

    fits = fitter.fit_indicator("hy_oas", dates, date_s, price_s, sources, _late_windows())

    assert len(fits.rows) == EXPECTED_GRID_ROWS["hy_oas"]
    assert all(row.separation is None for row in fits.rows)
    assert fits.status == "unscoreable"
    assert fits.reason is not None and "trough" in fits.reason
    assert fits.best_overall is None
    assert fits.best_medium is None
    assert fits.best_long is None
    # nothing scored -> nothing to call degenerate (never a fake flag).
    assert fits.degenerate is False
    assert fits.degenerate_pass is False


def _row(
    fitter: Any,
    *,
    window_days: int,
    separation: float | None,
    mean_peak_z: float | None = None,
    mean_trough_z: float | None = None,
) -> Any:
    """A hand-built GridRow for the pure selection/degenerate helpers.

    ``mean_*`` default to the row's own separation / 0.0 so the older
    tie-break callers keep reading naturally; pass them explicitly whenever the
    dead-zone side matters.
    """
    if separation is not None and mean_peak_z is None:
        mean_peak_z = separation
    return fitter.GridRow(
        params={"window": window_days},
        window_days=window_days,
        separation=separation,
        mean_peak_z=mean_peak_z,
        mean_trough_z=mean_trough_z,
        peak_negative_share=1.0 if (separation or 0.0) > 0 else 0.0,
        trough_positive_share=1.0 if (separation or 0.0) > 0 else 0.0,
        zero_z_share=0.0,
        coverage=1.0,
        z_coverage=1.0,
        peak_days=45,
        trough_days=45,
        scored_days=90,
        degenerate=(
            False
            if separation is None
            else fitter.row_is_degenerate(
                separation=separation, mean_peak_z=mean_peak_z, mean_trough_z=mean_trough_z
            )
        ),
        reason=None,
    )


def test_band_selection_breaks_ties_on_the_shorter_window() -> None:
    fitter = _load_fitter()
    rows = [
        _row(fitter, window_days=756, separation=1.0),
        _row(fitter, window_days=504, separation=1.0),
        _row(fitter, window_days=180, separation=0.5),
    ]
    assert fitter.best_row(rows).window_days == 504  # tie -> shorter window
    assert fitter.best_row_in_band(rows, max_window_days=378).window_days == 180
    assert fitter.best_row_in_band(rows, min_window_days=504).window_days == 504
    assert fitter.best_row_in_band(rows, max_window_days=90) is None
    assert fitter.best_row_in_band([_row(fitter, window_days=756, separation=None)]) is None
    assert fitter.best_row([_row(fitter, window_days=756, separation=None)]) is None
