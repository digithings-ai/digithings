#!/usr/bin/env python3
"""Recover a ledger commit from existing positions (#3330, #3426)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _env import load_repo_env  # noqa: E402

from digiquant.research.supabase_io import SupabaseConfig, build_client  # noqa: E402
from digiquant.portfolio.writers.recover_ledger import (  # noqa: E402
    recover_ledger_from_book,
)
from digiquant.dashboard.tenancy import house_workspace_id  # noqa: E402

APPLY_MAX_AGE_DAYS = 7


def _apply_guard(
    run_date: date, *, apply: bool, yes: bool, force_recommit: bool = False
) -> str | None:
    if not apply:
        return None
    if force_recommit and not yes:
        return "--force-recommit --apply requires --yes (re-run is a no-op once the book matches)"
    if yes:
        return None
    age = (datetime.now(tz=UTC).date() - run_date).days
    if 0 <= age <= APPLY_MAX_AGE_DAYS:
        return None
    return (
        f"--apply for {run_date.isoformat()} is {age} days from today; "
        f"pass --yes (guard is {APPLY_MAX_AGE_DAYS} days)"
    )


def main(argv: list[str] | None = None) -> int:
    load_repo_env()
    parser = argparse.ArgumentParser(
        description="Append a ledger commit from existing positions (no LLM)."
    )
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the ledger + commit-run document. Default is dry-run.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            f"Confirm --apply for dates older than {APPLY_MAX_AGE_DAYS} days "
            "and for --force-recommit."
        ),
    )
    parser.add_argument(
        "--force-recommit",
        action="store_true",
        help="Append a new commit when the head does not match the book. Requires --yes.",
    )
    args = parser.parse_args(argv)
    run_date = date.fromisoformat(args.date)
    refused = _apply_guard(
        run_date, apply=args.apply, yes=args.yes, force_recommit=args.force_recommit
    )
    if refused:
        print(json.dumps({"error": refused, "status": "refused"}, indent=2, sort_keys=True))
        return 1

    result = recover_ledger_from_book(
        client=build_client(SupabaseConfig.from_env()),
        run_date=run_date,
        apply=args.apply,
        force_recommit=args.force_recommit,
    )
    print(
        json.dumps(
            {
                "run_date": result.run_date.isoformat(),
                "status": result.status,
                "commit_id": result.commit_id,
                "source_run_id": result.source_run_id,
                "weights": result.weights,
                "cash_pct": result.cash_pct,
                "nav": result.nav,
                "message": result.message,
                "house_workspace_id": str(house_workspace_id()),
                "apply": args.apply,
                "force_recommit": args.force_recommit,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if result.status == "no_book":
        return 2
    if result.status == "conflict":
        return 3
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
