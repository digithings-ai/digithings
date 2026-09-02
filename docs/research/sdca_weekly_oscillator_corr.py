#!/usr/bin/env python3
"""Throwaway research: weekly RSI / MACD z vs BTC power-law power_law_z.

Not production code. Companion to ``docs/research/sdca-indicator-pool.md``.
Polars-only (matplotlib is used only to write a PNG).

Default inputs (override with flags):

* Coinbase daily cache: ``data/price-history/BTC-USD.csv``
* Power-law coefficients: ``btc_power_law_coefficients.json`` if present,
  else the checked-in synthetic example (loud warning).

Weekly resample is ISO-week (Monday-aligned truncate). Oscillators are
computed on the week's last daily close. Daily rows as-of join the latest
``week_end <= date`` so an in-progress week cannot see a future Friday/Sunday
close.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_CANDIDATES = (
    REPO_ROOT / "data" / "price-history" / "BTC-USD.csv",
    Path("/workspace/data/price-history/BTC-USD.csv"),
)
SDCA_DIR = REPO_ROOT / "digiquant" / "src" / "digiquant" / "strategies" / "sdca"
DEFAULT_COEFF_CANDIDATES = (
    Path("/tmp/sdca-research/btc_power_law_coefficients.json"),
    SDCA_DIR / "btc_power_law_coefficients.json",
    SDCA_DIR / "btc_power_law_coefficients.example.json",
)


def _add_src_to_path() -> None:
    src = REPO_ROOT / "digiquant" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _with_wilder_rsi(df: pl.DataFrame, close_col: str, out_col: str, length: int = 14) -> pl.DataFrame:
    """Wilder RSI on an ordered close column (weekly or daily)."""
    delta = pl.col(close_col).diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.ewm_mean(alpha=1.0 / length, adjust=False, min_samples=length)
    avg_loss = loss.ewm_mean(alpha=1.0 / length, adjust=False, min_samples=length)
    rs = avg_gain / avg_loss
    rsi = (
        pl.when(avg_loss == 0)
        .then(100.0)
        .when(avg_gain == 0)
        .then(0.0)
        .otherwise(100.0 - (100.0 / (1.0 + rs)))
    )
    return df.with_columns(rsi.alias(out_col))


def _rsi_to_z_expr(rsi_col: str) -> pl.Expr:
    """Map RSI in [0, 100] onto SDCA z: oversold = +3, overbought = -3."""
    return ((50.0 - pl.col(rsi_col)) / 50.0 * 3.0).clip(-3.0, 3.0)


def _causal_rolling_z_expr(col: str, window: int, min_samples: int) -> pl.Expr:
    """z vs a trailing window that includes today (no future bars)."""
    mean = pl.col(col).rolling_mean(window_size=window, min_samples=min_samples)
    std = pl.col(col).rolling_std(window_size=window, min_samples=min_samples)
    z = (pl.col(col) - mean) / std
    return pl.when(std.is_null() | (std == 0)).then(None).otherwise(z.clip(-3.0, 3.0))


def pearson(a: pl.Series, b: pl.Series) -> float | None:
    pair = pl.DataFrame({"a": a, "b": b}).drop_nulls()
    if pair.height < 30:
        return None
    val = pair.select(pl.corr("a", "b")).item()
    if val is None or (isinstance(val, float) and not math.isfinite(val)):
        return None
    return float(val)


def load_daily(path: Path) -> pl.DataFrame:
    df = pl.read_csv(path, try_parse_dates=True)
    lower = {c: c.lower() for c in df.columns if c != c.lower()}
    if lower:
        df = df.rename(lower)
    if "timestamp" in df.columns:
        df = df.rename({"timestamp": "date"})
    date_col = df["date"]
    if date_col.dtype == pl.Utf8:
        df = df.with_columns(pl.col("date").str.to_date())
    elif date_col.dtype != pl.Date:
        df = df.with_columns(pl.col("date").dt.date())
    return (
        df.select(pl.col("date").cast(pl.Date), pl.col("close").cast(pl.Float64))
        .drop_nulls()
        .unique(subset=["date"])
        .sort("date")
    )


def weekly_from_daily(daily: pl.DataFrame) -> pl.DataFrame:
    """One row per ISO week: last daily close, week_end = that day's date."""
    return (
        daily.with_columns(pl.col("date").dt.truncate("1w").alias("week"))
        .group_by("week")
        .agg(
            pl.col("close").last().alias("close"),
            pl.col("date").max().alias("week_end"),
        )
        .sort("week")
    )


