"""Unified tearsheet data contract — one schema both backtest engines emit.

The Pine-faithful validation backtester (``scripts/validation/pine_backtest.py``)
and the production NautilusTrader engine (``digiquant.backtest``) produce very
different native shapes. This module defines a single ``TearsheetData`` model
that both adapt into, so the standalone HTML/JS renderer in
``frontend/digiquant/`` has exactly one shape to consume.

Serialize with ``TearsheetData.to_json()`` and drop the result next to the
renderer (``frontend/digiquant/strategies/<strategy>.json``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from pydantic import BaseModel, Field

# 1.1 — added optional ``ohlc_bars`` (price candlesticks) + per-trade signal type
# carried in ``entry_label`` (MR/Trend/MR&T) on the nautilus path. Back-compatible:
# 1.0 consumers ignore ``ohlc_bars``; 1.1 fixtures may carry an empty list.
SCHEMA_VERSION = "1.1"


class SeriesPoint(BaseModel):
    """One (timestamp, value) sample on a time series (equity, drawdown)."""

    t: str = Field(..., description="ISO date or datetime")
    v: float = Field(..., description="Value at t")


class OHLCBar(BaseModel):
    """One OHLC price bar for the candlestick price chart.

    Single-letter ``t/o/h/l/c`` keys mirror ``SeriesPoint``'s compact ``t/v``
    style and keep the per-bar JSON small across a multi-year daily series.
    """

    t: str = Field(..., description="ISO date or datetime")
    o: float = Field(..., description="Open")
    h: float = Field(..., description="High")
    l: float = Field(..., description="Low")  # noqa: E741 — OHLC convention, compact chart key
    c: float = Field(..., description="Close")


class StatBlock(BaseModel):
    """TradingView-style performance block (All / Long / Short)."""

    trades: int = 0
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    gross_profit: float | None = None
    gross_loss: float | None = None
    percent_profitable: float = 0.0
    profit_factor: float | None = None
    avg_trade: float = 0.0
    wins: int = 0
    losses: int = 0


class TradeRecord(BaseModel):
    """A single closed trade."""

    n: int = Field(..., description="1-based trade index")
    direction: str = Field(..., description="long | short")
    entry_label: str = ""
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    qty: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    equity_after: float = 0.0
    exit_reason: str = ""
    max_runup_pct: float | None = None
    max_drawdown_pct: float | None = None


class TearsheetData(BaseModel):
    """Everything the renderer needs for one strategy/symbol backtest."""

    schema_version: str = SCHEMA_VERSION
    strategy: str
    symbol: str
    engine: str = Field("pine", description="pine | nautilus")
    generated_at: str = Field(..., description="ISO-8601 UTC generation timestamp")
    data_source: str = Field("", description="Provenance of the price data")

    # ── Run window ────────────────────────────────────────────────────────
    period_start: str = ""
    period_end: str = ""
    bars: int = 0
    initial_capital: float = 0.0
    final_equity: float = 0.0

    # ── Headline KPIs ─────────────────────────────────────────────────────
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    profit_factor: float | None = None
    win_rate_pct: float = 0.0
    total_trades: int = 0
    avg_trade: float = 0.0

    # ── Directional breakdown ─────────────────────────────────────────────
    overall: StatBlock = Field(default_factory=StatBlock)
    long: StatBlock | None = None
    short: StatBlock | None = None

    # ── Series + trades ───────────────────────────────────────────────────
    equity_curve: list[SeriesPoint] = Field(default_factory=list)
    drawdown_curve: list[SeriesPoint] = Field(default_factory=list)
    # Full-history OHLC price bars for the candlestick chart. Defaults to []
    # for back-compat: 1.0 fixtures (and adapters that have no bars) omit it.
    ohlc_bars: list[OHLCBar] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)

    notes: list[str] = Field(default_factory=list)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize to a JSON string for the static renderer to fetch."""
        return self.model_dump_json(indent=indent)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _drawdown_from_equity(
    equity: Sequence[tuple[str, float]], initial_capital: float
) -> list[SeriesPoint]:
    """Running peak-to-trough drawdown (%) of a mark-to-market equity curve."""
    peak = initial_capital
    out: list[SeriesPoint] = []
    for ts, eq in equity:
        peak = max(peak, eq)
        dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0
        out.append(SeriesPoint(t=ts, v=dd))
    return out


