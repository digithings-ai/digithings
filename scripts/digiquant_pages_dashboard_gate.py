#!/usr/bin/env python3
"""Fail-closed Pages /dashboard probe + optional settings EF redeploy.

Default ``--check`` exits 3 while live ``/dashboard`` 404s. ``--apply`` deploys
settings / checkout / portal only after those paths (including the Alpaca
OAuth brokers callback) return 200, this checkout
pins ``/dashboard`` + ``POST /access/redeem-invite``, **and** each live
settings / checkout / portal ESZIP contains those executable markers. Never
prints secret values. Never weakens ``public_app_urls_ok``. Exit 5 = stale
checkout; exit 6 = a live bundle still looks like v32.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_pages_dashboard_gate.py
    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_pages_dashboard_gate.py --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.execution.pages_dashboard_gate import (  # noqa: E402
    main as _main,
)


def main() -> int:
    return _main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
