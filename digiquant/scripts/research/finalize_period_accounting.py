#!/usr/bin/env python3
"""
finalize_period_accounting.py

Phase 0 Task 3.2 (#2597): EOD finalizer for Olympus period accounting.

Loads authoritative opening holdings/cash, same-day paper fills, and closing
marks; runs the pure ``compute_period`` engine; persists private
``olympus_accounting_*`` rows via ``accounting.io``. H9 provisional NAV in
``nav_history`` / ``positions`` stays as continuity data and is never selected
as final.

Flags:
  --date YYYY-MM-DD   Period date (default: today UTC)
  --dry-run           Assemble + compute + report; never INSERT
  --shadow            Persist labeled period + reconcile vs legacy nav day return
                      (default when not --dry-run; also via OLYMPUS_ACCOUNTING_FINALIZER)

Writes estimated/incomplete/failed periods as labeled non-final rows. Only
``status=final`` with a complete child set is selectable via
``select_final_period``. Declines (exit 3) when the ledger is cold (open lots
empty while a positions book exists) so no mislabeled partial final is published.

Usage:
  python3 scripts/atlas/finalize_period_accounting.py --supabase
  python3 scripts/atlas/finalize_period_accounting.py --supabase --date YYYY-MM-DD
  python3 scripts/atlas/finalize_period_accounting.py --supabase --dry-run
  python3 scripts/atlas/finalize_period_accounting.py --supabase --shadow

Exit codes: 0 ok · 1 hard failure · 2 reconcile miss (--strict-reconcile) · 3 declined
Environment: SUPABASE_URL / CORE_SUPABASE_*, OLYMPUS_ACCOUNTING_FINALIZER
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any  # score:allow untyped any — heterogeneous Supabase client / row dicts
from uuid import UUID

from digiquant.olympus.accounting.engine import compute_period
from digiquant.olympus.accounting.io import (
    PersistResult,
    period_head,
    persist_period,
)
from digiquant.olympus.accounting.models import (
    AccountingPeriod,
    AccountingPolicy,
    BenchmarkBoundary,
    FillSide,
    MarkObservation,
    OpeningHolding,
    PeriodAccountingInput,
    PeriodFill,
    PeriodStatus,
)
from digiquant.olympus.hermes.models.portfolio_ledger import (
    DecisionAction,
    HoldingLotStatus,
)
from digiquant.olympus.hermes.writers.execution_io import (
    HOLDING_LOTS,
    _decimal,
    _symbol,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    APPROVED_TARGETS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
    _rows_for_date,
)
from digiquant.olympus.hermes.writers.opening_snapshot import cold_start_requires_seed
from digiquant.olympus.tenancy import house_workspace_id

logger = logging.getLogger(__name__)


def _eq_house(query: Any) -> Any:
    return query.eq("workspace_id", str(house_workspace_id()))


_ENV_MODE = "OLYMPUS_ACCOUNTING_FINALIZER"
_OFF = frozenset({"0", "off", "false", "no", "disabled"})
_DEFAULT_POLICY = "accounting-v1"
_BENCHMARK = "SPY"
_RECONCILE_ABS_TOL = Decimal("0.05")  # 5 bps on percent return scale (0.05%)
_EXIT_DECLINED = 3
# PostgREST / supabase-js default max_rows is 1000 (see digiquant/supabase/config.toml).
# Closed lots accumulate forever; an unbounded select silently truncates the opening book.
_LOT_PAGE_SIZE = 1000
_LOT_SELECT_COLS = "opened_by_execution_id,opened_at,run_date,quantity,status,closed_at,symbol"


class FinalizerDeclined(RuntimeError):
    """Inputs are not safe to finalize — leave the date provisional, write nothing."""


try:
    from supabase import create_client  # type: ignore[import-untyped]

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(Path(__file__).resolve().parents[2] / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def resolve_mode(*, cli_mode: str | None, dry_run: bool, shadow: bool) -> str:
    """Resolve effective mode: off | dry-run | shadow | on."""
    if dry_run:
        return "dry-run"
    if shadow:
        return "shadow"
    raw = (cli_mode or os.environ.get(_ENV_MODE) or "shadow").strip().lower()
    if raw in _OFF:
        return "off"
    if raw in {"on", "shadow", "off", "dry-run"}:
        return raw
    return "shadow"


def _mark_from_close(
    *,
    client: Any,
    symbol: str,
    as_of: date,
    observed_at: datetime,
) -> MarkObservation | None:
    resp = (
        client.table("price_history")
        .select("close, date")
        .eq("ticker", symbol)
        .eq("date", as_of.isoformat())
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    close = _decimal(rows[0].get("close"))
    if close is None or close <= 0:
        return None
    return MarkObservation(
        symbol=symbol,
        price=close,
        as_of=as_of,
        observed_at=observed_at,
    )


def _opening_cash(*, client: Any, period_date: date) -> Decimal:
    """Prior accounting closing cash, else nav_history cash, else zero."""
    prior = period_date - timedelta(days=1)
    # Walk back a few calendar days for weekends.
    for offset in range(0, 7):
        day = prior - timedelta(days=offset)
        head = period_head(client=client, period_date=day)
        if head is not None:
            cash = _decimal(head.get("closing_cash"))
            if cash is not None and cash >= 0:
                return cash
    resp = (
        _eq_house(client.table("nav_history").select("date, nav, cash_pct"))
        .lt("date", period_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if rows:
        nav = _decimal(rows[0].get("nav"))
        cash_pct = _decimal(rows[0].get("cash_pct"))
        if nav is not None and cash_pct is not None and nav > 0:
            return (nav * cash_pct / Decimal(100)).quantize(Decimal("0.01"))
        # Absolute dollar NAV is not always available; weight-only books use indexed NAV.
        # Fall through to positions CASH weight * indexed nav as a continuity estimate.
        if nav is not None and nav > 0:
            pos = (
                _eq_house(client.table("positions").select("ticker, weight_pct"))
                .eq("date", str(rows[0]["date"])[:10])
                .execute()
            )
            for prow in getattr(pos, "data", None) or []:
                if _symbol(prow.get("ticker")) == "CASH":
                    w = _decimal(prow.get("weight_pct")) or Decimal(0)
                    return (nav * w / Decimal(100)).quantize(Decimal("0.01"))
    return Decimal(0)


def _fetch_all_holding_lots(*, client: Any) -> list[dict[str, Any]]:
    """Page through ``HOLDING_LOTS`` so PostgREST ``max_rows`` cannot truncate the book."""
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        resp = (
            client.table(HOLDING_LOTS)
            .select(_LOT_SELECT_COLS)
            .order("opened_at")
            .range(start, start + _LOT_PAGE_SIZE - 1)
            .execute()
        )
        batch = list(getattr(resp, "data", None) or [])
        rows.extend(batch)
        if len(batch) < _LOT_PAGE_SIZE:
            break
        start += _LOT_PAGE_SIZE
    return rows


def _opening_quantities(*, client: Any, period_date: date) -> dict[str, Decimal]:
    """Live lot quantities strictly before ``period_date`` (EOD prior)."""
    rows = _fetch_all_holding_lots(client=client)
    cutoff = datetime.combine(period_date, time(0, 0), tzinfo=UTC).isoformat()

    opens: dict[str, dict[str, Any]] = {}
    closed: dict[str, Decimal] = {}
    for row in rows:
        key = str(row.get("opened_by_execution_id") or "")
        if not key:
            continue
        opened_at = str(row.get("opened_at") or "")
        run_date = str(row.get("run_date") or "")[:10]
        # Opening book: lots opened before the period day.
        if opened_at and opened_at >= cutoff:
            continue
        if not opened_at and run_date >= period_date.isoformat():
            continue
        qty = _decimal(row.get("quantity")) or Decimal(0)
        if str(row.get("status") or "") == HoldingLotStatus.CLOSED:
            closed_at = str(row.get("closed_at") or "")
            # Only count closes that happened before the period opens.
            if closed_at and closed_at >= cutoff:
                continue
            if not closed_at:
                # Closed without stamp — treat as pre-period if run_date before period.
                if run_date >= period_date.isoformat():
                    continue
            closed[key] = closed.get(key, Decimal(0)) + qty
        else:
            opens[key] = row

    qty_by_symbol: dict[str, Decimal] = {}
    for key, open_row in opens.items():
        opened = _decimal(open_row.get("quantity")) or Decimal(0)
        live = opened - closed.get(key, Decimal(0))
        if live <= 0:
            continue
        sym = _symbol(open_row.get("symbol"))
        if not sym or sym == "CASH":
            continue
        qty_by_symbol[sym] = qty_by_symbol.get(sym, Decimal(0)) + live
    return qty_by_symbol


def _fills_for_period(*, client: Any, period_date: date) -> list[PeriodFill]:
    """Paper fills executed on ``period_date``, with side from the decision chain."""
    resp = (
        client.table(PAPER_EXECUTIONS)
        .select("*")
        .eq("executed_date", period_date.isoformat())
        .execute()
    )
    fills_raw = list(getattr(resp, "data", None) or [])
    if not fills_raw:
        return []

    order_ids = [str(r.get("order_intent_id")) for r in fills_raw if r.get("order_intent_id")]
    orders_resp = (
        client.table(ORDER_INTENTS).select("*").in_("id", order_ids).execute()
        if order_ids
        else type("R", (), {"data": []})()
    )
    orders = {str(r["id"]): r for r in (getattr(orders_resp, "data", None) or []) if r.get("id")}

    # Decision action may live on a prior run_date; batch by dates present on orders.
    run_dates = sorted(
        {
            date.fromisoformat(str(o.get("run_date"))[:10])
            for o in orders.values()
            if o.get("run_date")
        }
    )
    actions: dict[str, DecisionAction] = {}
    for rd in run_dates:
        approved = {
            str(r["id"]): r
            for r in _rows_for_date(client=client, table=APPROVED_TARGETS, run_date=rd)
            if r.get("id")
        }
        requested = {
            str(r["id"]): r
            for r in _rows_for_date(client=client, table=REQUESTED_TARGETS, run_date=rd)
            if r.get("id")
        }
        decisions = {
            str(r["id"]): r
            for r in _rows_for_date(client=client, table=DECISION_INTENTS, run_date=rd)
            if r.get("id")
        }
        for oid, order in orders.items():
            if str(order.get("run_date") or "")[:10] != rd.isoformat():
                continue
            approved_id = str(order.get("approved_target_id") or "")
            requested_id = str(approved.get(approved_id, {}).get("requested_target_id") or "")
            decision_id = str(requested.get(requested_id, {}).get("decision_intent_id") or "")
            raw = decisions.get(decision_id, {}).get("action")
            try:
                actions[oid] = DecisionAction(str(raw))
            except ValueError:
                continue

    sell_actions = frozenset({DecisionAction.TRIM, DecisionAction.EXIT})
    out: list[PeriodFill] = []
    for row in fills_raw:
        oid = str(row.get("order_intent_id") or "")
        action = actions.get(oid)
        if action is None:
            logger.warning("skip fill %s — no decision action for order %s", row.get("id"), oid)
            continue
        side = FillSide.SELL if action in sell_actions else FillSide.BUY
        qty = _decimal(row.get("quantity"))
        price = _decimal(row.get("price"))
        if qty is None or price is None or qty <= 0 or price <= 0:
            continue
        fee = _decimal(row.get("fee")) or Decimal(0)
        slip = _decimal(row.get("slippage")) or Decimal(0)
        executed_at_raw = row.get("executed_at")
        if isinstance(executed_at_raw, datetime):
            executed_at = executed_at_raw
        else:
            executed_at = datetime.fromisoformat(str(executed_at_raw).replace("Z", "+00:00"))
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=UTC)
        out.append(
            PeriodFill(
                symbol=_symbol(row.get("symbol")),
                side=side,
                quantity=qty,
                price=price,
                fee=fee if fee >= 0 else Decimal(0),
                slippage=slip,
                executed_at=executed_at,
                execution_id=UUID(str(row["id"])) if row.get("id") else None,
            )
        )
    return out


def assemble_period_input(
    *,
    client: Any,
    period_date: date,
    policy: AccountingPolicy | None = None,
) -> PeriodAccountingInput:
    """Build engine input from ledger fills/lots + price_history marks."""
    policy = policy or AccountingPolicy(policy_version_id=_DEFAULT_POLICY)
    opening_qty = _opening_quantities(client=client, period_date=period_date)
    fills = _fills_for_period(client=client, period_date=period_date)
    symbols = sorted(set(opening_qty) | {f.symbol for f in fills})
    prior = period_date - timedelta(days=1)
    # Opening marks: last close on or before prior calendar day (ffill window).
    open_observed = datetime.combine(prior, time(21, 0), tzinfo=UTC)
    close_observed = datetime.combine(period_date, time(21, 0), tzinfo=UTC)
    opening_marks: list[MarkObservation] = []
    closing_marks: list[MarkObservation] = []
    for sym in symbols:
        # Prefer exact prior date; walk back up to 5 days for weekends.
        om: MarkObservation | None = None
        for offset in range(0, 6):
            om = _mark_from_close(
                client=client,
                symbol=sym,
                as_of=prior - timedelta(days=offset),
                observed_at=open_observed,
            )
            if om is not None:
                break
        if om is not None:
            opening_marks.append(om)
        cm = _mark_from_close(
            client=client,
            symbol=sym,
            as_of=period_date,
            observed_at=close_observed,
        )
        if cm is not None:
            closing_marks.append(cm)

    benchmark = None
    b_open = _mark_from_close(
        client=client, symbol=_BENCHMARK, as_of=prior, observed_at=open_observed
    )
    b_close = _mark_from_close(
        client=client, symbol=_BENCHMARK, as_of=period_date, observed_at=close_observed
    )
    if b_open is not None and b_close is not None:
        benchmark = BenchmarkBoundary(
            symbol=_BENCHMARK,
            period_date=period_date,
            opening_price=b_open.price,
            closing_price=b_close.price,
        )

    return PeriodAccountingInput(
        period_date=period_date,
        policy=policy,
        opening_cash=_opening_cash(client=client, period_date=period_date),
        opening_holdings=tuple(
            OpeningHolding(symbol=s, quantity=q) for s, q in sorted(opening_qty.items())
        ),
        opening_marks=tuple(opening_marks),
        closing_marks=tuple(closing_marks),
        fills=tuple(fills),
        benchmark=benchmark,
    )


def _legacy_nav_day_return_pct(*, client: Any, period_date: date) -> Decimal | None:
    """Legacy indexed NAV day return from ``nav_history`` (provisional H9 continuity)."""
    iso = period_date.isoformat()
    cur = _eq_house(client.table("nav_history").select("nav")).eq("date", iso).limit(1).execute()
    cur_rows = list(getattr(cur, "data", None) or [])
    prev = (
        _eq_house(client.table("nav_history").select("nav"))
        .lt("date", iso)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    prev_rows = list(getattr(prev, "data", None) or [])
    if not cur_rows or not prev_rows:
        return None
    n1 = _decimal(cur_rows[0].get("nav"))
    n0 = _decimal(prev_rows[0].get("nav"))
    if n0 is None or n1 is None or n0 <= 0:
        return None
    return ((n1 - n0) / n0) * Decimal(100)


def reconcile_shadow(
    *,
    period: AccountingPeriod,
    client: Any,
) -> tuple[bool, str]:
    """Compare finalized period return to provisional H9 nav day return."""
    if period.status is not PeriodStatus.FINAL:
        return True, f"period status={period.status.value} — skip numeric reconcile"
    if period.opening_equity <= 0:
        return True, "zero opening equity — skip reconcile"
    acct = ((period.closing_equity - period.opening_equity) / period.opening_equity) * Decimal(100)
    legacy = _legacy_nav_day_return_pct(client=client, period_date=period.period_date)
    if legacy is None:
        return True, f"no legacy nav pair — accounting return={acct}%"
    delta = abs(acct - legacy)
    ok = delta <= _RECONCILE_ABS_TOL
    msg = f"accounting={acct}% legacy_nav={legacy}% delta={delta}% tol={_RECONCILE_ABS_TOL}%"
    return ok, msg


def _assert_ledger_ready(*, client: Any, period_date: date) -> None:
    """Refuse when open lots are cold while a positions book still has holdings."""
    prior = period_date - timedelta(days=1)
    for offset in range(0, 7):
        book_date = prior - timedelta(days=offset)
        if cold_start_requires_seed(client=client, book_date=book_date):
            raise FinalizerDeclined(
                f"ledger cold for book_date={book_date.isoformat()} — seed "
                "legacy_opening_snapshot before EOD finalization (no partial final)"
            )


def finalize_one_day(
    *,
    client: Any,
    period_date: date,
    mode: str = "shadow",
    strict_reconcile: bool = False,
) -> tuple[AccountingPeriod, PersistResult | None, bool]:
    """Assemble → compute → (optional) persist → optional shadow reconcile."""
    if mode == "off":
        raise RuntimeError("finalize_one_day called with mode=off")

    _assert_ledger_ready(client=client, period_date=period_date)
    inp = assemble_period_input(client=client, period_date=period_date)
    period = compute_period(inp)

    result: PersistResult | None = None
    if mode == "dry-run":
        ok, msg = reconcile_shadow(period=period, client=client)
        logger.info(
            "dry-run %s status=%s reasons=%s reconcile=%s (%s)",
            period_date.isoformat(),
            period.status.value,
            [r.value for r in period.quality_reasons],
            "ok" if ok else "MISS",
            msg,
        )
        print(
            f"{'✅' if ok else '⚠️'} accounting {period_date}: DRY-RUN "
            f"status={period.status.value} id={period.id} — {msg}"
        )
        return period, None, ok

    # Persist every labeled status (final / estimated / incomplete / failed).
    # Only complete final heads are selectable; incomplete children never publish as final.
    result = persist_period(client=client, period=period)
    ok, msg = reconcile_shadow(period=period, client=client)
    logger.info(
        "finalize %s status=%s wrote=%s repaired=%s reconcile=%s (%s)",
        period_date.isoformat(),
        period.status.value,
        result.wrote,
        result.repaired,
        "ok" if ok else "MISS",
        msg,
    )
    print(
        f"{'✅' if ok else '⚠️'} accounting {period_date}: status={period.status.value} "
        f"id={period.id} wrote={result.wrote} repaired={result.repaired} — {msg}"
    )
    if strict_reconcile and not ok:
        raise SystemExit(2)
    return period, result, ok


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="Period date YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--supabase", action="store_true", help="Required flag for clarity")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report without INSERT",
    )
    ap.add_argument(
        "--shadow",
        action="store_true",
        help="Persist labeled period and reconcile vs legacy nav (default mode)",
    )
    ap.add_argument(
        "--mode",
        choices=("shadow", "on", "off", "dry-run"),
        default=None,
        help="Override OLYMPUS_ACCOUNTING_FINALIZER (default shadow)",
    )
    ap.add_argument(
        "--strict-reconcile",
        action="store_true",
        help="Exit 2 when shadow reconcile misses tolerance",
    )
    args = ap.parse_args()
    if not args.supabase:
        print("--supabase required", file=sys.stderr)
        return 1
    mode = resolve_mode(cli_mode=args.mode, dry_run=args.dry_run, shadow=args.shadow)
    if mode == "off":
        print("OLYMPUS_ACCOUNTING_FINALIZER=off — skipping")
        return 0
    period_date = date.fromisoformat(args.date) if args.date else datetime.now(tz=UTC).date()
    try:
        client = _sb()
        finalize_one_day(
            client=client,
            period_date=period_date,
            mode=mode,
            strict_reconcile=args.strict_reconcile,
        )
    except FinalizerDeclined as exc:
        print(f"⛔ declined: {exc}", file=sys.stderr)
        return _EXIT_DECLINED
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except Exception as exc:
        logger.exception("finalize_period_accounting failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
