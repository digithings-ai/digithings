"""SDCA daily backtest loop — curve-driven buy/sell vs. a lump-sum buy-&-hold benchmark.

Mirrors the artifact's ``runCurveBacktest``. State (cash, holdings) is inherently
sequential, so the loop runs in plain Python; inputs and the emitted export frame
are Polars per the engine's Polars-only convention. Asset-agnostic: takes a
precomputed ``risk`` series (0-100, null on no-data days) and a ``price`` series —
no dependency on any specific indicator or ``RiskModel``.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, Field

from digiquant.strategies.sdca.curve import AccumDistCurve


class SdcaBacktestReport(BaseModel):
    """Summary stats for one SDCA backtest run vs. its lump-sum benchmark."""

    total_pnl: float = Field(..., description="Final portfolio value minus initial cash")
    total_return_pct: float = Field(..., description="total_pnl / initial_cash * 100")
    vs_lump_usd: float = Field(..., description="Final portfolio value minus lump-sum value")
    vs_lump_pct: float = Field(..., description="% difference vs. the lump-sum benchmark")
    dca_max_drawdown_pct: float = Field(..., description="Max peak-to-trough decline, e.g. -0.15")
    buy_hold_max_drawdown_pct: float = Field(..., description="Lump-sum benchmark's max drawdown")
    buy_days: int = Field(..., description="Days with rate > 0")
    sell_days: int = Field(..., description="Days with rate < 0")
    no_trade_days: int = Field(..., description="Days with null risk or rate == 0")
    avg_risk: float | None = Field(None, description="Mean risk over non-null days")
    avg_rate: float | None = Field(None, description="Mean curve rate (%) over non-null days")


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        worst = min(worst, (v - peak) / peak)
    return worst


def run_backtest(
    dates: pl.Series,
    price: pl.Series,
    risk: pl.Series,
    curve: AccumDistCurve,
    initial_cash: float,
) -> tuple[SdcaBacktestReport, pl.DataFrame]:
    """Run the daily SDCA backtest and return ``(report, per_day_export_frame)``."""
    prices = price.to_list()
    risks = risk.to_list()

    cash = initial_cash
    btc_units = 0.0
    btc_bought_at_start = initial_cash / prices[0]

    rates: list[float | None] = []
    daily_trade_usd: list[float] = []
    cash_col: list[float] = []
    btc_units_col: list[float] = []
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

            if rate > 0:
                buy_usd = min(max(cash * rate / 100.0, 0.0), cash)
                cash -= buy_usd
                btc_units += buy_usd / day_price
                daily_trade_usd.append(buy_usd)
                buy_days += 1
            elif rate < 0:
                sell_btc = min(max(btc_units * (-rate) / 100.0, 0.0), btc_units)
                cash += sell_btc * day_price
                btc_units -= sell_btc
                daily_trade_usd.append(-sell_btc * day_price)
                sell_days += 1
            else:
                daily_trade_usd.append(0.0)
                no_trade_days += 1

        cash_col.append(cash)
        btc_units_col.append(btc_units)
        net_deployed_col.append(initial_cash - cash)
        portfolio_value_col.append(cash + btc_units * day_price)
        buy_hold_value_col.append(btc_bought_at_start * day_price)

    frame = pl.DataFrame(
        {
            "date": dates,
            "price": price,
            "risk": risk,
            "rate": pl.Series(rates, dtype=pl.Float64),
            "daily_trade_usd": daily_trade_usd,
            "cash": cash_col,
            "btc_units": btc_units_col,
            "net_deployed": net_deployed_col,
            "portfolio_value": portfolio_value_col,
            "buy_hold_value": buy_hold_value_col,
        }
    )

    final_portfolio_value = portfolio_value_col[-1]
    final_buy_hold_value = buy_hold_value_col[-1]
    total_pnl = final_portfolio_value - initial_cash

    report = SdcaBacktestReport(
        total_pnl=total_pnl,
        total_return_pct=total_pnl / initial_cash * 100.0,
        vs_lump_usd=final_portfolio_value - final_buy_hold_value,
        vs_lump_pct=(final_portfolio_value / final_buy_hold_value - 1.0) * 100.0,
        dca_max_drawdown_pct=_max_drawdown_pct(portfolio_value_col),
        buy_hold_max_drawdown_pct=_max_drawdown_pct(buy_hold_value_col),
        buy_days=buy_days,
        sell_days=sell_days,
        no_trade_days=no_trade_days,
        avg_risk=risk_sum / non_null_days if non_null_days else None,
        avg_rate=rate_sum / non_null_days if non_null_days else None,
    )
    return report, frame


__all__ = ["SdcaBacktestReport", "run_backtest"]
