#!/usr/bin/env python3
"""Offload finished LangGraph checkpoint payloads to R2 (issue #3761)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.ops.checkpoint_archive import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
