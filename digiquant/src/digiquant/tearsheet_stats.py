# score:allow pandas
"""Tearsheet HTML stats tables (categorized / full / risk)."""

from __future__ import annotations

import math
from typing import NamedTuple

from digiquant.models import BacktestResult
from digiquant.stats.honesty import REFUSE_FLOOR, format_honest_rate

#: A counted ``k`` cannot be paired with a fill count. Kept as a named string
#: so every surface refuses it in the same words, and so the refusal is
#: assertable rather than an implied consequence of a floor.
MIXED_POPULATION = "REFUSED — counted wins and the fill count are different populations"

#: Nautilus emits this count under a trades name, but it counts fill rows.
#: Only the displayed label changes — the dict key it is looked up by is
#: untouched, so nothing downstream has to learn a new key.
FILL_COUNT_LABELS = {"Total Trades": "Total Fills"}


def _label(key: str) -> str:
    """Display label for a stats key, with fill counts named as fill counts."""
    return FILL_COUNT_LABELS.get(key, key)


class WinRateCounts(NamedTuple):
    """Resolved ``(k, n)`` for one win-rate surface, plus what it renders.

    ``counted`` records whether ``k`` was *counted* (``True`` — from the
    honest block or from caller-counted round trips) or reconstructed from a
    reported rate (``False`` — the legacy path, kept only for results built
    before L3 carried an ``honest_rate`` block).
    """

    k: int
    n: int
    counted: bool
    refused: bool
    text: str


def resolve_win_rate(
    result: BacktestResult,
    rate: object = None,
    *,
    wins: int | None = None,
) -> WinRateCounts:
    """Resolve the win rate a surface must render for ``result``.

    ``result.honest_rate`` is authoritative: ``k``, ``n`` and the sample-size
    floors come straight off the block, so no surface reconstructs ``k`` from
    a rate and no surface uses the fill count as a denominator.

    The fallback exists solely for results whose block is ``None`` — older
    fixtures and any caller that has not been through L3. It prefers a
    caller-counted ``wins``; failing that it reconstructs
    ``round(rate * num_trades)`` exactly as before. That single ``round`` is
    the module's last ``rate x n`` reconstruction and it never reaches a
    rendered surface when a block is present.
    """
    block = result.honest_rate
    if block is not None:
        return WinRateCounts(
            block.k,
            block.n,
            True,
            block.refused,
            format_honest_rate(block.k, block.n, warn=block.warn_floor, refuse=block.refuse_floor),
        )

    n = result.num_trades
    usable = isinstance(rate, (int, float)) and not math.isnan(rate)
    if wins is not None:
        # A counted k is closed round trips; the only n a blockless result
        # carries is a fill count. Publishing the pair is the
        # mixed-population rate this resolver exists to remove, and it is
        # live: nautilus_runner.py:706 builds the multi-symbol aggregate
        # with num_trades summed over fills and no honest_rate block. So the
        # pair is refused rather than rendered, and counted stays False so
        # the donut is handed no k to slice out of the fill count either.
        return WinRateCounts(min(n, max(0, wins)), n, False, True, MIXED_POPULATION)
    if usable:
        wr = float(rate)
        if wr > 1:  # tolerate percent-scale callers; Nautilus emits a fraction
            wr /= 100.0
        wr = max(0.0, min(1.0, wr))
        k = min(n, max(0, round(wr * n)))
        return WinRateCounts(k, n, False, n < REFUSE_FLOOR, format_honest_rate(k, n))
    return WinRateCounts(0, n, False, n < REFUSE_FLOOR, "—")


def _honest_win_rate_text(value: object, result: BacktestResult) -> str:
    """Honest win-rate string for a Nautilus ``Win Rate`` stat (fraction).

    Delegates to :func:`resolve_win_rate`, so the denominator is the honest
    block's ``n`` when one exists and the legacy fill-count fallback
    otherwise. Returns an em-dash for missing/non-numeric input, ``REFUSED``
    below the refuse floor, and ``"{pct}% (k/n, n=N, 95% CI …)"`` otherwise —
    never a bare percentage.
    """
    return resolve_win_rate(result, value).text


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
    win_rate_html = _honest_win_rate_text(combined.get("Win Rate"), result)
    trade_stats = (
        # Nautilus counts fill rows here, not closed round trips — say so.
        row("# Fills", "Total Trades", ".0f")
        + f'<tr><td class="sk">Win Rate</td><td class="sv">{win_rate_html}</td></tr>'
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
            rows.append((_label(k), _fmt(v)))
    for k, v in (stats_returns or {}).items():
        if isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((_label(k), _fmt(v)))
    for k, v in (stats_general or {}).items():
        if k == "Win Rate":
            if isinstance(v, (int, float)) and not math.isnan(v):
                rows.append((k, _honest_win_rate_text(v, result)))
        elif isinstance(v, (int, float)) and not math.isnan(v):
            rows.append((_label(k), _fmt(v)))
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
            if k == "Win Rate":
                rows.append((k, _honest_win_rate_text(v, result)))
            else:
                rows.append((k, _fmt(v)))
    if result.max_drawdown_pct is not None and not any("Max Drawdown" in r[0] for r in rows):
        rows.insert(0, ("Max Drawdown %", f"{result.max_drawdown_pct:.1f}%"))
    trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (
        f'<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{trs}</tbody></table>'
        if trs
        else "<p class='no-data'>No risk metrics.</p>"
    )
