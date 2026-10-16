#!/usr/bin/env python3
"""Build an SDCA-scoped Coinbase-sourced price cache.

Fetches BTC/ETH daily OHLCV from Coinbase (delegating to ``fetch_coinbase.py``)
into a dedicated cache directory, then copies the macro sibling series that
``load_sdca_extra_sources`` expects alongside the price files (M2SL, DXY).
Those series have no Coinbase equivalent, so they're carried over unchanged
from the canonical yfinance-sourced cache.

This is additive: it never touches ``data/price-history`` (the shared
yfinance cache used by other strategies and the Atlas dashboard), only the
new Coinbase-sourced directory.

Usage:
    python scripts/build_sdca_coinbase_cache.py
    python scripts/build_sdca_coinbase_cache.py --target-cache-dir data/price-history-coinbase
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_CACHE = ROOT / "data" / "price-history"
DEFAULT_TARGET_CACHE = ROOT / "data" / "price-history-coinbase"

MACRO_SIBLINGS = ("M2SL.csv", "DTWEXBGS.csv")


def copy_macro_siblings(source_cache: Path, target_cache: Path) -> list[str]:
    """Copy macro series with no Coinbase equivalent (m2, dxy) unchanged.

    Returns the filenames actually copied; a missing source is skipped
    (logged, not fatal) since not every cache needs every macro series.
    """
    copied = []
    for name in MACRO_SIBLINGS:
        src = source_cache / name
        if not src.exists():
            logger.warning("macro sibling not found, skipping: %s", src)
            continue
        shutil.copyfile(src, target_cache / name)
        copied.append(name)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-cache-dir",
        type=Path,
        default=DEFAULT_SOURCE_CACHE,
        help="Canonical yfinance cache to copy macro siblings (M2SL, DXY) from",
    )
    parser.add_argument(
        "--target-cache-dir",
        type=Path,
        default=DEFAULT_TARGET_CACHE,
        help="Destination cache dir for the Coinbase-sourced SDCA cache",
    )
    parser.add_argument("--symbols", default="BTC/USD,ETH/USD", help="Comma-separated CCXT symbols to fetch")
    parser.add_argument("--start", default="2015-07-20", help="Start date (YYYY-MM-DD); Coinbase BTC listing")
    args = parser.parse_args()

    args.target_cache_dir.mkdir(parents=True, exist_ok=True)

    fetch_script = Path(__file__).resolve().parent / "fetch_coinbase.py"
    subprocess.run(
        [
            sys.executable,
            str(fetch_script),
            "--symbols",
            args.symbols,
            "--start",
            args.start,
            "--cache-dir",
            str(args.target_cache_dir),
        ],
        check=True,
    )

    copied = copy_macro_siblings(args.source_cache_dir, args.target_cache_dir)
    logger.info("copied macro siblings: %s", copied)


if __name__ == "__main__":
    main()
