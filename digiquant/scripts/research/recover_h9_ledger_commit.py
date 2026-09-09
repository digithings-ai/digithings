#!/usr/bin/env python3
"""Alias for ``digiquant/scripts/recover_ledger.py`` (#3426)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_CLI = Path(__file__).resolve().parents[1] / "recover_ledger.py"

if __name__ == "__main__":
    sys.argv[0] = str(_CLI)
    runpy.run_path(str(_CLI), run_name="__main__")
