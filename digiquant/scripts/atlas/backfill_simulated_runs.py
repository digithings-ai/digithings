#!/usr/bin/env python3
"""
backfill_simulated_runs.py — Orchestrate the day-by-day historical backfill.

This script drives the 10-day replay from 2026-04-05 → 2026-04-14:
  1. Exports a pre-backfill snapshot of existing Supabase rows (backup).
  2. For each date in chronological order, prints the agent prompt + context.
  3. After research artifacts have been published (by the agent / operator),
     runs post-day validation via run_db_first.py + validate_pipeline_step.py.

The script itself does NOT call an AI — it is the orchestration wrapper that
ensures correct ordering, date-bounded context, and idempotent validation.

Usage:
    # Print plan (no DB writes)
    python3 scripts/backfill_simulated_runs.py --dry-run

    # Run preflight export (backup current state)
    python3 scripts/backfill_simulated_runs.py --export-only

    # Print context + prompt for a single date
    python3 scripts/backfill_simulated_runs.py --date 2026-04-12 --prompt

    # Normalize schemas for existing rows (non-destructive patch)
    python3 scripts/backfill_simulated_runs.py --normalize-schemas

    # Validate all 10 days post-backfill
    python3 scripts/backfill_simulated_runs.py --validate-all
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date as _date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).parent.parent
BACKUP_DIR = ROOT / "data" / "backfill-backup"

BACKFILL_DATES = [
    "2026-04-05",  # Sunday   → BASELINE (week 1 anchor)
    "2026-04-06",  # Monday   → delta
    "2026-04-07",  # Tuesday  → delta
    "2026-04-08",  # Wednesday→ delta
    "2026-04-09",  # Thursday → delta
    "2026-04-10",  # Friday   → delta
    "2026-04-11",  # Saturday → delta (no market; weekend research)
    "2026-04-12",  # Sunday   → BASELINE (week 2 anchor)
    "2026-04-13",  # Monday   → delta
    "2026-04-14",  # Tuesday  → delta (today)
]

# Dates that already have snapshots in Supabase (pre-backfill observation)
EXISTING_DATES = {
    "2026-04-05", "2026-04-06", "2026-04-07",
    "2026-04-08", "2026-04-09", "2026-04-10", "2026-04-11",
}
MISSING_DATES = {"2026-04-12", "2026-04-13", "2026-04-14"}


def _run(cmd: list[str], dry_run: bool = False, capture: bool = False) -> int:
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return 0
    if capture:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=False)
    else:
        r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode


def _day_of_week(d: str) -> str:
    return _date.fromisoformat(d).strftime("%A")


def _run_type(d: str) -> str:
    return "baseline" if _date.fromisoformat(d).weekday() == 6 else "delta"


def cmd_export(dry_run: bool) -> int:
    """Step 0: backup existing Supabase rows before overwriting."""
    print("\n=== STEP 0: Pre-backfill state export ===")
    return _run([
        sys.executable, "scripts/backfill_export_state.py",
        "--start", BACKFILL_DATES[0],
        "--end", BACKFILL_DATES[-1],
        "--out", str(BACKUP_DIR),
    ], dry_run=dry_run)


def cmd_normalize_schemas(dry_run: bool) -> int:
    """Patch schema violations in existing Apr 5-11 snapshots."""
    print("\n=== NORMALIZE SCHEMAS (Apr 5-11 existing rows) ===")
    rc = _run([
        sys.executable, "scripts/backfill_normalize_schemas.py",
        "--start", "2026-04-05",
        "--end", "2026-04-11",
    ] + (["--dry-run"] if dry_run else []), dry_run=False)
    return rc


def cmd_prompt(date_str: str) -> int:
    """Print the as-of date research context + agent prompt for one date."""
    print(f"\n=== CONTEXT + PROMPT for {date_str} ({_day_of_week(date_str)}) ===")
    rc = _run([
        sys.executable, "scripts/backfill_context.py",
        "--date", date_str,
        "--print-prompt",
    ], dry_run=False)
    return rc


def cmd_validate_day(date_str: str, dry_run: bool) -> int:
    """Post-publish validation for one date."""
    print(f"\n=== VALIDATE {date_str} ===")
    rc = _run([
        sys.executable, "scripts/run_db_first.py",
        "--date", date_str,
        "--validate-mode", "pm",
        "--skip-execute",
    ], dry_run=dry_run)
    return rc


def cmd_validate_all(dry_run: bool) -> int:
    """Validate all 10 backfill dates."""
    print("\n=== VALIDATE ALL 10 BACKFILL DATES ===")
    fails = []
    for d in BACKFILL_DATES:
        rc = cmd_validate_day(d, dry_run)
        if rc != 0:
            fails.append(d)
    if fails:
        print(f"\n❌ Validation failed for: {fails}")
        return 1
    print("\n✅ All 10 days validated successfully.")
    return 0


def cmd_dry_run() -> int:
    """Print the full backfill plan without executing."""
    print("\n=== BACKFILL PLAN (2026-04-05 → 2026-04-14) ===")
    print(f"{'Date':<12} {'Day':<12} {'Type':<10} {'State':<15} {'Action'}")
    print("-" * 75)
    for d in BACKFILL_DATES:
        dow = _day_of_week(d)
        rt = _run_type(d)
        state = "EXISTS" if d in EXISTING_DATES else "MISSING"
        if d in EXISTING_DATES and d in {"2026-04-07"}:
            action = "Patch: add Track B (rebalance docs)"
        elif d in EXISTING_DATES:
            action = "Normalize schema + refresh digest markdown"
        else:
            action = "FULL RUN: Track A (research) + Track B (portfolio)"
        print(f"{d:<12} {dow:<12} {rt:<10} {state:<15} {action}")

    print("""
