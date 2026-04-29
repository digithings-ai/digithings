#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date as dt_date, datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).parent.parent


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _run(cmd: list[str], dry_run: bool = False) -> int:
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return 0
    r = subprocess.run(cmd, cwd=str(ROOT))
    return int(r.returncode)


def _iso_today() -> str:
    return dt_date.today().isoformat()


def _detect_run_type(force_baseline: bool, force_delta: bool, d: str) -> str:
    if force_baseline and force_delta:
        raise ValueError("Choose at most one of --baseline/--delta")
    if force_baseline:
        return "baseline"
    if force_delta:
        return "delta"
    # Sunday baseline by default
    dow = datetime.fromisoformat(d).isoweekday()
    return "baseline" if dow == 7 else "delta"


def _latest_baseline_date(sb, before_or_on: str) -> Optional[str]:
    res = (
        sb.table("daily_snapshots")
        .select("date,run_type")
        .eq("run_type", "baseline")
        .lte("date", before_or_on)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    return str(rows[0]["date"])[:10]


def _prior_calendar_date(d: str) -> str:
    """ISO date immediately before d (for digest delta compiler chain)."""
    cur = datetime.fromisoformat(d).date()
    return (cur - timedelta(days=1)).isoformat()


def _latest_snapshot_date_strictly_before(sb, before_date: str) -> Optional[str]:
    """Most recent daily_snapshots.date strictly before before_date (fallback if prior calendar day missing)."""
    res = (
        sb.table("daily_snapshots")
        .select("date")
        .lt("date", before_date)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    return str(rows[0]["date"])[:10]


def _execute_at_open_argv(d: str) -> list[str]:
    argv = [sys.executable, "scripts/execute_at_open.py", "--date", d]
    sched = ROOT / "config" / "schedule.json"
    if not sched.exists():
        return argv
    try:
        cfg = json.loads(sched.read_text(encoding="utf-8"))
        mode = (cfg.get("rebalance_source_for_opens") or {}).get("mode", "same_day")
        if mode == "prior_trading_day":
            argv.append("--prior-trading-day-rebalance")
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return argv


def _print_agent_prompt(
    run_type: str,
    d: str,
    week_anchor_date: Optional[str],
    materialize_baseline_date: Optional[str],
) -> None:
    print("")
    print("=== AGENT PROMPT (JSON-first, DB-first) ===")
    if run_type == "baseline":
        print(f"Run the WEEKLY BASELINE digest for {d}.")
        print("Produce the full digest snapshot JSON (schema: templates/digest-snapshot-schema.json).")
        print("Return JSON only.")
    else:
        print(f"Run the DAILY DELTA digest for {d}.")
        print(
            f"Week anchor (snapshot.baseline_date in delta-request JSON): {week_anchor_date or '[MISSING — run Sunday baseline first]'}"
        )
        print(
            f"materialize_snapshot --baseline-date (load THIS row from daily_snapshots, then apply ops): "
            f"{materialize_baseline_date or '[MISSING]'}"
        )
        print(
            "Digest compiler chain: weekday ops apply to the **previous calendar day’s** materialized snapshot "
            "(not re-diffed from Sunday alone). delta-request.baseline_date stays the week’s Sunday anchor."
        )
        print("Emit a single Delta Request JSON (schema: templates/delta-request-schema.json).")
        print("Return JSON only.")
    print("")
    print("Track A (generic research, positioning-blind): skills/research-daily/SKILL.md")
    print("  → research_delta JSON → validate_artifact.py - → publish_document.py --payload - (document_key research-delta/<RUN_SUFFIX>.json)")
    print("  → run: python3 scripts/run_db_first.py --skip-execute --validate-mode research")
    print("")
    print("Track B (portfolio / analyst, user-specific): config/preferences.md + investment-profile.md")
    print("  → rebalance-decision.json + snapshot/digest path as today")
    print("  → run: python3 scripts/run_db_first.py --validate-mode full|pm")
    print("")
    print("Additional portfolio-layer artifacts (JSON):")
    print("- asset recommendations: templates/schemas/asset-recommendation.schema.json")
    print("- deliberation: templates/schemas/deliberation-transcript.schema.json")
    print("- rebalance decision: templates/schemas/rebalance-decision.schema.json")
    print("Publish + validate via this CLI after artifacts are produced.")
    print("")
    print("Step-wise pipeline checks (documents + JSON Schema): scripts/validate_pipeline_step.py")
    print("  e.g. python3 scripts/validate_pipeline_step.py --date <D> --chain research")
    print("       python3 scripts/validate_pipeline_step.py --date <D> --chain track_b")
    print("       python3 scripts/validate_pipeline_step.py --list")
    print("=== END PROMPT ===")
    print("")


def main() -> int:
    ap = argparse.ArgumentParser(description="DB-first daily entrypoint for digiquant-atlas.")
    ap.add_argument("--date", default=_iso_today(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--baseline", action="store_true", help="Force baseline mode")
    ap.add_argument("--delta", action="store_true", help="Force delta mode")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    ap.add_argument(
        "--skip-execute",
        action="store_true",
        help="Skip execute_at_open.py (use after Track A research-only publish).",
    )
    ap.add_argument(
        "--validate-mode",
        choices=("full", "research", "pm"),
        default="full",
        help="Passed to validate_db_first.py (default: full).",
    )
    ap.add_argument(
        "--skip-sync-positions",
        action="store_true",
        help="Skip sync_positions_from_rebalance.py (default: run for --validate-mode full|pm).",
    )
    args = ap.parse_args()

    d = args.date
    run_type = _detect_run_type(args.baseline, args.delta, d)

    week_anchor_date = None
    materialize_baseline_date = None
    if run_type == "delta":
        prior = _prior_calendar_date(d)
        if args.dry_run:
            materialize_baseline_date = prior
            week_anchor_date = None
        else:
            sb = _sb()
            week_anchor_date = _latest_baseline_date(sb, d)
            check = (
                sb.table("daily_snapshots")
                .select("date")
                .eq("date", prior)
                .limit(1)
                .execute()
            )
            rows = getattr(check, "data", None) or []
            materialize_baseline_date = prior if rows else _latest_snapshot_date_strictly_before(sb, d)

    # Preflight checks
    for p in [
        ROOT / "RUNBOOK.md",
        ROOT / "templates" / "digest-snapshot-schema.json",
        ROOT / "templates" / "delta-request-schema.json",
        ROOT / "templates" / "schemas",
    ]:
        if not p.exists():
            print(f"❌ missing required path: {p}", file=sys.stderr)
            return 2

    _print_agent_prompt(run_type, d, week_anchor_date, materialize_baseline_date)

    # After the agent publishes to Supabase, this CLI refreshes metrics and validates DB state.
    # 1) Validate artifacts on disk (if present)
    artifacts: list[Path] = []
    day_dir = ROOT / "data" / "agent-cache" / "daily" / d
    if day_dir.exists():
        artifacts.extend(day_dir.glob("*.json"))
        artifacts.extend((day_dir / "sectors").glob("*.json"))
        artifacts.extend((day_dir / "positions").glob("*.json"))

    for a in artifacts:
        rc = _run([sys.executable, "scripts/validate_artifact.py", str(a)], dry_run=args.dry_run)
        if rc != 0:
            return rc

    # 1.5) Track B: upsert positions from rebalance_decision.proposed_portfolio (before metrics refresh)
    if args.validate_mode in ("full", "pm") and not args.skip_sync_positions:
        rc = _run(
            [sys.executable, "scripts/sync_positions_from_rebalance.py", "--date", d],
            dry_run=args.dry_run,
        )
        if rc != 0:
            return rc

    # 2) Metrics / NAV alignment (Supabase)
    rc = _run(
        [
            sys.executable,
            "scripts/refresh_performance_metrics.py",
            "--supabase",
            "--fill-calendar-through",
            d,
        ],
        dry_run=args.dry_run,
    )
    if rc != 0:
        return rc

    # 2.5) Record market-open execution events (best-effort)
    if not args.skip_execute:
        rc = _run(_execute_at_open_argv(d), dry_run=args.dry_run)
        if rc != 0:
            return rc
    else:
        print("$ (skipped execute_at_open.py — --skip-execute)")

    # 3) DB-first validation
    rc = _run(
        [
            sys.executable,
            "scripts/validate_db_first.py",
            "--date",
            d,
            "--mode",
            args.validate_mode,
        ],
        dry_run=args.dry_run,
    )
    if rc != 0:
        return rc

    print("✅ run_db_first.py completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

