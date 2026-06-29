#!/usr/bin/env python3
"""Generate TradingView-faithful tearsheets via the NautilusTrader engine.

This is the DigiQuant flagship path for the Slapper family (BTC/ETH/SOL):

    Coinbase OHLCV cache
      → NautilusTrader backtest (digiquant.strategies.SlapperStrategy)
      → round-trip trades from the engine's positions report
      → TradingView-style percent-of-equity compounding equity curve
      → All / Long / Short performance summary
      → TearsheetData JSON in frontend/digiquant-web/public/strategies/

Structural config (symbol, capital, sizing, trade window, precision) comes from
the PUBLIC ``strategies/settings.json``; indicator calibrations come from the
gitignored ``calibrations.json``. The trade window (``trade_start``) is enforced
inside the strategy, so warmup uses earlier bars while reported trades match the
TradingView Strategy Tester window.

Usage:
    python scripts/generate_tearsheets.py
    python scripts/generate_tearsheets.py --strategy eth_slapper
    python scripts/generate_tearsheets.py --cache-dir digiquant/data/price-history
"""

from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Repo root = scripts/.. /.. (this file lives at <repo>/digiquant/scripts/).
REPO_ROOT = Path(__file__).resolve().parents[2]
DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_STRATEGIES = REPO_ROOT / "frontend" / "digiquant-web" / "public" / "strategies"
DEFAULT_CACHE = DIGIQUANT_ROOT / "data" / "price-history"
SETTINGS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "settings.json"
CALIBRATIONS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "calibrations.json"


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text())


def _mult(direction: str, entry_price: float, price: float) -> float:
    """Equity multiplier for a 100%-equity position marked at ``price``.

    Long: price/entry. Short: 1 + (entry - price)/entry. Matches TradingView's
    percent_of_equity=100 compounding.
    """
    if entry_price <= 0:
        return 1.0
    if direction == "long":
        return price / entry_price
    return 1.0 + (entry_price - price) / entry_price


# Signal-type → TradingView-style display label, mirroring the Pine validator's
# taxonomy (scripts/validation/pine_backtest.py: "MR Long"/"Trend Long"/"MR&T Long",
# "Reversal Long", + Short variants) so both engines emit the same entry_label strings.
_SIGNAL_LABELS = {
    ("mean_reversion", "long"): "MR Long",
    ("mean_reversion", "short"): "MR Short",
    ("trend", "long"): "Trend Long",
    ("trend", "short"): "Trend Short",
    ("trend+mr", "long"): "MR&T Long",
    ("trend+mr", "short"): "MR&T Short",
    ("reversal", "long"): "Reversal Long",
    ("reversal", "short"): "Reversal Short",
}


def _entry_label(signal_type: str | None, direction: str) -> str:
    """Map a recorded ``(signal_type, direction)`` to a Pine-style display label.

    Returns "" when the type is missing or unrecognized, so a join miss (e.g. the
    engine fills an entry on a different bar than the one the strategy recorded)
    degrades gracefully to a blank label instead of raising.
    """
    if not signal_type:
        return ""
    return _SIGNAL_LABELS.get((signal_type, direction), "")


def _dir_metrics(trades: list[dict], initial: float) -> dict:
    """All/Long/Short performance block from round-trip trades (pnl in quote ccy)."""
    if not trades:
        return {
            "trades": 0,
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "percent_profitable": 0.0,
            "profit_factor": None,
            "avg_trade": 0.0,
            "wins": 0,
            "losses": 0,
        }
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    net = sum(t["pnl"] for t in trades)
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


def _avg_trade_pct(trades: list[dict]) -> float:
    """Mean per-trade return (%%), matching frontend ``avgTradePct``."""
    if not trades:
        return 0.0
    return sum(t["pnl_pct"] for t in trades) / len(trades)


