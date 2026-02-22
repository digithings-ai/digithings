#!/usr/bin/env python3
"""
Download NautilusTrader test data so run_backtest and tests can use it.

TestDataProvider looks for tests/test_data under the parent of the nautilus_trader
package (e.g. .venv/lib/python3.12/site-packages/tests/test_data/).
Run after: uv pip install -e ".[nautilus]"

Usage:
  python -m digiquant.scripts.fetch_nautilus_test_data
  # or from repo root:
  python digiquant/scripts/fetch_nautilus_test_data.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path


NAUTILUS_TEST_DATA_URL = (
    "https://raw.githubusercontent.com/nautechsystems/nautilus_trader/develop"
    "/tests/test_data/binance/ethusdt-trades.csv"
)


def main() -> int:
    try:
        import nautilus_trader.test_kit.providers as pmod  # noqa: F401
    except ImportError:
        print("nautilus_trader not installed. Run: uv pip install -e '.[nautilus]'")
        return 1

    # Same logic as TestDataProvider._test_data_directory: parent of nautilus_trader pkg
    source_root = Path(pmod.__file__).resolve().parent.parent
    test_data_dir = source_root.parent / "tests" / "test_data" / "binance"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    dest = test_data_dir / "ethusdt-trades.csv"

    print(f"Downloading {NAUTILUS_TEST_DATA_URL} -> {dest}")
    urllib.request.urlretrieve(NAUTILUS_TEST_DATA_URL, dest)
    print(f"Done. Size: {dest.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
