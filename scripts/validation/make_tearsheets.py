"""Generate TradingView-style tear sheets for the Slapper family.

Runs the Pine-faithful backtester for each strategy on its matching daily Binance
data, writes a per-trade CSV (to diff against TradingView's List of Trades), and
emits a single markdown tear sheet laid out like the TradingView Strategy Tester
Performance Summary (All / Long / Short).

    python scripts/validation/make_tearsheets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pine_backtest import run_backtest, summarize, write_trades_csv  # noqa: E402

DATA_DIR = Path("digiquant/data/validation")
OUT_DIR = Path("digiquant/results/validation")

STRATEGIES = [
    ("btc_slapper", "BTC-USD_1d.csv"),
    ("eth_slapper", "ETH-USD_1d.csv"),
    ("sol_slapper", "SOL-USD_1d.csv"),
]


def _money(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.2f}"


def _pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.2f}%"


def _summary_table(s: dict) -> str:
    """TradingView-style All/Long/Short table."""
    a, lo, sh = s["all"], s["long"], s["short"]

    def row(label: str, key: str, fmt) -> str:
        return f"| {label} | {fmt(a[key])} | {fmt(lo[key])} | {fmt(sh[key])} |"

    lines = [
        "| Metric | All | Long | Short |",
        "|--------|----:|-----:|------:|",
        f"| Closed trades | {a['trades']} | {lo['trades']} | {sh['trades']} |",
        row("Net profit", "net_profit", _money),
        row("Net profit %", "net_profit_pct", _pct),
        row("Gross profit", "gross_profit", _money),
        row("Gross loss", "gross_loss", _money),
        row("Percent profitable", "percent_profitable", _pct),
        row("Profit factor", "profit_factor", lambda v: _money(v) if v is not None else "n/a"),
        row("Avg trade", "avg_trade", _money),
    ]
    return "\n".join(lines)


def _strategy_section(s: dict) -> str:
    reversal = "yes" if s["strategy"] == "btc_slapper" else "no"
    return f"""## {s['strategy']}  ·  {s['symbol']}

- **Period:** {s['period']}  ({s['bars']} daily bars)
- **Initial capital:** {_money(s['initial_capital'])}  →  **Final equity:** {_money(s['final_equity'])}
- **Net profit:** {_pct(s['net_profit_pct'])}
- **Max drawdown (mark-to-market):** {_pct(s['max_drawdown_pct'])}
- **Reversal stop:** {reversal}

{_summary_table(s)}

Per-trade list: `{OUT_DIR}/{s['strategy']}_trades.csv` — diff against TradingView's List of Trades (entry/exit date, direction, price, P&L).
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name, data_file in STRATEGIES:
        out = run_backtest(name, DATA_DIR / data_file)
        write_trades_csv(out, OUT_DIR / f"{name}_trades.csv")
        s = summarize(out)
        summaries.append(s)

    header = """# Slapper Family — TradingView 1:1 Validation Tear Sheet

**Purpose:** validate the Python conversion against the TradingView Strategy Tester.
Compare the All/Long/Short tables and the per-trade CSVs below against your
TradingView results for each strategy.

## Methodology (what this matches, and what to check)

- **Data:** daily OHLCV from **Binance** (`BTCUSDT`/`ETHUSDT`/`SOLUSDT`), fetched via
  the public klines API. ⚠️ If your TradingView chart used a different feed
  (e.g. INDEX, BNC:BLX, Coinbase), candles — and therefore signals — will differ.
- **Execution model (Pine-faithful):** fills at the **signal bar's close**
  (`process_orders_on_close=true`), **100% of equity per entry, compounding**
  (`percent_of_equity=100`), **no pyramiding**, reversal via close-then-open,
  `initial_capital=1000`, 1-tick adverse slippage.
- **Indicators & parameters:** the SAME validated indicator classes and registered
  parameters as the production NautilusTrader strategies — only the fill model is
  re-expressed here.
- **Drawdown:** computed on the **mark-to-market** equity curve (includes open-trade
  drawdown), matching TradingView. With the Pine header `margin_short=0` there is no
  margin cap, so an open short during a strong rally can show a **drawdown beyond
  -100%** (see SOL) — confirm this against your TradingView max drawdown.
- **SOL:** Binance SOL data starts **2020-08-11** (SOL did not trade earlier), so its
  backtest cannot extend to 2018.

> These strategies show very high win rates and profit factors compounded from a
> $1,000 base over ~8 years — the resulting net-profit percentages are enormous and
> are exactly what TradingView would also report under `percent_of_equity=100`. High
> profit factors on a single in-sample run are a classic overfitting signal; the
> robustness/walk-forward checks are the next step.

---

"""
    body = "\n---\n\n".join(_strategy_section(s) for s in summaries)
    report = header + body
    report_path = OUT_DIR / "TEARSHEET.md"
    report_path.write_text(report)
    print(f"Wrote {report_path}")
    for name, _ in STRATEGIES:
        print(f"  trades: {OUT_DIR}/{name}_trades.csv")


if __name__ == "__main__":
    main()
