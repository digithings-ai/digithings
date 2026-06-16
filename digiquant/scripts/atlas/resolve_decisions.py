#!/usr/bin/env python3
"""Standalone Atlas decision resolver (Pillar 3A, #726).

Resolves every *due* ``decision_log`` row — computes realized alpha vs the benchmark and
writes the reflection lesson — by calling
:func:`digiquant.olympus.atlas.decision_log.resolve_pending`. This decouples resolution
from the research pipeline so it can run on its own cron (daily, after EOD prices land),
independent of a baseline/delta run. The in-graph ``preflight_reflect`` stays as a
belt-and-suspenders path; this script is the authoritative, schedulable resolver.

Resolution is idempotent (only ``status='pending'`` rows are touched) and gracefully skips
a due row whose price window hasn't landed yet (it stays pending for the next run).

Usage::

    python digiquant/scripts/atlas/resolve_decisions.py [--run-date YYYY-MM-DD]

Env: ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY`` (reads/writes ``decision_log``);
``OPENROUTER_API_KEY`` for the reflector LLM (~1 cheap call per resolved decision).

Exit codes: 0 = clean run (resolving 0 due rows is success); 1 = hard failure (Supabase
unavailable / resolver crash); 2 = bad ``--run-date``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# repo root: .../digiquant/scripts/atlas/resolve_decisions.py → up 3 → repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _ensure_importable() -> None:
    """Add the monorepo ``*/src`` paths to sys.path so the atlas package imports."""
    for rel in ("digiquant/src", "digigraph/src", "digibase/src", "digismith/src"):
        path = str(_REPO_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _parse_run_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.now(timezone.utc).date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve due Atlas decision_log rows (alpha vs benchmark + reflection)."
    )
    parser.add_argument(
        "--run-date",
        default=None,
        help="Resolution as-of date YYYY-MM-DD (default: today UTC).",
    )
    args = parser.parse_args(argv)

    try:
        run_date = _parse_run_date(args.run_date)
    except ValueError:
        print(f"error: bad --run-date {args.run_date!r} (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    _ensure_importable()
    from digiquant.olympus.atlas.decision_log import resolve_pending
    from digiquant.olympus.atlas.supabase_io import (
        SupabaseConfig,
        build_client,
        query_pending_decisions,
    )

    try:
        client = build_client(SupabaseConfig.from_env())
    except Exception as exc:  # noqa: BLE001 — a config/connectivity failure is a hard error
        print(f"error: Supabase client unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        resolved = resolve_pending(client=client, run_date=run_date)
        remaining = len(query_pending_decisions(client=client, run_date=run_date))
    except Exception as exc:  # noqa: BLE001 — surface a hard failure as a non-zero exit
        print(f"error: resolve_pending failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"resolve_decisions: resolved {resolved} decision(s) as of {run_date.isoformat()}; "
        f"{remaining} still due-pending (awaiting price data)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
