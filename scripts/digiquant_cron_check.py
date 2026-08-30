#!/usr/bin/env python3
"""Agent-runnable loud-fail probe for overlay, execution sync, route, and Mailgun cron env.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_cron_check.py

Exit 0 when all four --check probes pass (names only; no dispatch / no send).
Exit 2 when any probe is unconfigured.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.olympus.kairos.cron_check import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