def _stat_block(block: Mapping[str, object] | None) -> StatBlock:
    """Build a StatBlock from a pine ``_dir_metrics`` dict (tolerant of gaps)."""
    if not block:
        return StatBlock()
    return StatBlock(
        trades=int(block.get("trades", 0) or 0),
        net_profit=float(block.get("net_profit", 0.0) or 0.0),
        net_profit_pct=float(block.get("net_profit_pct", 0.0) or 0.0),
        gross_profit=_opt_float(block.get("gross_profit")),
        gross_loss=_opt_float(block.get("gross_loss")),
        percent_profitable=float(block.get("percent_profitable", 0.0) or 0.0),
        profit_factor=_opt_float(block.get("profit_factor")),
        avg_trade=float(block.get("avg_trade", 0.0) or 0.0),
        wins=int(block.get("wins", 0) or 0),
        losses=int(block.get("losses", 0) or 0),
    )


def _opt_float(v: object) -> float | None:
    return None if v is None else float(v)  # type: ignore[arg-type]


def _build_tearsheet(
    summary: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    equity_curve: Sequence[tuple[str, float]],
    *,
    engine: str,
    data_source: str = "",
    generated_at: str | None = None,
    notes: Sequence[str] | None = None,
    ohlc_bars: Sequence[tuple[str, float, float, float, float]] | None = None,
) -> TearsheetData:
    """Shared builder for the summary-based adapters (``from_pine`` / ``from_nautilus_run``).

    ``summary`` is a dict with All/Long/Short metric blocks (keys mirroring
    ``pine_backtest.summarize``); ``trades`` is a sequence of per-closed-trade
    mappings; ``equity_curve`` is the ``(date, mark-to-market equity)`` list.
    ``ohlc_bars`` is an optional ``(date, open, high, low, close)`` list for the
    candlestick price chart (raw tuples so callers need not import ``OHLCBar``).
    """
    overall = summary.get("all")
    overall_block = _stat_block(overall if isinstance(overall, Mapping) else None)
    period = str(summary.get("period", ""))
    start, _, end = period.partition("→")

    trade_records = [
        TradeRecord(
            n=i,
            direction=str(t.get("direction", "")),
            entry_label=str(t.get("entry_label", "")),
            entry_date=str(t.get("entry_date", "")),
            entry_price=float(t.get("entry_price", 0.0) or 0.0),
            exit_date=str(t.get("exit_date", "")),
            exit_price=float(t.get("exit_price", 0.0) or 0.0),
            qty=float(t.get("qty", 0.0) or 0.0),
            pnl=float(t.get("pnl", 0.0) or 0.0),
            pnl_pct=float(t.get("pnl_pct", 0.0) or 0.0),
            equity_after=float(t.get("equity_after", 0.0) or 0.0),
            exit_reason=str(t.get("exit_reason", "")),
            max_runup_pct=_opt_float(t.get("max_runup_pct")),
            max_drawdown_pct=_opt_float(t.get("max_drawdown_pct")),
        )
        for i, t in enumerate(trades, 1)
    ]

    initial_capital = float(summary.get("initial_capital", 0.0) or 0.0)
    long_block = summary.get("long")
    short_block = summary.get("short")

    return TearsheetData(
        strategy=str(summary.get("strategy", "")),
        symbol=str(summary.get("symbol", "")),
        engine=engine,
        generated_at=generated_at or _utc_now_iso(),
        data_source=data_source,
        period_start=start.strip(),
        period_end=end.strip(),
        bars=int(summary.get("bars", 0) or 0),
        initial_capital=initial_capital,
        final_equity=float(summary.get("final_equity", 0.0) or 0.0),
        net_profit=overall_block.net_profit,
        net_profit_pct=float(summary.get("net_profit_pct", 0.0) or 0.0),
        max_drawdown_pct=float(summary.get("max_drawdown_pct", 0.0) or 0.0),
        profit_factor=overall_block.profit_factor,
        win_rate_pct=overall_block.percent_profitable,
        total_trades=overall_block.trades,
        avg_trade=overall_block.avg_trade,
        overall=overall_block,
        long=_stat_block(long_block if isinstance(long_block, Mapping) else None),
        short=_stat_block(short_block if isinstance(short_block, Mapping) else None),
        equity_curve=[SeriesPoint(t=ts, v=v) for ts, v in equity_curve],
        drawdown_curve=_drawdown_from_equity(equity_curve, initial_capital),
        ohlc_bars=[OHLCBar(t=t, o=o, h=h, l=low, c=c) for t, o, h, low, c in (ohlc_bars or [])],
        trades=trade_records,
        notes=list(notes or []),
    )


