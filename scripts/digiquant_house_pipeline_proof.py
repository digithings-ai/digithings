#!/usr/bin/env python3
"""Agent-runnable proof that the scheduled house GHA committed after main hotfixes.

Lists ``pipeline-olympus.yml`` runs. A **schedule** success strictly after
#3334 (2026-08-31T20:39Z) on a ``main`` that is **not** still ``3601f72df``
is EPIC house-pipeline acceptance. Never ``workflow_dispatch``.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_house_pipeline_proof.py

Exit codes:
  0 — schedule success after current ``origin/main`` committer time (and #3334)
  2 — counting schedule completed with failure
  3 — no counting schedule yet (waiting for cron ``0 12 * * *``)
  4 — could not list runs / resolve ``origin/main``, or the CLI was asked to dispatch
  5 — ``origin/main`` is still UUID-hotfix ``3601f72df`` (merge #3343 → #3348 → #3351 → #3354)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.olympus.kairos.house_pipeline_proof import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
