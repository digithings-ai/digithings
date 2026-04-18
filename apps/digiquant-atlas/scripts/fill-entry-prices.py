#!/usr/bin/env python3
"""fill-entry-prices.py — Back-fill entry_price_usd for portfolio positions.

Queries the Supabase price_history table for the closing price on each position's
entry_date, then writes the result back to config/portfolio.json.

Usage:
    python3 scripts/fill-entry-prices.py            # fill all null entry prices
    python3 scripts/fill-entry-prices.py --dry-run  # show diff without writing
    python3 scripts/fill-entry-prices.py --ticker IAU  # fill a single ticker only

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY env vars (or config/supabase.env)
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / "supabase.env")
except ImportError:
    pass

try:
    from supabase import create_client
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not _HAS_SUPABASE:
        print("❌ supabase-py not installed — pip install supabase", file=sys.stderr)
        sys.exit(1)
    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_SERVICE_KEY must be set", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


def lookup_close(sb, ticker: str, entry_date: str) -> float | None:
    """Return closing price for ticker on entry_date from price_history, or None."""
    resp = (
        sb.table("price_history")
        .select("close")
        .eq("ticker", ticker)
        .eq("date", entry_date)
        .single()
        .execute()
    )
    if resp.data and resp.data.get("close") is not None:
        return float(resp.data["close"])
    return None


def main():
    parser = argparse.ArgumentParser(
        description="fill-entry-prices.py — Back-fill entry_price_usd from Supabase price_history",
        epilog="Requires SUPABASE_URL and SUPABASE_SERVICE_KEY env vars."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would change without writing to portfolio.json"
    )
    parser.add_argument(
        "--ticker", default=None, metavar="TICKER",
        help="Only process a single ticker (default: all null positions)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing non-null entry_price_usd values"
    )
    args = parser.parse_args()

    portfolio_path = ROOT / "config" / "portfolio.json"
    if not portfolio_path.exists():
        print(f"❌ Not found: {portfolio_path}", file=sys.stderr)
        sys.exit(1)

    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    positions = portfolio.get("positions", [])

    # Filter candidates
    candidates = []
    for pos in positions:
        ticker = pos.get("ticker")
        entry_date = pos.get("entry_date")
        entry_price = pos.get("entry_price_usd")

        if args.ticker and ticker != args.ticker.upper():
            continue
        if not args.force and entry_price is not None:
            continue
        if not entry_date or not ticker:
            continue
        candidates.append(pos)

    if not candidates:
        print("✅ No positions need entry price filling (all set or filtered out)")
        return

    print(f"{'[dry-run] ' if args.dry_run else ''}Filling entry prices for {len(candidates)} position(s)...")
    sb = get_supabase_client()

    filled = 0
    not_found = []
    for pos in candidates:
        ticker = pos["ticker"]
        entry_date = pos["entry_date"]
        price = lookup_close(sb, ticker, entry_date)
        if price is not None:
            old = pos.get("entry_price_usd")
            print(f"  {ticker:6s}  {entry_date}  close={price:.4f}"
                  + (f"  (was {old})" if old is not None else ""))
            if not args.dry_run:
                pos["entry_price_usd"] = price
            filled += 1
        else:
            print(f"  {ticker:6s}  {entry_date}  ⚠️  not found in price_history")
            not_found.append(f"{ticker}@{entry_date}")

    if not args.dry_run and filled:
        portfolio_path.write_text(
            json.dumps(portfolio, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        print(f"\n✅ Updated {filled} entry price(s) in config/portfolio.json")
    elif args.dry_run:
        print(f"\n[dry-run] Would update {filled} entry price(s)")
    else:
        print("\nℹ️  Nothing to update")

    if not_found:
        print(f"\n⚠️  {len(not_found)} ticker(s) not found in price_history: {', '.join(not_found)}")
        print("   Run: python3 scripts/preload-history.py --supabase  to populate price_history first")


if __name__ == "__main__":
    main()