def from_pine(
    summary: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    equity_curve: Sequence[tuple[str, float]],
    *,
    data_source: str = "",
    generated_at: str | None = None,
    notes: Sequence[str] | None = None,
    ohlc_bars: Sequence[tuple[str, float, float, float, float]] | None = None,
) -> TearsheetData:
    """Adapt the Pine validation backtester output into ``TearsheetData`` (engine=pine)."""
    return _build_tearsheet(
        summary,
        trades,
        equity_curve,
        engine="pine",
        data_source=data_source,
        generated_at=generated_at,
        notes=notes,
        ohlc_bars=ohlc_bars,
    )


def from_nautilus_run(
    summary: Mapping[str, object],
    trades: Sequence[Mapping[str, object]],
    equity_curve: Sequence[tuple[str, float]],
    *,
    data_source: str = "",
    generated_at: str | None = None,
    notes: Sequence[str] | None = None,
    ohlc_bars: Sequence[tuple[str, float, float, float, float]] | None = None,
) -> TearsheetData:
    """Adapt a NautilusTrader backtest (round-trip positions + MTM equity) into
    ``TearsheetData`` (engine=nautilus). Same summary/trades/equity shape as
    ``from_pine`` so the renderer consumes one schema regardless of engine."""
    return _build_tearsheet(
        summary,
        trades,
        equity_curve,
        engine="nautilus",
        data_source=data_source,
        generated_at=generated_at,
        notes=notes,
        ohlc_bars=ohlc_bars,
    )


def from_nautilus(
    result: object,
    *,
    symbol: str = "",
    equity_curve: Sequence[tuple[str, float]] | None = None,
    trades: Sequence[Mapping[str, object]] | None = None,
    data_source: str = "",
    generated_at: str | None = None,
    notes: Sequence[str] | None = None,
) -> TearsheetData:
    """Adapt a ``digiquant.models.BacktestResult`` into ``TearsheetData``.

    ``result`` is duck-typed (only attribute access is used) so this module
    stays import-light and does not pull in the Nautilus stack. Optional
    ``equity_curve`` / ``trades`` enrich the charts when the caller has the
    account and fills reports; otherwise headline KPIs still render.
    """
    initial_capital = float(getattr(result, "initial_capital", 0.0) or 0.0)
    total_pnl = float(getattr(result, "total_pnl", 0.0) or 0.0)
    symbols = getattr(result, "symbols", None) or []
    resolved_symbol = symbol or (symbols[0] if symbols else "")
    eq = list(equity_curve or [])
    final_equity = eq[-1][1] if eq else initial_capital + total_pnl

    trade_records = [
        TradeRecord(
            n=i,
            direction=str(t.get("direction", "")),
            entry_label=str(t.get("entry_label", "")),
            entry_date=str(t.get("entry_date", "")),
            entry_price=float(t.get("entry_price", 0.0) or 0.0),
            exit_date=str(t.get("exit_date", "")),
            exit_price=float(t.get("exit_price", 0.0) or 0.0),
            qty=float(t.get("qty", 0.0) or 0.0),
            pnl=float(t.get("pnl", 0.0) or 0.0),
            pnl_pct=float(t.get("pnl_pct", 0.0) or 0.0),
            equity_after=float(t.get("equity_after", 0.0) or 0.0),
            exit_reason=str(t.get("exit_reason", "")),
            max_runup_pct=_opt_float(t.get("max_runup_pct")),
            max_drawdown_pct=_opt_float(t.get("max_drawdown_pct")),
        )
        for i, t in enumerate(trades or [], 1)
    ]

    max_dd = getattr(result, "max_drawdown_pct", None)

    return TearsheetData(
        strategy=str(getattr(result, "strategy_name", "")),
        symbol=resolved_symbol,
        engine="nautilus",
        generated_at=generated_at or _utc_now_iso(),
        data_source=data_source,
        period_start=str(getattr(result, "start_time", "")),
        period_end=str(getattr(result, "end_time", "")),
        bars=0,
        initial_capital=initial_capital,
        final_equity=final_equity,
        net_profit=total_pnl,
        net_profit_pct=float(getattr(result, "total_return_pct", 0.0) or 0.0),
        max_drawdown_pct=float(max_dd) if max_dd is not None else 0.0,
        sharpe_ratio=_opt_float(getattr(result, "sharpe_ratio", None)),
        total_trades=int(getattr(result, "num_trades", 0) or 0),
        equity_curve=[SeriesPoint(t=ts, v=v) for ts, v in eq],
        drawdown_curve=_drawdown_from_equity(eq, initial_capital) if eq else [],
        trades=trade_records,
        notes=list(notes or []),
    )


__all__ = [
    "SCHEMA_VERSION",
    "OHLCBar",
    "SeriesPoint",
    "StatBlock",
    "TearsheetData",
    "TradeRecord",
    "from_nautilus",
    "from_nautilus_run",
    "from_pine",
]
