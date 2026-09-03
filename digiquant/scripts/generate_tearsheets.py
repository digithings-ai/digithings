#!/usr/bin/env python3
"""Generate TradingView-faithful tearsheets via the NautilusTrader engine.

This is the digiquant flagship path for published strategies:

    Coinbase OHLCV cache
      → (SDCA: materialize risk-index parquet from this same frame)
      → NautilusTrader backtest
      → round-trip trades from the engine's positions report (Slapper)
      → TradingView-style percent-of-equity compounding equity curve
      → TearsheetData JSON in frontend/digiquant-web/public/strategies/

``settings.json`` ``strategy_type`` selects the family (``slapper`` default,
``sdca`` for ``btc_sdca``). Slapper calibrations stay in gitignored
``calibrations.json``; SDCA records the coefficients file + preset in notes
and does not use that gate.

Structural config (symbol, capital, sizing, trade window, precision) comes from
the PUBLIC ``strategies/settings.json``; indicator calibrations come from the
gitignored ``calibrations.json``. The trade window (``trade_start``) is enforced
inside Slapper (warmup bars, reported trades match TradingView). SDCA builds
the risk index on the full delayed cache, then feeds Nautilus only bars from
``trade_start`` so the spot cash book starts at ``initial_cash`` in that window.

Each strategy's backtest runs in its own spawned process: NautilusTrader's Rust
logging can only initialize once per process, so a second in-process
``BacktestEngine`` aborts the interpreter (#1389). Isolation also means one
crashing strategy cannot take down the rest — failures are collected and the
script exits non-zero if any strategy failed.

``--signal-delay-days N`` (#1462) lags the public view of every strategy by N
calendar days: the OHLCV frame is truncated so the run ends N days before the
freshest cached bar, and the whole tearsheet is generated from that shorter
series. End-date shift — not redaction — so the equity curve, drawdown, trade
log, open-position state, and headline metrics are self-consistent by
construction and none of them can leak the live position. Payloads declare the
lag via ``signal_delay_days``.

Usage:
    python scripts/generate_tearsheets.py
    python scripts/generate_tearsheets.py --strategy btc_sdca --cache-dir data/price-history
    python scripts/generate_tearsheets.py --signal-delay-days 3
    # Operator-only (not this environment): --push-supabase after a real run.
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import signal
import sys
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal
from multiprocessing.connection import Connection
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from digiquant.strategies.sdca.composite_risk import IndicatorWeight

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Repo root = scripts/.. /.. (this file lives at <repo>/digiquant/scripts/).
REPO_ROOT = Path(__file__).resolve().parents[2]
DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_STRATEGIES = REPO_ROOT / "frontend" / "digiquant-web" / "public" / "strategies"
DEFAULT_CACHE = REPO_ROOT / "data" / "price-history"
SETTINGS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "settings.json"
CALIBRATIONS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "calibrations.json"
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _env import load_repo_env  # noqa: E402

# Published tearsheet baselines (June 25 commit d0e59144). Warn when regen drifts.
_PUBLISHED_BASELINE: dict[str, dict[str, float | int]] = {
    "btc_slapper": {"trades": 79, "min_pf": 8.0},
    "eth_slapper": {"trades": 57, "min_pf": 6.0},
    "sol_slapper": {"trades": 46, "min_pf": 3.0},
}


def load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text())


def strategy_type_of(settings: dict, strategy: str) -> str:
    """Family selector (#3170). Missing field inherits defaults.strategy_type, then slapper."""
    entry = settings["strategies"][strategy]
    default = settings.get("defaults", {}).get("strategy_type", "slapper")
    return str(entry.get("strategy_type") or default or "slapper")


def catalog_row_from_settings(settings: dict, strategy: str) -> dict:
    """Public ``strategies`` registry row. Required FK parent of ``strategy_tearsheets``.

    Slapper rows were uploaded once via ``sync_strategy_calibrations.py``. SDCA has
    no private calibrations, so that script never inserted ``btc_sdca`` and the
    nightly upsert 409'd (#3453). Push must ensure this row first.
    """
    entry = settings["strategies"][strategy]
    defaults = settings.get("defaults", {})
    return {
        "id": strategy,
        "symbol": entry["symbol"],
        "label": entry.get("label", strategy),
        "engine": "nautilus",
        "config": {
            "kind": entry.get("kind", "long_short"),
            "strategy_type": strategy_type_of(settings, strategy),
            "trade_start": defaults.get("trade_start"),
            "initial_capital": defaults.get("initial_capital"),
            "size_pct_equity": defaults.get("size_pct_equity"),
        },
        "enabled": True,
    }


def materialize_sdca_risk_index(
    ohlcv: pl.DataFrame,
    output_path: Path,
    *,
    coefficients_path: Path | None = None,
    extra_indicators: list[IndicatorWeight] | None = None,
    valuation_weight: float = 1.0,
) -> pl.DataFrame:
    """Build the SDCA ``risk_path`` parquet from *this* OHLCV frame only (#1462).

    Callers must pass the already-``apply_signal_delay()``-truncated frame so
    the index cannot leak bars beyond the published window. Default
    ``valuation_weight=1`` and no extras matches the catalog model default.
    Published ``btc_sdca`` extras come from ``settings.json``.
    """
    import polars as pl

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.risk_index import build_risk_index, write_risk_index

    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    dates = ohlcv[ts_col]
    if dates.dtype != pl.Date:
        dates = dates.cast(pl.Date)
    model = BtcPowerLawRiskModel(load_coefficients(coefficients_path))
    index = build_risk_index(
        dates,
        ohlcv["close"],
        model,
        extra_indicators=extra_indicators,
        valuation_weight=valuation_weight,
    )
    write_risk_index(index, output_path)
    return index


def apply_signal_delay(ohlcv: pl.DataFrame, signal_delay_days: int) -> pl.DataFrame:
    """Truncate OHLCV so the run's end date lags the cached end by N calendar days.

    End-date shift (#1462): the public tearsheets are generated as if the run
    happened ``signal_delay_days`` days ago. Every derived artifact (equity
    curve, drawdown, trade log, open-position state, headline metrics) is then
    self-consistent by construction — there is no per-field redaction to get
    wrong. The cutoff is calendar days from the newest bar's timestamp, not a
    bar count, so gaps in the series still yield a true N-day lag.

    ``0`` is an exact no-op (the frame is returned unchanged); negative values
    would peek into the future and raise ``ValueError``.
    """
    import polars as pl

    if signal_delay_days < 0:
        raise ValueError(f"signal_delay_days must be >= 0, got {signal_delay_days}")
    if signal_delay_days == 0 or ohlcv.is_empty():
        return ohlcv
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    cutoff = ohlcv[ts_col].max() - timedelta(days=signal_delay_days)
    return ohlcv.filter(pl.col(ts_col) <= cutoff)


def window_ohlcv_to_trade_start(ohlcv: pl.DataFrame, trade_start: str) -> pl.DataFrame:
    """Drop bars before the published trade window.

    Risk-index construction keeps the full delayed cache (power-law rails need
    history). The Nautilus spot book starts at ``trade_start`` with
    ``initial_cash`` so lump/flat comparisons share that window.
    """
    import polars as pl

    if not trade_start or ohlcv.is_empty():
        return ohlcv
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    cutoff = date_cls.fromisoformat(trade_start)
    dtype = ohlcv[ts_col].dtype
    if dtype == pl.Date:
        return ohlcv.filter(pl.col(ts_col) >= cutoff)
    if dtype == pl.Datetime or isinstance(dtype, pl.Datetime):
        return ohlcv.filter(pl.col(ts_col).cast(pl.Date) >= cutoff)
    return ohlcv.filter(pl.col(ts_col).cast(pl.Utf8).str.slice(0, 10) >= trade_start)


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


def run_nautilus(
    strategy: str, symbol: str, ohlcv, settings: dict, calibration: dict | None = None
):
    """Run the Nautilus backtest; return (positions, bars_list, ohlc_bars, signal_log, fills_report).

    ``bars_list`` is [(date_str, close_float), ...] for the mark-to-market curve.
    ``ohlc_bars`` is [(date_str, o, h, l, c), ...] for the candlestick chart.
    ``signal_log`` maps (entry_date, direction) -> signal type recorded by the
    strategy on entry ("mean_reversion"/"trend"/"trend+mr"/"reversal"); may be
    empty for strategies that do not populate ``_signal_log``.
    ``fills_report`` is ``trader.generate_fills_report()`` (pandas, Nautilus
    boundary) so the SDCA publish path can derive schema 1.3 metrics from
    fills rather than ``SdcaBacktestReport``.
    """
    from datetime import datetime, timezone

    import nautilus_trader.model.identifiers as ids
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.model import BarType, Venue
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import Bar
    from nautilus_trader.model.enums import AccountType, OmsType
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.instruments import CryptoPerpetual, CurrencyPair
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    from digiquant.strategies import get_strategy
    from digiquant.strategies.registry import config_declares_field

    d = settings["defaults"]
    family = strategy_type_of(settings, strategy)
    venue_name = "SIM"
    base_ccy = symbol.split("-")[0]
    quote_ccy = Currency.from_str(str(d.get("quote_currency", "USD")))

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
    price_inc = Price.from_str(f"{10**-price_prec:.{price_prec}f}")
    size_inc = Quantity.from_str(f"{10**-size_prec:.{size_prec}f}")
    inst_id = InstrumentId.from_str(f"{symbol}.{venue_name}")
    raw_symbol = ids.Symbol(symbol)
    if family == "sdca":
        # Spot cash book: buy remaining cash / sell remaining holdings.
        # Slapper keeps the margin perpetual venue unchanged.
        inst = CurrencyPair(
            instrument_id=inst_id,
            raw_symbol=raw_symbol,
            base_currency=Currency.from_str(base_ccy),
            quote_currency=quote_ccy,
            price_precision=price_prec,
            size_precision=size_prec,
            price_increment=price_inc,
            size_increment=size_inc,
            lot_size=None,
            max_quantity=None,
            min_quantity=size_inc,
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
        account_type = AccountType.CASH
        venue_base = None
        start_money = Money(d["initial_capital"], quote_ccy)
    else:
        inst = CryptoPerpetual(
            instrument_id=inst_id,
            raw_symbol=raw_symbol,
            base_currency=Currency.from_str(base_ccy),
            quote_currency=USD,
            settlement_currency=USD,
            is_inverse=False,
            price_precision=price_prec,
            size_precision=size_prec,
            price_increment=price_inc,
            size_increment=size_inc,
            max_quantity=None,
            min_quantity=size_inc,
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
        account_type = AccountType.MARGIN
        venue_base = USD
        start_money = Money(d["initial_capital"], USD)
    bar_type = BarType.from_str(f"{symbol}.{venue_name}-{d.get('bar_spec', '1-DAY-LAST')}-EXTERNAL")

    def _epoch_ns(value) -> int:
        # Polars Date -> midnight-UTC ns (matches the previous BarDataWrangler index).
        dt = (
            value
            if isinstance(value, datetime)
            else datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)

    # Build Nautilus bars directly from the Polars frame — digiquant is Polars-only,
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
        account_type=account_type,
        base_currency=venue_base,
        starting_balances=[start_money],
    )
    engine.add_instrument(inst)
    engine.add_data(bars)
    injected: dict[str, object] = {
        k: v
        for k, v in dict(calibration or {}).items()
        if config_declares_field(strategy, k)
    }
    if config_declares_field(strategy, "size_pct_equity"):
        injected.setdefault("size_pct_equity", float(d["size_pct_equity"]))
    trade_size = Decimal(1) if config_declares_field(strategy, "trade_size") else None
    strat, _ = get_strategy(
        strategy_name=strategy,
        instrument_id=inst.id,
        bar_type=bar_type,
        trade_size=trade_size,
        **injected,
    )
    engine.add_strategy(strat)
    engine.run()
    positions = engine.trader.generate_positions_report()
    fills_report = engine.trader.generate_fills_report()
    # Read the strategy's signal-type side-channel BEFORE dispose() tears it down.
    signal_log = dict(getattr(strat, "_signal_log", {}) or {})
    engine.dispose()
    return positions, bars_list, ohlc_bars, signal_log, fills_report


def trades_from_positions(positions) -> list[dict]:
    """Round-trip trades (chronological) from the Nautilus positions report.

    The Nautilus report is read row-wise; missing exits (NaT/NaN) are detected via
    self-inequality, avoiding non-Polars dataframe helpers in digiquant code.
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


def _sdca_tearsheet_from_nautilus(
    fills_report: object,
    bars_list: list[tuple[str, float]],
    initial_capital: float,
    *,
    calibration: dict | None,
    trade_start: str,
    risk_index: object | None = None,
) -> tuple[object, list[tuple[str, float]], list[dict], dict, dict]:
    """DCA metrics + MTM equity + #3168 diagnostic overlays from Nautilus fills.

    Published numbers come from fills, never ``SdcaBacktestReport``. Rails/risk
    come from the in-memory risk-index frame (diagnostic columns); the parquet
    written for ``SdcaStrategy`` is date/risk only.
    """
    import polars as pl

    from digiquant.strategies.sdca.chart_series import z_from_risk_index
    from digiquant.strategies.sdca.curve import AccumDistCurve
    from digiquant.strategies.sdca.dca_metrics import (
        breakdown_from_daily,
        daily_state_from_fills,
        dca_current_signal,
        fills_from_nautilus_report,
        tearsheet_overlays,
    )

    windowed = [(d, c) for d, c in bars_list if not trade_start or d >= trade_start]
    fills = fills_from_nautilus_report(fills_report)
    state = daily_state_from_fills(fills, windowed, initial_capital)

    risk_vals: list[float | None] = [None] * len(windowed)
    rate_vals: list[float | None] = [None] * len(windowed)
    rail_vals: list[tuple[float | None, float | None, float | None]] = [(None, None, None)] * len(
        windowed
    )

    risk_df = None
    if risk_index is not None and hasattr(risk_index, "columns"):
        risk_df = risk_index
    else:
        risk_path = (calibration or {}).get("risk_path")
        if risk_path:
            risk_df = pl.read_parquet(risk_path)

    nodes = (calibration or {}).get("curve_nodes")
    indicator_z: dict = {}
    if risk_df is not None and nodes is not None:
        by_date: dict[str, tuple[float | None, float | None, float | None, float | None]] = {}
        dates = [str(d)[:10] for d in risk_df["date"].to_list()]
        risks = risk_df["risk"].to_list()
        has_rails = all(c in risk_df.columns for c in ("low", "median", "high"))
        lows = risk_df["low"].to_list() if has_rails else [None] * len(dates)
        medians = risk_df["median"].to_list() if has_rails else [None] * len(dates)
        highs = risk_df["high"].to_list() if has_rails else [None] * len(dates)
        for day, r, lo, med, hi in zip(dates, risks, lows, medians, highs, strict=True):
            by_date[day] = (
                None if r is None else float(r),
                None if lo is None else float(lo),
                None if med is None else float(med),
                None if hi is None else float(hi),
            )
        z_cols = z_from_risk_index(risk_df)
        z_by_date: dict[str, dict[str, float | None]] = {d: {} for d in dates}
        for name, values in z_cols.items():
            for day, z in zip(dates, values, strict=True):
                z_by_date[day][name] = z
        curve = AccumDistCurve(tuple(float(n) for n in nodes))
        for i, (day, _close) in enumerate(windowed):
            packed = by_date.get(day)
            if packed is None:
                continue
            r, lo, med, hi = packed
            risk_vals[i] = r
            rail_vals[i] = (lo, med, hi)
            rate_vals[i] = None if r is None else curve.value_at_risk(r)
        window_dates = [d for d, _c in windowed]
        for name in z_cols:
            indicator_z[name] = [z_by_date.get(d, {}).get(name) for d in window_dates]

    dca = breakdown_from_daily(
        prices=state["prices"],
        portfolio_values=state["portfolio_values"],
        daily_trade_usd=state["daily_trade_usd"],
        net_deployed=state["net_deployed"],
        asset_units=state["asset_units"],
        risk=risk_vals,
        rate=rate_vals,
        initial_cash=initial_capital,
    )
    equity_curve = [(d, v) for (d, _c), v in zip(windowed, state["portfolio_values"], strict=True)]
    overlays = tearsheet_overlays(
        dates=[d for d, _c in windowed],
        prices=state["prices"],
        daily_trade_usd=state["daily_trade_usd"],
        net_deployed=state["net_deployed"],
        initial_cash=initial_capital,
        rails=rail_vals,
        risk=risk_vals,
        asset_units=state["asset_units"],
        indicator_z=indicator_z or None,
        weights=(calibration or {}).get("indicator_weights"),
        preset_name=(calibration or {}).get("preset"),
    )
    last_date = windowed[-1][0] if windowed else ""
    last_price = windowed[-1][1] if windowed else None
    signal = dca_current_signal(
        last_date=last_date,
        last_price=last_price,
        last_risk=risk_vals[-1] if risk_vals else None,
        last_rate=rate_vals[-1] if rate_vals else None,
        units_accumulated=dca.units_accumulated,
    )
    return dca, equity_curve, [], overlays, signal


def run_and_write(
    strategy: str,
    symbol: str,
    settings: dict,
    cache_dir: Path,
    output_dir: Path,
    *,
    cal_source: str,
    push_supabase: bool = False,
    signal_delay_days: int = 0,
) -> dict | None:
    from digiquant.data.prices.history_cache import load_cached
    from digiquant.strategies.calibrations_loader import resolve_calibrations
    from digiquant.tearsheet_data import from_nautilus_run

    ohlcv = load_cached(symbol, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        logger.error("No data for %s in %s", symbol, cache_dir)
        return None
    # Public signal delay (#1462): shift the whole run's end date back, so all
    # published artifacts describe the same (lagged) point in time.
    ohlcv = apply_signal_delay(ohlcv, signal_delay_days)
    if ohlcv.is_empty():
        logger.error(
            "No data left for %s after applying %d-day signal delay", symbol, signal_delay_days
        )
        return None

    d = settings["defaults"]
    initial_capital = float(d["initial_capital"])
    trade_start = d.get("trade_start") or ""
    family = strategy_type_of(settings, strategy)
    entry = settings["strategies"][strategy]

    calibration: dict | None = None
    provenance_notes: list[str] = []
    sdca_index = None
    beats_flat_dca_oos: bool | None = None
    if family == "slapper":
        calibration = resolve_calibrations(
            strategy,
            source=cal_source,  # type: ignore[arg-type]
            trade_start=trade_start or None,
        )
        cal_label = cal_source
    else:
        cal_label = "n/a"

    if family == "sdca":
        import tempfile

        import polars as pl

        from digiquant.strategies.sdca.btc_power_law import load_coefficients
        from digiquant.strategies.sdca.indicator_catalog import (
            SdcaCompositeWeights,
            build_extra_indicators,
            indicator_display_name,
        )
        from digiquant.strategies.sdca.presets import load_preset

        sdca_cfg = entry.get("sdca") or {}
        preset_name = str(sdca_cfg.get("preset") or "balanced")
        preset = load_preset(preset_name)
        tmp_risk = Path(tempfile.mkdtemp(prefix="sdca_risk_")) / "risk.parquet"
        raw_w = sdca_cfg.get("indicator_weights") or {}
        published_weights = SdcaCompositeWeights(
            valuation=float(raw_w.get("valuation", 1.0)),
            m2=float(raw_w.get("m2", 0.0)),
            rs_eth=float(raw_w.get("rs_eth", 0.0)),
            dxy=float(raw_w.get("dxy", 0.0)),
            weekly_rsi=float(raw_w.get("weekly_rsi", 0.0)),
            weekly_macd=float(raw_w.get("weekly_macd", 0.0)),
            sma_band=float(raw_w.get("sma_band", 0.0)),
        )
        ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
        idx_dates = ohlcv[ts_col]
        if idx_dates.dtype != pl.Date:
            idx_dates = idx_dates.cast(pl.Date)
        from digiquant.strategies.sdca.optimize import (
            drop_extras_missing_sources,
            load_btc_optimized_provenance,
            load_sdca_extra_sources,
        )

        sources = load_sdca_extra_sources(cache_dir)
        weights = drop_extras_missing_sources(published_weights, sources)
        dropped_this_run = [
            name
            for name in ("m2", "dxy", "rs_eth")
            if getattr(published_weights, name) > 0.0 and getattr(weights, name) == 0.0
        ]
        try:
            load_btc_optimized_provenance()
        except Exception:
            pass
        # Public payload never claims an OOS beat (Stage 1 curve_simulator sidecar
        # is not a Nautilus walk-forward result).
        beats_flat_dca_oos = False
        extras = build_extra_indicators(idx_dates, ohlcv["close"], weights, sources)
        index = materialize_sdca_risk_index(
            ohlcv,
            tmp_risk,
            extra_indicators=extras or None,
            valuation_weight=weights.valuation,
        )
        sdca_index = index
        coefficients = load_coefficients()
        calibration = {
            "risk_path": str(tmp_risk),
            "curve_nodes": preset.curve_nodes,
            "long_only": bool(sdca_cfg.get("long_only", preset.long_only)),
            "initial_cash": float(sdca_cfg.get("initial_cash", initial_capital)),
            "preset": preset_name,
            "indicator_weights": weights.model_dump(),
        }
        extra_weights = (
            published_weights.m2,
            published_weights.rs_eth,
            published_weights.dxy,
            published_weights.weekly_rsi,
            published_weights.weekly_macd,
            published_weights.sma_band,
        )
        extras_unused = all(w == 0.0 for w in extra_weights)
        provenance_notes.append(
            "SDCA risk index built from the signal-delayed OHLCV frame "
            f"{index['date'].min()} → {index['date'].max()} "
            f"({index.height} rows, risk_model={sdca_cfg.get('risk_model', 'btc_power_law')}, "
            f"weights=valuation:{weights.valuation}/m2:{weights.m2}/"
            f"rs_eth:{weights.rs_eth}/dxy:{weights.dxy}/"
            f"weekly_rsi:{weights.weekly_rsi}/weekly_macd:{weights.weekly_macd}/"
            f"sma_band:{weights.sma_band})."
        )
        if extras_unused:
            provenance_notes.append(
                "Published index is power-law only (valuation weight 1.0). Extra "
                "indicators (M2, DXY, weekly RSI/MACD, SMA band, BTC/ETH RS) are "
                "unused (weight 0) — not a multi-indicator composite."
            )
        else:
            keepers = [
                f"{indicator_display_name(name)} {weight:g}"
                for name, weight in published_weights.model_dump().items()
                if weight > 0.0
            ]
            unused = [
                indicator_display_name(name)
                for name, weight in published_weights.model_dump().items()
                if name != "valuation" and weight == 0.0
            ]
            note = "Published index is a composite valuation index (" + " + ".join(keepers) + ")."
            if unused:
                note += " Unused (weight 0): " + ", ".join(unused) + "."
            provenance_notes.append(note)
        if dropped_this_run:
            provenance_notes.append(
                "This run omitted "
                + ", ".join(dropped_this_run)
                + " (missing source series)."
            )
        provenance_notes.append(
            f"Coefficients {coefficients.fit_start} → {coefficients.fit_end} "
            f"({coefficients.fit_rows} rows). Preset {preset_name}."
        )
        provenance_notes.append(
            "Nautilus venue: spot CurrencyPair + CASH (remaining cash / remaining "
            "holdings). Engine bars from trade_start; risk index uses the full "
            "delayed cache. Remaining-book sizing. Not a long/short book; "
            "not broker live-trading; backtest only."
        )

    engine_ohlcv = ohlcv
    if family == "sdca":
        engine_ohlcv = window_ohlcv_to_trade_start(ohlcv, trade_start)
        if engine_ohlcv.is_empty():
            logger.error(
                "No bars left for %s after trade_start=%s",
                symbol,
                trade_start,
            )
            return None

    logger.info(
        "Running Nautilus backtest: %s (%s, %d bars, cal=%s, signal_delay=%dd)",
        strategy,
        symbol,
        len(engine_ohlcv),
        cal_label,
        signal_delay_days,
    )
    positions, bars_list, ohlc_bars, signal_log, fills_report = run_nautilus(
        strategy, symbol, engine_ohlcv, settings, calibration=calibration
    )
    if family == "sdca":
        # DCA is remaining-cash / remaining-holdings, not round-trip legs.
        # An open spot book leaves pandas NA on ts_closed; skip the slapper parser.
        trades = []
    else:
        trades = trades_from_positions(positions)
        trades = carry_open_at_period_end(trades, bars_list, trade_start)

    dca_block = None
    sdca_overlays: dict = {}
    sdca_signal: dict | None = None
    if family == "sdca":
        dca_block, equity_curve, closed, sdca_overlays, sdca_signal = _sdca_tearsheet_from_nautilus(
            fills_report,
            bars_list,
            initial_capital,
            calibration=calibration,
            trade_start=trade_start,
            risk_index=sdca_index,
        )
    else:
        equity_curve, closed = build_equity_and_trades(
            trades, bars_list, initial_capital, trade_start
        )

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
    net_profit_pct = (
        (final_equity / initial_capital - 1.0) * 100.0
        if family == "sdca"
        else all_m["net_profit_pct"]
    )
    summary = {
        "strategy": strategy,
        "symbol": symbol,
        "period": period,
        "bars": len(window),
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "net_profit_pct": net_profit_pct,
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

    # Current signal: slapper uses the open round-trip. SDCA is not long/short —
    # today's risk, band, and remaining-book daily rate.
    if sdca_signal is not None:
        current_signal = sdca_signal
    else:
        open_leg = next((t for t in trade_dicts if t.get("exit_reason") == "open"), None)
        current_signal = {
            "position": open_leg["direction"] if open_leg else "flat",
            "entry_label": open_leg.get("entry_label", "") if open_leg else "",
            "last_signal_date": (
                open_leg["entry_date"] if open_leg else (window[-1][0] if window else "")
            ),
            "last_price": bars_list[-1][1] if bars_list else None,
        }

    if family == "sdca":
        notes = [
            f"NautilusTrader backtest, {settings['strategies'][strategy].get('label', strategy)}; "
            f"remaining-book SDCA from a composite valuation index "
            f"(buy % of remaining cash / sell % of remaining holdings), "
            f"marked to market (not 100% equity compounding), "
            f"trade window from {trade_start}. Backtest only — not a live strategy."
        ]
        notes.append(
            "Buy-and-hold (lump from trade_start) is the public benchmark. "
            "Full-sample Nautilus vs-flat is not shown as a public comparable. "
            f"beats_flat_dca_oos={'true' if beats_flat_dca_oos else 'false'}."
        )
    else:
        notes = [
            f"NautilusTrader backtest, {settings['strategies'][strategy].get('label', strategy)}; "
            f"100% equity compounding, trade window from {trade_start}."
        ]
    notes.extend(provenance_notes)
    if signal_delay_days:
        notes.append(
            f"Public signal delay: end date shifted back {signal_delay_days} days; "
            f"all figures are as of {window[-1][0] if window else ''}."
        )
    dca_kwargs: dict = {}
    if dca_block is not None:
        dca_kwargs = {
            "current_signal": current_signal,
            "rails": sdca_overlays.get("rails"),
            "risk_curve": sdca_overlays.get("risk_curve"),
            "cost_basis_curve": sdca_overlays.get("cost_basis_curve"),
            "capital_deployed_curve": sdca_overlays.get("capital_deployed_curve"),
            "lump_equity_curve": sdca_overlays.get("lump_equity_curve"),
            "flat_dca_equity_curve": sdca_overlays.get("flat_dca_equity_curve"),
            "allocated_pct_curve": sdca_overlays.get("allocated_pct_curve"),
            "fill_markers": sdca_overlays.get("fill_markers"),
            "indicator_curves": sdca_overlays.get("indicator_curves"),
            "indicator_weights": sdca_overlays.get("indicator_weights"),
            "curve_knees": sdca_overlays.get("curve_knees"),
            "label": entry.get("label"),
            "kind": entry.get("kind"),
            "beats_flat_dca_oos": beats_flat_dca_oos,
        }
    td = from_nautilus_run(
        summary,
        trade_dicts,
        equity_curve,
        data_source=d.get("data_source", "Coinbase daily OHLCV (CCXT)"),
        ohlc_bars=[b for b in ohlc_bars if not trade_start or b[0] >= trade_start],
        notes=notes,
        signal_delay_days=signal_delay_days,
        dca=dca_block,
        **dca_kwargs,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{strategy}.json"
    out_path.write_text(td.to_json())
    logger.info(
        "  Wrote %s | net %.0f%% | maxDD %.1f%% | PF %s | win %s | %d trades",
        out_path,
        td.net_profit_pct,
        td.max_drawdown_pct,
        f"{td.profit_factor:.2f}" if td.profit_factor is not None else "n/a",
        f"{td.win_rate_pct:.1f}%" if td.win_rate_pct is not None else "n/a",
        td.total_trades,
    )
    baseline = _PUBLISHED_BASELINE.get(strategy)
    if baseline is not None and dca_block is None:
        exp_trades = int(baseline["trades"])
        min_pf = float(baseline["min_pf"])
        pf = float(td.profit_factor or 0.0)
        if td.total_trades != exp_trades or pf < min_pf:
            logger.warning(
                "  Baseline drift for %s: got %d trades PF %.2f (expected %d trades, PF >= %.1f). "
                "Check calibrations.json / Supabase strategy_calibrations before publishing.",
                strategy,
                td.total_trades,
                pf,
                exp_trades,
                min_pf,
            )

    index_entry = {
        "strategy": td.strategy,
        "symbol": td.symbol,
        "engine": td.engine,
        "label": settings["strategies"][strategy].get("label", strategy),
        "kind": settings["strategies"][strategy].get("kind", "long_short"),
        "period_start": td.period_start,
        "period_end": td.period_end,
        "signal_delay_days": td.signal_delay_days,
        "net_profit_pct": td.net_profit_pct,
        "max_drawdown_pct": td.max_drawdown_pct,
        "profit_factor": td.profit_factor,
        "win_rate_pct": td.win_rate_pct,
        "avg_trade_pct": None if dca_block is not None else _avg_trade_pct(trade_dicts),
        "total_trades": td.total_trades,
        "generated_at": td.generated_at,
        "href": f"/strategies/{td.strategy}",
    }
    if dca_block is not None:
        index_entry["vs_lump_pct"] = dca_block.vs_lump_pct
        index_entry["vs_flat_dca_pct"] = dca_block.vs_flat_dca_pct
        index_entry["capital_deployed_pct"] = dca_block.capital_deployed_pct
        index_entry["allocated_pct"] = dca_block.allocated_pct
        index_entry["beats_flat_dca_oos"] = beats_flat_dca_oos

    if push_supabase:
        _push_tearsheet_to_supabase(strategy, td, equity_curve, current_signal, index_entry)

    return index_entry


def _push_tearsheet_to_supabase(
    strategy: str,
    td,
    equity_curve: list[tuple[str, float]],
    current_signal: dict,
    index_entry: dict,
) -> None:
    """Upsert the full tearsheet payload + current signal to Supabase (service role).

    The website reads ``strategy_tearsheets`` live, so the row must carry the
    whole payload digiquant.io renders — the full ``TearsheetData`` (metrics,
    equity/drawdown curves, OHLC bars, trades), plus the derived ``current_signal``
    and the index-level extras (label/kind/avg_trade) that live in settings, not
    ``TearsheetData``. The normalized ``strategy_signals`` row is refreshed too
    (service-role write) for any relational consumer.
    """
    from digiquant.data.store.client import build_digiquant_client
    from digiquant.data.store.strategies import upsert_signal, upsert_strategies, upsert_tearsheet

    client = build_digiquant_client()
    if client is None:
        logger.warning("Supabase push skipped — credentials missing")
        return

    settings = load_settings()
    upsert_strategies(client, [catalog_row_from_settings(settings, strategy)])

    payload = td.model_dump(mode="json")
    payload["current_signal"] = current_signal
    payload["label"] = index_entry["label"]
    payload["kind"] = index_entry["kind"]
    payload["avg_trade_pct"] = index_entry["avg_trade_pct"]
    if "vs_lump_pct" in index_entry:
        payload["vs_lump_pct"] = index_entry["vs_lump_pct"]
        payload["vs_flat_dca_pct"] = index_entry["vs_flat_dca_pct"]
        payload["capital_deployed_pct"] = index_entry["capital_deployed_pct"]
        if "allocated_pct" in index_entry:
            payload["allocated_pct"] = index_entry["allocated_pct"]
        if "beats_flat_dca_oos" in index_entry:
            payload["beats_flat_dca_oos"] = index_entry["beats_flat_dca_oos"]

    curve = [{"t": t, "v": v} for t, v in equity_curve]
    upsert_tearsheet(
        client,
        strategy_id=strategy,
        metrics=payload,
        as_of=td.generated_at,
        equity_curve=curve,
    )
    upsert_signal(
        client,
        strategy_id=strategy,
        position=current_signal["position"],
        as_of=td.generated_at,
        last_signal_date=current_signal["last_signal_date"] or None,
        last_price=current_signal["last_price"],
    )
    logger.info(
        "  Pushed tearsheet + %s signal → Supabase (%s)", current_signal["position"], strategy
    )


def _strategy_worker(
    conn: Connection,
    strategy: str,
    symbol: str,
    settings: dict,
    cache_dir: Path,
    output_dir: Path,
    cal_source: str,
    push_supabase: bool,
    signal_delay_days: int,
) -> None:
    """Child-process entry point: run one strategy end-to-end, report via ``conn``."""
    status: tuple[str, dict | str | None]
    try:
        entry = run_and_write(
            strategy,
            symbol,
            settings,
            cache_dir,
            output_dir,
            cal_source=cal_source,
            push_supabase=push_supabase,
            signal_delay_days=signal_delay_days,
        )
        if entry is not None:
            status = ("ok", entry)
        else:
            status = ("error", "no tearsheet produced (see logs above)")
    except Exception as exc:
        logger.exception("Tearsheet run failed for %s", strategy)
        status = ("error", f"{type(exc).__name__}: {exc}")
    try:
        conn.send(status)
    finally:
        conn.close()
    if status[0] != "ok":
        raise SystemExit(1)


def _describe_exitcode(exitcode: int | None) -> str:
    """Human-readable process exit description (signal-aware)."""
    if exitcode is None:
        return "unknown exit"
    if exitcode < 0:
        try:
            name = signal.Signals(-exitcode).name
        except ValueError:
            name = f"signal {-exitcode}"
        return f"killed by {name}"
    return f"exit code {exitcode}"


def _interpret_worker_result(
    result: tuple[str, dict | str | None] | None,
    exitcode: int | None,
) -> tuple[dict | None, str | None]:
    """Map a worker's pipe message + exit code to ``(index_entry, error)``."""
    if result is None:
        return None, f"backtest process died before reporting ({_describe_exitcode(exitcode)})"
    kind, payload = result
    if kind == "ok" and isinstance(payload, dict):
        return payload, None
    return None, str(payload)


def run_strategy_isolated(
    strategy: str,
    symbol: str,
    settings: dict,
    cache_dir: Path,
    output_dir: Path,
    *,
    cal_source: str,
    push_supabase: bool = False,
    signal_delay_days: int = 0,
) -> tuple[dict | None, str | None]:
    """Run one strategy's backtest in its own spawned process; return (entry, error).

    NautilusTrader's Rust logging can only initialize once per process
    (``log::set_boxed_logger``); a fresh in-process ``BacktestEngine`` per strategy
    panics on the second engine — "Failed to initialize logging: attempted to set a
    logger after the logging system was already initialized" — and SIGABRTs the
    whole run (#1389). A spawned process per strategy gives each engine a clean
    slate and contains any engine crash to that one strategy.
    """
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_strategy_worker,
        args=(
            child_conn,
            strategy,
            symbol,
            settings,
            cache_dir,
            output_dir,
            cal_source,
            push_supabase,
            signal_delay_days,
        ),
        name=f"tearsheet-{strategy}",
    )
    proc.start()
    child_conn.close()
    result: tuple[str, dict | str | None] | None = None
    try:
        result = parent_conn.recv()
    except EOFError:
        result = None
    finally:
        parent_conn.close()
    proc.join()
    return _interpret_worker_result(result, proc.exitcode)


def main() -> None:
    load_repo_env()
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
    parser.add_argument(
        "--signal-delay-days",
        type=int,
        default=0,
        help="Lag the public tearsheets by N calendar days: truncate OHLCV so the run "
        "ends N days before the freshest cached bar (end-date shift, #1462). Default 0.",
    )
    args = parser.parse_args()
    if args.signal_delay_days < 0:
        parser.error("--signal-delay-days must be >= 0")

    from digiquant.strategies.calibrations_loader import pick_calibration_source

    targets = {args.strategy: strategies[args.strategy]} if args.strategy else strategies
    slapper_targets = [name for name in targets if strategy_type_of(settings, name) == "slapper"]

    if args.from_supabase:
        cal_source = "supabase"
        from digiquant.strategies.calibrations_loader import load_calibrations_from_supabase

        if slapper_targets:
            load_calibrations_from_supabase(slapper_targets)
    elif slapper_targets:
        cal_source = pick_calibration_source(
            prefer_supabase=False,
            allow_example=args.allow_example_calibrations,
        )
    else:
        cal_source = "example"

    entries: list[dict] = []
    failures: list[tuple[str, str]] = []
    for strat, cfg in targets.items():
        entry, error = run_strategy_isolated(
            strat,
            cfg["symbol"],
            settings,
            args.cache_dir,
            args.output_dir,
            cal_source=cal_source,
            push_supabase=args.push_supabase,
            signal_delay_days=args.signal_delay_days,
        )
        if entry is not None:
            entries.append(entry)
        else:
            failures.append((strat, error or "unknown error"))
            logger.error("FAILED: %s — %s", strat, error)

    if entries:
        idx_path = args.output_dir / "index.json"
        merged = list(entries)
        if idx_path.exists() and (args.strategy or failures):
            # Partial run (single strategy, or some strategies failed): keep prior
            # index entries for strategies not refreshed here, so one failure does
            # not drop a live strategy card from digiquant.io.
            refreshed = {e["strategy"] for e in entries}
            prior = [e for e in json.loads(idx_path.read_text()) if e["strategy"] not in refreshed]
            merged = prior + entries
        idx_path.write_text(json.dumps(merged, indent=2))
        logger.info("Updated index.json (%d strategies)", len(merged))

    succeeded = {e["strategy"] for e in entries}
    logger.info("Done: %d/%d strategies succeeded.", len(succeeded), len(targets))
    for strat in targets:
        if strat in succeeded:
            logger.info("  OK      %s", strat)
        else:
            logger.error("  FAILED  %s: %s", strat, dict(failures).get(strat, "unknown error"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
