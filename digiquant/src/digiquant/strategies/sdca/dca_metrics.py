"""DCA tearsheet metrics — Nautilus fills / daily state, never ``SdcaBacktestReport``.

``SdcaBacktestReport`` is a CI-only parity harness. Published numbers for a
``kind == "dca"`` book come from this module, fed by Nautilus fills and the
mark-to-market equity path (#3171). Tests assert the two agree within
tolerance; they must not substitute one for the other at publish time.

``_pct`` conventions (pin these; a 100× error must fail the tests):

- ``vs_lump_pct`` / ``vs_flat_dca_pct`` — true percents (×100), same as
  ``SdcaBacktestReport.vs_lump_pct`` / ``total_return_pct``.
- ``final_cost_basis_vs_price`` — cost basis as a percent of the final
  close (×100): ``50.0`` means the average buy is 50% of the last price.
- ``capital_deployed_pct`` / ``capital_deployed_peak_pct`` — share of
  initial cash put to work (×100).
- ``max_drawdown_pct`` on ``TearsheetData`` is **not** this module; it
  stays a percent on the tearsheet path (already ×100 from
  ``generate_tearsheets``) and a raw fraction on ``SdcaBacktestReport``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from digiquant.tearsheet_data import TearsheetDcaBreakdown


class SdcaFill(BaseModel):
    """One buy or sell fill used to reconstruct the DCA book."""

    model_config = ConfigDict(frozen=True, strict=True)

    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    side: Literal["buy", "sell"]
    qty: float = Field(..., gt=0)
    price: float = Field(..., gt=0)


def flat_dca_mark_to_market(prices: Sequence[float], initial_cash: float) -> list[float]:
    """Equal remaining-cash spend each day; fully deploys by the last bar.

    Day ``i`` spends ``cash / (n - i)`` at that day's price. With exact
    arithmetic that is ``initial_cash / n`` every day. Returns the
    mark-to-market value (cash + units × price) after each day.
    """
    n = len(prices)
    if n == 0:
        raise ValueError("flat_dca_mark_to_market requires at least one price")
    if initial_cash <= 0:
        raise ValueError("flat_dca_mark_to_market requires positive initial_cash")
    cash = float(initial_cash)
    units = 0.0
    out: list[float] = []
    for i, price in enumerate(prices):
        spend = cash / float(n - i)
        cash -= spend
        units += spend / float(price)
        out.append(cash + units * float(price))
    return out


def lump_mark_to_market(prices: Sequence[float], initial_cash: float) -> list[float]:
    """All capital deployed at day-0 price, marked to each later close."""
    if not prices:
        raise ValueError("lump_mark_to_market requires at least one price")
    units = float(initial_cash) / float(prices[0])
    return [units * float(p) for p in prices]


def breakdown_from_daily(
    *,
    prices: Sequence[float],
    portfolio_values: Sequence[float],
    daily_trade_usd: Sequence[float],
    net_deployed: Sequence[float],
    asset_units: Sequence[float],
    risk: Sequence[float | None],
    rate: Sequence[float | None],
    initial_cash: float,
) -> TearsheetDcaBreakdown:
    """Build the schema 1.3 DCA block from aligned daily series."""
    n = len(prices)
    if not (
        len(portfolio_values)
        == len(daily_trade_usd)
        == len(net_deployed)
        == len(asset_units)
        == len(risk)
        == len(rate)
        == n
    ):
        raise ValueError("breakdown_from_daily requires equal-length daily series")
    if n == 0:
        raise ValueError("breakdown_from_daily requires at least one day")

    flat = flat_dca_mark_to_market(prices, initial_cash)
    lump = lump_mark_to_market(prices, initial_cash)
    final_pv = float(portfolio_values[-1])
    final_flat = flat[-1]
    final_lump = lump[-1]

    gross_spent = sum(u for u in daily_trade_usd if u > 0)
    units_bought = 0.0
    for trade_usd, price in zip(daily_trade_usd, prices, strict=True):
        if trade_usd > 0:
            units_bought += float(trade_usd) / float(price)
    avg_cost = (gross_spent / units_bought) if units_bought > 0 else None
    final_price = float(prices[-1])
    cost_vs_price = (avg_cost / final_price * 100.0) if avg_cost is not None else None

    buy_days = sell_days = no_trade_days = 0
    risk_sum = rate_sum = 0.0
    non_null = 0
    for day_risk, day_rate, trade_usd in zip(risk, rate, daily_trade_usd, strict=True):
        if day_risk is None:
            no_trade_days += 1
            continue
        non_null += 1
        risk_sum += float(day_risk)
        r = 0.0 if day_rate is None else float(day_rate)
        rate_sum += r
        if r > 0:
            buy_days += 1
        elif r < 0:
            sell_days += 1
        else:
            no_trade_days += 1

    return TearsheetDcaBreakdown(
        vs_lump_pct=(final_pv / final_lump - 1.0) * 100.0,
        vs_flat_dca_pct=(final_pv / final_flat - 1.0) * 100.0,
        avg_cost_basis=avg_cost,
        final_cost_basis_vs_price=cost_vs_price,
        capital_deployed_pct=float(net_deployed[-1]) / initial_cash * 100.0,
        capital_deployed_peak_pct=max(float(v) for v in net_deployed) / initial_cash * 100.0,
        units_accumulated=float(asset_units[-1]),
        buy_days=buy_days,
        sell_days=sell_days,
        no_trade_days=no_trade_days,
        avg_risk=(risk_sum / non_null) if non_null else None,
        avg_rate=(rate_sum / non_null) if non_null else None,
    )


def daily_state_from_fills(
    fills: Sequence[SdcaFill],
    bars: Sequence[tuple[str, float]],
    initial_cash: float,
) -> dict[str, list]:
    """Replay fills onto the bar calendar; return daily series for ``breakdown_from_daily``."""
    by_date: dict[str, list[SdcaFill]] = {}
    for fill in fills:
        by_date.setdefault(fill.date, []).append(fill)

    cash = float(initial_cash)
    units = 0.0
    prices: list[float] = []
    portfolio_values: list[float] = []
    daily_trade_usd: list[float] = []
    net_deployed: list[float] = []
    asset_units: list[float] = []

    for date, close in bars:
        traded = 0.0
        for fill in by_date.get(date, []):
            notional = fill.qty * fill.price
            if fill.side == "buy":
                cash -= notional
                units += fill.qty
                traded += notional
            else:
                cash += notional
                units -= fill.qty
                traded -= notional
        prices.append(float(close))
        daily_trade_usd.append(traded)
        asset_units.append(units)
        net_deployed.append(initial_cash - cash)
        portfolio_values.append(cash + units * float(close))

    return {
        "prices": prices,
        "portfolio_values": portfolio_values,
        "daily_trade_usd": daily_trade_usd,
        "net_deployed": net_deployed,
        "asset_units": asset_units,
    }


def fills_from_nautilus_report(report: object) -> list[SdcaFill]:
    """Parse ``trader.generate_fills_report()`` (pandas, Nautilus boundary)."""
    if report is None:
        return []
    empty = getattr(report, "empty", None)
    if empty is True or getattr(report, "shape", (0,))[0] == 0:
        return []
    reset = report.reset_index() if hasattr(report, "reset_index") else report
    records = reset.to_dict("records") if hasattr(reset, "to_dict") else []
    out: list[SdcaFill] = []
    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        side = _fill_side(rec)
        qty = _fill_float(rec, ("last_qty", "quantity", "qty"))
        price = _fill_float(rec, ("last_px", "price", "avg_px"))
        ts = rec.get("ts_event") or rec.get("ts_last") or rec.get("timestamp")
        if side is None or qty is None or price is None or ts is None or qty <= 0 or price <= 0:
            continue
        out.append(SdcaFill(date=str(ts)[:10], side=side, qty=qty, price=price))
    return out


def _fill_side(rec: Mapping[str, object]) -> Literal["buy", "sell"] | None:
    raw = str(rec.get("order_side") or rec.get("side") or rec.get("last_order_side") or "")
    upper = raw.upper()
    if "BUY" in upper:
        return "buy"
    if "SELL" in upper:
        return "sell"
    return None


def _fill_float(rec: Mapping[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in rec or rec[key] is None:
            continue
        try:
            return float(rec[key])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return None


def risk_band_label(risk: float | None) -> str | None:
    """Band copy for composite risk in [0, 100]. Matches the frontend labels (#3172)."""
    if risk is None:
        return None
    if risk < 10.0:
        return "Fire sale"
    if risk < 25.0:
        return "Accumulate"
    if risk < 50.0:
        return "Value"
    if risk < 75.0:
        return "Above mid"
    if risk < 95.0:
        return "Hot"
    return "Bubble"


def running_cost_basis(
    prices: Sequence[float], daily_trade_usd: Sequence[float]
) -> list[float | None]:
    """Average buy price after each day (None until the first buy). Sells do not rebase."""
    if len(prices) != len(daily_trade_usd):
        raise ValueError("running_cost_basis requires equal-length prices and daily_trade_usd")
    spent = 0.0
    bought = 0.0
    out: list[float | None] = []
    for price, trade_usd in zip(prices, daily_trade_usd, strict=True):
        if trade_usd > 0:
            spent += float(trade_usd)
            bought += float(trade_usd) / float(price)
        out.append((spent / bought) if bought > 0 else None)
    return out


def tearsheet_overlays(
    *,
    dates: Sequence[str],
    prices: Sequence[float],
    daily_trade_usd: Sequence[float],
    net_deployed: Sequence[float],
    initial_cash: float,
    rails: Sequence[tuple[float | None, float | None, float | None]],
    risk: Sequence[float | None],
) -> dict[str, list[dict[str, float | str]]]:
    """Diagnostic series for schema 1.3 charts (#3168 columns → #3172 overlays).

    Keys match the optional ``TearsheetData`` fields the renderer already reads:
    ``rails``, ``risk_curve``, ``cost_basis_curve``, ``capital_deployed_curve``,
    ``lump_equity_curve``, ``flat_dca_equity_curve``. Null rail/risk/cost days
    are omitted so the SVG path does not have to encode gaps.
    """
    n = len(dates)
    if not (
        len(prices) == len(daily_trade_usd) == len(net_deployed) == len(rails) == len(risk) == n
    ):
        raise ValueError("tearsheet_overlays requires equal-length daily series")
    if n == 0:
        return {
            "rails": [],
            "risk_curve": [],
            "cost_basis_curve": [],
            "capital_deployed_curve": [],
            "lump_equity_curve": [],
            "flat_dca_equity_curve": [],
        }

    lump = lump_mark_to_market(prices, initial_cash)
    flat = flat_dca_mark_to_market(prices, initial_cash)
    cost = running_cost_basis(prices, daily_trade_usd)

    rails_out: list[dict[str, float | str]] = []
    risk_out: list[dict[str, float | str]] = []
    cost_out: list[dict[str, float | str]] = []
    deployed_out: list[dict[str, float | str]] = []
    lump_out: list[dict[str, float | str]] = []
    flat_out: list[dict[str, float | str]] = []

    for i, day in enumerate(dates):
        low, median, high = rails[i]
        if low is not None and median is not None and high is not None:
            rails_out.append(
                {"t": day, "low": float(low), "median": float(median), "high": float(high)}
            )
        if risk[i] is not None:
            risk_out.append({"t": day, "v": float(risk[i])})
        if cost[i] is not None:
            cost_out.append({"t": day, "v": float(cost[i])})
        deployed_out.append({"t": day, "v": float(net_deployed[i]) / initial_cash * 100.0})
        lump_out.append({"t": day, "v": float(lump[i])})
        flat_out.append({"t": day, "v": float(flat[i])})

    return {
        "rails": rails_out,
        "risk_curve": risk_out,
        "cost_basis_curve": cost_out,
        "capital_deployed_curve": deployed_out,
        "lump_equity_curve": lump_out,
        "flat_dca_equity_curve": flat_out,
    }


def dca_current_signal(
    *,
    last_date: str,
    last_price: float | None,
    last_risk: float | None,
    last_rate: float | None,
    units_accumulated: float,
) -> dict[str, float | str | None]:
    """Today's DCA signal: risk, band, daily buy/sell rate — not long/short.

    ``position`` stays ``long``/``flat`` only because ``strategy_signals.position``
    is CHECK-constrained to those values. The product story is ``risk`` / ``band``
    / ``daily_rate_pct`` (percent of remaining cash on buys, remaining holdings
    on sells).
    """
    band = risk_band_label(last_risk)
    return {
        "position": "long" if units_accumulated > 0 else "flat",
        "entry_label": band or "",
        "last_signal_date": last_date,
        "last_price": last_price,
        "risk": last_risk,
        "band": band,
        "daily_rate_pct": last_rate,
    }


__all__ = [
    "SdcaFill",
    "flat_dca_mark_to_market",
    "lump_mark_to_market",
    "breakdown_from_daily",
    "daily_state_from_fills",
    "fills_from_nautilus_report",
    "risk_band_label",
    "running_cost_basis",
    "tearsheet_overlays",
    "dca_current_signal",
]
