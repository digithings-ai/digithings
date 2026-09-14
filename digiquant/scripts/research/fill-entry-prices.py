#!/usr/bin/env python3
"""fill-entry-prices.py — Back-fill entry_price_usd for portfolio positions.

Looks up each position's entry-date close in the sealed R2 generations (#4053),
then writes the result back to config/portfolio.json.

Usage:
    python3 scripts/fill-entry-prices.py            # fill all null entry prices
    python3 scripts/fill-entry-prices.py --dry-run  # show diff without writing
    python3 scripts/fill-entry-prices.py --ticker IAU  # fill a single ticker only

Requires:
    R2 credentials (R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
    for the sealed-generation market-data read.
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Load .env if present (repo root carries the R2 credentials this read needs).
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def lookup_close(ticker: str, entry_date: str) -> float | None:
    """Return the entry date's close from the sealed R2 generations, or None.

    R2-only since #4053: an unsealed date (today, before the evening refresh) has
    no generation row yet, so a same-day lookup returns None rather than a
    Supabase read — there is no live close source.
    """
    # Imported per call (cached in sys.modules afterwards) so the default path needs no
    # digiquant import at module scope.
    from digiquant.research.data.queries import r2_close_rows

    day = str(entry_date)[:10]
    try:
        rows = r2_close_rows(tickers=[ticker], since=day, until=day)
    except LookupError:
        return None
    if not rows or rows[0].get("close") is None:
        return None
    try:
        price = float(rows[0]["close"])
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def main():
    parser = argparse.ArgumentParser(
        description="fill-entry-prices.py — Back-fill entry_price_usd from Supabase price_history",
        epilog="Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars."
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

    filled = 0
    not_found = []
    for pos in candidates:
        ticker = pos["ticker"]
        entry_date = pos["entry_date"]
        price = lookup_close(ticker, entry_date)
        if price is not None:
            old = pos.get("entry_price_usd")
            print(f"  {ticker:6s}  {entry_date}  close={price:.4f}"
                  + (f"  (was {old})" if old is not None else ""))
            if not args.dry_run:
                pos["entry_price_usd"] = price
            filled += 1
        else:
            print(f"  {ticker:6s}  {entry_date}  ⚠️  no sealed R2 close")
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
        print(f"\n⚠️  {len(not_found)} ticker(s) have no sealed R2 close: {', '.join(not_found)}")
        print("   Run: python3 scripts/refresh_market_data_r2.py  to refresh the R2 generations first")


if __name__ == "__main__":
    main()
