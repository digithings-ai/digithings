#!/usr/bin/env python3
"""Seed ``portfolio_ledger_holding_lots`` from the legacy ``positions`` book (#2589).

Writes one labeled ``legacy_opening_snapshot`` chain (commit → fill → open lot) so
at-open residuals match the committed book. Idempotent: a no-op when open lots already
exist or the book is empty.

Usage:
  python digiquant/scripts/atlas/seed_ledger_opening_snapshot.py
  python digiquant/scripts/atlas/seed_ledger_opening_snapshot.py --date 2026-08-20
  python digiquant/scripts/atlas/seed_ledger_opening_snapshot.py --dry-run

Environment: CORE_SUPABASE_URL / CORE_SUPABASE_SERVICE_KEY (or legacy SUPABASE_* names).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as dt_date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    path = str(_REPO_ROOT / "digiquant" / "src")
    if path not in sys.path:
        sys.path.insert(0, path)


_ensure_importable()
from digiquant.olympus.atlas.supabase_io import (  # noqa: E402
    SupabaseConfig,
    SupabaseNotConfiguredError,
    build_client,
)
from digiquant.olympus.tenancy import eq_house_workspace  # noqa: E402

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def _sb():
    try:
        return build_client(SupabaseConfig.from_env())
    except SupabaseNotConfiguredError as exc:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required") from exc
    except ImportError as exc:
        raise RuntimeError("pip install supabase") from exc


def _latest_positions_date(client) -> dt_date | None:
    resp = (
        eq_house_workspace(client.table("positions").select("date"))
        .neq("ticker", "CASH")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    raw = rows[0].get("date")
    if not raw:
        return None
    return dt_date.fromisoformat(str(raw)[:10])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed portfolio_ledger_holding_lots from the positions book (#2589)."
    )
    parser.add_argument(
        "--date",
        help="positions book date (YYYY-MM-DD). Default: latest non-CASH positions date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve the book date and report whether a seed would run; do not write.",
    )
    args = parser.parse_args(argv)

    # Import after argv parse so --help works without digiquant on PYTHONPATH quirks.
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root / "digiquant" / "src"))
    from digiquant.olympus.hermes.writers.opening_snapshot import (
        POLICY_VERSION_ID,
        cold_start_requires_seed,
        ensure_legacy_opening_snapshot,
    )

    client = _sb()
    if args.date:
        try:
            book_date = dt_date.fromisoformat(args.date)
        except ValueError:
            print(f"error: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
            return 2
    else:
        book_date = _latest_positions_date(client)
        if book_date is None:
            print("error: no positions rows to seed from", file=sys.stderr)
            return 2

    if args.dry_run:
        needs = cold_start_requires_seed(client=client, book_date=book_date)
        print(
            f"[dry-run] book_date={book_date.isoformat()} "
            f"policy={POLICY_VERSION_ID} cold_start={needs}"
        )
        return 0

    ok, reason = ensure_legacy_opening_snapshot(client, book_date)
    print(f"{'ok' if ok else 'error'}: {reason} (book_date={book_date.isoformat()})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
