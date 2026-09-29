"""Replica of the Railway production signals-app composite (UI-spec reimplementation).

Production source is unavailable, so every formula below is a documented proxy
for the UI-described vote, tagged ``ASSUMPTION[Sn]``. These tags are load-bearing:
do not treat replica numbers as production numbers. See
``docs/superpowers/plans/2026-09-29-signals-replica-challenger.md``.

Convention throughout (matches ``composite_risk``): z in ``[-3, 3]``,
cheap/buy-favorable = +z, rich/sell-favorable = -z, risk = 50 - z*50/3.
All series are causal: output day ``i`` uses only inputs up to day ``i``.
"""

from __future__ import annotations

import math

import polars as pl

from digiquant.strategies.sdca.composite_risk import (
    IndicatorWeight,
    causal_ema_smooth,
    causal_rolling_z,
    compute_composite_risk,
)
from digiquant.strategies.sdca.indicator_catalog import (
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)

REPLICA_VOTE_NAMES = ("tail_curvature", "sharpe", "cost_basis", "onchain")
ONCHAIN_LEGS = ("mvrv", "asopr", "puell", "rhodl")
_ANNUALIZATION_SQRT_DAYS = math.sqrt(365.0)


def _log_returns(prices: pl.Series) -> list[float | None]:
    """Daily log returns; first row is null (no prior close)."""
    closes = prices.to_list()
    out: list[float | None] = [None]
    for prev, cur in zip(closes, closes[1:]):
        if prev is None or cur is None or prev <= 0 or cur <= 0:
            out.append(None)
        else:
            out.append(math.log(cur / prev))
    return out


def tail_curvature_z(
    prices: pl.Series,
    *,
    tail_window: int = 252,
    z_window: int = 90,
    min_samples: int = 20,
) -> pl.Series:
    """ASSUMPTION[S1]: production's tail-curvature formula is unknown.

    Proxy: trailing-window tail asymmetry of log returns = mean upside tail
    minus mean downside-tail magnitude. Fat upside tails (euphoric chase) read
    rich (-z); fat downside tails (panic) read cheap (+z). Null until a full
    ``tail_window`` of returns is available.
    """
    rets = _log_returns(prices)
    n = len(rets)
    asym: list[float | None] = []
    for i in range(n):
        window = [r for r in rets[max(0, i - tail_window + 1) : i + 1] if r is not None]
        if len(window) < tail_window:
            asym.append(None)
            continue
        up = [r for r in window if r > 0]
        down = [-r for r in window if r < 0]
        if not up or not down:
            asym.append(0.0)
        else:
            asym.append(sum(up) / len(up) - sum(down) / len(down))
    raw = pl.Series("asym", asym)
    return (-causal_rolling_z(raw, window=z_window, min_samples=min_samples)).alias(
        "tail_curvature"
    )


def sharpe_z(
    prices: pl.Series,
    *,
    window: int = 90,
    min_samples: int = 20,
    ema_half_life: float = 14.0,
) -> pl.Series:
    """ASSUMPTION[S2]: production's realized-P/L denominator is unknown.

    Proxy: annualized Sharpe of daily log returns over ``window`` days,
    sign-flipped (strong risk-adjusted gains = rich = -z), then causal EMA
    smooth with the UI-stated 14d half-life. Sign convention is an assumption.
    """
    rets = pl.Series("ret", _log_returns(prices))
    mu = rets.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = rets.rolling_std(window_size=window, min_samples=min_samples).clip(lower_bound=1e-12)
    sharpe = (mu / sigma * _ANNUALIZATION_SQRT_DAYS).alias("sharpe_raw")
    z = -causal_rolling_z(sharpe, window=window, min_samples=min_samples)
    return causal_ema_smooth(z, half_life=ema_half_life).alias("sharpe")


def cost_basis_ratio_z(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    window: int = 90,
    min_samples: int = 20,
    ema_half_life: float = 7.0,
) -> pl.Series:
    """ASSUMPTION[S3]: network (MVRV-style) cost-basis reading, not the book's.

    Reuses ``onchain_mvrv_z`` (log, sign-flipped rolling-z: elevated MVRV =
    rich) then applies the UI-stated 7d EMA. The book-dependent reading (DCA
    book's own avg cost vs price) is rejected: a curve-dependent index cannot
    serve as a fixed baseline.
    """
    z = onchain_mvrv_z(dates, src_dates, src_values, window=window, min_samples=min_samples)
    return causal_ema_smooth(z, half_life=ema_half_life).alias("cost_basis")


def onchain_composite_z(
    dates: pl.Series,
    feeds: dict[str, tuple[pl.Series, pl.Series]],
    *,
    window: int = 90,
    min_samples: int = 20,
    ema_half_life: float = 7.0,
) -> pl.Series:
    """ASSUMPTION[S4]: production's onchain constituents are unknown.

    Proxy: equal-weight blend of the four existing catalog onchain z legs
    (MVRV, aSOPR, Puell, RHODL — all sign-flipped overheated = -z), then the
    UI-stated 7d EMA smooth.
    """
    builders = {
        "mvrv": onchain_mvrv_z,
        "asopr": onchain_asopr_z,
        "puell": onchain_puell_z,
        "rhodl": onchain_rhodl_z,
    }
    legs = []
    for leg in ONCHAIN_LEGS:
        src_dates, src_values = feeds[leg]
        legs.append(
            IndicatorWeight(
                name=leg,
                z=builders[leg](
                    dates, src_dates, src_values, window=window, min_samples=min_samples
                ),
                weight=1.0,
            )
        )
    blended = compute_composite_risk(legs)["composite_z"]
    return causal_ema_smooth(blended, half_life=ema_half_life).alias("onchain")


def build_replica_composite(votes: dict[str, pl.Series]) -> pl.DataFrame:
    """Equal-weight blend of the four replica votes -> composite_z + risk.

    Requires exactly the four ``REPLICA_VOTE_NAMES``; anything else raises.
    Null-rule inherited from ``compute_composite_risk`` (any null vote nulls
    the row — matches the UI's equal-votes semantics).
    """
    missing = [name for name in REPLICA_VOTE_NAMES if name not in votes]
    if missing:
        raise ValueError(f"build_replica_composite missing replica votes: {missing}")
    return compute_composite_risk(
        [IndicatorWeight(name=name, z=votes[name], weight=1.0) for name in REPLICA_VOTE_NAMES]
    )


__all__ = [
    "ONCHAIN_LEGS",
    "REPLICA_VOTE_NAMES",
    "build_replica_composite",
    "cost_basis_ratio_z",
    "onchain_composite_z",
    "sharpe_z",
    "tail_curvature_z",
]
