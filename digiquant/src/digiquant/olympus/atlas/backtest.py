"""Backtest of the agent's recorded decisions (Pillar 3C).

Zero LLM cost: replays the realized outcome of each ``decision_log`` decision — the
ticker's return over its holding window vs the benchmark (alpha) — into a decision-level
tear sheet. The point is to measure the *track record* of the agent's calls: do they beat
the benchmark, and do **higher-conviction** calls earn **higher alpha** (calibration)?

Pure-functional (no I/O, no pandas): the caller assembles realized :class:`Trade` records
(entry date, conviction, stance, the holding-window return + the benchmark return over the
same window — both computed look-ahead-safely from ``price_history``) and this returns a
:class:`BacktestResult`. The script half does the Supabase reads.

This is a *decision-sequence* tear sheet (each decision = one trade), not a daily
overlapping-portfolio NAV simulation — the honest, well-defined quantity given the
decision-level data. Metric formulas mirror the frontend's TypeScript: Sharpe/Sortino/vol
from frontend/olympus/lib/portfolio-risk-metrics.ts, max-drawdown + information ratio from
frontend/olympus/components/portfolio/advanced-stats-panel.tsx (ported to Python; the pandas
``tearsheet.py`` is intentionally NOT imported).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

# Conviction buckets (effective conviction is −5..+5; decisions booked are long-side ≥ ~2).
_HIGH_CONVICTION = 4.0
_MED_CONVICTION = 2.0


@dataclass(frozen=True)
class Trade:
    """One realized decision: its holding-window return + the benchmark's, as fractions."""

    date: date
    ticker: str
    return_frac: float
    benchmark_frac: float
    conviction: float | None = None
    stance: str | None = None
    end_date: date | None = None  # holding-window close; lets same-run decisions still annualize


@dataclass(frozen=True)
class BucketStat:
    """Calibration stats for one conviction bucket."""

    bucket: str
    n: int
    mean_alpha_pct: float
    hit_rate: float


@dataclass(frozen=True)
class BacktestResult:
    n_trades: int
    hit_rate: float  # share of decisions with positive alpha
    mean_alpha_pct: float
    median_alpha_pct: float
    total_return_pct: float  # compounded over the decision sequence
    benchmark_total_return_pct: float
    annualized_return_pct: float | None  # total compounded, annualized over the decision span
    max_drawdown_pct: float  # worst peak-to-trough of the decision equity curve
    information_ratio: float  # mean(alpha) / std(alpha) — per-decision, NOT annualized
    sortino_ratio: float  # mean(alpha)/downside-std; falls back to info ratio if no downside
    conviction_buckets: list[BucketStat]


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _downside_std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    downs = [min(0.0, x) for x in xs]
    return (sum(d * d for d in downs) / len(xs)) ** 0.5


def _max_drawdown_pct(returns: Sequence[float]) -> float:
    """Worst peak-to-trough (%) of the equity curve built by compounding ``returns``."""
    nav = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        nav *= 1.0 + r
        peak = max(peak, nav)
        if peak > 0:
            worst = min(worst, nav / peak - 1.0)
    return round(worst * 100.0, 4)


def _compound(returns: Sequence[float]) -> float:
    nav = 1.0
    for r in returns:
        nav *= 1.0 + r
    return nav - 1.0


def _bucket_for(conviction: float | None) -> str:
    if conviction is None:
        return "unknown"
    if conviction >= _HIGH_CONVICTION:
        return "high"
    if conviction >= _MED_CONVICTION:
        return "medium"
    return "low"


def _bucket_stats(trades: Sequence[Trade]) -> list[BucketStat]:
    order = ["high", "medium", "low", "unknown"]
    grouped: dict[str, list[float]] = {b: [] for b in order}
    for t in trades:
        grouped[_bucket_for(t.conviction)].append(t.return_frac - t.benchmark_frac)
    out: list[BucketStat] = []
    for bucket in order:
        alphas = grouped[bucket]
        if not alphas:
            continue
        out.append(
            BucketStat(
                bucket=bucket,
                n=len(alphas),
                mean_alpha_pct=round(_mean(alphas) * 100.0, 4),
                hit_rate=round(sum(a > 0 for a in alphas) / len(alphas), 4),
            )
        )
    return out


def backtest_decisions(trades: Sequence[Trade]) -> BacktestResult:
    """Decision-level tear sheet over realized ``trades`` (chronological by entry date)."""
    if not trades:
        return BacktestResult(
            n_trades=0,
            hit_rate=0.0,
            mean_alpha_pct=0.0,
            median_alpha_pct=0.0,
            total_return_pct=0.0,
            benchmark_total_return_pct=0.0,
            annualized_return_pct=None,
            max_drawdown_pct=0.0,
            information_ratio=0.0,
            sortino_ratio=0.0,
            conviction_buckets=[],
        )

    ordered = sorted(trades, key=lambda t: t.date)
    rets = [t.return_frac for t in ordered]
    bench = [t.benchmark_frac for t in ordered]
    alphas = [r - b for r, b in zip(rets, bench, strict=True)]

    total_return = _compound(rets)
    # Span the sequence entry→holding-window-close, not entry→entry: decision_log records many
    # tickers under a single run_date, so an entry-to-entry span collapses to 0 days for a
    # single-run book and would null out annualization even with many trades. Fall back to
    # entry-to-entry when no window-close dates are carried (e.g. legacy callers).
    first_day = ordered[0].date
    ends = [t.end_date for t in ordered if t.end_date is not None]
    last_day = max(ends) if ends else ordered[-1].date
    span_days = (last_day - first_day).days
    annualized = (
        round(((1.0 + total_return) ** (365.0 / span_days) - 1.0) * 100.0, 4)
        if span_days > 0 and total_return > -1.0
        else None
    )
    std_a = _std(alphas)
    dstd_a = _downside_std(alphas)
    info_ratio = round(_mean(alphas) / std_a, 4) if std_a > 0 else 0.0
    # No downside deviation (every alpha ≥ 0 — the best case) leaves Sortino undefined; fall
    # back to the information ratio (its Sharpe analogue here), mirroring advanced-stats-panel's
    # downside-zero handling, rather than reporting a misleading 0.0.
    sortino = round(_mean(alphas) / dstd_a, 4) if dstd_a > 0 else info_ratio

    return BacktestResult(
        n_trades=len(ordered),
        hit_rate=round(sum(a > 0 for a in alphas) / len(alphas), 4),
        mean_alpha_pct=round(_mean(alphas) * 100.0, 4),
        median_alpha_pct=round(_median(alphas) * 100.0, 4),
        total_return_pct=round(total_return * 100.0, 4),
        benchmark_total_return_pct=round(_compound(bench) * 100.0, 4),
        annualized_return_pct=annualized,
        max_drawdown_pct=_max_drawdown_pct(rets),
        information_ratio=info_ratio,
        sortino_ratio=sortino,
        conviction_buckets=_bucket_stats(ordered),
    )


__all__ = ["BacktestResult", "BucketStat", "Trade", "backtest_decisions"]
