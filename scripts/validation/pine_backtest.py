"""Pine-faithful backtester for the Slapper strategy family — TradingView 1:1 validation.

This is NOT the production engine. It is a deliberate, line-by-line replica of the
TradingView/PineScript execution model so results can be compared trade-by-trade
against the TradingView Strategy Tester:

  * fills at the SIGNAL BAR's close (`process_orders_on_close=true`)
  * 100% of equity per entry, compounding (`default_qty_type=percent_of_equity`,
    `default_qty_value=100`)
  * no pyramiding (`pyramiding=0`) — a same-direction signal while in position is ignored
  * reversal via `strategy.entry` (a buy while short closes the short and opens a long)
  * `initial_capital=1000`, adverse `slippage` in ticks
  * the BTC `is_mr_only_entry` var semantics, including the `position_size==0` reset that
    runs AFTER the buy/sell tracking blocks (so the flag only persists on a reversal entry)

It reuses the SAME validated indicator classes as the production NautilusTrader
SlapperStrategy (digiquant.indicators.*) and the SAME registered parameters
(digiquant.strategies.registry), so the only thing re-expressed here is the
execution/fill model — the indicator math and parameters are shared, not forked.

Usage:
    python scripts/validation/pine_backtest.py btc_slapper digiquant/data/validation/BTC-USD_1d.csv
"""
from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure the package is importable when run as a script.
_SRC = Path(__file__).resolve().parents[2] / "digiquant" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from digiquant.indicators import BollingerBands, DPSDTrend, RollingADF, RSI, make_ma  # noqa: E402
from digiquant.indicators.ma import VWMA  # noqa: E402
from digiquant.strategies.registry import _REGISTRY  # noqa: E402

# ── Effective config (mirrors SlapperConfig defaults; overridden by registry) ──


@dataclass
class SlapperParams:
    """Signal + execution parameters. Defaults mirror SlapperConfig; the registry
    default_params for a given strategy are layered on top in `from_registry`."""

    rsi_length: int = 14
    rsi_use_ma: bool = True
    rsi_ma_length: int = 14
    rsi_ma_type: str = "EMA"
    rsi_upper_band: float = 44.0
    rsi_lower_band: float = 37.0

    adf_lookback: int = 44
    adf_nlag: int = 0
    adf_use_ma: bool = True
    adf_ma_length: int = 45
    adf_ma_type: str = "EMA"
    adf_upper_entry: float = -1.25
    adf_use_lower_entry: bool = True
    adf_lower_entry: float = -1.65

    bb_length: int = 37
    bb_ma_type: str = "EMA"
    bb_mult: float = 0.3

    dpsd_dema_length: int = 4
    dpsd_dema_src: str = "hlcc4"
    dpsd_percentile_length: int = 69
    dpsd_percentile_type: str = "55/45"
    dpsd_sd_length: int = 25
    dpsd_ema_length: int = 41
    dpsd_include_ema: bool = True

    use_reversal_stop: bool = False
    stop_drawdown_threshold: float = 20.0

    enable_long: bool = True
    enable_short: bool = True

    @classmethod
    def from_registry(cls, strategy_name: str) -> SlapperParams:
        spec = _REGISTRY[strategy_name]
        params = cls()
        for key, val in spec.default_params.items():
            if hasattr(params, key):
                setattr(params, key, val)
        return params


# ── Trade record ──────────────────────────────────────────────────────────────


@dataclass
class Trade:
    direction: str  # "long" | "short"
    entry_label: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float  # return on equity-at-entry
    equity_after: float
    exit_reason: str  # "reversal" | "reversal_stop" | "end_of_data"
    max_runup_pct: float
    max_drawdown_pct: float


# ── Backtester ──────────────────────────────────────────────────────────────────


@dataclass
class BacktestOutput:
    strategy_name: str
    symbol: str
    bars: int
    start_date: str
    end_date: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    initial_capital: float = 1000.0


def _load_ohlcv(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "date": r["timestamp"],
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": float(r["volume"]),
                }
            )
    return rows


def _make_rsi_ma(p: SlapperParams):
    if p.rsi_ma_type == "VWMA":
        return VWMA(p.rsi_ma_length), True
    return make_ma(p.rsi_ma_type, p.rsi_ma_length), False


