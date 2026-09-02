#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as dt_date
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _ensure_importable() -> None:
    """Add the monorepo ``*/src`` paths to sys.path so the portfolio writers import."""
    for rel in ("digiquant/src", "digigraph/src", "digibase/src", "digismith/src"):
        path = str(_REPO_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


# Bootstrap before importing digiquant packages — this file is also a standalone script.
_ensure_importable()
from digiquant.dashboard.tenancy import house_workspace_id  # noqa: E402
from digiquant.research.supabase_io import (  # noqa: E402
    SupabaseConfig,
    SupabaseNotConfiguredError,
    build_client,
)


def _house_id() -> str:
    return str(house_workspace_id())


def _eq_house(query: Any) -> Any:
    return query.eq("workspace_id", _house_id())


def _sb():
    try:
        return build_client(SupabaseConfig.from_env())
    except SupabaseNotConfiguredError as exc:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required") from exc
    except ImportError as exc:
        raise RuntimeError("pip install supabase") from exc


def _is_calendar_date(raw: str) -> bool:
    """True when `raw` is a plain ISO calendar date — `YYYY-MM-DD` and nothing more.

    Strictly narrower than :func:`_trading_day_only`, which parses with
    `datetime.fromisoformat` and so accepts `2026-08-19T09:35:00` as a Wednesday. That
    string then reaches `date.fromisoformat` downstream, which rejects it — so the loose
    gate would wave through a value nothing after it can use.
    """
    try:
        dt_date.fromisoformat(raw)
    except (TypeError, ValueError):
        return False
    return True


def _trading_day_only(d: str) -> bool:
    try:
        wd = datetime.fromisoformat(d).isoweekday()
        return 1 <= wd <= 5
    except (TypeError, ValueError):
        return False


def _prior_trading_date(execution_date: str) -> Optional[str]:
    """Previous calendar date that falls on Mon–Fri (US equity session proxy).

    **For `documents.date` walks only** — "the PM decision published the prior
    session" (Fri decision → Mon open). `resolve_rebalance_payload_fallback` and
    `main`'s ``--prior-trading-day-rebalance`` use it that way, as does
    ``backfill_position_event_reasons._resolve_rebalance_doc_date``.

    Do **not** use it to pick the book to diff a new book against: `positions` is
    not written every weekday, so the calendar proxy resolves to a date with no
    rows and every held name then looks like a fresh OPEN (#1743). Positions
    comparisons use :func:`_prior_book_date`.
    """
    try:
        cur = datetime.fromisoformat(execution_date).date()
    except (TypeError, ValueError):
        return None
    for _ in range(12):
        cur = cur - timedelta(days=1)
        if cur.weekday() < 5:
            return cur.isoformat()
    return None


def _prior_book_date(sb, execution_date: str) -> Optional[str]:
    """Latest `positions` date strictly before ``execution_date`` that holds a book.

    The comparison basis for the event ledger is the previous *committed book*, not
    the previous calendar weekday. The pipeline skips days (07-21, 07-22, 07-24 and
    07-30 have no `positions` rows), so the weekday proxy made EXIT unreachable —
    a dropped ticker never entered the diff — and classified every survivor as an
    OPEN with a null prior weight (#1743).

    Returns ``None`` when no earlier book exists at all (the first book ever
    committed, or an unparseable ``execution_date``). Callers must read that as
    "empty prior book" — every held name is then a genuine OPEN — and not as an
    error, which is why the old ``if not prior_d: return None`` guards are gone.
    """
    try:
        dt_date.fromisoformat(execution_date)
    except (TypeError, ValueError):
        return None
    res = (
        _eq_house(sb.table("positions").select("date"))
        .lt("date", execution_date)
        .neq("ticker", "CASH")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    d = rows[0].get("date")
    return str(d)[:10] if d else None


def _book_weights(sb, book_date: Optional[str]) -> Dict[str, float]:
    """Non-CASH ``TICKER -> weight_pct`` for one `positions` date ({} when absent)."""
    if not book_date:
        return {}
    res = (
        _eq_house(sb.table("positions").select("ticker,weight_pct")).eq("date", book_date).execute()
    )
    out: Dict[str, float] = {}
    for row in getattr(res, "data", None) or []:
        if not isinstance(row, dict):
            continue
        tk = row.get("ticker")
        if not tk or str(tk).upper() == "CASH":
            continue
        try:
            out[str(tk).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
    return out


# Desk Activity shows weight deltas at 1 decimal pp. A fill that does not move that
# display is a lot true-up, not a position change (house 2026-09-01 FXI/VGK/XLF).
_DESK_PP_DECIMALS = 1


def _desk_weight_unchanged(weight_pct: Optional[float], prev_weight_pct: Optional[float]) -> bool:
    """True when both weights exist and round to a 0.0pp move at desk precision."""
    if weight_pct is None or prev_weight_pct is None:
        return False
    delta = float(weight_pct) - float(prev_weight_pct)
    if not (delta == delta):  # NaN
        return False
    return round(delta, _DESK_PP_DECIMALS) == 0.0


def _event_kind_from_order_delta(
    *,
    fill: Any,
    weight_pct: Optional[float],
    prev_weight_pct: Optional[float],
) -> str:
    """Name the event from the prior→target weight delta that sized the order.

    Lot residual is fill-vs-intent reconciliation for OPEN/EXIT (a sell that
    consumes every share is still an EXIT even when H7 said trim — #1743) and
    for quantity-only targets with no approved weight. ADD vs TRIM vs HOLD
    comes from that same delta, never from a later ``positions`` join. A
    0.0pp display move cannot be ADD/TRIM.
    """
    if fill.is_sell:
        lot_kind = "EXIT" if fill.residual_quantity <= 0 else "TRIM"
    else:
        lot_kind = "OPEN" if fill.prior_quantity <= 0 else "ADD"
    if weight_pct is None or lot_kind in ("OPEN", "EXIT"):
        return lot_kind
    prev = 0.0 if prev_weight_pct is None else float(prev_weight_pct)
    if _desk_weight_unchanged(weight_pct, prev):
        return "HOLD"
    chg = float(weight_pct) - prev
    if chg > 0:
        return "ADD"
    if chg < 0:
        return "TRIM"
    return "HOLD"


def _parse_pct(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_open(sb, ticker: str, d: str) -> Optional[float]:
    res = (
        sb.table("price_history")
        .select("open")
        .eq("ticker", ticker)
        .eq("date", d)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    o = rows[0].get("open")
    return float(o) if o is not None else None


def _rebalance_payload_for_date(sb, rebalance_date: str) -> Optional[Dict[str, Any]]:
    """Load rebalance_decision for a given documents.date (fast path + fallback scan)."""
    res = (
        _eq_house(sb.table("documents").select("payload"))
        .eq("date", rebalance_date)
        .eq("document_key", "rebalance-decision.json")
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if rows:
        p = rows[0].get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return p

    res2 = (
        _eq_house(sb.table("documents").select("payload"))
        .eq("date", rebalance_date)
        .order("document_key", desc=True)
        .execute()
    )
    for r in getattr(res2, "data", None) or []:
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return p
    return None


def _rebalance_table_nonempty(payload: Dict[str, Any]) -> bool:
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    table = body.get("rebalance_table") if isinstance(body, dict) else None
    return isinstance(table, list) and len(table) > 0


def resolve_rebalance_payload_fallback(
    sb, execution_d: str
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    When no rebalance_decision row exists for documents.date == execution day, find the PM
    artifact used for that session: walk backward along prior trading days (Fri decision → Mon
    open), then search calendar neighbors (+/- days) like backfill_position_event_reasons.
    """
    d = execution_d
    for _ in range(25):
        p = _rebalance_payload_for_date(sb, d)
        if (
            isinstance(p, dict)
            and p.get("doc_type") == "rebalance_decision"
            and _rebalance_table_nonempty(p)
        ):
            return d, p
        pd = _prior_trading_date(d)
        if not pd or pd == d:
            break
        d = pd

    try:
        anchor = dt_date.fromisoformat(execution_d)
    except ValueError:
        return None, None
    order: List[dt_date] = [anchor]
    for i in range(1, 12):
        order.append(anchor + timedelta(days=i))
    for i in range(1, 16):
        order.append(anchor - timedelta(days=i))
    seen: Set[dt_date] = set()
    for ad in order:
        if ad in seen:
            continue
        seen.add(ad)
        ds = ad.isoformat()
        p = _rebalance_payload_for_date(sb, ds)
        if (
            isinstance(p, dict)
            and p.get("doc_type") == "rebalance_decision"
            and _rebalance_table_nonempty(p)
        ):
            return ds, p
    return None, None


def _event_tickers_for_date(sb, execution_date: str) -> Set[str]:
    res = (
        _eq_house(sb.table("position_events").select("ticker")).eq("date", execution_date).execute()
    )
    out: Set[str] = set()
    for r in getattr(res, "data", None) or []:
        if isinstance(r, dict) and r.get("ticker"):
            out.add(str(r["ticker"]))
    return out


def _prior_position_weight(sb, prior_date: Optional[str], ticker: str) -> Optional[float]:
    if not prior_date:
        return None
    res = (
        _eq_house(sb.table("positions").select("weight_pct"))
        .eq("date", prior_date)
        .eq("ticker", ticker)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    return _parse_pct(rows[0].get("weight_pct"))


# Compatibility projection labels (#2422 / Task 2.5). Historical prose rows stay
# ``legacy`` permanently; ledger paper-fill projections stamp ``authoritative``.
BOOK_SOURCE_LEGACY = "legacy"
BOOK_SOURCE_AUTHORITATIVE = "authoritative"


def _with_book_source(events: List[Dict[str, Any]], book_source: str) -> List[Dict[str, Any]]:
    """Return shallow copies stamped with ``book_source`` (never mutates inputs).

    T0 (#5-T0): also stamps ``workspace_id`` here, the single choke point every
    ``position_events`` upsert in this script passes through. The column is NOT NULL
    as of migration 097 (with a house-workspace column DEFAULT as a legacy-writer
    safety net); this script is patched to pass it explicitly like every other writer
    this WP touches, rather than relying on the fallback.
    """
    house_id = str(house_workspace_id())
    out: List[Dict[str, Any]] = []
    for event in events:
        row = dict(event)
        row["book_source"] = book_source
        row["workspace_id"] = house_id
        out.append(row)
    return out


def _hold_events_for_positions_not_in_rebalance(
    sb, execution_date: str, skip_tickers: Set[str], *, prior_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    For every held line in `positions` on execution_date whose ticker is not in skip_tickers,
    emit a HOLD ledger row so Activity shows the full book.
    skip_tickers should include rebalance_table tickers and any tickers already present in
    position_events for this date (so we do not overwrite OPEN/TRIM/etc.).

    ``prior_date`` is the comparison book for ``prev_weight_pct``. When omitted it is
    ``_prior_book_date(execution_date)`` (legacy prose callers). The ledger path must
    pass ``_prior_book_date(run_date)`` so HOLD uses the same prior as fill projection
    and does not display a later book's move.
    """
    res = (
        _eq_house(sb.table("positions").select("ticker,weight_pct,thesis_id,rationale"))
        .eq("date", execution_date)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    prior_d = _prior_book_date(sb, execution_date) if prior_date is None else prior_date
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not ticker or not isinstance(ticker, str):
            continue
        if str(ticker).upper() == "CASH":
            continue
        if ticker in skip_tickers:
            continue
        w = _parse_pct(row.get("weight_pct"))
        if w is None or w <= 0:
            continue
        prev_w = _prior_position_weight(sb, prior_d, ticker)
        price = _fetch_open(sb, ticker, execution_date)
        reason = row.get("rationale")
        if isinstance(reason, str) and reason.strip():
            reason_s = reason.strip()
        else:
            reason_s = (
                "Held — position on book; not listed in rebalance_table for this session "
                "(synced via positions snapshot)."
            )
        out.append(
            {
                "date": execution_date,
                "ticker": ticker,
                "event": "HOLD",
                "weight_pct": w,
                "prev_weight_pct": prev_w,
                "price": price,
                "reason": reason_s,
                "thesis_id": row.get("thesis_id"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# The authoritative path (Task 2.4, #2420)
#
# Everything below this block reconstructs the day's events from prose — the digest
# snapshot or the mutable `positions` book — and disagrees with itself when the two
# disagree. This block instead reads what the portfolio actually did from the
# migration-069 ledger: one row per fill, written by the process that filled it, from the
# order it filled.
#
# The prose builders are deliberately still here. Production's migration tail is 065, so
# the ledger tables do not yet exist there and the ledger is the fallback's fallback until
# 069/070 are applied and H9 has written a commit row. They also carry the whole #1743
# regression suite (the incident where the weight-diff ladder made EXIT unreachable and
# classified every survivor as an OPEN). Removing them is a post-cutover follow-up, gated
# on production reaching 070 — not part of this change. `--require-ledger` is the lever
# that makes a silent fallback fatal once that is true.
# ---------------------------------------------------------------------------


def _open_marks(sb, tickers: List[str], d: str) -> Dict[str, Decimal]:
    """Declared opens for `tickers` on `d`, in one batched read, as `Decimal`.

    The executor needs a mark per symbol before it will fill anything, and the symbol list
    comes from the ledger itself (`pending_symbols`). One `in_` read rather than the
    per-ticker `_fetch_open` loop the legacy paths use: the set is bounded by the day's
    pending orders (~30), and a row-per-symbol round trip is the shape #2484 exists to
    stop adding to. Tickers with no row, a null open, or a non-finite one are simply
    absent — the executor rejects those orders `data_unavailable` rather than filling at
    a guessed price.

    `Decimal(str(raw))`, never `float(raw)`: this mark becomes a fill price and then a
    lot's cost basis, and the ledger's whole numeric contract is that money never passes
    through binary floating point. Every other path in this file returns floats because
    `position_events` is a display table; this one feeds the record of what was bought.
    """
    if not tickers:
        return {}
    res = (
        sb.table("price_history")
        .select("ticker,open")
        .in_("ticker", sorted(set(tickers)))
        .eq("date", d)
        .execute()
    )
    marks: Dict[str, Decimal] = {}
    for row in getattr(res, "data", None) or []:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        raw = row.get("open")
        if not ticker or raw is None:
            continue
        try:
            price = Decimal(str(raw))
        except (TypeError, ValueError, InvalidOperation):
            continue
        # `is_finite()` first, and not merely for tidiness. `price_history.open` is a bare
        # `numeric` with no CHECK, and Postgres `numeric` stores `NaN` and `Infinity`, both
        # of which `Decimal(str(raw))` parses happily. `Decimal("NaN") > 0` *raises*
        # `InvalidOperation`, and this call sits outside the decline contract — so a single
        # poisoned row would take down the morning job rather than skipping one symbol.
        # `Decimal("Infinity") > 0` is worse for being quiet here: it clears the gate,
        # becomes a mark, and dies later inside `PaperExecution`, whose `PositivePrice` sets
        # `allow_inf_nan=False`. Neither is a declared price, so both take the same exit as
        # a null: absent from `marks`, and `data_unavailable` on the ledger.
        if price.is_finite() and price > 0:
            marks[str(ticker).upper()] = price
    return marks


def resolve_execution_venue_for_run(workspace_id: Optional[str] = None) -> str:
    """execution venue-dispatch seam (K4).

    House cron passes ``workspace_id=None`` → always ``paper_internal``, so the
    existing ``build_events_from_paper_fills`` path and its outputs stay
    byte-identical. External venues are reachable only when
    ``DIGIQUANT_EXECUTION_ROUTING`` (alias ``OLYMPUS_KAIROS_ROUTING``) is on
    *and* a workspace with an active paper ``broker_connections`` row is
    supplied — that path is wired by the execution router, not by mutating
    the paper-fill writer.

    Invalid / empty ``DIGIQUANT_EXECUTION_WORKSPACE_ID`` values warn and fall back to
    ``None`` (house) rather than crashing the open job.

    Returns the venue's string value (``ExecutionVenue`` value) so this script
    does not need a top-level digiquant import at module load time.
    """
    _ensure_importable()
    from uuid import UUID

    from digiquant.execution.policy import resolve_venue

    resolved: Optional[UUID] = None
    raw = (workspace_id or "").strip()
    if raw:
        try:
            resolved = UUID(raw)
        except ValueError:
            print(
                f"⚠️  DIGIQUANT_EXECUTION_WORKSPACE_ID={raw!r} is not a valid UUID; "
                f"treating as house (paper_internal).",
                file=sys.stderr,
            )
            resolved = None
    return resolve_venue(resolved).value


def build_events_from_paper_fills(
    sb,
    run_d: str,
    execution_d: str,
    now: Optional[datetime] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Book the ledger's pending orders and project the fills into `position_events`.

    `run_d` is the decision date (the date H9 committed a chain for) and `execution_d` the
    morning the fills happen — normally the next trading day, which is why the two are
    separate.

    Two different "nothing" answers, and the caller must not conflate them:

    * ``(None, reason)`` — **the ledger declined to speak.** The kill switch is off, no
      commit exists for `run_d`, a ledger read raised (the tables are not there yet), or
      a date argument is not a calendar date. Falling back to a prose reconstruction is
      legitimate. `reason` names which one it was, because each implies a different
      operator action.
    * ``([], "")`` — **the ledger spoke and nothing traded.** A quiet day. HOLD continuity
      rows still belong on the book, but reconstructing events from prose would be
      inventing activity the authority says did not happen.

    Only the read-only probe is guarded. The `execute_pending_orders` call below is
    deliberately left bare: it *writes*, and a half-written fill must fail loudly rather
    than degrade into a prose reconstruction that silently disagrees with the rows already
    on the record. The probe is a sufficient existence test because migration 069 creates
    all eight ledger tables in one transaction — either they are all there or none are —
    and it touches two of them (`commits` via `ledger_is_authoritative`, `order_intents`
    via `pending_symbols`).
    """
    _ensure_importable()
    try:
        from digiquant.portfolio.models.position_event import (
            PositionEventRow,
        )
        from digiquant.portfolio.writers.execution_io import (
            approved_weights,
            execute_pending_orders,
            ledger_is_authoritative,
            pending_symbols,
        )
        from digiquant.portfolio.writers.ledger_io import ledger_enabled
        from digiquant.portfolio.writers.opening_snapshot import (
            COLD_START_DECLINE,
            cold_start_requires_seed,
            ensure_legacy_opening_snapshot,
        )
    except ImportError as exc:
        return None, f"the digiquant package is not importable from this script ({exc})"

    if not ledger_enabled():
        return None, "the DIGIQUANT_PORTFOLIO_LEDGER kill switch is off"

    # Parsed here, inside the decline contract, rather than at the first use below. This
    # function's promise to its caller is `(None, reason)` on every way the ledger can
    # fail to speak, and a hand-typed `--rebalance-date` is one of those ways: an
    # unguarded parse would raise out of a function documented never to, taking the prose
    # fallback down with it. `main` rejects a malformed date up front with exit 2, so
    # reaching this branch means a programmatic caller, which still deserves the contract.
    try:
        run_date = dt_date.fromisoformat(run_d)
        execution_date = dt_date.fromisoformat(execution_d)
    except (TypeError, ValueError) as exc:
        return None, f"a date argument is not an ISO-8601 calendar date ({exc})"
    stamp = now or datetime.now(timezone.utc)

    try:
        authoritative = ledger_is_authoritative(client=sb, run_date=run_date)
        symbols = pending_symbols(client=sb, run_date=run_date)
        approved = approved_weights(client=sb, run_date=run_date)
    except Exception as exc:  # a missing ledger table is the pre-cutover state, not a bug
        return None, f"a portfolio-ledger read failed, so the tables are likely absent ({exc})"

    if not authoritative:
        return None, f"no portfolio_ledger_commits row for run_date={run_d}"

    # Cold-start / opening snapshot (#2589): empty lots + non-empty prior book must not
    # reach execute_pending_orders (residuals would invent OPEN/EXIT). Auto-ensure once;
    # if still cold after, decline so --require-ledger exits 3 instead of mislabeling.
    # The prior is the book *before* ``run_d`` — H9 already wrote today's targets onto
    # ``run_date`` before the open, so ``_prior_book_date(execution_d)`` would compare
    # the fill against that new book and project ADD/TRIM of +0.0pp.
    prior_book_d = _prior_book_date(sb, run_d)
    prior_book_date = None
    if prior_book_d:
        try:
            prior_book_date = dt_date.fromisoformat(prior_book_d)
        except ValueError:
            prior_book_date = None
    try:
        if prior_book_date is not None and cold_start_requires_seed(
            client=sb, book_date=prior_book_date
        ):
            ok, seed_reason = ensure_legacy_opening_snapshot(sb, prior_book_date, now=stamp)
            if not ok:
                return None, seed_reason
            if cold_start_requires_seed(client=sb, book_date=prior_book_date):
                return None, COLD_START_DECLINE
    except Exception as exc:
        return None, f"a portfolio-ledger cold-start probe failed ({exc})"

    result = execute_pending_orders(
        client=sb,
        run_date=run_date,
        executed_date=execution_date,
        marks=_open_marks(sb, symbols, execution_d),
        now=stamp,
    )
    if not result.authoritative:
        # execute_pending_orders re-checks the switch and the commit row itself. Reaching
        # here means one of them changed between the probe and the call.
        return None, "the ledger stopped being authoritative between the probe and the write"

    for rejection in result.rejections:
        print(
            f"⛔ {rejection.symbol}: order not filled ({rejection.reason}) — recorded as "
            f"rejected on the ledger, no position_events row written."
        )
    if result.already_booked:
        print(
            f"↩️  {len(result.already_booked)} order(s) were already filled on a previous run "
            f"({', '.join(result.already_booked)}) — fills are immutable, nothing re-booked."
        )
    if result.rejections and not result.fills:
        # Without this line the run ends on `_record_ledger_events`' "booked no fills"
        # summary, which reads as a quiet day. The ledger had orders and refused every
        # one of them — a different situation, and the only one of the two worth paging on.
        print(
            f"⚠️  the ledger was authoritative for run_date={run_d} and rejected all "
            f"{len(result.rejections)} order(s) — this was not a quiet day."
        )

    prior_weights = _book_weights(sb, prior_book_d)

    events: List[Dict[str, Any]] = []
    for fill in result.fills:
        weight = approved.get(fill.symbol)
        # approved_weight is a 0..1 fraction; position_events.weight_pct is in percent.
        # The ×100 happens in Decimal and only then becomes a float, because binary floats
        # do not survive the scaling: float(Decimal("0.07")) * 100 is 7.000000000000001,
        # and 0.29 comes out 28.999999999999996. Writing those into a numeric column would
        # make ordinary weights look like rounding artefacts.
        weight_pct = float(weight * 100) if weight is not None else None
        prev_weight_pct = prior_weights.get(fill.symbol)
        event_kind = _event_kind_from_order_delta(
            fill=fill,
            weight_pct=weight_pct,
            prev_weight_pct=prev_weight_pct,
        )
        row = PositionEventRow(
            date=execution_d,
            ticker=fill.symbol,
            event=event_kind,
            weight_pct=weight_pct,
            # Display-only: the pre-commit ``positions`` book (``_prior_book_date(run_d)``),
            # which is the same prior H8/ledger used to size the ``OrderIntent``. Never the
            # ``run_date`` book H9 already wrote before the open.
            prev_weight_pct=prev_weight_pct,
            price=float(fill.price),
            reason=(
                f"{event_kind} — filled {fill.quantity} share(s) at {fill.price} from order "
                f"intent {fill.order_intent_id} (portfolio ledger paper execution "
                f"{fill.execution_id}, decision run_date {run_d}). Prior weight shown "
                f"from the {prior_book_d or 'unavailable'} positions book, for display only."
            ),
            thesis_id=None,
            book_source=BOOK_SOURCE_AUTHORITATIVE,
        )
        events.append(row.to_postgrest_row())
    return events, ""


def build_events_from_digest_snapshot(sb, execution_d: str) -> Optional[List[Dict[str, Any]]]:
    """
    When `rebalance-decision.json` is not published for this date, derive OPEN/TRIM/ADD/HOLD/EXIT
    from `daily_snapshots.snapshot.portfolio.proposed_positions` (post-trade targets) vs the
    weights of the prior *committed book* (:func:`_prior_book_date`), using market-open prices
    for execution_d.
    """
    res = sb.table("daily_snapshots").select("snapshot").eq("date", execution_d).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    raw = rows[0].get("snapshot")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    port = raw.get("portfolio")
    if not isinstance(port, dict):
        return None
    pp = port.get("proposed_positions")
    if not isinstance(pp, list) or not pp:
        return None
    targets: Dict[str, float] = {}
    for row in pp:
        if not isinstance(row, dict):
            continue
        t = row.get("ticker")
        if not t or t == "CASH":
            continue
        try:
            targets[str(t).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
    prior_d = _prior_book_date(sb, execution_d)
    prior_w = _book_weights(sb, prior_d)
    all_tickers = set(prior_w) | set(targets)
    out: List[Dict[str, Any]] = []
    eps = 0.0001
    basis = f"prior committed book {prior_d}" if prior_d else "no prior committed book"
    for t in sorted(all_tickers):
        prev = prior_w.get(t, 0.0)
        rec = targets.get(t, 0.0)
        chg = rec - prev
        if prev <= eps and rec > eps:
            ev = "OPEN"
        elif prev > eps and rec <= eps:
            ev = "EXIT"
        elif chg < -eps:
            ev = "TRIM"
        elif chg > eps:
            ev = "ADD"
        else:
            ev = "HOLD"
        price = _fetch_open(sb, t, execution_d)
        out.append(
            {
                "date": execution_d,
                "ticker": t,
                "event": ev,
                "weight_pct": rec,
                "prev_weight_pct": prev if prev > eps else None,
                "price": price,
                "reason": (
                    f"Derived from digest snapshot proposed_positions vs {basis} "
                    "(no rebalance_decision.json for this date)."
                ),
                "thesis_id": None,
            }
        )
    return out if out else None


def build_events_from_positions_book(sb, execution_d: str) -> Optional[List[Dict[str, Any]]]:
    """
    When digest `proposed_positions` is absent, infer OPEN/TRIM/ADD/HOLD/EXIT from the book
    recorded in `positions` on execution_d vs the prior *committed book*
    (:func:`_prior_book_date`) — the last date that actually has `positions` rows, which is
    not necessarily the prior weekday.
    """
    res = (
        _eq_house(sb.table("positions").select("ticker,weight_pct,thesis_id"))
        .eq("date", execution_d)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    targets: Dict[str, float] = {}
    thesis: Dict[str, Optional[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        t = row.get("ticker")
        if not t or t == "CASH":
            continue
        try:
            targets[str(t).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
        tid = row.get("thesis_id")
        thesis[str(t).upper()] = str(tid) if tid else None
    if not targets:
        return None
    prior_d = _prior_book_date(sb, execution_d)
    prior_w = _book_weights(sb, prior_d)
    all_tickers = set(prior_w) | set(targets)
    out: List[Dict[str, Any]] = []
    eps = 0.0001
    basis = f"prior committed book {prior_d}" if prior_d else "no prior committed book"
    for t in sorted(all_tickers):
        prev = prior_w.get(t, 0.0)
        rec = targets.get(t, 0.0)
        chg = rec - prev
        if prev <= eps and rec > eps:
            ev = "OPEN"
        elif prev > eps and rec <= eps:
            ev = "EXIT"
        elif chg < -eps:
            ev = "TRIM"
        elif chg > eps:
            ev = "ADD"
        else:
            ev = "HOLD"
        price = _fetch_open(sb, t, execution_d)
        out.append(
            {
                "date": execution_d,
                "ticker": t,
                "event": ev,
                "weight_pct": rec,
                "prev_weight_pct": prev if prev > eps else None,
                "price": price,
                "reason": (
                    f"Derived from positions book vs {basis} "
                    "(digest proposed_positions unavailable; no rebalance_decision.json for this date)."
                ),
                "thesis_id": thesis.get(t),
            }
        )
    return out if out else None


def _record_ledger_events(sb, d: str, rebalance_d: str, ledger_events: List[Dict[str, Any]]) -> int:
    """Write the ledger-projected events plus HOLD continuity, and report what happened.

    `ledger_events` may legitimately be empty — the ledger spoke and nothing traded. The
    HOLD rows still go on so Activity stays continuous, but no prose reconstruction runs:
    the authority already said the day had no fills.
    """
    filled: Set[str] = {str(e["ticker"]) for e in ledger_events if e.get("ticker")}
    holds = _hold_events_for_positions_not_in_rebalance(
        sb,
        d,
        filled | _event_tickers_for_date(sb, d),
        prior_date=_prior_book_date(sb, rebalance_d),
    )
    # Ledger path owns the day: fills already carry authoritative; HOLD continuity under
    # ledger authority is stamped the same so Activity cannot mix unlabeled rows (#2422).
    events = _with_book_source(ledger_events + holds, BOOK_SOURCE_AUTHORITATIVE)
    if not events:
        print(
            f"✅ portfolio ledger is authoritative for run_date={rebalance_d} and booked no "
            f"fills for {d}; no positions on book to hold either — nothing to record."
        )
        return 0

    for e in events:
        sb.table("position_events").upsert(e, on_conflict="workspace_id,date,ticker").execute()

    # No null-price hint here on purpose: a ledger row's price *is* the fill price, so it
    # cannot be missing. Only the HOLD rows read price_history, hence the narrower count.
    null_px = sum(1 for e in holds if e.get("price") is None)
    if null_px:
        print(
            f"⚠️  {null_px} HOLD event(s) have null price (no price_history.open for {d} yet). "
            f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
        )
    print(
        f"✅ recorded {len(ledger_events)} authoritative fill event(s) from the portfolio "
        f"ledger (run_date={rebalance_d}) plus {len(holds)} HOLD row(s) for {d}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Record market-open execution events into position_events (OPEN/EXIT/TRIM/ADD/HOLD). "
        "Execution prices use price_history.open for --date (execution day). "
        "HOLD rows keep the ledger continuous on no-trade days."
    )
    ap.add_argument(
        "--date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="Execution session date YYYY-MM-DD (opens from this day)",
    )
    ap.add_argument(
        "--rebalance-date",
        default=None,
        help="documents.date for rebalance_decision (default: same as --date, or prior weekday with --prior-trading-day-rebalance)",
    )
    ap.add_argument(
        "--prior-trading-day-rebalance",
        action="store_true",
        help="Use rebalance_decision from the previous Mon–Fri, execute at opens on --date (e.g. Fri decision → Mon open).",
    )
    ap.add_argument(
        "--no-rebalance-fallback",
        action="store_true",
        help="Do not search nearby documents.dates when same-day rebalance_decision is missing (strict).",
    )
    ap.add_argument(
        "--no-digest-events",
        action="store_true",
        help="Do not derive events from daily_snapshots when rebalance_decision is missing.",
    )
    ap.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip the authoritative portfolio-ledger path and reconstruct from prose (#2420).",
    )
    ap.add_argument(
        "--require-ledger",
        action="store_true",
        help="Fail (exit 3) instead of falling back to prose when the ledger declines to speak. "
        "Use this once migration 070 is applied in production and H9 commits every run.",
    )
    args = ap.parse_args()
    d = args.date

    # Both dates are validated before anything else runs. `--rebalance-date` had no check
    # at all, and `--date`'s weekday gate accepts an ISO *datetime*, so either flag could
    # carry a value past this point that only fails much later, mid-read, as a traceback.
    for flag, value in (("--date", d), ("--rebalance-date", args.rebalance_date)):
        if value is not None and not _is_calendar_date(value):
            print(
                f"error: {flag} must be an ISO-8601 calendar date (YYYY-MM-DD), got {value!r}",
                file=sys.stderr,
            )
            return 2

    if not _trading_day_only(d):
        print("Skipping execution: non-trading day (weekend).")
        return 0

    if args.prior_trading_day_rebalance and args.rebalance_date:
        print(
            "error: use only one of --prior-trading-day-rebalance or --rebalance-date",
            file=sys.stderr,
        )
        return 2

    rebalance_d = args.rebalance_date
    if args.prior_trading_day_rebalance:
        rebalance_d = _prior_trading_date(d)
        if not rebalance_d:
            print("Could not resolve prior trading date for rebalance source.", file=sys.stderr)
            return 2
    elif not rebalance_d:
        rebalance_d = d

    if args.no_ledger and args.require_ledger:
        print("error: use only one of --no-ledger or --require-ledger", file=sys.stderr)
        return 2

    sb = _sb()

    # Execution venue-dispatch seam. House path: workspace_id is unset →
    # paper_internal → existing ledger paper fills, unchanged. External routing
    # is env-gated inside resolve_venue; this script does not submit to brokers.
    from digiquant.dashboard.envcompat import EXECUTION_WORKSPACE_ID, env_lookup

    venue = resolve_execution_venue_for_run(env_lookup(EXECUTION_WORKSPACE_ID) or None)
    if venue != "paper_internal":
        print(
            f"error: execute_at_open external venue {venue!r} requires the execution "
            f"router (route_pending_orders); this script keeps the paper_internal path only",
            file=sys.stderr,
        )
        return 4

    # Authoritative first. The prose paths below run only when the ledger declines.
    ledger_events: Optional[List[Dict[str, Any]]] = None
    if args.no_ledger:
        declined = "--no-ledger was passed"
    else:
        ledger_events, declined = build_events_from_paper_fills(sb, rebalance_d, d)
    if ledger_events is None:
        if args.require_ledger:
            print(
                f"error: --require-ledger was passed but the portfolio ledger is not "
                f"authoritative for run_date={rebalance_d}: {declined}",
                file=sys.stderr,
            )
            return 3
        print(f"↪️  portfolio ledger not authoritative ({declined}); using prose fallback.")
    else:
        return _record_ledger_events(sb, d, rebalance_d, ledger_events)

    payload = _rebalance_payload_for_date(sb, rebalance_d)
    if (
        not payload
        and not args.rebalance_date
        and not args.prior_trading_day_rebalance
        and not args.no_rebalance_fallback
    ):
        rd_fb, p_fb = resolve_rebalance_payload_fallback(sb, d)
        if p_fb:
            rebalance_d = rd_fb
            payload = p_fb
            print(
                f"Resolved rebalance_decision from documents.date={rebalance_d} "
                f"(no same-day row for {d}; using PM artifact search)."
            )
    if not payload:
        if not args.no_digest_events:
            digest_events = build_events_from_digest_snapshot(sb, d)
            if not digest_events:
                digest_events = build_events_from_positions_book(sb, d)
            if digest_events:
                digest_events = _with_book_source(digest_events, BOOK_SOURCE_LEGACY)
                for e in digest_events:
                    sb.table("position_events").upsert(
                        e, on_conflict="workspace_id,date,ticker"
                    ).execute()
                null_px = sum(1 for e in digest_events if e.get("price") is None)
                if null_px:
                    print(
                        f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                        f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
                    )
                trade_n = sum(1 for e in digest_events if e.get("event") != "HOLD")
                hold_n = len(digest_events) - trade_n
                print(
                    f"✅ recorded {len(digest_events)} event(s) from digest snapshot vs prior positions for {d} "
                    f"({trade_n} trade-related, {hold_n} HOLD) — no rebalance_decision.json for this date."
                )
                return 0
        print(
            f"No rebalance_decision payload for documents.date={rebalance_d}; filling from positions only."
        )
        extra = _with_book_source(
            _hold_events_for_positions_not_in_rebalance(sb, d, _event_tickers_for_date(sb, d)),
            BOOK_SOURCE_LEGACY,
        )
        if not extra:
            print("No positions rows for this date — nothing to record.")
            return 0
        for e in extra:
            sb.table("position_events").upsert(e, on_conflict="workspace_id,date,ticker").execute()
        null_px = sum(1 for e in extra if e.get("price") is None)
        if null_px:
            print(
                f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
            )
        print(f"✅ recorded {len(extra)} HOLD event(s) from positions snapshot only for {d}")
        return 0

    if rebalance_d != d:
        print(f"Using rebalance_decision from {rebalance_d} for execution on {d} (opens).")

    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    table = body.get("rebalance_table") if isinstance(body, dict) else None
    if not isinstance(table, list) or not table:
        print("rebalance_decision has no rebalance_table; filling from positions only.")
        extra = _with_book_source(
            _hold_events_for_positions_not_in_rebalance(sb, d, _event_tickers_for_date(sb, d)),
            BOOK_SOURCE_LEGACY,
        )
        if not extra:
            print("No positions rows for this date — nothing to record.")
            return 0
        for e in extra:
            sb.table("position_events").upsert(e, on_conflict="workspace_id,date,ticker").execute()
        null_px = sum(1 for e in extra if e.get("price") is None)
        if null_px:
            print(
                f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
            )
        print(f"✅ recorded {len(extra)} HOLD event(s) from positions snapshot only for {d}")
        return 0

    # Build events for every rebalance row (including HOLD) so quiet days still have ledger rows.
    events: List[Dict[str, Any]] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        action = row.get("action")
        if not ticker or not isinstance(ticker, str):
            continue

        action_u = str(action or "").upper()
        is_hold = action_u in ("HOLD", "")

        weight_pct = _parse_pct(row.get("recommended_pct"))
        prev_weight_pct = _parse_pct(row.get("current_pct"))
        weight_change_pct = _parse_pct(row.get("change_pct"))

        price = _fetch_open(sb, ticker, d)

        if is_hold:
            event = "HOLD"
        elif action_u in ("EXIT",):
            event = "EXIT"
        elif action_u in ("NEW",):
            event = "OPEN"
        elif action_u == "ADD":
            event = "ADD"
        elif action_u == "TRIM":
            event = "TRIM"
        else:
            # Legacy rows or unknown action: infer direction from weights (never emit REBALANCE).
            if weight_change_pct is not None and weight_change_pct < 0:
                event = "TRIM"
            elif weight_change_pct is not None and weight_change_pct > 0:
                event = "ADD"
            elif (
                prev_weight_pct is not None
                and weight_pct is not None
                and weight_pct < prev_weight_pct
            ):
                event = "TRIM"
            elif (
                prev_weight_pct is not None
                and weight_pct is not None
                and weight_pct > prev_weight_pct
            ):
                event = "ADD"
            else:
                event = "TRIM"

        rec: Dict[str, Any] = {
            "date": d,
            "ticker": ticker,
            "event": event,
            "weight_pct": weight_pct,
            "prev_weight_pct": prev_weight_pct,
            "price": price,
            "reason": row.get("rationale"),
            "thesis_id": None,
        }
        events.append(rec)

    table_tickers: Set[str] = {str(e["ticker"]) for e in events if e.get("ticker")}
    pre_existing = _event_tickers_for_date(sb, d)
    skip_for_gap = table_tickers | pre_existing
    gap_holds = _hold_events_for_positions_not_in_rebalance(sb, d, skip_for_gap)
    if gap_holds:
        events.extend(gap_holds)

    if not events:
        print("rebalance_table produced no rows after filtering, and no positions to backfill.")
        return 0

    if gap_holds and table_tickers:
        print(
            f"➕ {len(gap_holds)} extra ticker(s) on book but not in rebalance_table → HOLD rows "
            f"({', '.join(e['ticker'] for e in gap_holds)})"
        )
    elif gap_holds:
        print(
            f"➕ {len(gap_holds)} HOLD row(s) from positions snapshot "
            f"({', '.join(e['ticker'] for e in gap_holds)})"
        )

    # Upsert by date,ticker (current schema). Prose path is permanently legacy (#2422).
    events = _with_book_source(events, BOOK_SOURCE_LEGACY)
    for e in events:
        sb.table("position_events").upsert(e, on_conflict="workspace_id,date,ticker").execute()

    null_px = sum(1 for e in events if e.get("price") is None)
    if null_px:
        print(
            f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
            f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
        )

    hold_n = sum(1 for e in events if e.get("event") == "HOLD")
    trade_n = len(events) - hold_n
    print(
        f"✅ recorded {len(events)} execution event(s) at market open for {d} "
        f"({trade_n} trade-related, {hold_n} HOLD)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