=== AS-OF DATE GUARDRAILS ===
For each date D:
  • Prices/technicals: Supabase price_history + price_technicals WHERE date <= D
  • Macro: macro_series_observations WHERE obs_date <= D
  • News/catalysts: web search with before:D+1 date filter
  • Continuity: daily_snapshots WHERE date < D (prior day's snapshot)
  • Forward-looking exclusion: any source without a timestamp or dated > D is excluded

=== DOCUMENT KEYS PUBLISHED PER DAY ===
Track A (research):
  documents.digest  + daily_snapshots (overwrite canonical)
  [optional] research-delta/{DATE}T{TIME}Z.json

Track B (portfolio):
  market-thesis-exploration/{DATE}.json
  thesis-vehicle-map/{DATE}.json
  deliberation-transcript/{DATE}/{TICKER}.json
  deliberation-transcript-index/{DATE}.json
  pm-allocation-memo/{DATE}.json
  rebalance-decision.json               [canonical key, overwritten]

=== EXECUTION ORDER ===
  Step 0: Export current Supabase state (backup)
  Step 1: Normalize schemas for existing Apr 5-11 rows
  Step 2: Add missing Track B for Apr 7 (research exists; only PM work missing)
  Step 3: Fresh full run for Apr 12 (Sunday baseline)
  Step 4: Fresh full run for Apr 13 (delta, Monday)
  Step 5: Fresh full run for Apr 14 (delta, Tuesday — today)
  Step 6: Validate all 10 days
""")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Orchestrate the 10-day historical backfill (Apr 5–14, 2026)."
    )
    ap.add_argument("--dry-run", action="store_true", help="Print plan only; no DB writes")
    ap.add_argument("--export-only", action="store_true", help="Export backup only")
    ap.add_argument("--normalize-schemas", action="store_true", help="Patch schema violations in Apr 5-11")
    ap.add_argument("--date", default=None, help="Print context + prompt for a single date")
    ap.add_argument("--prompt", action="store_true", help="Used with --date to print the agent prompt")
    ap.add_argument("--validate-all", action="store_true", help="Validate all 10 dates post-backfill")
    ap.add_argument("--validate-date", default=None, help="Validate a single date")
    args = ap.parse_args()

    if args.dry_run and not any([
        args.export_only, args.normalize_schemas, args.date, args.validate_all, args.validate_date
    ]):
        return cmd_dry_run()

    if args.export_only:
        return cmd_export(dry_run=args.dry_run)

    if args.normalize_schemas:
        return cmd_normalize_schemas(dry_run=args.dry_run)

    if args.date:
        if args.prompt:
            return cmd_prompt(args.date)
        # Default: just show context JSON
        return _run([
            sys.executable, "scripts/backfill_context.py", "--date", args.date
        ], dry_run=False)

    if args.validate_all:
        return cmd_validate_all(dry_run=args.dry_run)

    if args.validate_date:
        return cmd_validate_day(args.validate_date, dry_run=args.dry_run)

    # Default: print plan
    return cmd_dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