def run_backtest(
    strategy_name: str,
    csv_path: str | Path,
    initial_capital: float = 1000.0,
    slippage_ticks: float = 1.0,
    tick_size: float = 0.01,
) -> BacktestOutput:
    p = SlapperParams.from_registry(strategy_name)
    bars = _load_ohlcv(csv_path)
    slip = slippage_ticks * tick_size

    rsi = RSI(p.rsi_length)
    rsi_ma, rsi_ma_is_vwma = _make_rsi_ma(p)
    adf = RollingADF(
        lookback=p.adf_lookback,
        nlag=p.adf_nlag,
        use_ma=p.adf_use_ma,
        ma_type=p.adf_ma_type,
        ma_length=p.adf_ma_length,
    )
    bb = BollingerBands(length=p.bb_length, mult=p.bb_mult, ma_type=p.bb_ma_type)
    dpsd = DPSDTrend(
        dema_length=p.dpsd_dema_length,
        percentile_length=p.dpsd_percentile_length,
        percentile_type=p.dpsd_percentile_type,
        sd_length=p.dpsd_sd_length,
        ema_length=p.dpsd_ema_length,
        include_ema=p.dpsd_include_ema,
    )

    prev_selected_rsi: float | None = None

    # Position state (Pine `var`-style, persists across bars).
    pos = 0  # 0 flat, +1 long, -1 short
    entry_price = 0.0
    entry_date = ""
    entry_label = ""
    qty = 0.0
    is_mr_only = False
    signal_close_price: float | None = None
    # Excursion tracking for the open position.
    peak_price = 0.0
    trough_price = 0.0

    equity = initial_capital
    bankrupt = False
    out = BacktestOutput(
        strategy_name=strategy_name,
        symbol=Path(csv_path).stem.replace("_1d", ""),
        bars=len(bars),
        start_date=bars[0]["date"] if bars else "",
        end_date=bars[-1]["date"] if bars else "",
        initial_capital=initial_capital,
    )

    def close_position(exit_price: float, exit_date: str, reason: str) -> None:
        nonlocal equity, pos, qty, entry_price, entry_date, entry_label
        nonlocal is_mr_only, signal_close_price, peak_price, trough_price
        if pos == 0:
            return
        fill = exit_price - slip if pos > 0 else exit_price + slip
        if pos > 0:
            pnl = qty * (fill - entry_price)
            runup = (peak_price - entry_price) / entry_price * 100
            ddown = (trough_price - entry_price) / entry_price * 100
        else:
            pnl = qty * (entry_price - fill)
            runup = (entry_price - trough_price) / entry_price * 100
            ddown = (entry_price - peak_price) / entry_price * 100
        nonlocal bankrupt
        equity_before = equity
        equity += pnl
        if equity <= 0:
            equity = 0.0
            bankrupt = True
        out.trades.append(
            Trade(
                direction="long" if pos > 0 else "short",
                entry_label=entry_label,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=fill,
                qty=qty,
                pnl=pnl,
                pnl_pct=(pnl / equity_before * 100) if equity_before else 0.0,
                equity_after=equity,
                exit_reason=reason,
                max_runup_pct=max(0.0, runup),
                max_drawdown_pct=min(0.0, ddown),
            )
        )
        pos = 0
        qty = 0.0

    def open_position(direction: int, price: float, date: str, label: str) -> None:
        nonlocal equity, pos, qty, entry_price, entry_date, entry_label, peak_price, trough_price
        fill = price + slip if direction > 0 else price - slip
        qty = equity / fill  # 100% of equity, fractional units (Pine percent_of_equity=100)
        pos = direction
        entry_price = fill
        entry_date = date
        entry_label = label
        peak_price = price
        trough_price = price

    for bar in bars:
        close = bar["close"]
        high = bar["high"]
        low = bar["low"]
        volume = bar["volume"]

        dpsd_src = (
            (high + low) / 2.0
            if p.dpsd_dema_src == "hl2"
            else (high + low + close * 2.0) / 4.0
        )

        rsi.update(close)
        adf.update(close)
        bb.update(close)
        dpsd.update(src=dpsd_src, close=close)

        # Track excursion for any open position (uses this bar's high/low).
        if pos != 0:
            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

        if not (rsi.initialized and adf.initialized and bb.initialized):
            continue

        if bankrupt:
            # Account ruined — a real venue (and the TradingView tester) halts here
            # rather than letting a 100%-equity short ride into negative equity.
            out.equity_curve.append((bar["date"], 0.0))
            break

        # ── RSI MA ────────────────────────────────────────────────────────────
        if p.rsi_use_ma:
            if rsi_ma_is_vwma:
                rsi_ma.update(price=rsi.value, volume=volume)
            else:
                rsi_ma.update(rsi.value)
            selected_rsi = rsi_ma.value if rsi_ma.initialized else None
        else:
            selected_rsi = rsi.value
        if selected_rsi is None:
            continue

        # ── Signals (mirror SlapperStrategy.on_bar) ───────────────────────────
        upper_b, lower_b = p.rsi_upper_band, p.rsi_lower_band
        prev = prev_selected_rsi
        rsi_long = prev is not None and prev < upper_b and selected_rsi >= upper_b
        rsi_short = prev is not None and prev > upper_b and selected_rsi <= upper_b
        rsi_over_under = selected_rsi > upper_b or selected_rsi < lower_b
        prev_selected_rsi = selected_rsi

        adf_long = adf.crossover(p.adf_upper_entry) or (
            p.adf_use_lower_entry and adf.crossover(p.adf_lower_entry)
        )
        adf_short = adf.crossunder(p.adf_upper_entry) or (
            p.adf_use_lower_entry and adf.crossunder(p.adf_lower_entry)
        )

        bb_long = close < bb.lower
        bb_short = close > bb.upper

        mr_long = (adf_long or rsi_long) and rsi_over_under and bb_long
        mr_short = (adf_short or rsi_short) and bb_short
        trend_long = dpsd.crossed_up() if dpsd.initialized else False
        trend_short = dpsd.crossed_down() if dpsd.initialized else False

        buy_signal = mr_long or trend_long
        sell_signal = mr_short or trend_short

        # ── Position tracking for reversal stop (Pine ordering, exact) ────────
        # position_size here = position ENTERING this bar (fills happen at close,
        # after this logic), so we read `pos` before any close/open below.
        pos_entering = pos
        if p.use_reversal_stop:
            if buy_signal and pos_entering <= 0:
                is_mr_only = mr_long and not trend_long
                signal_close_price = close
            if sell_signal and pos_entering >= 0:
                is_mr_only = mr_short and not trend_short
                signal_close_price = close
            if pos_entering == 0:
                is_mr_only = False
                signal_close_price = None

        # ── Reversal stop logic (BTC) ─────────────────────────────────────────
        trigger_long_reversal = False
        trigger_short_reversal = False
        if p.use_reversal_stop and signal_close_price is not None:
            dpsd_trend = dpsd.trend if dpsd.initialized else 0.0
            if pos_entering > 0 and is_mr_only and dpsd_trend == -1.0:
                long_dd = (signal_close_price - close) / signal_close_price * 100
                if long_dd > p.stop_drawdown_threshold:
                    trigger_short_reversal = True
            if pos_entering < 0 and is_mr_only and dpsd_trend == 1.0:
                short_dd = (close - signal_close_price) / signal_close_price * 100
                if short_dd > p.stop_drawdown_threshold:
                    trigger_long_reversal = True

        if trigger_long_reversal and p.enable_long:
            close_position(close, bar["date"], "reversal_stop")
            open_position(1, close, bar["date"], "Reversal Long")
            is_mr_only = False
        elif trigger_short_reversal and p.enable_short:
            close_position(close, bar["date"], "reversal_stop")
            open_position(-1, close, bar["date"], "Reversal Short")
            is_mr_only = False

        # ── Entries (pyramiding=0 reversal) ───────────────────────────────────
        if buy_signal and p.enable_long:
            if pos <= 0:  # flat or short → reverse/open long
                label = (
                    "MR&T Long" if mr_long and trend_long
                    else "Trend Long" if trend_long
                    else "MR Long"
                )
                if pos < 0:
                    close_position(close, bar["date"], "reversal")
                open_position(1, close, bar["date"], label)
            # already long → ignored (pyramiding=0)
        elif sell_signal and p.enable_short:
            if pos >= 0:  # flat or long → reverse/open short
                label = (
                    "MR&T Short" if mr_short and trend_short
                    else "Trend Short" if trend_short
                    else "MR Short"
                )
                if pos > 0:
                    close_position(close, bar["date"], "reversal")
                open_position(-1, close, bar["date"], label)
            # already short → ignored (pyramiding=0)

        # Mark-to-market equity (realized + unrealized) for the equity curve, so
        # max drawdown matches TradingView (which includes open-trade drawdown).
        # While flat: equity. Long: position is worth qty*close. Short: equity at
        # entry + qty*(entry_price - close).
        if pos > 0:
            mtm = qty * close
        elif pos < 0:
            mtm = equity + qty * (entry_price - close)
        else:
            mtm = equity
        out.equity_curve.append((bar["date"], mtm))

    return out


