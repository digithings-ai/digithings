#!/usr/bin/env python3
"""Plan / dry-run helper for #2589 ``legacy_opening_snapshot`` lot seed.

Computes opening share quantities from the latest ``positions`` book × ``nav_history``
÷ mark (entry/current/close). Does **not** invent historical fills/costs for P&L —
this is a labeled cold-start so residuals match the book before `--require-ledger`.

Full INSERT of the migration-069 chain is intentionally gated: run with ``--apply``
only after reviewing dry-run output against core. Default is dry-run.
"""

from __future__ import annotations

import argparse
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))


def _dec(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


def opening_shares(*, weight_pct: Decimal, nav: Decimal, price: Decimal) -> Decimal:
    """Shares for a target weight percent at NAV and mark (same quantum as ledger_io)."""
    if price <= 0 or nav <= 0 or weight_pct <= 0:
        return Decimal(0)
    raw = (weight_pct / Decimal(100)) * nav / price
    return raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Reserved: write legacy_opening_snapshot chain (not yet implemented — dry-run only).",
    )
    ap.add_argument("--date", default=None, help="Book date YYYY-MM-DD (default: latest positions).")
    args = ap.parse_args()
    if args.apply:
        print(
            "error: --apply is not implemented yet; use dry-run to review quantities, "
            "then land the INSERT path after review (#2589).",
            file=sys.stderr,
        )
        return 2
    print(
        "dry-run only: connect CORE_SUPABASE_* and print planned opening lots "
        f"(date={args.date or 'latest'}). INSERT path lands in a follow-up commit."
    )
    print("Policy: one labeled legacy_opening_snapshot; no fabricated historical P&L.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
