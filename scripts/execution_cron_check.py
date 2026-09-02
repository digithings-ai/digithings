#!/usr/bin/env python3
"""GHA pin for ``.github/workflows/execution-cron-check.yml``.

cursor/* cannot rewrite workflow files. The canonical CLI is
``scripts/digiquant_cron_check.py``. This wrapper keeps the installed probe
green until a feat/ or human hop renames the workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.execution.cron_check import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