def run_nautilus(strategy: str, symbol: str, ohlcv, settings: dict, calibration: dict | None = None):
    """Run the Nautilus backtest; return (positions_report_df, bars_list, ohlc_bars, signal_log).

    ``bars_list`` is [(date_str, close_float), ...] for the mark-to-market curve.
    ``ohlc_bars`` is [(date_str, o, h, l, c), ...] for the candlestick chart.
    ``signal_log`` maps (entry_date, direction) -> signal type recorded by the
    strategy on entry ("mean_reversion"/"trend"/"trend+mr"/"reversal"); may be
    empty for strategies that do not populate ``_signal_log``.
    """
    from datetime import datetime, timezone

    import nautilus_trader.model.identifiers as ids
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.model import BarType, Venue
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import Bar
    from nautilus_trader.model.enums import AccountType, OmsType
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.instruments import CryptoPerpetual
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    from digiquant.strategies import get_strategy

    d = settings["defaults"]
    venue_name = "SIM"
    base_ccy = symbol.split("-")[0]

    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    ts_vals = ohlcv[ts_col].to_list()
    opens = ohlcv["open"].to_list()
    highs = ohlcv["high"].to_list()
    lows = ohlcv["low"].to_list()
    closes = ohlcv["close"].to_list()
    vols = ohlcv["volume"].to_list() if "volume" in ohlcv.columns else None
    bars_list = [(str(t)[:10], float(c)) for t, c in zip(ts_vals, closes)]
    # OHLC for the candlestick chart — clipped to the trade window (matches equity).
    ohlc_bars = [
        (str(t)[:10], float(o), float(h), float(low), float(c))
        for t, o, h, low, c in zip(ts_vals, opens, highs, lows, closes)
    ]

    price_prec = int(d.get("price_precision", 2))
    size_prec = int(d.get("size_precision", 8))
    inst = CryptoPerpetual(
        instrument_id=InstrumentId.from_str(f"{symbol}.{venue_name}"),
        raw_symbol=ids.Symbol(symbol),
        base_currency=Currency.from_str(base_ccy),
        quote_currency=USD,
        settlement_currency=USD,
        is_inverse=False,
        price_precision=price_prec,
        size_precision=size_prec,
        price_increment=Price.from_str(f"{10**-price_prec:.{price_prec}f}"),
        size_increment=Quantity.from_str(f"{10**-size_prec:.{size_prec}f}"),
        max_quantity=None,
        min_quantity=Quantity.from_str(f"{10**-size_prec:.{size_prec}f}"),
        max_notional=None,
        min_notional=None,
        max_price=None,
        min_price=None,
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )
    bar_type = BarType.from_str(f"{symbol}.{venue_name}-{d.get('bar_spec', '1-DAY-LAST')}-EXTERNAL")

    def _epoch_ns(value) -> int:
        # Polars Date -> midnight-UTC ns (matches the previous BarDataWrangler index).
        dt = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)

    # Build Nautilus bars directly from the Polars frame — DigiQuant is Polars-only,
    # so OHLCV is not routed through the DataFrame-wrangler ingestion path.
    bars = []
    for i, t in enumerate(ts_vals):
        ts = _epoch_ns(t)
        vol = vols[i] if vols is not None and vols[i] is not None else 1_000_000.0
        bars.append(
            Bar(
                bar_type,
                inst.make_price(opens[i]),
                inst.make_price(highs[i]),
                inst.make_price(lows[i]),
                inst.make_price(closes[i]),
                inst.make_qty(vol),
                ts,
                ts,
            )
        )
    if not bars:
        raise RuntimeError(f"No bars produced for {symbol}")

    engine = BacktestEngine()
    engine.add_venue(
        venue=Venue(venue_name),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(d["initial_capital"], USD)],
    )
    engine.add_instrument(inst)
    engine.add_data(bars)
    strat, _ = get_strategy(
        strategy_name=strategy,
        instrument_id=inst.id,
        bar_type=bar_type,
        trade_size=Decimal(1),
        size_pct_equity=float(d["size_pct_equity"]),
        **(calibration or {}),
    )
    engine.add_strategy(strat)
    engine.run()
    positions = engine.trader.generate_positions_report()
    # Read the strategy's signal-type side-channel BEFORE dispose() tears it down.
    signal_log = dict(getattr(strat, "_signal_log", {}) or {})
    engine.dispose()
    return positions, bars_list, ohlc_bars, signal_log


