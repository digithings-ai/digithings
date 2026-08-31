#!/usr/bin/env python3
"""Operator CLI for :mod:`digiquant.olympus.hermes.writers.recover_ledger` (#3330).

Reads an already-booked ``positions`` / ``nav_history`` day and appends the
missing H9 ledger commit + ``commit-run/{run_id}`` document. Does not re-run
H8 or the LLM pipeline.

Usage:
  python digiquant/scripts/atlas/recover_h9_ledger_commit.py --date 2026-08-31
  python digiquant/scripts/atlas/recover_h9_ledger_commit.py --date 2026-08-31 --apply
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    load_dotenv()
except ImportError:
    pass

from digiquant.olympus.hermes.writers.recover_ledger import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