# ── Metrics ───────────────────────────────────────────────────────────────────


def _dir_metrics(trades: list[Trade], initial: float) -> dict:
    if not trades:
        return {
            "trades": 0, "net_profit": 0.0, "net_profit_pct": 0.0,
            "percent_profitable": 0.0, "profit_factor": None,
            "avg_trade": 0.0, "wins": 0, "losses": 0,
        }
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    net = sum(t.pnl for t in trades)
    return {
        "trades": len(trades),
        "net_profit": net,
        "net_profit_pct": net / initial * 100,
        "gross_profit": gross_profit,
        "gross_loss": -gross_loss,
        "percent_profitable": len(wins) / len(trades) * 100,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "avg_trade": net / len(trades),
        "wins": len(wins),
        "losses": len(losses),
    }


def _max_equity_drawdown_pct(out: BacktestOutput) -> float:
    """Max peak-to-trough drawdown of the mark-to-market equity curve, in percent.

    Uses the full bar-by-bar equity curve (realized + unrealized) so it matches
    TradingView, which includes open-trade drawdown — not just closed-trade equity.
    """
    peak = out.initial_capital
    max_dd = 0.0
    for _date, eq in out.equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            dd = (eq - peak) / peak * 100
            max_dd = min(max_dd, dd)
    return max_dd


