#!/usr/bin/env python3
"""Delegates to ``digiquant/scripts/recover_ledger.py`` (#3426)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parents[1] / "recover_ledger.py"
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")
