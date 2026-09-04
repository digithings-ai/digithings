# score:allow pandas
"""Tearsheet HTML stats tables (categorized / full / risk)."""

from __future__ import annotations

import math

from digiquant.models import BacktestResult


def _build_categorized_stats(
    stats_returns: dict | None,
    stats_pnls: dict | None,
    stats_general: dict | None,
    result: BacktestResult,
) -> str:
    """Build categorized stats grid replacing the dropdown."""
    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {})
    ret = stats_returns or {}
    gen = stats_general or {}
    combined = {**pnl, **ret, **gen}

    def fv(k: str, fmt: str = ".2f") -> str:
        v = combined.get(k)
        if v is None and k == "Max Drawdown %" and result.max_drawdown_pct is not None:
            v = result.max_drawdown_pct
        if v is None:
            return "—"
        if isinstance(v, (int, float)) and not math.isnan(v):
            return f"{v:{fmt}}"
        return str(v)

    def row(
        label: str, key: str, fmt: str = ".2f", is_pct: bool = False, positive_good: bool = True
    ) -> str:
        v = combined.get(key)
        if v is None and key == "Max Drawdown %":
            v = result.max_drawdown_pct
        if v is None:
            val_str = "—"
            cls = ""
        elif isinstance(v, (int, float)) and not math.isnan(v):
            if is_pct:
                val_str = f"{v:{fmt}}%"
            else:
                val_str = f"{v:{fmt}}"
            good = v > 0 if positive_good else v < 0
            cls = " pos" if good else " neg"
        else:
            val_str = str(v)
            cls = ""
        return f'<tr><td class="sk">{label}</td><td class="sv{cls}">{val_str}</td></tr>'

    def section(title: str, rows_html: str) -> str:
        return f'<div class="stats-section"><div class="stats-section-title">{title}</div><table class="stats-mini-table">{rows_html}</table></div>'

    perf = (
        row("Total Return", "Total Return", ".2f", True)
        + row("Total PnL", "PnL (USD)", ",.2f")
        + row("Ann. Return", "Annualized Return", ".2f", True)
        + row("Best Day", "Max Return", ".2f", True)
        + row("Worst Day", "Min Return", ".2f", True)
    )
    risk = (
        row("Sharpe (252d)", "Sharpe Ratio (252 days)", ".2f")
        + row("Sortino (252d)", "Sortino Ratio (252 days)", ".2f")
        + row("Calmar Ratio", "Calmar Ratio", ".2f")
        + row("Max Drawdown", "Max Drawdown %", ".1f", True, False)
        + row("Volatility", "Returns Volatility (252 days)", ".4f")
        + row("Value at Risk", "Value at Risk", ".4f")
    )
    trade_stats = (
        row("# Trades", "Total Trades", ".0f")
        + row("Win Rate", "Win Rate", ".2f", True)
        + row("Avg Winner", "Avg Winner", ",.2f")
        + row("Avg Loser", "Avg Loser", ",.2f")
        + row("Max Winner", "Max Winner", ",.2f")
        + row("Max Loser", "Max Loser", ",.2f")
    )
    ratios = (
        row("Profit Factor", "Profit Factor", ".2f")
        + row("Expectancy", "Expectancy", ",.2f")
        + row("Risk/Return", "Risk Return Ratio", ".2f")
        + row("Avg Trade", "Avg Trade", ",.2f")
        + row("Win Streak", "Max Win Streak", ".0f")
        + row("Loss Streak", "Max Loss Streak", ".0f")
    )

    return (
        f'<div class="stats-grid">'
        f"{section('Performance', perf)}"
        f"{section('Risk & Ratios', risk)}"
        f"{section('Trade Stats', trade_stats)}"
        f"{section('Additional', ratios)}"
        f"</div>"
    )


def _build_full_stats_table(
    stats_returns: dict | None,
    stats_pnls: dict | None,
    stats_general: dict | None,
    result: BacktestResult,
) -> str:
    rows: list[tuple[str, str]] = []

    def _fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {})
    for k, v in (pnl or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    for k, v in (stats_returns or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    for k, v in (stats_general or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    if result.max_drawdown_pct is not None and not any("Max Drawdown" in r[0] for r in rows):
        rows.append(("Max Drawdown %", f"{result.max_drawdown_pct:.1f}%"))
    trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (
        f'<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{trs}</tbody></table>'
        if trs
        else "<p class='no-data'>No stats available.</p>"
    )


def _build_risk_metrics_table(
    stats_pnls: dict | None, stats_returns: dict | None, result: BacktestResult
) -> str:
    risk_keys = (
        "Max Drawdown %",
        "Max Loser",
        "Max Winner",
        "Avg Loser",
        "Avg Winner",
        "Min Loser",
        "Min Winner",
        "Win Rate",
        "Expectancy",
        "Returns Volatility (252 days)",
        "Sharpe Ratio (252 days)",
        "Sortino Ratio (252 days)",
        "Profit Factor",
        "Risk Return Ratio",
    )
    rows: list[tuple[str, str]] = []

    def _fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    pnl = stats_pnls or {}
    if isinstance(pnl, dict) and any(isinstance(v, dict) for v in pnl.values()):
        pnl = pnl.get("USD", pnl) if "USD" in pnl else next(iter(pnl.values()), {}) or {}
    combined = {**(pnl or {}), **(stats_returns or {})}
    for k in risk_keys:
        v = combined.get(k)
        if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((k, _fmt(v)))
    if result.max_drawdown_pct is not None and not any("Max Drawdown" in r[0] for r in rows):
        rows.insert(0, ("Max Drawdown %", f"{result.max_drawdown_pct:.1f}%"))
    trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (
        f'<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{trs}</tbody></table>'
        if trs
        else "<p class='no-data'>No risk metrics.</p>"
    )