def summarize(out: BacktestOutput) -> dict:
    longs = [t for t in out.trades if t.direction == "long"]
    shorts = [t for t in out.trades if t.direction == "short"]
    final_equity = out.trades[-1].equity_after if out.trades else out.initial_capital
    return {
        "strategy": out.strategy_name,
        "symbol": out.symbol,
        "period": f"{out.start_date} → {out.end_date}",
        "bars": out.bars,
        "initial_capital": out.initial_capital,
        "final_equity": final_equity,
        "net_profit_pct": (final_equity - out.initial_capital) / out.initial_capital * 100,
        "max_drawdown_pct": _max_equity_drawdown_pct(out),
        "all": _dir_metrics(out.trades, out.initial_capital),
        "long": _dir_metrics(longs, out.initial_capital),
        "short": _dir_metrics(shorts, out.initial_capital),
    }


def write_trades_csv(out: BacktestOutput, path: str | Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "trade_num", "direction", "entry_label", "entry_date", "entry_price",
            "exit_date", "exit_price", "qty", "pnl", "pnl_pct_equity",
            "cumulative_equity", "exit_reason", "max_runup_pct", "max_drawdown_pct",
        ])
        for i, t in enumerate(out.trades, 1):
            w.writerow([
                i, t.direction, t.entry_label, t.entry_date, f"{t.entry_price:.2f}",
                t.exit_date, f"{t.exit_price:.2f}", f"{t.qty:.6f}", f"{t.pnl:.2f}",
                f"{t.pnl_pct:.2f}", f"{t.equity_after:.2f}", t.exit_reason,
                f"{t.max_runup_pct:.2f}", f"{t.max_drawdown_pct:.2f}",
            ])


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def print_summary(s: dict) -> None:
    print(f"\n{'='*64}")
    print(f"  {s['strategy']}  ·  {s['symbol']}  ·  {s['period']}")
    print(f"{'='*64}")
    print(f"  Initial capital : {_fmt(s['initial_capital'])}")
    print(f"  Final equity    : {_fmt(s['final_equity'])}")
    print(f"  Net profit      : {_fmt(s['net_profit_pct'])}%")
    print(f"  Max drawdown    : {_fmt(s['max_drawdown_pct'])}%")
    print(f"\n  {'':14s}{'All':>14s}{'Long':>14s}{'Short':>14s}")
    rows = [
        ("Trades", "trades", "d"),
        ("Net profit %", "net_profit_pct", "f"),
        ("% profitable", "percent_profitable", "f"),
        ("Profit factor", "profit_factor", "f"),
        ("Avg trade", "avg_trade", "f"),
    ]
    for label, key, kind in rows:
        a, lo, sh = s["all"][key], s["long"][key], s["short"][key]
        if kind == "d":
            print(f"  {label:14s}{a:>14d}{lo:>14d}{sh:>14d}")
        else:
            print(f"  {label:14s}{_fmt(a):>14s}{_fmt(lo):>14s}{_fmt(sh):>14s}")


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: pine_backtest.py <strategy_name> <ohlcv_csv> [out_dir]")
        sys.exit(1)
    strategy_name, csv_path = sys.argv[1], sys.argv[2]
    out_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("digiquant/results/validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    out = run_backtest(strategy_name, csv_path)
    s = summarize(out)
    print_summary(s)

    trades_csv = out_dir / f"{strategy_name}_trades.csv"
    summary_json = out_dir / f"{strategy_name}_summary.json"
    write_trades_csv(out, trades_csv)
    summary_json.write_text(json.dumps(s, indent=2))
    print(f"\n  Trade list : {trades_csv}")
    print(f"  Summary    : {summary_json}\n")


if __name__ == "__main__":
    main()
