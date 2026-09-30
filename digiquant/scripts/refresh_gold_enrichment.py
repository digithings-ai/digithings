#!/usr/bin/env python3
"""Refresh gold enrichment snapshots (idempotent, anon tools only, #4804).

Pulls options-skew + calendar + news on every run (fast-moving), 13F + LBMA
probe only with --include-slow (slow-moving). Prunes each tool dir to the
keep bound afterwards. Exit 0 with per-pull status lines; a single pull
failing prints a warning and continues (exit 1 only if ALL pulls fail).

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/refresh_gold_enrichment.py
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/refresh_gold_enrichment.py --include-slow --keep 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pull_gold_enrichment import (
    probe_lbma_series,
    snapshot_13f_gld,
    snapshot_econ_calendar,
    snapshot_gold_news,
    snapshot_options_skew,
)

from digiquant.data.enrichment.snapshots import prune_tool

TOOLS = (
    "digifetch_options_chain",
    "digifetch_econ_calendar",
    "digifetch_news",
    "digifetch_13f_funds",
    "digifetch_econ_series",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh gold enrichment snapshots")
    parser.add_argument("--include-slow", action="store_true")
    parser.add_argument("--keep", type=int, default=30)
    args = parser.parse_args()

    ok = total = 0

    def attempt(name: str, fn) -> None:
        nonlocal ok, total
        total += 1
        try:
            result = fn()
            ok += 1
            print(f"ok {name}: {result}")
        except Exception as exc:  # one pull must not kill the refresh
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")

    attempt("options-skew", snapshot_options_skew)
    attempt("econ-calendar", snapshot_econ_calendar)
    attempt("gold-news", snapshot_gold_news)
    if args.include_slow:
        attempt("13f-gld", snapshot_13f_gld)
        attempt("probe-lbma", probe_lbma_series)
    for tool in TOOLS:
        print(f"prune {tool}: removed {prune_tool(tool, keep=args.keep)}")
    print(f"{ok}/{total} pulls ok")
    return 0 if ok else 1


if __name__ == "__main__":
    main()
