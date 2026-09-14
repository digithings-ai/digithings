"""Unit tests for the causal levels engine (Track E, issue #137).

Deterministic, network-free. Plain-Python references recompute the Wilder/ATR
math from first principles so a regression in the promoted primitives or the
regime scaler fails loudly.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices._primitives import atr as atr_expr
from digiquant.data.prices._primitives import true_range as true_range_expr
from digiquant.data.prices._primitives import wilder_ema
from digiquant.data.prices.levels import (
    LevelsConfig,
    LevelsError,
    augment,
    cluster_levels,
    compute_levels,
    select_structure,
    snap_sourced,
    trail_policy_str,
    trail_stop,
)
from digiquant.data.prices.technicals import compute_indicators

pytestmark = pytest.mark.unit

SOURCE_REF_RE = re.compile(
    r"^computed:atr14@.+?\|k=[0-9.]+\|reg=[0-9.]+\|br=(atr|pivot|donchian)"
    r"\|piv=2\|rr=[0-9.]+\|src=base$"
)


# ─── Deterministic fixture ───────────────────────────────────────────────────


def _fixture(n: int = 220, *, ampl: float = 3.0) -> pl.DataFrame:
    """OHLC series whose volatility regime genuinely moves (two vol regimes)."""
    timestamps = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    close: list[float] = []
    price = 100.0
    for i in range(n):
        amp = ampl if i % 80 < 40 else ampl * 3.0
        price += amp * math.sin(i / 5.0) + 0.05
        close.append(price)
    high = [c + 1.5 + (i % 4) * 0.2 for i, c in enumerate(close)]
    low = [c - 1.5 - (i % 5) * 0.2 for i, c in enumerate(close)]
    open_ = [close[i] - 0.3 + (i % 3) * 0.1 for i in range(n)]
    volume = [1_000_000.0 + i * 500 for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _monotonic_fixture(n: int = 60) -> pl.DataFrame:
    """Strictly increasing series — has no fractal pivots by construction."""
    closes = [100.0 + i for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
            "open": [c - 0.2 for c in closes],
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1_000_000.0] * n,
        }
    )


def _ref_wilder(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = []
    prev: float | None = None
    for value in values:
        if prev is None:
            prev = value
        else:
            prev = prev + (value - prev) / length
        out.append(prev if len(out) + 1 >= length else None)
    return out


# ─── E1: primitives parity ───────────────────────────────────────────────────


def test_true_range_first_row_is_high_low() -> None:
    df = _fixture(5)
    out = df.select(true_range_expr().alias("tr"))
    assert out["tr"][0] == pytest.approx(float(df["high"][0] - df["low"][0]))


def test_atr_matches_independent_wilder_reference() -> None:
    df = _fixture(40)
    atr = df.select(atr_expr(5).alias("atr"))["atr"].to_list()
    close = df["close"].to_list()
    high = df["high"].to_list()
    low = df["low"].to_list()
    trs = [high[0] - low[0]]
    for i in range(1, len(df)):
        prev = close[i - 1]
        trs.append(max(high[i] - low[i], abs(high[i] - prev), abs(low[i] - prev)))
    ref = _ref_wilder(trs, 5)
    for got, want in zip(atr, ref, strict=True):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, abs=1e-9)


def test_technicals_atr_14_uses_promoted_primitive() -> None:
    df = _fixture(80)
    out = compute_indicators(df)
    assert "atr_14" in out.columns
    expected = df.select(atr_expr(14).alias("atr_14"))["atr_14"].to_list()
    for got, want in zip(out["atr_14"].to_list(), expected, strict=True):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, abs=1e-12)


def test_wilder_ema_is_causal_and_seeded_with_first_value() -> None:
    df = pl.DataFrame({"x": [2.0, 3.0, 6.0, 9.0, 2.0]})
    got = df.select(wilder_ema(pl.col("x"), 3))["x"].to_list()
    ref = _ref_wilder([2.0, 3.0, 6.0, 9.0, 2.0], 3)
    assert got[0] is None and got[1] is None  # min_periods=length
    for got_v, want in zip(got, ref, strict=True):
        if want is None:
            assert got_v is None
        else:
            assert got_v == pytest.approx(want, abs=1e-12)


# ─── E1: config / regime / ATR stop ──────────────────────────────────────────


def test_levels_config_defaults_match_brief() -> None:
    cfg = LevelsConfig()
    assert cfg.atr_len == 14
    assert cfg.fractal_width == 2
    assert cfg.cluster_atr == 0.5
    assert cfg.donchian_len == 20
    assert cfg.k_base == 1.5
    assert cfg.k_regime_bounds == (0.75, 1.5)
    assert cfg.rr_floor == 1.5
    assert cfg.tp_rmultiples == (1.0, 2.0, 3.0)


def test_regime_factor_is_clamped_to_bounds() -> None:
    cfg = LevelsConfig()
    aug = augment(_fixture(240), cfg)
    factor = aug["regime_factor"].drop_nulls().to_list()
    assert factor, "regime factor should be defined with enough bars"
    assert min(factor) >= cfg.k_regime_bounds[0] - 1e-12
    assert max(factor) <= cfg.k_regime_bounds[1] + 1e-12


def test_k_eff_is_k_base_times_regime() -> None:
    cfg = LevelsConfig(k_base=1.5)
    aug = augment(_fixture(240), cfg)
    row = aug.tail(1).to_dicts()[0]
    assert row["k_eff"] == pytest.approx(1.5 * row["regime_factor"])


def test_augment_is_causal_at_every_row() -> None:
    cfg = LevelsConfig()
    df = _fixture(160)
    full = augment(df, cfg)
    for i in (99, 120, 159):
        sliced = augment(df[: i + 1], cfg).tail(1).to_dicts()[0]
        row = full.row(i, named=True)
        for col in ("atr_14", "regime_factor", "k_eff"):
            assert sliced[col] == pytest.approx(row[col], abs=1e-12), (i, col)


def test_augment_emits_no_lookahead_raw_columns() -> None:
    # The raw fractal detectors consume future bars (shift(-j)); they must never
    # be exposed on the public augment() frame. Only the shift(width)-confirmed
    # pivot columns are causal and therefore emitted.
    aug = augment(_fixture(160), LevelsConfig())
    assert "_piv_high_raw" not in aug.columns
    assert "_piv_low_raw" not in aug.columns
    assert "piv_high" in aug.columns
    assert "piv_low" in aug.columns


def test_atr_stop_long_and_short_are_correct_side_of_ref() -> None:
    # 15 bars: ATR(14) is defined but Donchian(20)/regime(100) are not, so the
    # ATR branch is the only available stop.
    df = _monotonic_fixture(15)
    cfg = LevelsConfig()
    long = compute_levels(df, "long", cfg, pair="EUR/USD")
    short = compute_levels(df, "short", cfg, pair="EUR/USD")
    assert long.branch == "atr" and short.branch == "atr"
    assert long.sl == pytest.approx(long.entry_ref - long.k_eff * long.atr)
    assert short.sl == pytest.approx(short.entry_ref + short.k_eff * short.atr)
    assert long.sl < long.entry_ref < short.sl


def test_entry_band_and_ladder_r_multiples() -> None:
    df = _monotonic_fixture()
    cfg = LevelsConfig()
    result = compute_levels(df, "long", cfg, pair="EUR/USD")
    half = cfg.entry_half_atr * result.atr
    assert result.entry_low == pytest.approx(result.entry_ref - half)
    assert result.entry_high == pytest.approx(result.entry_ref + half)
    risk = abs(result.entry_ref - result.sl)
    assert [rung.r for rung in result.tp_ladder] == [1.0, 2.0, 3.0]
    for rung in result.tp_ladder:
        assert rung.price == pytest.approx(result.entry_ref + rung.r * risk)
        assert rung.src == "atr"


def test_source_ref_grammar() -> None:
    df = _fixture(220)
    result = compute_levels(df, "long", LevelsConfig(), pair="EUR/USD")
    assert SOURCE_REF_RE.match(result.source_ref), result.source_ref
    assert "atr14@2024-" in result.source_ref


def test_full_precision_contract_values_are_not_4dp_rounded() -> None:
    df = _fixture(220)
    result = compute_levels(df, "long", LevelsConfig(), pair="EUR/USD")
    payload = result.as_dict()
    assert payload["entry"]["ref"] == result.entry_ref
    assert payload["sl"] == result.sl
    assert payload["atr"] == result.atr
    assert len({payload["entry"]["ref"], payload["sl"], payload["atr"]}) >= 2


def test_insufficient_bars_raise_levels_error() -> None:
    with pytest.raises(LevelsError, match="at least"):
        compute_levels(_fixture(5), "long", LevelsConfig())


def test_bad_direction_raises() -> None:
    with pytest.raises(LevelsError, match="direction"):
        compute_levels(_fixture(220), "sideways", LevelsConfig())


def test_trail_stop_ratchets_only_one_way() -> None:
    cfg = LevelsConfig(trail_atr=2.0)
    # Long: a new high raises the stop; a pullback never lowers it.
    assert trail_stop(
        direction="long",
        high_water=110.0,
        low_water=90.0,
        entry_ref=100.0,
        atr_value=1.0,
        cfg=cfg,
    ) == pytest.approx(108.0)
    assert trail_stop(
        direction="long",
        high_water=101.0,
        low_water=90.0,
        entry_ref=100.0,
        atr_value=1.0,
        cfg=cfg,
    ) == pytest.approx(99.0)
    # Short mirror.
    assert trail_stop(
        direction="short",
        high_water=110.0,
        low_water=90.0,
        entry_ref=100.0,
        atr_value=1.0,
        cfg=cfg,
    ) == pytest.approx(92.0)


def test_technicals_columns_unchanged_by_refactor() -> None:
    df = _fixture(80)
    out = compute_indicators(df)
    assert list(out.columns) == list(TECHNICAL_COLUMNS)


# ─── E2: causal fractal pivots + clustering + structural stop + snap ─────────


def _structural_fixture(
    *,
    n: int = 60,
    support: float = 99.0,
    resistance: float = 102.0,
) -> pl.DataFrame:
    """Flat 100 +/- 0.5 range with one swing low (idx 30) and high (idx 40)."""
    rows = {
        "timestamp": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
        "open": [100.0] * n,
        "high": [100.5] * n,
        "low": [99.5] * n,
        "close": [100.0] * n,
        "volume": [1_000_000.0] * n,
    }
    rows["low"][30] = support
    rows["high"][40] = resistance
    return pl.DataFrame(rows)


def test_fractal_pivots_confirmed_only_after_width_bars() -> None:
    df = _structural_fixture()
    cfg = LevelsConfig(fractal_width=2)
    aug = augment(df, cfg)
    piv_low = aug["piv_low"].to_list()
    piv_high = aug["piv_high"].to_list()
    assert piv_low[30] is None  # not yet confirmed at the pivot bar
    assert piv_low[31] is None
    assert piv_low[32] == pytest.approx(99.0)  # confirmed after `width` bars
    assert piv_high[41] is None
    assert piv_high[42] == pytest.approx(102.0)


def test_pivot_columns_are_causal_at_every_row() -> None:
    df = _structural_fixture()
    cfg = LevelsConfig(fractal_width=2)
    full = augment(df, cfg)
    for i in (29, 30, 31, 32, 41, 42, 59):
        sliced = augment(df[: i + 1], cfg).tail(1).to_dicts()[0]
        row = full.row(i, named=True)
        assert sliced["piv_low"] == row["piv_low"], i
        assert sliced["piv_high"] == row["piv_high"], i


def test_cluster_levels_groups_within_tolerance() -> None:
    # support reps use the cluster low; resistance reps use the cluster high.
    values = [100.0, 100.3, 101.0, 95.0]
    assert cluster_levels(values, 1.5, side="support") == [95.0, 100.0]
    assert cluster_levels(values, 1.5, side="resistance") == [95.0, 101.0]
    assert cluster_levels([], 1.5, side="support") == []


def test_select_structure_picks_nearest_valid_side() -> None:
    support, resistance = select_structure(
        [90.0, 98.0, 101.0],  # lows: 101 is above ref, must be ignored
        [97.0, 103.0, 110.0],  # highs: 97 is below ref, must be ignored
        100.0,
        0.5,
    )
    assert support == pytest.approx(98.0)
    assert resistance == pytest.approx(103.0)
    assert select_structure([], [], 100.0, 0.5) == (None, None)


def test_structural_branch_uses_pivot_stop_and_snaps_ladder() -> None:
    df = _structural_fixture(support=99.0, resistance=102.0)
    cfg = LevelsConfig(structural_buffer_atr=0.0)
    result = compute_levels(df, "long", cfg, pair="EUR/USD")
    assert result.branch == "pivot"
    assert result.pivot_count == 2
    assert result.sl == pytest.approx(99.0)
    snapped = [rung for rung in result.tp_ladder if rung.src == "pivot"]
    assert len(snapped) == 1
    assert snapped[0].r == 2.0
    assert snapped[0].price == pytest.approx(102.0)
    assert "br=pivot" in result.source_ref


def test_structural_stop_short_mirrors_long() -> None:
    df = _structural_fixture(support=98.0, resistance=101.0)
    cfg = LevelsConfig(structural_buffer_atr=0.0)
    result = compute_levels(df, "short", cfg, pair="EUR/USD")
    assert result.branch == "pivot"
    assert result.sl == pytest.approx(101.0)
    assert result.sl > result.entry_ref


def test_monotonic_trend_uses_donchian_branch() -> None:
    df = _monotonic_fixture()
    result = compute_levels(df, "long", LevelsConfig(), pair="EUR/USD")
    assert result.pivot_count == 0
    assert result.branch == "donchian"
    assert "br=donchian" in result.source_ref


def test_atr_branch_when_donchian_not_yet_defined() -> None:
    # 15 bars clears ATR(14) but not Donchian(20) or the 100-bar regime.
    result = compute_levels(_monotonic_fixture(15), "long", LevelsConfig(), pair="EUR/USD")
    assert result.branch == "atr"
    assert "br=atr" in result.source_ref


def test_reward_uncapped_flag_tracks_missing_opposite_structure() -> None:
    # No pivot/Donchian target above a monotonic advance: reward is undefined and
    # the structural stop is accepted uncapped by design.
    uncapped = compute_levels(_monotonic_fixture(), "long", LevelsConfig(), pair="EUR/USD")
    assert uncapped.as_dict()["reward_uncapped"] is True

    # A resistance pivot above ref means a real R:R check actually ran.
    checked = compute_levels(
        _structural_fixture(support=99.0, resistance=102.0),
        "long",
        LevelsConfig(structural_buffer_atr=0.0),
        pair="EUR/USD",
    )
    assert checked.branch == "pivot"
    assert checked.as_dict()["reward_uncapped"] is False


# ─── E3: Donchian branch + trail policy + regime scaling ─────────────────────


def test_donchian_channel_uses_prior_bars_only() -> None:
    df = _fixture(60)
    cfg = LevelsConfig(donchian_len=20)
    aug = augment(df, cfg)
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    don_high = aug["don_high_prev"].to_list()
    don_low = aug["don_low_prev"].to_list()
    assert don_high[19] is None and don_low[19] is None
    for i in (20, 35, 59):
        assert don_high[i] == pytest.approx(max(highs[i - 20 : i]))
        assert don_low[i] == pytest.approx(min(lows[i - 20 : i]))


def test_donchian_columns_are_causal() -> None:
    df = _fixture(80)
    cfg = LevelsConfig()
    full = augment(df, cfg)
    for i in (25, 50, 79):
        sliced = augment(df[: i + 1], cfg).tail(1).to_dicts()[0]
        row = full.row(i, named=True)
        assert sliced["don_high_prev"] == pytest.approx(row["don_high_prev"], abs=1e-12)
        assert sliced["don_low_prev"] == pytest.approx(row["don_low_prev"], abs=1e-12)


def test_donchian_stop_sits_beyond_prior_channel_low() -> None:
    df = _monotonic_fixture()
    cfg = LevelsConfig()
    aug = augment(df, cfg)
    result = compute_levels(df, "long", cfg, pair="EUR/USD")
    expected = aug["don_low_prev"][-1] - cfg.structural_buffer_atr * result.atr
    assert result.sl == pytest.approx(expected)


def test_snap_sourced_keeps_provenance() -> None:
    pool = [(102.0, "pivot"), (110.0, "donchian")]
    assert snap_sourced(102.3, pool, 0.5) == (102.0, "pivot")
    assert snap_sourced(110.2, pool, 0.5) == (110.0, "donchian")
    assert snap_sourced(105.0, pool, 0.5) is None


def test_trail_policy_carries_multiple_and_activation() -> None:
    cfg = LevelsConfig(trail_atr=2.5, trail_activate_r=1.0)
    policy = trail_policy_str(cfg)
    assert "2.5" in policy and "1" in policy
    result = compute_levels(_monotonic_fixture(), "long", cfg, pair="EUR/USD")
    assert result.trail_policy == policy


def test_regime_scaling_both_raises_and_lowers_k_eff() -> None:
    cfg = LevelsConfig()
    aug = augment(_fixture(240), cfg)
    factors = aug["regime_factor"].drop_nulls().to_list()
    assert min(factors) < 1.0 < max(factors), (min(factors), max(factors))
    k_eff = aug["k_eff"].drop_nulls().to_list()
    lo, hi = cfg.k_regime_bounds
    assert min(k_eff) >= cfg.k_base * lo - 1e-12
    assert max(k_eff) <= cfg.k_base * hi + 1e-12
