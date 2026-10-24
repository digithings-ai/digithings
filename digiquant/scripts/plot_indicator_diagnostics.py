#!/usr/bin/env python3
"""Per-indicator diagnostic charts: raw (native-scale) value vs. production z-score.

Context: before doing any curve optimization or walk-forward OOS validation on
the Stage 3 floor-diversified weight mix (power_law=1.0, sma_band=1.0,
onchain_rhodl=0.55, rest at the 0.1 floor -- see run_full_indicator_diversification_search.py),
Chris asked to see all 17 indicators (power_law + the 16 EXTRA_INDICATOR_NAMES)
plotted one-chart-per-indicator, raw value and z-scored value overlaid on dual
axes, so he can visually validate that each is being computed/processed
correctly.

"Raw" is reconstructed per indicator family:
  - power_law: BTC close price (log y-axis) against the power-law confluence z.
  - source-driven extras (m2, dxy, rs_eth, onchain_*, fear_greed): the native
    source series from load_sdca_extra_sources, on its own native dates.
  - RSI-derived (weekly/monthly/weekly_monthly _rsi): the underlying completed
    weekly/monthly Wilder RSI (0-100), reusing completed_weekly_closes /
    completed_monthly_closes + the private _wilder_rsi exactly as the
    production z functions do.
  - MACD-derived (weekly/monthly/weekly_monthly _macd): the underlying
    completed weekly/monthly log-MACD (log10(EMA_fast) - log10(EMA_slow)),
    same EMA spans as weekly_macd_z/monthly_macd_z.
  - sma_band: BTC close plotted against its rolling SMA (the band itself) is
    the natural "raw" view here -- the production quantity is already
    sign-flipped (close-mu)/sigma, i.e. already z-like.

Diagnostic only -- no settings.json/RESEARCH_STATE.md writes. Produces a
single self-contained HTML file with one dual-axis chart per indicator.

Usage:
    uv run python -m scripts.plot_indicator_diagnostics
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.indicator_catalog import EXTRA_INDICATOR_NAMES
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import (
    _wilder_rsi,
    completed_monthly_closes,
    completed_weekly_closes,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"
OUTPUT_PATH = DIGIQUANT_ROOT / "reports" / "indicator_diagnostics.html"

_MACD_FAST = 12
_MACD_SLOW = 26
_SMA_WINDOW = 200
_SIGMA_FLOOR = 1e-12

# Source-driven extras: which load_sdca_extra_sources() field + label to plot raw.
_SOURCE_FIELD_BY_NAME = {
    "m2": ("m2_dates", "m2_values", "M2SL (FRED, native units)"),
    "dxy": ("dxy_dates", "dxy_values", "DTWEXBGS (FRED, native units)"),
    "rs_eth": ("eth_dates", "eth_close", "ETH-USD close ($)"),
    "onchain_mvrv": ("onchain_mvrv_dates", "onchain_mvrv_values", "MVRV ratio"),
    "onchain_asopr": ("onchain_asopr_dates", "onchain_asopr_values", "aSOPR"),
    "onchain_puell": ("onchain_puell_dates", "onchain_puell_values", "Puell Multiple"),
    "onchain_rhodl": ("onchain_rhodl_dates", "onchain_rhodl_values", "RHODL ratio"),
    "onchain_addr_ratio": ("onchain_addr_ratio_dates", "onchain_addr_ratio_values", "active-address ratio"),
    "fear_greed": ("fear_greed_dates", "fear_greed_values", "Fear & Greed index (0-100)"),
}

_RSI_NAMES = {"weekly_rsi": "weekly", "monthly_rsi": "monthly", "weekly_monthly_rsi": "weekly"}
_MACD_NAMES = {"weekly_macd": "weekly", "monthly_macd": "monthly", "weekly_monthly_macd": "weekly"}


def _lmacd(close: pl.Series) -> pl.Series:
    frame = pl.DataFrame({"close": close})
    ema_fast = pl.col("close").ewm_mean(span=_MACD_FAST, adjust=False, min_samples=_MACD_FAST)
    ema_slow = pl.col("close").ewm_mean(span=_MACD_SLOW, adjust=False, min_samples=_MACD_SLOW)
    with_ema = frame.select(
        ema_fast.clip(lower_bound=_SIGMA_FLOOR).alias("ema_fast"),
        ema_slow.clip(lower_bound=_SIGMA_FLOOR).alias("ema_slow"),
    )
    return with_ema["ema_fast"].log(10) - with_ema["ema_slow"].log(10)


def _raw_rsi_series(dates: pl.Series, close: pl.Series, timeframe: str) -> tuple[list, list[float | None]]:
    period = completed_weekly_closes(dates, close) if timeframe == "weekly" else completed_monthly_closes(dates, close)
    end_col = "week_end" if timeframe == "weekly" else "month_end"
    rsi = _wilder_rsi(period["close"])
    return period[end_col].to_list(), rsi.to_list()


def _raw_macd_series(dates: pl.Series, close: pl.Series, timeframe: str) -> tuple[list, list[float | None]]:
    period = completed_weekly_closes(dates, close) if timeframe == "weekly" else completed_monthly_closes(dates, close)
    end_col = "week_end" if timeframe == "weekly" else "month_end"
    lmacd = _lmacd(period["close"])
    return period[end_col].to_list(), lmacd.to_list()


def _add_chart(fig_rows: list, name: str, raw_x: list, raw_y: list, raw_label: str, z_x: list, z_y: list) -> None:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=raw_x, y=raw_y, name=raw_label, line=dict(color="#1f77b4"), connectgaps=False),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=z_x, y=z_y, name=f"{name} (z-score)", line=dict(color="#d62728", width=1)),
        secondary_y=True,
    )
    fig.update_yaxes(title_text=raw_label, secondary_y=False)
    fig.update_yaxes(title_text="z-score", range=[-3.2, 3.2], secondary_y=True)
    fig.update_layout(
        title=f"{name}: raw vs. z-scored",
        height=420,
        margin=dict(t=60, b=30, l=60, r=60),
        legend=dict(orientation="h", y=1.08),
    )
    fig_rows.append(fig)


def run(cache_dir: Path = DEFAULT_CACHE_DIR, output_path: Path = OUTPUT_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    dates_s = pl.Series("date", dates)
    close_s = pl.Series("close", prices)

    extra_z = load_sdca_extra_z(dates_s, close_s, data_path=None, data_dir=str(cache_dir))
    sources = load_sdca_extra_sources(cache_dir)

    figs: list = []

    # power_law
    rails = BtcPowerLawRiskModel(load_coefficients()).rails(dates_s)
    pl_z = power_law_confluence_z(dates_s, close_s, rails["low"], rails["median"], rails["high"])
    _add_chart(figs, "power_law", dates, prices, "BTC-USD close ($, log)", dates, pl_z.to_list())

    for name in EXTRA_INDICATOR_NAMES:
        if name not in extra_z:
            print(f"  skip {name}: not present in load_sdca_extra_z output")
            continue
        z_series = extra_z[name]
        z_vals = z_series.to_list() if hasattr(z_series, "to_list") else list(z_series)

        if name in _SOURCE_FIELD_BY_NAME:
            dates_field, values_field, label = _SOURCE_FIELD_BY_NAME[name]
            raw_dates_s = getattr(sources, dates_field, None)
            raw_vals_s = getattr(sources, values_field, None)
            if raw_dates_s is None or raw_vals_s is None:
                print(f"  skip raw for {name}: source series unavailable")
                _add_chart(figs, name, dates, [None] * len(dates), "(source unavailable)", dates, z_vals)
                continue
            _add_chart(figs, name, raw_dates_s.to_list(), raw_vals_s.to_list(), label, dates, z_vals)
        elif name in _RSI_NAMES:
            raw_dates, raw_vals = _raw_rsi_series(dates_s, close_s, _RSI_NAMES[name])
            _add_chart(figs, name, raw_dates, raw_vals, f"{_RSI_NAMES[name]} Wilder RSI (0-100)", dates, z_vals)
        elif name in _MACD_NAMES:
            raw_dates, raw_vals = _raw_macd_series(dates_s, close_s, _MACD_NAMES[name])
            _add_chart(figs, name, raw_dates, raw_vals, f"{_MACD_NAMES[name]} log-MACD (log10 EMA12 - log10 EMA26)", dates, z_vals)
        elif name == "sma_band":
            sma = close_s.to_frame().select(pl.col("close").rolling_mean(window_size=_SMA_WINDOW, min_samples=_SMA_WINDOW))["close"]
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=dates, y=prices, name="BTC-USD close", line=dict(color="#1f77b4")), secondary_y=False)
            fig.add_trace(go.Scatter(x=dates, y=sma.to_list(), name=f"{_SMA_WINDOW}d SMA", line=dict(color="#2ca02c")), secondary_y=False)
            fig.add_trace(go.Scatter(x=dates, y=z_vals, name="sma_band (z-score)", line=dict(color="#d62728", width=1)), secondary_y=True)
            fig.update_yaxes(title_text="BTC-USD close ($, log)", type="log", secondary_y=False)
            fig.update_yaxes(title_text="z-score", range=[-3.2, 3.2], secondary_y=True)
            fig.update_layout(title="sma_band: price vs. rolling SMA vs. z-scored", height=420, margin=dict(t=60, b=30, l=60, r=60), legend=dict(orientation="h", y=1.08))
            figs.append(fig)
        else:
            print(f"  no raw-value mapping defined for {name}, skipping")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write("<html><head><title>SDCA indicator diagnostics: raw vs. z-scored</title></head><body>\n")
        f.write(f"<h1>SDCA indicator diagnostics ({len(figs)} charts)</h1>\n")
        f.write("<p>Diagnostic only -- one chart per indicator, raw (native-scale) value overlaid with the production z-score. Not touching settings.json/RESEARCH_STATE.md.</p>\n")
        for i, fig in enumerate(figs):
            f.write(fig.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False))
        f.write("</body></html>\n")

    print(f"wrote {len(figs)} charts to {output_path}")


if __name__ == "__main__":
    run()
