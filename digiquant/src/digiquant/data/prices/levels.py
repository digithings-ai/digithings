"""Causal ATR / swing-pivot / Donchian trade-levels engine (Track E, issue #137).

Pure Polars, no I/O. Every time-series derivation is causal — Wilder ATR, the
volatility-regime scaler, fractal pivots (confirmed via ``shift(width)``), and
the Donchian channel (``shift(1)``) never read a bar the engine could not have
seen at its as-of timestamp. :func:`compute_levels` folds those columns into a
deterministic :class:`LevelsResult` for the latest bar.

The engine emits *candidate* levels only. It never sizes or places orders; the
twelve-x consumer maps the contract onto ``Level(provenance="computed")`` and
``apply_guard`` remains the final authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from digiquant.data.prices._primitives import atr as _atr_expr


class LevelsError(ValueError):
    """Raised when the input frame cannot support a causal levels computation."""


@dataclass(frozen=True)
class LevelsConfig:
    """Tunables for :func:`compute_levels`.

    Defaults mirror the Phase 1 brief: ATR(14), 2-bar fractal pivots, Donchian
    (20), base stop ``k=1.5`` scaled by a regime factor clamped to
    ``(0.75, 1.5)``, an R:R floor of ``1.5`` and a ``1R/2R/3R`` ladder.
    """

    atr_len: int = 14
    fractal_width: int = 2
    cluster_atr: float = 0.5
    donchian_len: int = 20
    k_base: float = 1.5
    k_regime_bounds: tuple[float, float] = (0.75, 1.5)
    rr_floor: float = 1.5
    tp_rmultiples: tuple[float, ...] = (1.0, 2.0, 3.0)
    regime_len: int = 100
    entry_half_atr: float = 0.25
    structural_buffer_atr: float = 0.25
    snap_tol_atr: float = 0.5
    trail_atr: float = 2.0
    trail_activate_r: float = 1.0


@dataclass(frozen=True)
class TpRung:
    """One r-multiple target rung."""

    r: float
    price: float
    src: str


@dataclass(frozen=True)
class LevelsResult:
    """Deterministic causal levels snapshot for one direction/pair."""

    pair: str
    direction: str
    entry_ref: float
    entry_low: float
    entry_high: float
    sl: float
    tp_ladder: tuple[TpRung, ...]
    trail_policy: str
    source_ref: str
    computed_at: str
    atr: float
    k_eff: float
    regime: float
    branch: str
    pivot_count: int
    asof: str | None = None
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """JSON contract — full-precision floats, never 4dp-rounded."""
        out = {
            "pair": self.pair,
            "direction": self.direction,
            "entry": {
                "low": self.entry_low,
                "high": self.entry_high,
                "ref": self.entry_ref,
            },
            "sl": self.sl,
            "tp_ladder": [
                {"r": rung.r, "price": rung.price, "src": rung.src} for rung in self.tp_ladder
            ],
            "trail_policy": self.trail_policy,
            "source_ref": self.source_ref,
            "computed_at": self.computed_at,
            "atr": self.atr,
            "k_eff": self.k_eff,
            "regime": self.regime,
            "branch": self.branch,
            "pivot_count": self.pivot_count,
            "asof": self.asof,
        }
        if self.extras:
            out.update(self.extras)
        return out


def _normalize(df: pl.DataFrame) -> pl.DataFrame:
    rename = {c: c.lower() for c in df.columns if c != c.lower()}
    if rename:
        df = df.rename(rename)
    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise LevelsError(f"OHLC columns missing: {sorted(missing)}. Got: {df.columns}")
    casts = [pl.col(c).cast(pl.Float64) for c in ("high", "low", "close")]
    df = df.with_columns(casts)
    if "timestamp" in df.columns:
        df = df.sort("timestamp")
    return df


def _regime_expr(cfg: LevelsConfig) -> pl.Expr:
    """``atr / SMA(atr, regime_len)`` — the volatility-regime ratio (causal)."""
    atr_col = pl.col(f"atr_{cfg.atr_len}")
    baseline = atr_col.rolling_mean(window_size=cfg.regime_len, min_periods=cfg.regime_len)
    return (atr_col / baseline).alias("_regime_ratio")


def _regime_factor_expr(cfg: LevelsConfig) -> pl.Expr:
    lo, hi = cfg.k_regime_bounds
    return pl.col("_regime_ratio").clip(lo, hi).fill_null(1.0).alias("regime_factor")


def _k_eff_expr(cfg: LevelsConfig) -> pl.Expr:
    return (pl.lit(cfg.k_base) * pl.col("regime_factor")).alias("k_eff")


def _pivot_high_raw_expr(cfg: LevelsConfig) -> pl.Expr:
    """Boolean: is this bar a strict fractal high? (Consumes future bars.)"""
    cond = pl.lit(True)
    for j in range(1, cfg.fractal_width + 1):
        cond = cond & (pl.col("high") > pl.col("high").shift(j))
        cond = cond & (pl.col("high") > pl.col("high").shift(-j))
    return cond.alias("_piv_high_raw")


def _pivot_low_raw_expr(cfg: LevelsConfig) -> pl.Expr:
    cond = pl.lit(True)
    for j in range(1, cfg.fractal_width + 1):
        cond = cond & (pl.col("low") < pl.col("low").shift(j))
        cond = cond & (pl.col("low") < pl.col("low").shift(-j))
    return cond.alias("_piv_low_raw")


def _confirmed_pivot_expr(cfg: LevelsConfig, *, side: str) -> pl.Expr:
    """Pivot price made visible only ``fractal_width`` bars after the pivot.

    Detection may look forward, but ``shift(width)`` aligns the value to the
    first bar at which the fractal was knowable — so the exposed column is
    causal even though the raw detector is not.
    """
    if side == "high":
        raw = pl.when(pl.col("_piv_high_raw")).then(pl.col("high")).otherwise(None)
        return raw.shift(cfg.fractal_width).alias("piv_high")
    raw = pl.when(pl.col("_piv_low_raw")).then(pl.col("low")).otherwise(None)
    return raw.shift(cfg.fractal_width).alias("piv_low")


def cluster_levels(values: list[float], tol: float, *, side: str) -> list[float]:
    """Greedy 1-D clustering of pivot prices.

    Values are sorted and merged while they stay within ``tol`` of the current
    cluster's anchor. Support clusters report their *low* edge (where a long
    stop sits) and resistance clusters their *high* edge.
    """
    if not values:
        return []
    ordered = sorted(float(v) for v in values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][0] <= tol:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    if side == "support":
        return [min(cluster) for cluster in clusters]
    if side == "resistance":
        return [max(cluster) for cluster in clusters]
    raise LevelsError(f"side must be 'support' or 'resistance'; got {side!r}")


def select_structure(
    pivot_lows: list[float],
    pivot_highs: list[float],
    ref: float,
    tol: float,
) -> tuple[float | None, float | None]:
    """Nearest support below *ref* and nearest resistance above *ref*."""
    supports = [level for level in cluster_levels(pivot_lows, tol, side="support") if level < ref]
    resistances = [
        level for level in cluster_levels(pivot_highs, tol, side="resistance") if level > ref
    ]
    support = max(supports) if supports else None
    resistance = min(resistances) if resistances else None
    return support, resistance


def snap_sourced(
    price: float, structures: list[tuple[float, str]], tol: float
) -> tuple[float, str] | None:
    """Snap *price* to the closest structural level within *tol*, keeping its provenance."""
    candidates = [item for item in structures if abs(item[0] - price) <= tol]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item[0] - price))


def _donchian_exprs(cfg: LevelsConfig) -> list[pl.Expr]:
    """Prior-bar Donchian extremes (``shift(1)`` keeps the channel causal)."""
    return [
        pl.col("high")
        .rolling_max(window_size=cfg.donchian_len, min_periods=cfg.donchian_len)
        .shift(1)
        .alias("don_high_prev"),
        pl.col("low")
        .rolling_min(window_size=cfg.donchian_len, min_periods=cfg.donchian_len)
        .shift(1)
        .alias("don_low_prev"),
    ]


def augment(df: pl.DataFrame, cfg: LevelsConfig) -> pl.DataFrame:
    """Attach every causal derivation column the engine consumes.

    Every returned column is causal: the value at row *i* equals the value
    computed from ``df[: i + 1]`` alone. The raw fractal detectors consume
    future bars (``shift(-j)``), so they exist only as intermediates here and
    are dropped before return; the exposed ``piv_high``/``piv_low`` columns are
    the ``shift(fractal_width)``-confirmed, knowable-only versions.
    """
    out = _normalize(df)
    if out.height < cfg.atr_len + 1:
        raise LevelsError(
            f"need at least {cfg.atr_len + 1} bars for ATR({cfg.atr_len}); got {out.height}"
        )
    out = out.with_columns(_atr_expr(cfg.atr_len))
    out = out.with_columns(_regime_expr(cfg))
    out = out.with_columns(_regime_factor_expr(cfg))
    out = out.with_columns(_k_eff_expr(cfg))
    out = out.with_columns([_pivot_high_raw_expr(cfg), _pivot_low_raw_expr(cfg)])
    out = out.with_columns(
        [
            _confirmed_pivot_expr(cfg, side="high"),
            _confirmed_pivot_expr(cfg, side="low"),
        ]
    )
    out = out.with_columns(_donchian_exprs(cfg))
    # Drop the non-causal raw detectors so the public frame is causal throughout.
    return out.drop(["_piv_high_raw", "_piv_low_raw"])


def _last_float(df: pl.DataFrame, column: str) -> float | None:
    value = df[column][-1]
    if value is None:
        return None
    return float(value)


def _asof(df: pl.DataFrame) -> str | None:
    if "timestamp" not in df.columns or df.height == 0:
        return None
    raw = df["timestamp"][-1]
    if raw is None:
        return None
    return str(raw)


def _format_meta(value: float) -> str:
    return f"{value:.10g}"


def _source_ref(
    cfg: LevelsConfig,
    *,
    asof: str | None,
    k_eff: float,
    regime: float,
    branch: str,
) -> str:
    atr_tag = f"atr{cfg.atr_len}"
    asof_tag = asof if asof else "na"
    return (
        f"computed:{atr_tag}@{asof_tag}|k={_format_meta(k_eff)}|reg={_format_meta(regime)}"
        f"|br={branch}|piv={cfg.fractal_width}|rr={_format_meta(cfg.rr_floor)}|src=base"
    )


def trail_policy_str(cfg: LevelsConfig) -> str:
    return (
        f"atr_trail:{_format_meta(cfg.trail_atr)}|activate_r={_format_meta(cfg.trail_activate_r)}"
    )


def trail_stop(
    *,
    direction: str,
    high_water: float,
    low_water: float,
    entry_ref: float,
    atr_value: float,
    cfg: LevelsConfig,
) -> float:
    """Causal ATR trailing stop for the current best price.

    Long: ``max(entry - trail_atr*ATR, high_water - trail_atr*ATR)`` — the stop
    only ratchets up. Short: the mirror, only ratcheting down.
    """
    offset = cfg.trail_atr * atr_value
    if direction == "long":
        return max(entry_ref - offset, high_water - offset)
    if direction == "short":
        return min(entry_ref + offset, low_water + offset)
    raise LevelsError(f"direction must be 'long' or 'short'; got {direction!r}")


def compute_levels(
    df: pl.DataFrame,
    direction: str,
    cfg: LevelsConfig | None = None,
    *,
    pair: str = "UNKNOWN",
    computed_at: str | None = None,
) -> LevelsResult:
    """Fold the causal derivations at the latest bar into a :class:`LevelsResult`.

    Raises :class:`LevelsError` when the frame is too short or ATR is not yet
    defined, so callers can surface a structured error instead of a partial
    level set.

    When no opposite structure exists the reward is undefined rather than zero:
    the engine accepts the stop uncapped (open-sky breakout) instead of failing
    an R:R check it cannot compute. The contract exposes that choice as the
    ``reward_uncapped`` diagnostic (``true`` = no opposite structure, accepted
    without an R:R check; ``false`` = a real R:R check ran).
    """
    cfg = cfg or LevelsConfig()
    if direction not in ("long", "short"):
        raise LevelsError(f"direction must be 'long' or 'short'; got {direction!r}")
    aug = augment(df, cfg)
    atr_value = _last_float(aug, f"atr_{cfg.atr_len}")
    regime = _last_float(aug, "regime_factor")
    k_eff = _last_float(aug, "k_eff")
    ref = _last_float(aug, "close")
    if atr_value is None or ref is None or k_eff is None:
        raise LevelsError("ATR/close not yet defined at the latest bar")
    if regime is None:
        regime = 1.0
    if atr_value <= 0:
        raise LevelsError(f"ATR must be positive; got {atr_value!r}")

    sign = 1.0 if direction == "long" else -1.0
    half = cfg.entry_half_atr * atr_value
    entry_low = ref - half
    entry_high = ref + half

    tol = cfg.cluster_atr * atr_value
    pivot_lows = aug["piv_low"].drop_nulls().to_list()
    pivot_highs = aug["piv_high"].drop_nulls().to_list()
    pivot_count = len(pivot_lows) + len(pivot_highs)

    support, resistance = select_structure(pivot_lows, pivot_highs, ref, tol)
    don_high = _last_float(aug, "don_high_prev")
    don_low = _last_float(aug, "don_low_prev")

    pivot_res = cluster_levels(pivot_highs, tol, side="resistance")
    pivot_sup = cluster_levels(pivot_lows, tol, side="support")
    targets_above = sorted(
        [level for level in pivot_res if level > ref]
        + ([don_high] if don_high is not None and don_high > ref else [])
    )
    targets_below = sorted(
        [level for level in pivot_sup if level < ref]
        + ([don_low] if don_low is not None and don_low < ref else []),
        reverse=True,
    )
    reward_long = targets_above[0] if targets_above else None
    reward_short = targets_below[0] if targets_below else None
    # True when there is no opposite structure, so the chosen stop was accepted
    # without a bounded reward (and therefore without an R:R check).
    reward = reward_long if direction == "long" else reward_short
    reward_uncapped = reward is None

    # Branch preference: pivot structure > Donchian channel > ATR. A structural
    # branch is taken when its stop sits on the correct side and either the
    # nearest opposite structure clears the R:R floor or there is no opposite
    # structure at all. In the latter case ``reward`` is ``None`` (undefined),
    # which means the upside/downside is uncapped and the stop is accepted
    # without an R:R check *by design* — an open-sky breakout has no structure
    # to measure reward against. ``reward_uncapped`` in the contract records
    # which branch of this rule applied.
    buffer = cfg.structural_buffer_atr * atr_value
    stop_value: float | None = None
    branch: str = "atr"
    if direction == "long":
        if support is not None and support < ref:
            candidate = support - buffer
            risk = ref - candidate
            if risk > 0 and (reward_long is None or reward_long / risk >= cfg.rr_floor):
                stop_value = candidate
                branch = "pivot"
        if stop_value is None and don_low is not None and don_low < ref:
            candidate = don_low - buffer
            risk = ref - candidate
            if risk > 0 and (reward_long is None or reward_long / risk >= cfg.rr_floor):
                stop_value = candidate
                branch = "donchian"
    else:
        if resistance is not None and resistance > ref:
            candidate = resistance + buffer
            risk = candidate - ref
            if risk > 0 and (reward_short is None or reward_short / risk >= cfg.rr_floor):
                stop_value = candidate
                branch = "pivot"
        if stop_value is None and don_high is not None and don_high > ref:
            candidate = don_high + buffer
            risk = candidate - ref
            if risk > 0 and (reward_short is None or reward_short / risk >= cfg.rr_floor):
                stop_value = candidate
                branch = "donchian"

    if stop_value is None:
        stop_value = ref - sign * k_eff * atr_value
        branch = "atr"

    sl = stop_value
    risk = abs(ref - sl)
    snap_tol = cfg.snap_tol_atr * atr_value
    snap_pool: list[tuple[float, str]] = []
    if direction == "long":
        snap_pool.extend((level, "pivot") for level in pivot_res)
        if don_high is not None and don_high > ref:
            snap_pool.append((don_high, "donchian"))
    else:
        snap_pool.extend((level, "pivot") for level in pivot_sup)
        if don_low is not None and don_low < ref:
            snap_pool.append((don_low, "donchian"))
    ladder: list[TpRung] = []
    for r in cfg.tp_rmultiples:
        base_price = ref + sign * float(r) * risk
        snapped = snap_sourced(base_price, snap_pool, snap_tol)
        if snapped is not None:
            ladder.append(TpRung(r=float(r), price=snapped[0], src=snapped[1]))
        else:
            ladder.append(TpRung(r=float(r), price=base_price, src="atr"))
    ladder_tuple = tuple(ladder)

    asof = _asof(aug)
    src_ref = _source_ref(cfg, asof=asof, k_eff=k_eff, regime=regime, branch=branch)
    return LevelsResult(
        pair=pair,
        direction=direction,
        entry_ref=ref,
        entry_low=entry_low,
        entry_high=entry_high,
        sl=sl,
        tp_ladder=ladder_tuple,
        trail_policy=trail_policy_str(cfg),
        source_ref=src_ref,
        computed_at=computed_at or "",
        atr=atr_value,
        k_eff=k_eff,
        regime=regime,
        branch=branch,
        pivot_count=pivot_count,
        asof=asof,
        extras={"reward_uncapped": reward_uncapped},
    )


__all__ = [
    "LevelsConfig",
    "LevelsError",
    "LevelsResult",
    "TpRung",
    "augment",
    "cluster_levels",
    "compute_levels",
    "select_structure",
    "snap_sourced",
    "trail_policy_str",
    "trail_stop",
]
