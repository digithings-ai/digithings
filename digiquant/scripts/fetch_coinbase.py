#!/usr/bin/env python3
"""Fetch daily OHLCV from Coinbase via CCXT and save to price-history cache.

Usage:
    python scripts/fetch_coinbase.py
    python scripts/fetch_coinbase.py --symbols BTC/USD,ETH/USD,SOL/USD
    python scripts/fetch_coinbase.py --start 2017-01-01
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import ccxt
import polars as pl

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / "data" / "price-history"

SYMBOLS = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "SOL/USD": "SOL-USD",
}


def fetch_all_daily(exchange: ccxt.Exchange, symbol: str, since: str) -> list[list]:
    """Paginate through all daily OHLCV from `since` to now."""
    since_ms = exchange.parse8601(f"{since}T00:00:00Z")
    now_ms = int(time.time() * 1000)
    all_bars = []
    while since_ms < now_ms:
        bars = exchange.fetch_ohlcv(symbol, "1d", since=since_ms, limit=300)
        if not bars:
            since_ms += 300 * 86_400_000
            time.sleep(exchange.rateLimit / 1000)
            continue
        all_bars.extend(bars)
        last_ts = bars[-1][0]
        since_ms = last_ts + 86_400_000
        time.sleep(exchange.rateLimit / 1000)
    return all_bars


def bars_to_polars(bars: list[list], ticker: str) -> pl.DataFrame:
    """Convert CCXT OHLCV bars to the cache CSV schema."""
    return pl.DataFrame({
        "timestamp": [datetime.fromtimestamp(b[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d") for b in bars],
        "open": [b[1] for b in bars],
        "high": [b[2] for b in bars],
        "low": [b[3] for b in bars],
        "close": [b[4] for b in bars],
        "volume": [b[5] for b in bars],
        "symbol": [ticker] * len(bars),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Coinbase daily OHLCV via CCXT")
    parser.add_argument("--symbols", default=",".join(SYMBOLS.keys()), help="Comma-separated CCXT symbols")
    parser.add_argument("--start", default="2017-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument(
        "--through-yesterday",
        action="store_true",
        help="Drop today's UTC daily bar (incomplete until Coinbase EOD)",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    exchange = ccxt.coinbase()
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    for ccxt_sym in args.symbols.split(","):
        ccxt_sym = ccxt_sym.strip()
        ticker = SYMBOLS.get(ccxt_sym, ccxt_sym.replace("/", "-"))

        logger.info("Fetching %s (%s) from %s", ccxt_sym, ticker, args.start)
        bars = fetch_all_daily(exchange, ccxt_sym, args.start)
        if not bars:
            logger.error("No data for %s", ccxt_sym)
            continue

        df = bars_to_polars(bars, ticker)
        df = df.unique(subset=["timestamp"], keep="last").sort("timestamp")
        if args.through_yesterday:
            today = date.today().isoformat()
            before = len(df)
            df = df.filter(pl.col("timestamp") < today)
            if before != len(df):
                logger.info("  dropped incomplete bar(s) on/after %s", today)

        out = args.cache_dir / f"{ticker}.csv"
        df.write_csv(out)
        logger.info("  %s: %d bars (%s → %s) → %s", ticker, len(df),
                     df["timestamp"][0], df["timestamp"][-1], out)


if __name__ == "__main__":
    main()
