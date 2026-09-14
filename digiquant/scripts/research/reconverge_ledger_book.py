#!/usr/bin/env python3
"""Plan (and optionally apply) ledger reconvergence onto the committed book.

Dry-run by default: prints the trades that would converge the executed ledger
onto the committed positions book, with the resulting notionals. ``--apply``
is a deliberate second step and only supports ``--mode catch-up`` in v1; the
backdated walk stays planning-only until the accounting restatement path lands
(#4010).

Usage:
    python digiquant/scripts/research/reconverge_ledger_book.py --book-date 2026-09-10
    python digiquant/scripts/research/reconverge_ledger_book.py --book-date 2026-09-10 --apply

Env:
    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (loaded from digiquant/config/supabase.env).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as dt_date
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    src = str(_REPO_ROOT / "digiquant" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


_ensure_importable()

from digiquant.dashboard.tenancy import eq_house_workspace  # noqa: E402
from digiquant.research.supabase_io import (  # noqa: E402
    SupabaseClient,
    SupabaseConfig,
    SupabaseNotConfiguredError,
    build_client,
)

try:  # pragma: no cover - optional local convenience
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _sb() -> SupabaseClient:
    try:
        return build_client(SupabaseConfig.from_env())
    except SupabaseNotConfiguredError as exc:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required") from exc
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install supabase") from exc


def _latest_positions_date(client: SupabaseClient) -> dt_date | None:
    res = (
        eq_house_workspace(client.table("positions").select("date"))
        .neq("ticker", "CASH")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    raw = rows[0].get("date")
    if not raw:
        return None
    return dt_date.fromisoformat(str(raw)[:10])


def _parse_date(raw: str, flag: str) -> dt_date:
    try:
        return dt_date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{flag} must be YYYY-MM-DD, got {raw!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plan ledger reconvergence onto the committed positions book (dry-run default)."
        )
    )
    parser.add_argument(
        "--book-date",
        help="target positions book date (YYYY-MM-DD). Default: latest non-CASH positions date.",
    )
    parser.add_argument(
        "--since",
        help="backdated mode start date (YYYY-MM-DD). Default: the book date.",
    )
    parser.add_argument(
        "--exec-date",
        help="catch-up execution date (YYYY-MM-DD). Default: the book date.",
    )
    parser.add_argument("--mode", choices=("catch-up", "backdated"), default="catch-up")
    parser.add_argument(
        "--min-notional",
        default="1.00",
        help="skip legs below this notional in USD (default 1.00).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the labeled reconvergence chain (catch-up only; dry-run otherwise).",
    )
    args = parser.parse_args(argv)

    from digiquant.portfolio.writers.reconvergence import (
        POLICY_VERSION_ID,
        apply_catch_up,
        plan_convergence,
        render_plan,
    )

    client = _sb()

    try:
        if args.book_date:
            book_date = _parse_date(args.book_date, "--book-date")
        else:
            book_date = _latest_positions_date(client)
        exec_date = _parse_date(args.exec_date, "--exec-date") if args.exec_date else None
        since = _parse_date(args.since, "--since") if args.since else None
        min_notional = Decimal(str(args.min_notional))
    except (ValueError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if book_date is None:
        print("error: no positions rows to converge from", file=sys.stderr)
        return 2

    try:
        plan = plan_convergence(
            client=client,
            book_date=book_date,
            exec_date=exec_date,
            mode=args.mode,
            since=since,
            min_notional=min_notional,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_plan(plan))

    if not args.apply:
        print(
            f"[dry-run] mode={args.mode} book_date={book_date.isoformat()} "
            f"policy={POLICY_VERSION_ID}"
        )
        return 0

    try:
        ok, reason = apply_catch_up(client=client, plan=plan)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{'ok' if ok else 'error'}: {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
