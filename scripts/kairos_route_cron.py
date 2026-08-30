#!/usr/bin/env python3
"""Agent-runnable Kairos overlay order-intent route cron (K4).

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_route_cron.py --check
    PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_route_cron.py --dry-run

``--all`` submits only when ``OLYMPUS_KAIROS_ROUTING`` is on. Kill switch
defaults off. Never ``workflow_dispatch``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.olympus.kairos.route_cron import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
