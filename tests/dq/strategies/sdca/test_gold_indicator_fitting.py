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

And the EQUAL-WEIGHT GREEDY SELECTION (Task 2), on synthetic z-vectors: the
anchor is the shipped rolling90/z1.0 no-trend ``valuation_z``, the aggregate is
the SHIPPED equal-weight blend (``compute_composite_risk``, weight 1.0 — mean and
clip, never a hand-rolled mean), the candidate pool is ``verdict == "keep"`` in a
FROZEN order (individual separation DESC, ties to the shorter window then the
name), and a candidate is kept iff its addition STRICTLY improves the aggregate —
a delta of exactly 0.0 is a drop. Every candidate's delta is recorded, together
with the scored-day count before and after, because the shipped blend sums with
``ignore_nulls=False`` and a warm-up null shrinks the scored sample mid-run.

Not vacuous: the one-sided case fails the scoring tests, the abs-guard fails on
any ``abs()`` of the metric, and the dispatch test compares against the shipped
function's own output rather than a restated copy.
"""

from __future__ import annotations

import importlib.util
import json
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


# --------------------------------------------------------------------------- #
# 5. Equal-weight greedy selection (Plan-19 Task 2 — the frozen rule, verbatim)
# --------------------------------------------------------------------------- #


def _greedy_inputs(fitter: Any) -> dict[str, Any]:
    """Synthetic z-vectors covering the three roles the rule must separate.

    Anchor (``valuation``, peak -1.0 / trough +1.0) scores +2.0 alone.

    * ``improver`` (peak -3.0 / trough +3.0, individual +6.0) lifts the aggregate.
    * ``diluter`` (peak -1.0 / trough +1.0, individual +2.0) drags the aggregate
      back toward its own weaker separation -> strict improvement fails.
    * ``hurter`` (peak +3.0 / trough -3.0, individual -6.0) votes backwards.
    * ``neutral`` is built in its own test: a candidate whose individual
      separation EXACTLY equals the current aggregate (delta == 0.0).
    """
    dates, windows = _calendar(), _windows()
    z_vectors = {
        "improver": _two_level_z(dates, windows, peak=-3.0, trough=3.0),
        "diluter": _two_level_z(dates, windows, peak=-1.0, trough=1.0),
        "hurter": _two_level_z(dates, windows, peak=3.0, trough=-3.0),
    }
    candidates = (
        fitter.Candidate(
            name="improver",
            params={"window": 180},
            window_days=180,
            individual_separation=6.0,
        ),
        fitter.Candidate(
            name="diluter",
            params={"window": 378},
            window_days=378,
            individual_separation=2.0,
        ),
        fitter.Candidate(
            name="hurter",
            params={"window": 90},
            window_days=90,
            individual_separation=-6.0,
        ),
    )
    return {
        "dates": dates,
        "windows": windows,
        "anchor": _two_level_z(dates, windows, peak=-1.0, trough=1.0),
        "candidates": candidates,
        "z_vectors": z_vectors,
    }


def test_greedy_select_keeps_the_improver_and_drops_the_rest_with_recorded_deltas() -> None:
    """The owner's rule: aggregate improves -> keep, does not -> drop (delta recorded).

    Anchored on the anchor alone (aggregate +2.0), in the FROZEN order
    (individual separation DESC):

    * ``improver`` -> aggregate +4.0, delta +2.0 -> KEPT.
    * ``diluter``  -> aggregate +10/3, delta -2/3 -> dropped.
    * ``hurter``   -> aggregate +2/3, delta -10/3 -> dropped.

    ``step 3``'s ``aggregate_before`` is the KEPT aggregate (+4.0), not the
    diluter's trial (+10/3): a dropped candidate is never carried forward.
    """
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)

    run = fitter.greedy_select(
        dates=inputs["dates"],
        windows=inputs["windows"],
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=inputs["candidates"],
        z_vectors=inputs["z_vectors"],
    )

    assert run.kept == ("improver",)
    assert run.dropped == ("diluter", "hurter")
    # steps come out in the frozen candidate order, one row per candidate
    assert [s.name for s in run.steps] == ["improver", "diluter", "hurter"]
    assert [s.step for s in run.steps] == [1, 2, 3]
    assert run.anchor_separation == pytest.approx(2.0)
    assert run.final_separation == pytest.approx(4.0)

    by_name = {s.name: s for s in run.steps}
    assert by_name["improver"].kept is True
    assert by_name["improver"].aggregate_before == pytest.approx(2.0)
    assert by_name["improver"].aggregate_after == pytest.approx(4.0)
    assert by_name["improver"].delta == pytest.approx(2.0)
    assert by_name["improver"].individual_separation == pytest.approx(6.0)
    assert by_name["improver"].params == {"window": 180}
    assert by_name["improver"].window_days == 180

    assert by_name["diluter"].kept is False
    assert by_name["diluter"].aggregate_after == pytest.approx(10.0 / 3.0)
    assert by_name["diluter"].delta == pytest.approx(-2.0 / 3.0)

    assert by_name["hurter"].kept is False
    assert by_name["hurter"].aggregate_before == pytest.approx(4.0)  # not the diluter's 2.0
    assert by_name["hurter"].aggregate_after == pytest.approx(2.0 / 3.0)
    assert by_name["hurter"].delta == pytest.approx(-10.0 / 3.0)


def test_greedy_select_drops_a_candidate_that_only_equals_the_aggregate() -> None:
    """STRICT improvement: a delta of exactly 0.0 is a DROP, not a keep.

    The candidate's own separation equals the anchor's aggregate (+2.0), so the
    equal-weight blend of the two is exactly +2.0 again — no improvement.
    """
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)
    neutral = fitter.Candidate(
        name="neutral",
        params={"window": 180},
        window_days=180,
        individual_separation=2.0,
    )

    run = fitter.greedy_select(
        dates=inputs["dates"],
        windows=inputs["windows"],
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=(neutral,),
        z_vectors={"neutral": inputs["z_vectors"]["diluter"]},
    )

    assert len(run.steps) == 1
    step = run.steps[0]
    assert step.aggregate_before == pytest.approx(2.0)
    assert step.aggregate_after == pytest.approx(2.0)
    assert step.delta == pytest.approx(0.0, abs=1e-12)
    assert step.delta == 0.0  # exactly, not approximately
    assert step.kept is False
    assert run.kept == ()
    assert run.dropped == ("neutral",)
    assert run.final_separation == pytest.approx(2.0)  # unchanged by the drop


def test_greedy_select_records_the_scored_day_shrink_from_a_warm_up_null() -> None:
    """The null-propagation hazard, made visible: days-delta rides with the delta.

    ``compute_composite_risk`` sums with ``ignore_nulls=False``, so a candidate
    whose warm-up leaves a few PINNED-window days null removes those days from the
    scored sample. The delta table must therefore carry ``scored_days`` before /
    after and the days-delta, or a shrinking sample reads like a vote change.
    """
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)
    dates, windows = inputs["dates"], inputs["windows"]
    scored = _window_days(windows, dates)
    total_window_days = len(scored[CycleKind.PEAK]) + len(scored[CycleKind.TROUGH])
    gap = scored[CycleKind.PEAK][:20]
    warm = list(_two_level_z(dates, windows, peak=-3.0, trough=3.0))
    for i in gap:
        warm[i] = None

    run = fitter.greedy_select(
        dates=dates,
        windows=windows,
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=(
            fitter.Candidate(
                name="warmup",
                params={"window": 180},
                window_days=180,
                individual_separation=6.0,
            ),
        ),
        z_vectors={"warmup": warm},
    )

    step = run.steps[0]
    assert step.scored_days_before == total_window_days
    assert step.scored_days_after == total_window_days - len(gap)
    assert step.days_delta == -len(gap)
    assert step.days_delta < 0  # the sample really did shrink
    assert step.kept is True
    assert step.delta == pytest.approx(2.0)
    assert step.coverage_before == pytest.approx(1.0)
    assert step.coverage_after == pytest.approx((total_window_days - len(gap)) / total_window_days)


def test_greedy_select_rejects_a_candidate_order_that_is_not_frozen() -> None:
    """The frozen order is the rule, not an accident: separation DESC is enforced."""
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)
    reversed_candidates = tuple(reversed(inputs["candidates"]))

    with pytest.raises(ValueError, match="frozen order"):
        fitter.greedy_select(
            dates=inputs["dates"],
            windows=inputs["windows"],
            anchor_name=fitter.ANCHOR_NAME,
            anchor=inputs["anchor"],
            candidates=reversed_candidates,
            z_vectors=inputs["z_vectors"],
        )


def test_greedy_select_requires_a_z_vector_for_every_candidate() -> None:
    """A missing vector is a loud failure, never a silently skipped candidate."""
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)

    with pytest.raises(ValueError, match="no z vector"):
        fitter.greedy_select(
            dates=inputs["dates"],
            windows=inputs["windows"],
            anchor_name=fitter.ANCHOR_NAME,
            anchor=inputs["anchor"],
            candidates=inputs["candidates"],
            z_vectors={"improver": inputs["z_vectors"]["improver"]},
        )


def test_aggregate_z_is_the_shipped_equal_weight_blend_with_its_clip() -> None:
    """Reuse, not reimplementation: equal weight 1.0 -> the shipped mean-and-clip.

    ``compute_composite_risk`` is the shipped blend: with every member at
    ``weight=EQUAL_WEIGHT`` it IS ``(sum(z)/n).clip(-3, 3)``. ``aggregate_z`` must
    return exactly that (including the clip and the null-day rule), and must
    refuse the duplicate member name the shipped blend refuses.
    """
    from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk

    fitter = _load_fitter()
    assert fitter.EQUAL_WEIGHT == 1.0
    a = [1.0, -2.0, None, 0.5]
    b = [0.0, 0.0, 4.0, -1.0]

    got = fitter.aggregate_z([("a", a), ("b", b)])

    shipped = compute_composite_risk(
        [
            IndicatorWeight(name="a", z=pl.Series(a, dtype=pl.Float64), weight=fitter.EQUAL_WEIGHT),
            IndicatorWeight(name="b", z=pl.Series(b, dtype=pl.Float64), weight=fitter.EQUAL_WEIGHT),
        ]
    )["composite_z"].to_list()
    assert got == shipped
    # a null in ANY member nulls that day (ignore_nulls=False), never partial
    assert got[2] is None
    # a loud leg is clipped, exactly as shipped (5.0 + 4.0)/2 -> 3.0
    assert fitter.aggregate_z([("a", [5.0]), ("b", [4.0])]) == [3.0]
    assert fitter.aggregate_z([("a", [-5.0]), ("b", [-4.0])]) == [-3.0]
    # duplicate member names are refused by the shipped blend, not merged away
    with pytest.raises(ValueError, match="duplicate"):
        fitter.aggregate_z([("a", [1.0]), ("a", [2.0])])


def test_equal_weight_separation_scores_the_aggregate_with_the_frozen_metric() -> None:
    """The aggregate is scored by the SAME Ruling-1 metric as a single leg."""
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()

    score = fitter.equal_weight_separation(
        dates,
        windows,
        [("valuation", _two_level_z(dates, windows, peak=-1.0, trough=1.0))],
    )

    assert score.separation == pytest.approx(2.0)
    assert score.reason is None


def test_anchor_z_is_the_shipped_rolling90_z10_no_trend_anchor() -> None:
    """The anchor is built with SHIPPED code, zero production edits (the v4 seed)."""
    from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
    from digiquant.strategies.sdca.risk_index import build_risk_index

    fitter = _load_fitter()
    assert (fitter.ANCHOR_FORM, fitter.ANCHOR_ROLLING_WINDOW, fitter.ANCHOR_ROLLING_Z) == (
        "rolling_z",
        90,
        1.0,
    )
    dates = _calendar(DISPATCH_DAYS)
    price_s = pl.Series(
        "price",
        [100.0 + 0.02 * i for i in range(len(dates))],
        dtype=pl.Float64,
    )
    date_s = pl.Series("date", dates, dtype=pl.Date)

    anchor = fitter.anchor_z(date_s, price_s)

    model = resolve_sdca_risk_model(
        "rolling_z",
        dates=date_s,
        price=price_s,
        rolling_window=fitter.ANCHOR_ROLLING_WINDOW,
        rolling_z=fitter.ANCHOR_ROLLING_Z,
    )
    expected = build_risk_index(
        date_s, price_s, model, extra_indicators=None, valuation_weight=fitter.EQUAL_WEIGHT
    )["valuation_z"].to_list()
    assert anchor == expected
    assert len(anchor) == len(dates)
    assert any(v is not None for v in anchor)
    # the rails are null only at the very start of the calendar, never inside it
    assert anchor[0] is None
    assert all(v is not None for v in anchor[100:])


def _indicator_fits(
    fitter: Any,
    name: str,
    *,
    verdict: str,
    separation: float | None,
    window_days: int,
    params: dict[str, int] | None = None,
    reason: str | None = None,
    degenerate_pass: bool = False,
) -> Any:
    """A minimal VALIDATED IndicatorFits for the candidate-pool helpers."""
    row = _row(
        fitter,
        window_days=window_days,
        separation=separation,
        mean_peak_z=None if separation is None else -1.0,
        mean_trough_z=None if separation is None else 1.0,
    ).model_copy(update={"params": params or {"window": window_days}})
    return fitter.IndicatorFits(
        name=name,
        family="level_z",
        grid_rows=1,
        status="unscoreable" if separation is None else "scored",
        reason=reason,
        rows=() if separation is None else (row,),
        best_overall=row if separation is not None else None,
        best_medium=row if separation is not None else None,
        best_long=row if separation is not None else None,
        degenerate=degenerate_pass,
        degenerate_pass=degenerate_pass,
        verdict=verdict,
    )


def test_candidate_pool_takes_verdict_keep_only_and_freezes_the_order() -> None:
    """`verdict == "keep"` is the filter — `separation > 0` would admit the
    degenerate oscillators, which Ruling 1 keeps out of every keep list."""
    fitter = _load_fitter()
    fits = {
        "real_rate": _indicator_fits(
            fitter, "real_rate", verdict="keep", separation=3.40, window_days=504
        ),
        "sma_band": _indicator_fits(
            fitter,
            "sma_band",
            verdict="keep",
            separation=3.12,
            window_days=378,
            params={"sma_band_window": 378, "sma_band_min_samples": 30},
        ),
        "gld_slv": _indicator_fits(
            fitter, "gld_slv", verdict="keep", separation=2.39, window_days=504
        ),
        "nfci": _indicator_fits(fitter, "nfci", verdict="keep", separation=1.60, window_days=756),
        "walcl": _indicator_fits(
            fitter,
            "walcl",
            verdict="keep",
            separation=1.02,
            window_days=180,
            params={"roc_days": 90, "window": 180},
        ),
        # positive separation, but a dead-side pass -> owner review, NOT a candidate
        "weekly_rsi": _indicator_fits(
            fitter, "weekly_rsi", verdict="degenerate_pass", separation=0.4420, window_days=105
        ),
        "weekly_macd": _indicator_fits(
            fitter, "weekly_macd", verdict="degenerate_pass", separation=0.3477, window_days=90
        ),
        "uup": _indicator_fits(fitter, "uup", verdict="drop", separation=-1.88, window_days=90),
        "hy_oas": _indicator_fits(
            fitter, "hy_oas", verdict="unscoreable", separation=None, window_days=90, reason="late"
        ),
    }

    pool = fitter.candidate_pool(fits)

    assert [c.name for c in pool] == ["real_rate", "sma_band", "gld_slv", "nfci", "walcl"]
    assert [c.individual_separation for c in pool] == [3.40, 3.12, 2.39, 1.60, 1.02]
    assert [c.window_days for c in pool] == [504, 378, 504, 756, 180]
    assert pool[1].params == {"sma_band_window": 378, "sma_band_min_samples": 30}
    # a degenerate pass is never a candidate, whatever its individual separation
    assert "weekly_rsi" not in {c.name for c in pool}
    assert "weekly_macd" not in {c.name for c in pool}
    assert "uup" not in {c.name for c in pool}
    assert "hy_oas" not in {c.name for c in pool}


def test_candidate_pool_ties_break_on_shorter_window_then_name() -> None:
    fitter = _load_fitter()
    fits = {
        "long_leg": _indicator_fits(
            fitter, "long_leg", verdict="keep", separation=2.0, window_days=756
        ),
        "short_leg": _indicator_fits(
            fitter, "short_leg", verdict="keep", separation=2.0, window_days=90
        ),
        "b_leg": _indicator_fits(fitter, "b_leg", verdict="keep", separation=2.0, window_days=90),
        "a_leg": _indicator_fits(fitter, "a_leg", verdict="keep", separation=2.0, window_days=90),
    }

    assert [c.name for c in fitter.candidate_pool(fits)] == [
        "a_leg",
        "b_leg",
        "short_leg",
        "long_leg",
    ]


def test_two_member_equal_weight_blend_is_the_mean_of_the_two_separations() -> None:
    """Why a single weak candidate cannot help a strong anchor (clip aside).

    With two members at equal weight and no clip binding, the aggregate
    separation is the MEAN of the two members' separations, so a two-member step
    can only improve on the anchor when the candidate's own separation is HIGHER
    than the anchor's. This is the arithmetic behind the real run's verdict, and
    it is pinned here on synthetic vectors with no clip in play (both legs stay
    inside +/-1 so the mean can never reach the +/-3 bound).
    """
    fitter = _load_fitter()
    dates, windows = _calendar(), _windows()
    anchor = _two_level_z(dates, windows, peak=-1.0, trough=1.0)  # sep +2.0
    weaker = _two_level_z(dates, windows, peak=-0.5, trough=0.5)  # sep +1.0
    stronger = _two_level_z(dates, windows, peak=-1.5, trough=1.5)  # sep +3.0

    anchor_sep = fitter.separation(dates, anchor, windows).separation
    assert anchor_sep == pytest.approx(2.0)
    down = fitter.equal_weight_separation(dates, windows, [("a", anchor), ("b", weaker)])
    up = fitter.equal_weight_separation(dates, windows, [("a", anchor), ("b", stronger)])
    assert down.separation == pytest.approx(1.5)  # (2.0 + 1.0) / 2
    assert up.separation == pytest.approx(2.5)  # (2.0 + 3.0) / 2
    # delta = half the gap between the candidate and the anchor, either direction
    assert down.separation - anchor_sep == pytest.approx(-0.5)
    assert up.separation - anchor_sep == pytest.approx(+0.5)


def test_trajectory_walks_the_live_member_set_not_the_final_one() -> None:
    """Trajectory rows must show the set kept SO FAR, not the final set."""
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)
    run = fitter.greedy_select(
        dates=inputs["dates"],
        windows=inputs["windows"],
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=inputs["candidates"],
        z_vectors=inputs["z_vectors"],
    )

    rows = fitter._trajectory(run)

    assert rows[0] == {
        "step": 0,
        "added": None,
        "kept": None,
        "members": ["valuation"],
        "separation": pytest.approx(2.0),
        "scored_days": 273,
    }
    # kept -> joins the live set; dropped -> does NOT, and its trial value is
    # carried only as `separation_if_kept`.
    assert rows[1]["members"] == ["valuation", "improver"]
    assert rows[1]["separation"] == pytest.approx(4.0)
    assert rows[2]["members"] == ["valuation", "improver"]
    assert rows[2]["separation"] == pytest.approx(4.0)
    assert rows[2]["separation_if_kept"] == pytest.approx(10.0 / 3.0)
    assert rows[3]["members"] == ["valuation", "improver"]
    assert rows[-1]["members"] == list(run.final_members)


def test_selection_payload_carries_the_deliverable_tables() -> None:
    """The artifact must carry the delta table, pool order, cross-check and review."""
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)
    dates, windows = inputs["dates"], inputs["windows"]
    run = fitter.greedy_select(
        dates=dates,
        windows=windows,
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=inputs["candidates"],
        z_vectors=inputs["z_vectors"],
    )
    cross, members = fitter.cross_check_aggregate(
        dates=dates,
        windows=windows,
        anchor=inputs["anchor"],
        candidates=inputs["candidates"],
        z_vectors=inputs["z_vectors"],
    )
    outcome = fitter.SelectionOutcome(
        pool=tuple(inputs["candidates"]),
        run=run,
        cross_check=cross,
        cross_check_members=members,
    )
    fits = {
        "improver": _indicator_fits(
            fitter, "improver", verdict="keep", separation=6.0, window_days=180
        ),
        "weekly_rsi": _indicator_fits(
            fitter,
            "weekly_rsi",
            verdict="degenerate_pass",
            separation=0.44,
            window_days=105,
            degenerate_pass=True,
        ),
    }

    payload = fitter.selection_payload(dates, fits, outcome, windows_label="synthetic ±45d")

    assert payload["kept"] == ["improver"]
    assert payload["kept_params"] == {"improver": {"window": 180}}
    assert payload["dropped"] == ["diluter", "hurter"]
    assert payload["dropped_deltas"]["hurter"]["delta"] == pytest.approx(-10.0 / 3.0)
    assert payload["dropped_deltas"]["hurter"]["days_delta"] == 0
    assert [row["name"] for row in payload["candidate_pool"]] == [
        "improver",
        "diluter",
        "hurter",
    ]
    assert [row["order"] for row in payload["candidate_pool"]] == [1, 2, 3]
    assert len(payload["delta_table"]) == 3
    assert payload["final"]["members"] == ["valuation", "improver"]
    assert payload["cross_check"]["used_for_selection"] is False
    assert payload["cross_check"]["members"] == [
        "valuation",
        "improver",
        "diluter",
        "hurter",
    ]
    # the degenerate pass is listed for owner review, never inside `kept`
    assert [row["name"] for row in payload["degenerate_owner_review"]] == ["weekly_rsi"]
    assert "weekly_rsi" not in payload["kept"]
    assert payload["in_sample"] is True
    assert "IN-SAMPLE" in payload["in_sample_label"]
    assert "STRICTLY improves" in payload["rule"]
    # json-serializable end to end
    json.dumps(payload)


def test_print_selection_prints_the_plain_keep_drop_list_with_deltas(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The owner deliverable is the console table — every keep/drop and its delta."""
    fitter = _load_fitter()
    inputs = _greedy_inputs(fitter)

    run = fitter.greedy_select(
        dates=inputs["dates"],
        windows=inputs["windows"],
        anchor_name=fitter.ANCHOR_NAME,
        anchor=inputs["anchor"],
        candidates=inputs["candidates"],
        z_vectors=inputs["z_vectors"],
    )
    fitter.print_selection(run, anchor_label="rolling_z 90d/z1.0 (no time trend)")

    out = capsys.readouterr().out
    assert "improver" in out and "KEEP" in out
    assert "diluter" in out and "DROP" in out
    assert "hurter" in out
    assert "+2.0000" in out  # the improver's recorded delta
    assert "-10.0000/3" not in out  # formatted, not a bare fraction
    assert "-3.3333" in out  # the hurter's recorded delta
    assert "IN-SAMPLE" in out


def test_cli_requires_exactly_one_mode() -> None:
    """No mode -> usage error; `--fit` and `--select` are the only two modes."""
    fitter = _load_fitter()
    with pytest.raises(SystemExit):
        fitter.main([])
    with pytest.raises(SystemExit):
        fitter.main(["--fit", "--select"])