def trades_from_positions(positions) -> list[dict]:
    """Round-trip trades (chronological) from the Nautilus positions report.

    The Nautilus report is read row-wise; missing exits (NaT/NaN) are detected via
    self-inequality, avoiding non-Polars dataframe helpers in DigiQuant code.
    """

    def _missing(x) -> bool:
        return x is None or x != x  # NaN/NaT compare unequal to themselves

    rows = []
    for _, r in positions.iterrows():
        entry = str(r.get("entry", "")).upper()
        direction = "long" if "BUY" in entry else "short"
        ts_close = r.get("ts_closed")
        avg_close = r.get("avg_px_close")
        rows.append(
            {
                "direction": direction,
                "entry_date": str(r.get("ts_opened"))[:10],
                "entry_price": float(r.get("avg_px_open") or 0.0),
                "exit_date": "" if _missing(ts_close) else str(ts_close)[:10],
                "exit_price": None if _missing(avg_close) else float(avg_close),
            }
        )
    rows.sort(key=lambda t: t["entry_date"])
    return rows


def carry_open_at_period_end(
    trades: list[dict],
    bars_list: list[tuple[str, float]],
    trade_start: str,
) -> list[dict]:
    """Always-in-market: a close on the final bar is live MTM, not a flat book.

    Nautilus may record ``ts_closed`` on the last daily bar when the backtest ends
  while still positioned. For tearsheet / digiquant.io we keep that leg open so
    the current-position banner matches TradingView's open trade at series end.
    """
    if not trades or not bars_list:
        return trades
    windowed = [(d, c) for d, c in bars_list if not trade_start or d >= trade_start]
    if not windowed:
        return trades
    last_bar_date = windowed[-1][0]
    out = [dict(t) for t in trades]
    last = out[-1]
    if last.get("exit_date") == last_bar_date:
        last["exit_date"] = ""
        last["exit_price"] = None
    return out


def build_equity_and_trades(
    trades: list[dict], bars_list, initial_capital: float, trade_start: str
):
    """Walk bars to build a TV-style MTM equity curve and per-trade PnL.

    Equity compounds at 100% per position (bankruptcy-floored at 0), matching the
    TradingView Strategy Tester. Reversals (exit and re-entry on the same bar) are
    handled by realizing the exit before opening the next position.
    """
    entries = {t["entry_date"]: t for t in trades}

    equity = initial_capital
    pos = None  # {"direction","entry_price","entry_equity","trade"}
    equity_curve: list[tuple[str, float]] = []
    closed: list[dict] = []

    for date, close in bars_list:
        if trade_start and date < trade_start:
            continue
        # Exit (realize) first so a reversal can re-enter on the same bar.
        if pos is not None and date == pos["trade"]["exit_date"]:
            ep = pos["trade"]["exit_price"] if pos["trade"]["exit_price"] is not None else close
            equity = max(pos["entry_equity"] * _mult(pos["direction"], pos["entry_price"], ep), 0.0)
            t = pos["trade"]
            closed.append(
                {
                    **t,
                    "exit_price": ep,
                    "pnl": equity - pos["entry_equity"],
                    "pnl_pct": (equity / pos["entry_equity"] - 1) * 100
                    if pos["entry_equity"]
                    else 0.0,
                    "equity_after": equity,
                }
            )
            pos = None
        if pos is None and date in entries:
            t = entries[date]
            pos = {
                "direction": t["direction"],
                "entry_price": t["entry_price"],
                "entry_equity": equity,
                "trade": t,
            }
        mtm = (
            pos["entry_equity"] * _mult(pos["direction"], pos["entry_price"], close)
            if pos
            else equity
        )
        equity_curve.append((date, max(mtm, 0.0)))

    # Open position at the end → unrealized, listed like TradingView's open trade.
    if pos is not None:
        last_close = bars_list[-1][1]
        eq = max(pos["entry_equity"] * _mult(pos["direction"], pos["entry_price"], last_close), 0.0)
        t = pos["trade"]
        closed.append(
            {
                **t,
                "exit_date": "",
                "exit_price": last_close,
                "pnl": eq - pos["entry_equity"],
                "pnl_pct": (eq / pos["entry_equity"] - 1) * 100 if pos["entry_equity"] else 0.0,
                "equity_after": eq,
                "exit_reason": "open",
            }
        )
    return equity_curve, closed


