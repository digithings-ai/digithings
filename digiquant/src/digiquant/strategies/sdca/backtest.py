"""SDCA daily backtest loop — curve-driven buy/sell vs. a lump-sum buy-&-hold benchmark.

Mirrors the artifact's ``runCurveBacktest``. State (cash, holdings) is inherently
sequential, so the loop runs in plain Python; inputs and the emitted export frame
are Polars per the engine's Polars-only convention. Asset-agnostic: takes a
precomputed ``risk`` series (0-100, null on no-data days) and a ``price`` series —
no dependency on any specific indicator or ``RiskModel``.
"""

from __future__ import annotations

import math

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.dca_metrics import flat_dca_mark_to_market


class SdcaBacktestReport(BaseModel):
    """Summary stats for one SDCA backtest run vs. its lump-sum benchmark.

    This report is a CI-only parity harness for the allocation math in this
    module (curve/composite-risk/valuation) — it is never the authoritative
    backtest result. NautilusTrader remains the sole backtest/live engine
    (digiquant/AGENTS.md); the Nautilus strategy wrapper (#1081) calls
    ``size_trade()`` below rather than reimplementing it, so there is exactly
    one source of truth for the allocation decision math, and PnL/Sharpe/
    drawdown surfaced to users always comes from a completed Nautilus
    ``BacktestResult``/``OptimizeResult``, never from this report.
    """

    model_config = ConfigDict(strict=True)

    total_pnl: float = Field(..., description="Final portfolio value minus initial cash")
    total_return_pct: float = Field(..., description="total_pnl / initial_cash * 100")
    vs_lump_usd: float = Field(..., description="Final portfolio value minus lump-sum value")
    vs_lump_pct: float = Field(
        ...,
        description="% difference vs. the lump-sum benchmark (×100; -15.0 means −15%)",
    )
    vs_flat_dca_usd: float = Field(
        ...,
        description="Final portfolio value minus the equal-daily-spend benchmark",
    )
    vs_flat_dca_pct: float = Field(
        ...,
        description="% difference vs. flat DCA (×100; same convention as vs_lump_pct)",
    )
    dca_max_drawdown_pct: float = Field(..., description="Max peak-to-trough decline, e.g. -0.15")
    buy_hold_max_drawdown_pct: float = Field(..., description="Lump-sum benchmark's max drawdown")
    buy_days: int = Field(..., description="Days with rate > 0")
    sell_days: int = Field(..., description="Days with rate < 0")
    no_trade_days: int = Field(..., description="Days with null risk or rate == 0")
    avg_risk: float | None = Field(None, description="Mean risk over non-null days")
    avg_rate: float | None = Field(None, description="Mean curve rate (%) over non-null days")
    avg_cost_basis: float | None = Field(
        None, description="Total spent on buys / units acquired (quote per unit)"
    )
    final_cost_basis_vs_price: float | None = Field(
        None,
        description="avg_cost_basis / final price × 100 (percent of last close)",
    )
    capital_deployed_pct: float = Field(..., description="Final net deployed / initial cash × 100")
    capital_deployed_peak_pct: float = Field(
        ..., description="Peak net deployed / initial cash × 100"
    )
    units_accumulated: float = Field(..., description="Ending asset units")


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        worst = min(worst, (v - peak) / peak)
    return worst


def size_trade(rate: float, cash: float, asset_units: float) -> tuple[float, float]:
    """Size a buy (USD) or sell (asset units) from the curve rate, cash, and holdings.

    Returns ``(buy_usd, sell_units)`` — exactly one is non-zero (both zero at
    ``rate == 0``). This is the single source of truth for the allocation
    sizing math: both ``run_backtest()`` below and
    ``nautilus_strategy.py::SdcaStrategy.on_bar()`` call this instead of
    reimplementing the clamping.
    """
    if rate > 0:
        return min(max(cash * rate / 100.0, 0.0), cash), 0.0
    if rate < 0:
        return 0.0, min(max(asset_units * (-rate) / 100.0, 0.0), asset_units)
    return 0.0, 0.0


