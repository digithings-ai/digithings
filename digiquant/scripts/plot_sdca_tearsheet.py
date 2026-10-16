#!/usr/bin/env python3
"""Render SDCA diagnostic tearsheet charts from a published JSON payload.

    python digiquant/scripts/plot_sdca_tearsheet.py \\
        --tearsheet /tmp/sdca-2025-exit-tearsheet/btc_sdca.json \\
        --out /opt/cursor/artifacts

Does not run Nautilus, does not push supabase. Allocation is reconstructed
from equity + capital_deployed when ``allocated_pct_curve`` is absent:
percent allocated = 100 * (equity - cash) / equity, cash = initial * (1 - deployed/100).
Fill dots use |trade_usd| / portfolio (fills, or reconstructed Δunits).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from digiquant.charts.sdca import render_sdca_diagnostic_charts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tearsheet",
        type=Path,
        required=True,
        help="Path to btc_sdca.json (TearsheetData)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Directory for PNG figures",
    )
    parser.add_argument("--prefix", default="sdca", help="Filename prefix (default sdca)")
    parser.add_argument(
        "--start",
        default=None,
        help="Optional inclusive YYYY-MM-DD window start (zoom)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional inclusive YYYY-MM-DD window end (zoom)",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.tearsheet.read_text())
    paths = render_sdca_diagnostic_charts(
        payload,
        args.out,
        prefix=args.prefix,
        date_start=args.start,
        date_end=args.end,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
