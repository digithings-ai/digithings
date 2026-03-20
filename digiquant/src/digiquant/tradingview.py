"""TradingView Pine Script v5 export. Import not implemented."""

from __future__ import annotations

import os
from pathlib import Path
from string import Template

from pydantic import BaseModel, Field


class PineExportResult(BaseModel):
    """Result of exporting strategy to Pine (TradingView)."""

    success: bool = Field(False, description="True if export succeeded")
    artifact_path: str | None = Field(None, description="Path to .pine or script")
    message: str = Field("", description="Status or error message")
    script: str | None = Field(None, description="Pine Script v5 source")


class PineImportResult(BaseModel):
    """Result of importing strategy from Pine."""

    success: bool = Field(False, description="True if import succeeded")
    strategy_name: str | None = Field(None, description="Parsed strategy name")
    message: str = Field("", description="Status or error message")


# --- Pine Script v5 templates ---

_PINE_TEMPLATES: dict[str, str] = {
    "ema_cross": """\
//@version=5
strategy("EMA Cross", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

fast_len = input.int($fast_period, title="Fast EMA Length", minval=1)
slow_len = input.int($slow_period, title="Slow EMA Length", minval=1)

fast_ema = ta.ema(close, fast_len)
slow_ema = ta.ema(close, slow_len)

long_cond  = ta.crossover(fast_ema, slow_ema)
short_cond = ta.crossunder(fast_ema, slow_ema)

if long_cond
    strategy.entry("Long", strategy.long)
if short_cond
    strategy.close("Long")

plot(fast_ema, color=color.new(color.blue, 0),  title="Fast EMA")
plot(slow_ema, color=color.new(color.orange, 0), title="Slow EMA")
""",
    "bollinger_mr": """\
//@version=5
strategy("Bollinger Mean Reversion", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

bb_period = input.int($bb_period, title="BB Period",    minval=2)
bb_std    = input.float($bb_std,   title="BB StdDev",   minval=0.1, step=0.1)
sl_pct    = input.float($sl_pct,   title="Stop Loss %", minval=0.0, step=0.1) / 100

basis = ta.sma(close, bb_period)
dev   = bb_std * ta.stdev(close, bb_period)
upper = basis + dev
lower = basis - dev

long_cond  = close < lower
short_cond = close > upper

if long_cond and strategy.position_size == 0
    strategy.entry("Long", strategy.long)
    strategy.exit("SL-Long", "Long", stop=close * (1 - sl_pct))
if short_cond and strategy.position_size == 0
    strategy.entry("Short", strategy.short)
    strategy.exit("SL-Short", "Short", stop=close * (1 + sl_pct))

if strategy.position_size > 0 and close >= basis
    strategy.close("Long")
if strategy.position_size < 0 and close <= basis
    strategy.close("Short")

plot(basis, color=color.gray,   title="Basis")
plot(upper, color=color.red,    title="Upper")
plot(lower, color=color.green,  title="Lower")
""",
    "rsi_momentum": """\
//@version=5
strategy("RSI Momentum", overlay=false, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

rsi_period = input.int($rsi_period,   title="RSI Period",    minval=2)
oversold   = input.float($oversold,   title="Oversold Level",  minval=0,  maxval=100, step=1)
overbought = input.float($overbought, title="Overbought Level", minval=0, maxval=100, step=1)

rsi_val = ta.rsi(close, rsi_period)

if ta.crossover(rsi_val, oversold)
    strategy.entry("Long", strategy.long)
if ta.crossunder(rsi_val, overbought)
    strategy.close("Long")

hline(oversold,   "Oversold",   color=color.green)
hline(overbought, "Overbought", color=color.red)
hline(50,         "Midline",    color=color.gray)
plot(rsi_val, title="RSI", color=color.purple)
""",
    "macd_trend": """\
//@version=5
strategy("MACD Trend", overlay=false, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

fast_len   = input.int($fast_period,   title="MACD Fast",   minval=1)
slow_len   = input.int($slow_period,   title="MACD Slow",   minval=1)
signal_len = input.int($signal_period, title="Signal Line", minval=1)

[macd_line, signal_line, hist] = ta.macd(close, fast_len, slow_len, signal_len)

long_cond  = ta.crossover(macd_line, signal_line)
short_cond = ta.crossunder(macd_line, signal_line)

if long_cond
    strategy.entry("Long", strategy.long)
if short_cond
    strategy.close("Long")

plot(macd_line,   color=color.blue,   title="MACD")
plot(signal_line, color=color.orange, title="Signal")
plot(hist,        color=hist >= 0 ? color.teal : color.red, style=plot.style_histogram, title="Histogram")
""",
}

# Default param values used when caller does not provide a value.
_PARAM_DEFAULTS: dict[str, dict[str, float | int]] = {
    "ema_cross":     {"fast_period": 9, "slow_period": 21},
    "bollinger_mr":  {"bb_period": 20, "bb_std": 2.0, "sl_pct": 1.0},
    "rsi_momentum":  {"rsi_period": 14, "oversold": 30.0, "overbought": 70.0},
    "macd_trend":    {"fast_period": 12, "slow_period": 26, "signal_period": 9},
}

# Strategy name aliases (mirrors strategy_specs.py).
_ALIAS_MAP: dict[str, str] = {
    "ema":           "ema_cross",
    "ema_crossover": "ema_cross",
    "bollinger":     "bollinger_mr",
    "bb_mr":         "bollinger_mr",
    "rsi":           "rsi_momentum",
    "macd":          "macd_trend",
}


def _resolve(name: str) -> str:
    return _ALIAS_MAP.get(name.lower(), name.lower())


def export_to_pine(
    strategy_name: str,
    params: dict[str, float | int | str] | None = None,
    output_path: str | Path | None = None,
) -> PineExportResult:
    """Generate a Pine Script v5 stub for the given strategy.

    Parameters
    ----------
    strategy_name:
        Strategy name or alias (e.g. ``"ema_cross"``, ``"ema"``).
    params:
        Parameter overrides. Missing params fall back to :data:`_PARAM_DEFAULTS`.
    output_path:
        If provided, write the script to this path and set ``artifact_path``.
    """
    canonical = _resolve(strategy_name)
    tmpl_str = _PINE_TEMPLATES.get(canonical)
    if tmpl_str is None:
        supported = ", ".join(sorted(_PINE_TEMPLATES))
        return PineExportResult(
            success=False,
            message=f"No Pine template for strategy {strategy_name!r}. Supported: {supported}.",
        )

    # Merge defaults with caller-supplied params.
    merged: dict[str, object] = dict(_PARAM_DEFAULTS.get(canonical, {}))
    if params:
        merged.update(params)

    try:
        script = Template(tmpl_str).substitute(merged)
    except KeyError as exc:
        return PineExportResult(
            success=False,
            message=f"Missing template variable: {exc}",
        )

    artifact: str | None = None
    if output_path is not None:
        p = Path(output_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(script, encoding="utf-8")
            artifact = str(p)
        except OSError as exc:
            return PineExportResult(
                success=False,
                script=script,
                message=f"Script generated but could not write to {output_path}: {exc}",
            )

    return PineExportResult(
        success=True,
        script=script,
        artifact_path=artifact,
        message="Pine Script v5 export succeeded." if artifact else "Pine Script v5 generated (no output_path provided).",
    )


def import_from_pine(pine_path: str) -> PineImportResult:
    """PyneCore Pine import not implemented."""
    return PineImportResult(
        success=False,
        strategy_name=None,
        message="Pine/TradingView import not implemented.",
    )