def run_backtest(
    dates: pl.Series,
    price: pl.Series,
    risk: pl.Series,
    curve: AccumDistCurve,
    initial_cash: float,
) -> tuple[SdcaBacktestReport, pl.DataFrame]:
    """Run the daily SDCA backtest and return ``(report, per_day_export_frame)``."""
    if dates.len() == 0:
        raise ValueError("run_backtest requires at least one row")
    if not (price.len() == dates.len() and risk.len() == dates.len()):
        raise ValueError(
            f"run_backtest requires dates, price, and risk to have the same length, "
            f"got {dates.len()}, {price.len()}, {risk.len()}"
        )
    if dates.is_null().any():
        raise ValueError("run_backtest requires dates to have no null values")
    date_list = dates.to_list()
    if any(date_list[i] >= date_list[i + 1] for i in range(len(date_list) - 1)):
        raise ValueError("run_backtest requires dates to be strictly increasing")
    if price.is_null().any():
        raise ValueError("run_backtest requires price to have no null values")
    if not price.is_finite().all():
        raise ValueError("run_backtest requires price to be finite")
    if not (price > 0).all():
        raise ValueError("run_backtest requires price to be positive")
    if not math.isfinite(initial_cash):
        raise ValueError(f"run_backtest requires a finite initial_cash, got {initial_cash}")
    if initial_cash <= 0:
        raise ValueError(f"run_backtest requires a positive initial_cash, got {initial_cash}")

    prices = price.to_list()
    risks = risk.to_list()

    cash = initial_cash
    asset_units = 0.0
    asset_units_bought_at_start = initial_cash / prices[0]

    rates: list[float | None] = []
    daily_trade_usd: list[float] = []
    cash_col: list[float] = []
    asset_units_col: list[float] = []
    net_deployed_col: list[float] = []
    portfolio_value_col: list[float] = []
    buy_hold_value_col: list[float] = []

    buy_days = sell_days = no_trade_days = 0
    risk_sum = rate_sum = 0.0
    non_null_days = 0

    for day_risk, day_price in zip(risks, prices, strict=True):
        if day_risk is None:
            rates.append(None)
            daily_trade_usd.append(0.0)
            no_trade_days += 1
        else:
            rate = curve.value_at_risk(day_risk)
            rates.append(rate)
            risk_sum += day_risk
            rate_sum += rate
            non_null_days += 1

            buy_usd, sell_units = size_trade(rate, cash, asset_units)
            if rate > 0:
                cash -= buy_usd
                asset_units += buy_usd / day_price
                daily_trade_usd.append(buy_usd)
                buy_days += 1
            elif rate < 0:
                cash += sell_units * day_price
                asset_units -= sell_units
                daily_trade_usd.append(-sell_units * day_price)
                sell_days += 1
            else:
                daily_trade_usd.append(0.0)
                no_trade_days += 1

        cash_col.append(cash)
        asset_units_col.append(asset_units)
        net_deployed_col.append(initial_cash - cash)
        portfolio_value_col.append(cash + asset_units * day_price)
        buy_hold_value_col.append(asset_units_bought_at_start * day_price)

    flat_dca_value_col = flat_dca_mark_to_market(prices, initial_cash)

    frame = pl.DataFrame(
        {
            "date": dates,
            "price": price,
            "risk": risk,
            "rate": pl.Series(rates, dtype=pl.Float64),
            "daily_trade_usd": daily_trade_usd,
            "cash": cash_col,
            "asset_units": asset_units_col,
            "net_deployed": net_deployed_col,
            "portfolio_value": portfolio_value_col,
            "buy_hold_value": buy_hold_value_col,
            "flat_dca_value": flat_dca_value_col,
        }
    )

    final_portfolio_value = portfolio_value_col[-1]
    final_buy_hold_value = buy_hold_value_col[-1]
    final_flat_dca_value = flat_dca_value_col[-1]
    total_pnl = final_portfolio_value - initial_cash

    gross_spent = sum(u for u in daily_trade_usd if u > 0)
    units_bought = 0.0
    for trade_usd, day_price in zip(daily_trade_usd, prices, strict=True):
        if trade_usd > 0:
            units_bought += trade_usd / day_price
    avg_cost = (gross_spent / units_bought) if units_bought > 0 else None
    cost_vs_price = (avg_cost / prices[-1] * 100.0) if avg_cost is not None else None

    report = SdcaBacktestReport(
        total_pnl=total_pnl,
        total_return_pct=total_pnl / initial_cash * 100.0,
        vs_lump_usd=final_portfolio_value - final_buy_hold_value,
        vs_lump_pct=(final_portfolio_value / final_buy_hold_value - 1.0) * 100.0,
        vs_flat_dca_usd=final_portfolio_value - final_flat_dca_value,
        vs_flat_dca_pct=(final_portfolio_value / final_flat_dca_value - 1.0) * 100.0,
        dca_max_drawdown_pct=_max_drawdown_pct(portfolio_value_col),
        buy_hold_max_drawdown_pct=_max_drawdown_pct(buy_hold_value_col),
        buy_days=buy_days,
        sell_days=sell_days,
        no_trade_days=no_trade_days,
        avg_risk=risk_sum / non_null_days if non_null_days else None,
        avg_rate=rate_sum / non_null_days if non_null_days else None,
        avg_cost_basis=avg_cost,
        final_cost_basis_vs_price=cost_vs_price,
        capital_deployed_pct=net_deployed_col[-1] / initial_cash * 100.0,
        capital_deployed_peak_pct=max(net_deployed_col) / initial_cash * 100.0,
        units_accumulated=asset_units_col[-1],
    )
    return report, frame


__all__ = ["SdcaBacktestReport", "run_backtest", "size_trade"]