def run_and_write(
    strategy: str,
    symbol: str,
    settings: dict,
    cache_dir: Path,
    output_dir: Path,
    *,
    cal_source: str,
    push_supabase: bool = False,
) -> dict | None:
    from digiquant.data.prices.history_cache import load_cached
    from digiquant.strategies.calibrations_loader import resolve_calibrations
    from digiquant.tearsheet_data import from_nautilus_run

    ohlcv = load_cached(symbol, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        logger.error("No data for %s in %s", symbol, cache_dir)
        return None

    d = settings["defaults"]
    initial_capital = float(d["initial_capital"])
    trade_start = d.get("trade_start") or ""

    calibration = resolve_calibrations(
        strategy,
        source=cal_source,  # type: ignore[arg-type]
        trade_start=trade_start or None,
    )
    logger.info("Running Nautilus backtest: %s (%s, %d bars, cal=%s)", strategy, symbol, len(ohlcv), cal_source)
    positions, bars_list, ohlc_bars, signal_log = run_nautilus(
        strategy, symbol, ohlcv, settings, calibration=calibration
    )
    trades = trades_from_positions(positions)
    trades = carry_open_at_period_end(trades, bars_list, trade_start)
    equity_curve, closed = build_equity_and_trades(trades, bars_list, initial_capital, trade_start)

    longs = [t for t in closed if t["direction"] == "long"]
    shorts = [t for t in closed if t["direction"] == "short"]
    all_m = _dir_metrics(closed, initial_capital)
    final_equity = equity_curve[-1][1] if equity_curve else initial_capital

    # Max drawdown from the MTM curve (includes open-trade drawdown, like TV).
    peak, max_dd = initial_capital, 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = min(max_dd, (eq - peak) / peak * 100.0)

    window = [t for t in equity_curve]
    period = f"{window[0][0]} → {window[-1][0]}" if window else ""
    summary = {
        "strategy": strategy,
        "symbol": symbol,
        "period": period,
        "bars": len(window),
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "net_profit_pct": all_m["net_profit_pct"],
        "max_drawdown_pct": max_dd,
        "all": all_m,
        "long": _dir_metrics(longs, initial_capital),
        "short": _dir_metrics(shorts, initial_capital),
    }
    # entry_label carries the per-trade signal type (MR/Trend/MR&T/Reversal),
    # joined on (entry_date, direction) from the strategy's signal log. Misses
    # (e.g. a fill recorded on a different bar) fall back to "".
    trade_dicts = [
        {
            **t,
            "entry_label": _entry_label(
                signal_log.get((t["entry_date"], t["direction"])), t["direction"]
            ),
        }
        for t in closed
    ]

    td = from_nautilus_run(
        summary,
        trade_dicts,
        equity_curve,
        data_source=d.get("data_source", "Coinbase daily OHLCV (CCXT)"),
        ohlc_bars=[b for b in ohlc_bars if not trade_start or b[0] >= trade_start],
        notes=[
            f"NautilusTrader backtest, {settings['strategies'][strategy].get('label', strategy)}; "
            f"100% equity compounding, trade window from {trade_start}."
        ],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{strategy}.json"
    out_path.write_text(td.to_json())
    logger.info(
        "  Wrote %s | net %.0f%% | maxDD %.1f%% | PF %.2f | win %.1f%% | %d trades",
        out_path,
        td.net_profit_pct,
        td.max_drawdown_pct,
        td.profit_factor or 0.0,
        td.win_rate_pct,
        td.total_trades,
    )

    if push_supabase:
        _push_tearsheet_to_supabase(strategy, td, equity_curve)

    return {
        "strategy": td.strategy,
        "symbol": td.symbol,
        "engine": td.engine,
        "label": settings["strategies"][strategy].get("label", strategy),
        "kind": settings["strategies"][strategy].get("kind", "long_short"),
        "period_start": td.period_start,
        "period_end": td.period_end,
        "net_profit_pct": td.net_profit_pct,
        "max_drawdown_pct": td.max_drawdown_pct,
        "profit_factor": td.profit_factor,
        "win_rate_pct": td.win_rate_pct,
        "avg_trade_pct": _avg_trade_pct(trade_dicts),
        "total_trades": td.total_trades,
        "generated_at": td.generated_at,
        "href": f"/strategies/{td.strategy}",
    }


def _push_tearsheet_to_supabase(strategy: str, td, equity_curve: list[tuple[str, float]]) -> None:
    """Upsert headline metrics + equity curve to strategy_tearsheets (service role)."""
    from digiquant.data.store.client import build_digiquant_client
    from digiquant.data.store.strategies import upsert_tearsheet

    client = build_digiquant_client()
    if client is None:
        logger.warning("Supabase push skipped — credentials missing")
        return
    metrics = {
        "net_profit_pct": td.net_profit_pct,
        "max_drawdown_pct": td.max_drawdown_pct,
        "profit_factor": td.profit_factor,
        "win_rate_pct": td.win_rate_pct,
        "total_trades": td.total_trades,
        "period_start": td.period_start,
        "period_end": td.period_end,
        "final_equity": td.final_equity,
        "generated_at": td.generated_at,
    }
    curve = [{"t": t, "v": v} for t, v in equity_curve]
    upsert_tearsheet(
        client,
        strategy_id=strategy,
        metrics=metrics,
        as_of=td.generated_at,
        equity_curve=curve,
    )
    logger.info("  Pushed tearsheet summary → strategy_tearsheets (%s)", strategy)


def main() -> None:
    settings = load_settings()
    strategies = settings["strategies"]
    parser = argparse.ArgumentParser(
        description="Generate Nautilus tearsheet JSONs for digiquant.io"
    )
    parser.add_argument("--strategy", choices=list(strategies.keys()), help="Run a single strategy")
    parser.add_argument(
        "--cache-dir", type=Path, default=DEFAULT_CACHE, help="OHLCV cache directory"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=FRONTEND_STRATEGIES, help="Output directory"
    )
    parser.add_argument(
        "--allow-example-calibrations",
        action="store_true",
        help="Permit running without calibrations.json (uses calibrations.example.json — NOT production parity)",
    )
    parser.add_argument(
        "--from-supabase",
        action="store_true",
        help="Load calibrations from strategy_calibrations (overrides local file)",
    )
    parser.add_argument(
        "--push-supabase",
        action="store_true",
        help="Upsert headline metrics to strategy_tearsheets after each run",
    )
    args = parser.parse_args()

    from digiquant.strategies.calibrations_loader import pick_calibration_source

    if args.from_supabase:
        cal_source = "supabase"
        # Validate early
        from digiquant.strategies.calibrations_loader import load_calibrations_from_supabase

        load_calibrations_from_supabase()
    else:
        cal_source = pick_calibration_source(
            prefer_supabase=False,
            allow_example=args.allow_example_calibrations,
        )

    targets = {args.strategy: strategies[args.strategy]} if args.strategy else strategies

    entries = []
    for strat, cfg in targets.items():
        entry = run_and_write(
            strat,
            cfg["symbol"],
            settings,
            args.cache_dir,
            args.output_dir,
            cal_source=cal_source,
            push_supabase=args.push_supabase,
        )
        if entry:
            entries.append(entry)
        else:
            logger.error("FAILED: %s", strat)

    if entries:
        idx_path = args.output_dir / "index.json"
        if args.strategy and idx_path.exists():
            existing = [
                e for e in json.loads(idx_path.read_text()) if e["strategy"] != args.strategy
            ]
            entries = existing + entries
        idx_path.write_text(json.dumps(entries, indent=2))
        logger.info("Updated index.json (%d strategies)", len(entries))
    logger.info("Done.")


if __name__ == "__main__":
    main()
