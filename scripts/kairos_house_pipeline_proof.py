#!/usr/bin/env python3
"""Agent-runnable proof that the scheduled house GHA committed after main hotfixes.

Lists ``pipeline-olympus.yml`` runs. A **schedule** success strictly after
#3334 (2026-08-31T20:39Z) is EPIC house-pipeline acceptance. Never
``workflow_dispatch``.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_house_pipeline_proof.py

Exit codes:
  0 — post-hotfix schedule succeeded
  2 — post-hotfix schedule completed with failure
  3 — no post-hotfix schedule yet (waiting for cron ``0 12 * * *``)
  4 — could not list runs, or the CLI was asked to dispatch
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.olympus.kairos.house_pipeline_proof import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