def attach_weekly_oscillators(weekly: pl.DataFrame) -> pl.DataFrame:
    weekly = _with_wilder_rsi(weekly, "close", "weekly_rsi", 14)
    ema12 = pl.col("close").ewm_mean(span=12, adjust=False, min_samples=12)
    ema26 = pl.col("close").ewm_mean(span=26, adjust=False, min_samples=26)
    macd = ema12 - ema26
    hist = macd - macd.ewm_mean(span=9, adjust=False, min_samples=9)
    sma200 = pl.col("close").rolling_mean(window_size=200, min_samples=200)
    # Invert Mayer/MACD so cheap or oversold = +z, matching power_law_z.
    return weekly.with_columns(
        hist.alias("weekly_macd_hist"),
        (pl.col("close") / sma200).alias("mayer"),
        (-hist).alias("_macd_inv"),
        (1.0 - pl.col("close") / sma200).alias("_mayer_inv"),
    ).with_columns(
        _rsi_to_z_expr("weekly_rsi").alias("weekly_rsi_z"),
        _causal_rolling_z_expr("_macd_inv", window=104, min_samples=26).alias("weekly_macd_z"),
        _causal_rolling_z_expr("_mayer_inv", window=156, min_samples=52).alias("mayer_z"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--coefficients", type=Path, default=None)
    parser.add_argument(
        "--plot",
        type=Path,
        default=Path("/opt/cursor/artifacts/sdca-indicator-pool-weekly-corr.png"),
    )
    args = parser.parse_args()

    cache = args.cache or _first_existing(DEFAULT_CACHE_CANDIDATES)
    if cache is None:
        print("no BTC-USD.csv cache found; skip", file=sys.stderr)
        return 2
    coeff_path = args.coefficients or _first_existing(DEFAULT_COEFF_CANDIDATES)
    if coeff_path is None:
        print("no power-law coefficients found; skip", file=sys.stderr)
        return 2

    _add_src_to_path()
    from digiquant.strategies.sdca.btc_power_law import (
        BtcPowerLawRiskModel,
        load_coefficients,
    )
    from digiquant.strategies.sdca.power_law_zscore import power_law_z_score

    daily = load_daily(cache)
    weekly = attach_weekly_oscillators(weekly_from_daily(daily))

    coeffs = load_coefficients(coeff_path)
    model = BtcPowerLawRiskModel(coeffs)
    rails = model.rails(daily["date"])
    val_z = power_law_z_score(daily["close"], rails["low"], rails["median"], rails["high"])

    daily = daily.with_columns(val_z.alias("power_law_z"))
    daily = _with_wilder_rsi(daily, "close", "daily_rsi", 14)
    daily = daily.with_columns(_rsi_to_z_expr("daily_rsi").alias("daily_rsi_z"))

    joined = daily.join_asof(
        weekly.select(
            "week_end",
            "weekly_rsi",
            "weekly_rsi_z",
            "weekly_macd_hist",
            "weekly_macd_z",
            "mayer",
            "mayer_z",
        ).sort("week_end"),
        left_on="date",
        right_on="week_end",
        strategy="backward",
    )

    pairs = (
        ("power_law_z", "weekly_rsi_z"),
        ("power_law_z", "weekly_macd_z"),
        ("power_law_z", "mayer_z"),
        ("power_law_z", "daily_rsi_z"),
        ("weekly_rsi_z", "weekly_macd_z"),
        ("weekly_rsi_z", "daily_rsi_z"),
        ("weekly_macd_z", "mayer_z"),
        ("mayer_z", "daily_rsi_z"),
    )
    print(f"cache={cache}")
    print(f"coefficients={coeff_path}")
    print(f"notes={coeffs.notes[:160]}")
    print(f"daily_rows={daily.height} {daily['date'][0]} → {daily['date'][-1]}")
    print(f"weekly_rows={weekly.height}")
    print("pearson_r")
    rows: list[tuple[str, str, float | None, int]] = []
    for a, b in pairs:
        pair = joined.select(a, b).drop_nulls()
        r = pearson(pair[a], pair[b])
        n = pair.height
        rows.append((a, b, r, n))
        r_s = "na" if r is None else f"{r:+.3f}"
        print(f"  {a:16s} vs {b:16s}  r={r_s}  n={n}")

    plot_path = args.plot
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    _write_plot(joined, rows, plot_path, coeffs.notes)
    print(f"plot={plot_path}")
    return 0


def _write_plot(
    joined: pl.DataFrame,
    rows: list[tuple[str, str, float | None, int]],
    path: Path,
    notes: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_df = joined.select(
        "date",
        "power_law_z",
        "weekly_rsi_z",
        "weekly_macd_z",
        "mayer_z",
    ).drop_nulls()

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    ax = axes[0]
    ax.plot(plot_df["date"], plot_df["power_law_z"], label="power_law_z (power-law)", lw=1.2)
    ax.plot(plot_df["date"], plot_df["weekly_rsi_z"], label="weekly RSI z", lw=0.9, alpha=0.85)
    ax.plot(plot_df["date"], plot_df["weekly_macd_z"], label="weekly MACD-hist z", lw=0.9, alpha=0.85)
    ax.axhline(0, color="0.6", lw=0.6)
    ax.set_ylim(-3.2, 3.2)
    ax.set_ylabel("z (cheap = +)")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("BTC SDCA indicator pool — weekly oscillators vs power-law power_law_z")
    ax.grid(True, alpha=0.25)

    ax2 = axes[1]
    labels = [f"{a}\nvs {b}" for a, b, _, _ in rows]
    vals = [0.0 if r is None else r for _, _, r, _ in rows]
    colors = ["#6b8f71" if (v is not None and abs(v) < 0.6) else "#b07d62" for v in vals]
    ax2.bar(range(len(vals)), vals, color=colors)
    ax2.axhline(0, color="0.3", lw=0.6)
    ax2.axhline(0.6, color="0.5", ls="--", lw=0.7, label="|r|=0.6 collinear flag")
    ax2.axhline(-0.6, color="0.5", ls="--", lw=0.7)
    ax2.set_xticks(range(len(labels)), labels, fontsize=7)
    ax2.set_ylabel("Pearson r")
    ax2.set_ylim(-1.05, 1.05)
    ax2.legend(loc="lower right", fontsize=8)
    ax2.set_title("Pairwise correlation (overlapping non-null days)")
    ax2.grid(True, axis="y", alpha=0.25)

    fig.supxlabel(
        "Throwaway research — not a published backtest. "
        + ("Real fit. " if "Real Coinbase" in notes else "SYNTHETIC coefficients. "),
        fontsize=8,
    )
    fig.savefig(path, dpi=140)


if __name__ == "__main__":
    raise SystemExit(main())
