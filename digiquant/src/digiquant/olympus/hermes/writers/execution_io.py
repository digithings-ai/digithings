"""Task 2.4 — the authoritative paper-fill writer (#2420).

:mod:`ledger_io` (H9) appends the decision→order half of the migration-069 chain and
stops at ``pending`` order intents. This module appends the other half: it consumes those
pending intents and books the fill, the position lot, and the order's terminal status.
Nothing else in the codebase may write ``portfolio_ledger_paper_executions`` or
``portfolio_ledger_holding_lots`` except this module and its owned helper
:mod:`opening_snapshot` (the labeled cutover seed).

The point of the task is *authority*. Before this, "what did the portfolio actually do
today" was reconstructed at read time from a prose digest snapshot or from the mutable
``positions`` book, and those reconstructions disagreed with each other. Here a fill is a
row that was written once, by the process that filled it, from the order it filled.

Four properties shape every line below.

**Append-only.** Like :mod:`ledger_io`: ``service_role`` holds SELECT + INSERT and a
trigger rejects UPDATE/DELETE/TRUNCATE, so ``upsert`` must not appear in this module and
an order is never "flipped" from pending to executed. Marking an order executed means
appending a *new* order-intent row, already ``status='executed'``, whose ``supersedes_id``
points back at the pending row it replaces.

**Direction is not on the order row.** ``portfolio_ledger_order_intents`` has no ``side``
column and CHECKs ``quantity > 0`` — the quantity is an absolute share count, and buy vs
sell lives in ``decision_intents.action`` three hops up the chain
(:func:`_directions_by_order`). Direction is deliberately *not* re-derived by diffing the
``positions`` book: that mutable, read-time-reconstructed state is the thing this task
exists to stop depending on.

**Every write is idempotent by construction, not by exception handling.** All four id
families are deterministic ``uuid5`` values derived from the row's own identity, so a
retry after a partial failure recomputes the *same* primary keys and collides instead of
duplicating. This matters most for ``holding_lots``, which carries no UNIQUE constraint —
a randomized lot id would let a retry silently double the position. The executor also
reads existing state first and writes only what is missing, so a crash between the fill
insert and the executed-intent insert is *repaired* on the next run rather than leaving a
filled order permanently reading ``pending``.

**A partial close is a partial close row.** A trim does not close a whole lot and does not
invent a replacement one. It appends one row per consumed lot lineage carrying
``status='closed'``, the *closed quantity*, and the original lot's ``open_price``, so a
lot's live size is ``opened.quantity - sum(closed rows sharing opened_by_execution_id)``
and a full exit is just the case where that difference reaches zero.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous Supabase row dicts
)
from uuid import UUID, uuid5

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.portfolio_ledger import (
    DecisionAction,
    HoldingLot,
    HoldingLotStatus,
    OrderIntent,
    OrderIntentStatus,
    OrderRejectionReason,
    PaperExecution,
    paper_execution_id,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
    _heads,
    _insert,
    _rows_for_date,
    _symbol,
    ledger_enabled,
)

logger = logging.getLogger(__name__)

HOLDING_LOTS = "portfolio_ledger_holding_lots"

_QUANTUM = Decimal("0.000001")
_MONEY_QUANTUM = Decimal("0.01")

# Separate namespaces per id family. One shared namespace would still be collision-free
# because the payload strings are prefixed, but a distinct namespace per family means a
# future change to one payload format cannot silently alias another family's ids.
_EXECUTED_INTENT_ID_NAMESPACE = UUID("b3d0f5c4-6a91-5f2e-8c47-1d9b3e6a0c85")
_LOT_ID_NAMESPACE = UUID("c7e14a92-2f83-5b6d-9a10-4e8c7d2b5f36")

# Actions that imply a sell. NO_OP and REJECT imply no order at all; if one nonetheless
# carries a pending intent the chain is inconsistent and the executor refuses to guess.
_SELL_ACTIONS = frozenset({DecisionAction.TRIM, DecisionAction.EXIT})


def executed_intent_id(pending_order_intent_id: UUID, executed_date: date) -> UUID:
    """Deterministic id for the ``executed`` row that supersedes a pending order.

    Mirrors :func:`paper_execution_id`'s reasoning, for the same reason and one more.
    Two rows superseding the same pending row are two heads of one chain, and
    :func:`ledger_io._heads` would then report a forked chain that
    ``ledger_io.append_commit_chain`` raises on — so a retry must recompute *this* id,
    not mint a fresh one.

    Unlike ``paper_execution_id`` this is not enforced by a model validator: an order
    intent id is free-form in general (``append_commit_chain`` legitimately mints
    ``uuid4`` for a fresh order), and only the executed-supersession row has an identity
    a retry must reproduce. The rule therefore belongs to this writer, not to the model.
    """
    return uuid5(
        _EXECUTED_INTENT_ID_NAMESPACE,
        f"executed:{pending_order_intent_id}:{executed_date.isoformat()}",
    )


def open_lot_id(execution_id: UUID) -> UUID:
    """Deterministic id for the lot a buy fill opens. One lot per opening fill."""
    return uuid5(_LOT_ID_NAMESPACE, f"open:{execution_id}")


def close_lot_id(*, closing_execution_id: UUID, opened_by_execution_id: UUID) -> UUID:
    """Deterministic id for the row recording that a sell closed part of one lot.

    Keyed by *both* executions because one sell can consume several lot lineages (one row
    each) and one lineage can be consumed by several sells over time (one row each), while
    the same sell against the same lineage is always the same row.
    """
    return uuid5(
        _LOT_ID_NAMESPACE,
        f"close:{closing_execution_id}:{opened_by_execution_id}",
    )


@dataclass(frozen=True)
class FillCosts:
    """Transaction costs for one fill, in **total dollars for the whole fill**.

    ``price`` is the *effective* fill price. ``slippage`` is signed:
    ``(price - declared mark) * quantity``, positive when the fill was worse than the
    mark. For a paper fill at the declared open all three are exact: the effective price
    *is* the mark, so fee and slippage are a measured ``0``, not an unknown (see
    migration 070's header).
    """

    price: Decimal
    fee: Decimal
    slippage: Decimal


@dataclass(frozen=True)
class Fill:
    """One booked paper fill, for the caller's manifest and projection.

    ``prior_quantity`` and ``residual_quantity`` are the symbol's live lot total either
    side of this fill, both *measured* from the lot lineages rather than inferred from
    ``action``. They exist so a projection can name the event from the position instead of
    from the label: a buy into nothing is an open and a buy on top of something is an add;
    a sell to zero is an exit and a sell to anything else is a trim. Deriving that from
    ``action`` alone would call a trim-to-zero a trim, which is exactly the class of
    mislabelling the #1743 incident was — 31 OPEN rows, and not one EXIT.
    """

    symbol: str
    action: DecisionAction
    order_intent_id: UUID
    execution_id: UUID
    quantity: Decimal
    price: Decimal
    fee: Decimal
    slippage: Decimal
    prior_quantity: Decimal = Decimal(0)
    residual_quantity: Decimal = Decimal(0)

    @property
    def is_sell(self) -> bool:
        return self.action in _SELL_ACTIONS


@dataclass(frozen=True)
class Rejection:
    """One pending order the executor refused to fill, with a closed reason code."""

    symbol: str
    order_intent_id: UUID
    reason: OrderRejectionReason


@dataclass(frozen=True)
class ExecutionResult:
    """What one at-open run booked.

    ``authoritative`` is the discriminator the caller needs before deciding that "no
    fills" means "nothing traded". It is False when no ``portfolio_ledger_commits`` row
    exists for ``run_date`` — i.e. H9 never appended a chain for that date, so the ledger
    has no opinion and an empty result says nothing about the day.
    """

    authoritative: bool
    fills: list[Fill]
    rejections: list[Rejection]
    already_booked: list[str]


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _shares(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _pending_quantity(raw: Any) -> Decimal:
    """Normalize a pending order's quantity for the fill/reject gate.

    Non-finite values must reach :func:`_rejection_reason` intact — ``_shares`` raises
    ``InvalidOperation`` on Infinity, which would crash the public executor before the
    gate can decline (#2497). Finite values are still share-quantized.
    """
    value = _decimal(raw) or Decimal(0)
    if not value.is_finite():
        return value
    return _shares(value)


def _intent_quantity(pending_row: dict[str, Any]) -> Decimal:
    """``OrderIntent.quantity`` is ``PositiveQuantity`` (finite, > 0).

    A pending head with a non-finite or non-positive quantity cannot be mirrored onto
    the terminal rejected row — Postgres ``numeric`` and Pydantic both refuse them.
    Stamp one share; ``rejection_reason`` and the absence of a fill are authoritative
    (#2497).
    """
    value = _decimal(pending_row.get("quantity")) or Decimal(0)
    if value.is_finite() and value > 0:
        return _shares(value)
    return Decimal("1")


def _decimal(raw: Any) -> Decimal | None:
    """Supabase returns numerics as str/int/float. Never float(); never a bare Decimal(float)."""
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


def ledger_is_authoritative(*, client: SupabaseClient, run_date: date) -> bool:
    """Whether the ledger is the authority for ``run_date``.

    The check that keeps authoritative-first honest. A *missing* ledger table fails loudly
    and is easy to handle; the dangerous state is tables that exist and return zero
    pending intents, which is indistinguishable from "nothing traded today" and would let
    the executor write nothing, with no error, while the day's real activity went
    unrecorded. A commit row is the discriminator: no commit for the run_date means H9
    never spoke for that date (pre-cutover, or a failed upstream run), so a caller may
    legitimately fall back to a legacy projection. A commit row with zero pending order
    heads is a genuine no-op day, and booking nothing is then correct.
    """
    return bool(_rows_for_date(client=client, table=COMMITS, run_date=run_date))


def _pending_order_heads(
    *,
    client: SupabaseClient,
    run_date: date,
    workspace_id: UUID | str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(pending heads, all order rows)`` for ``run_date``.

    Heads only, and by exclusion — ``supersedes_id IS NULL`` would match the permanent
    chain root, which after one recommit is the *stale* order (see
    :func:`ledger_io._heads`). A pending row that some later row supersedes was already
    replaced and must never be filled.

    ``workspace_id`` omitted ⇒ house (same as :func:`ledger_io._rows_for_date`). Overlay
    / Kairos callers pass the connection's workspace so private books stay isolated.
    """
    rows = _rows_for_date(
        client=client, table=ORDER_INTENTS, run_date=run_date, workspace_id=workspace_id
    )
    pending = [
        row
        for row in _heads(rows)
        if str(row.get("status") or "") == OrderIntentStatus.PENDING and row.get("symbol")
    ]
    return pending, rows


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in rows if row.get("id")}


def _directions_by_order(
    *,
    client: SupabaseClient,
    run_date: date,
    order_rows: list[dict[str, Any]],
    workspace_id: UUID | str | None = None,
) -> tuple[dict[str, DecisionAction], set[str]]:
    """Walk order → approved → requested → decision to recover each order's direction.

    Returns ``({order_intent_id: action}, {stale order_intent_ids})``. An order is *stale*
    when the approved target it descends from is no longer that symbol's approved head:
    H8 re-approved a different target for the same run_date, so this order is an artefact
    of a superseded decision and filling it would execute a target nobody approved.

    Three ``in_`` reads, not one per order: the chain fans in by id, and the fan-out is
    bounded by the day's symbol count (~30). The whole walk is scoped to ``run_date``
    because every table in it carries one. ``workspace_id`` omitted ⇒ house.
    """
    approved_rows = _rows_for_date(
        client=client, table=APPROVED_TARGETS, run_date=run_date, workspace_id=workspace_id
    )
    requested_rows = _rows_for_date(
        client=client, table=REQUESTED_TARGETS, run_date=run_date, workspace_id=workspace_id
    )
    decision_rows = _rows_for_date(
        client=client, table=DECISION_INTENTS, run_date=run_date, workspace_id=workspace_id
    )

    approved = _by_id(approved_rows)
    requested = _by_id(requested_rows)
    decisions = _by_id(decision_rows)
    approved_head_ids = {str(row["id"]) for row in _heads(approved_rows) if row.get("id")}

    actions: dict[str, DecisionAction] = {}
    stale: set[str] = set()
    for row in order_rows:
        order_id = str(row.get("id") or "")
        approved_id = str(row.get("approved_target_id") or "")
        if not order_id or not approved_id:
            continue
        if approved_id not in approved_head_ids:
            stale.add(order_id)
            continue
        requested_id = str(approved.get(approved_id, {}).get("requested_target_id") or "")
        decision_id = str(requested.get(requested_id, {}).get("decision_intent_id") or "")
        raw_action = decisions.get(decision_id, {}).get("action")
        try:
            actions[order_id] = DecisionAction(str(raw_action))
        except ValueError:
            continue
    return actions, stale


def _existing_fill_ids(
    *, client: SupabaseClient, order_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Fills already booked against these order intents, keyed by ``order_intent_id``.

    ``paper_executions`` has no ``run_date`` column — it is reachable only through the
    order intents it references (same constraint as
    :func:`ledger_io._frozen_symbols`), so the filter is on those ids alone.
    """
    if not order_ids:
        return {}
    resp = client.table(PAPER_EXECUTIONS).select("*").in_("order_intent_id", order_ids).execute()
    return {str(row.get("order_intent_id")): row for row in resp.data or []}


def _lot_rows(*, client: SupabaseClient, symbols: list[str]) -> list[dict[str, Any]]:
    """Every lot row for these symbols, across all run dates.

    Deliberately not filtered to ``status='open'``: under the partial-close convention a
    lineage's live size is its opening quantity minus the closed rows against it, so the
    closed rows *are* the data. Filtering them out would report every partially trimmed
    lot at full size. Unbounded in run_date but bounded by symbol (``in_`` on the day's
    tickers) and by one row per fill against them.
    """
    if not symbols:
        return []
    resp = client.table(HOLDING_LOTS).select("*").in_("symbol", symbols).execute()
    return list(resp.data or [])


@dataclass(frozen=True)
class _Lineage:
    """One lot lineage: the opening fill plus how much of it is still live."""

    opened_by_execution_id: str
    open_row: dict[str, Any]
    live: Decimal
    opened_at: str


def _lineages(rows: list[dict[str, Any]]) -> dict[str, list[_Lineage]]:
    """Live lot lineages per symbol, FIFO-ordered by ``opened_at``.

    ``live = opened.quantity - sum(closed rows sharing opened_by_execution_id)`` — the
    subtraction rule the partial-close convention implies. Lineages with nothing left are
    dropped; a negative residue means the ledger over-closed a lot, which is a real
    inconsistency, so it is logged rather than clamped silently.
    """
    opens: dict[str, dict[str, Any]] = {}
    closed: dict[str, Decimal] = {}
    for row in rows:
        key = str(row.get("opened_by_execution_id") or "")
        quantity = _decimal(row.get("quantity")) or Decimal(0)
        if not key:
            continue
        if str(row.get("status") or "") == HoldingLotStatus.CLOSED:
            closed[key] = closed.get(key, Decimal(0)) + quantity
        else:
            opens[key] = row

    by_symbol: dict[str, list[_Lineage]] = {}
    for key, open_row in opens.items():
        opened = _decimal(open_row.get("quantity")) or Decimal(0)
        live = opened - closed.get(key, Decimal(0))
        if live < 0:
            logger.error(
                "portfolio ledger: lot lineage %s is over-closed (opened %s, closed %s) — "
                "review portfolio_ledger_holding_lots for %s",
                key,
                opened,
                closed.get(key),
                _symbol(open_row.get("symbol")),
            )
            continue
        if live <= 0:
            continue
        by_symbol.setdefault(_symbol(open_row.get("symbol")), []).append(
            _Lineage(
                opened_by_execution_id=key,
                open_row=open_row,
                live=_shares(live),
                opened_at=str(open_row.get("opened_at") or ""),
            )
        )
    for lineages in by_symbol.values():
        lineages.sort(key=lambda item: item.opened_at)
    return by_symbol


def _execution_ids_with_lots(rows: list[dict[str, Any]]) -> set[str]:
    """Execution ids that already have at least one lot row, opening or closing.

    A buy's execution appears as an ``opened_by_execution_id``, a sell's as a
    ``closed_by_execution_id``; either one proves that execution's lot write landed.
    """
    return {
        str(row.get(column))
        for row in rows
        for column in ("opened_by_execution_id", "closed_by_execution_id")
        if row.get(column)
    }


def _recovered_lot_rows(
    *,
    execution_row: dict[str, Any],
    symbol: str,
    action: DecisionAction | None,
    lot_execution_ids: set[str],
    run_date: date,
    lineages: dict[str, list[_Lineage]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Lot rows for a fill that is on the record without any, or ``[]`` if it has them.

    The hole this closes: ``paper_executions``, ``holding_lots`` and ``order_intents`` are
    three separate INSERTs, and if the lot write fails after the fill lands, the order stays
    pending (its status row is written last) and the next run reaches the already-booked
    branch. Repairing only the status row there would retire the order with no lot behind
    it, and ``_live_quantity`` reads lots — so that position would be invisible forever:
    the next buy would book as an OPEN on top of shares already held, and a sell would find
    nothing to close. That is the #1743 mislabelling class, re-entered through a crash.

    Everything is taken from the immutable execution row, never from today's marks: the
    fill happened at a price the ledger already recorded, and a lot rebuilt from a fresh
    mark would give the position a cost basis the fill never had. ``open_lot_id`` and
    ``close_lot_id`` are derived from that execution id, so the rebuilt rows carry the ids
    the crashed run would have written — the repair is a re-derivation, not a new opinion.

    The recovered fill is deliberately *not* added to ``ExecutionResult.fills``. Its
    ``prior_quantity``/``residual_quantity`` would be measured against today's lots rather
    than the day it happened, and naming an event from a stale residual is the very error
    the measured-residual design removes. Lots are the durable record; a missing
    ``position_events`` row is a display gap to backfill, not a corrupted position.
    """
    execution_id = str(execution_row.get("id") or "")
    if not execution_id or execution_id in lot_execution_ids:
        return []
    if action is None or action not in (DecisionAction.ADD, *_SELL_ACTIONS):
        # Without a direction there is no way to know whether this fill opened or closed,
        # and guessing is the read-time reconstruction this task exists to remove.
        logger.error(
            "portfolio ledger: execution %s for %s has no lot rows and no derivable "
            "direction — its lots cannot be recovered",
            execution_id,
            symbol,
        )
        return []

    quantity = _shares(_decimal(execution_row.get("quantity")) or Decimal(0))
    price = _decimal(execution_row.get("price"))
    order_intent_id = str(execution_row.get("order_intent_id") or "")
    if quantity <= 0 or price is None or price <= 0 or not order_intent_id:
        logger.error(
            "portfolio ledger: execution %s for %s has no lot rows and is missing the "
            "quantity/price needed to rebuild them",
            execution_id,
            symbol,
        )
        return []

    rows = _lot_rows_for_fill(
        fill=Fill(
            symbol=symbol,
            action=action,
            order_intent_id=UUID(order_intent_id),
            execution_id=UUID(execution_id),
            quantity=quantity,
            price=price,
            fee=_decimal(execution_row.get("fee")) or Decimal(0),
            slippage=_decimal(execution_row.get("slippage")) or Decimal(0),
        ),
        run_date=run_date,
        lineages=lineages,
        now=now,
    )
    if rows:
        logger.warning(
            "portfolio ledger: execution %s for %s was on the record with no lot rows — "
            "a prior run's lot write did not land; rebuilding %s row(s) from the fill",
            execution_id,
            symbol,
            len(rows),
        )
    return rows


def _live_quantity(lineages: dict[str, list[_Lineage]], symbol: str) -> Decimal:
    """The symbol's live share count across its lot lineages."""
    return _shares(sum((item.live for item in lineages.get(symbol, [])), Decimal(0)))


def pending_symbols(*, client: SupabaseClient, run_date: date) -> list[str]:
    """Symbols carrying a pending order head on ``run_date``, sorted and de-duplicated.

    A caller has to supply ``marks`` to :func:`execute_pending_orders` but cannot know
    which symbols to price until it has read the chain — and reading the chain is this
    module's job, not the caller's. So the executor exposes the question rather than
    making every caller re-derive the heads-only, supersession-aware walk that
    :func:`_pending_order_heads` performs. The alternative, a marks *callable* invoked
    per symbol, would push one price read per symbol through a loop; this way the caller
    can fetch them in a single bounded query.

    Cheap and read-only: it is one ``order_intents`` select for the date, and it returns
    ``[]`` for a date the ledger never spoke for, so it is safe to call before
    :func:`ledger_is_authoritative`.
    """
    pending, _ = _pending_order_heads(client=client, run_date=run_date)
    return sorted({_symbol(row.get("symbol")) for row in pending if _symbol(row.get("symbol"))})


def approved_weights(*, client: SupabaseClient, run_date: date) -> dict[str, Decimal]:
    """Head approved portfolio weight per symbol for ``run_date``, as a 0..1 fraction.

    The only weight the ledger holds. ``portfolio_ledger_commits`` carries no NAV column,
    so a *position* weight cannot be derived from the lots — shares and a cost basis do
    not make a fraction of a portfolio without a denominator. What migration 069 does
    record is ``approved_targets.approved_weight``, H8's approved target, and that is what
    this returns: the weight the portfolio was *approved to hold*, not a weight measured
    from the book afterwards.

    Heads only, so a re-approval on the same ``run_date`` reports the surviving target and
    not the superseded one. Symbols whose approved target was expressed as a quantity
    rather than a weight are absent rather than zero — 069 requires one or the other, and
    a missing weight is unknown, not flat.
    """
    rows = _rows_for_date(client=client, table=APPROVED_TARGETS, run_date=run_date)
    weights: dict[str, Decimal] = {}
    for row in _heads(rows):
        symbol = _symbol(row.get("symbol"))
        weight = _decimal(row.get("approved_weight"))
        if symbol and weight is not None:
            weights[symbol] = weight
    return weights


def _zero_cost(*, price: Decimal, quantity: Decimal) -> FillCosts:
    """The paper venue: fill exactly at the declared mark.

    Both costs are ``0`` because both are *measured* as zero here, not unknown — the fill
    price and the mark are the same number by construction. No env knob gates this: a
    configurable fee that nothing ever sets would be config theatre, and a real cost model
    belongs to whatever later task introduces one, as a replacement for this function.
    """
    del quantity
    return FillCosts(price=price, fee=Decimal("0.00"), slippage=Decimal("0.00"))


def execute_pending_orders(
    *,
    client: SupabaseClient,
    run_date: date,
    executed_date: date,
    marks: dict[str, float | Decimal],
    now: datetime,
) -> ExecutionResult:
    """Book fills for every pending order head on ``run_date``. The authoritative path.

    ``marks`` is the declared open per symbol; a symbol with no usable mark is rejected
    ``data_unavailable`` rather than filled at a guessed price. ``run_date`` is the
    decision date and ``executed_date`` the date the fill happened — normally the next
    trading morning, which is why they are separate parameters.

    Returns without writing when :func:`ledger_enabled` is off (the Phase-0 rollback
    switch) or when no commit exists for ``run_date``; both cases report
    ``authoritative=False`` so the caller can tell "the ledger declined to speak" from
    "the ledger says nothing traded".
    """
    if not ledger_enabled():
        logger.info("portfolio ledger disabled — skipping authoritative paper execution")
        return ExecutionResult(authoritative=False, fills=[], rejections=[], already_booked=[])

    if not ledger_is_authoritative(client=client, run_date=run_date):
        logger.warning(
            "portfolio ledger: no portfolio_ledger_commits row for run_date %s — the ledger "
            "is not authoritative for that date and no fills will be booked",
            run_date.isoformat(),
        )
        return ExecutionResult(authoritative=False, fills=[], rejections=[], already_booked=[])

    pending, all_orders = _pending_order_heads(client=client, run_date=run_date)
    actions, stale = _directions_by_order(client=client, run_date=run_date, order_rows=pending)
    fills_by_order = _existing_fill_ids(
        client=client, order_ids=[str(r.get("id")) for r in all_orders if r.get("id")]
    )
    executed_ids = {
        str(row.get("id"))
        for row in all_orders
        if str(row.get("status") or "") == OrderIntentStatus.EXECUTED
    }
    prior_lot_rows = _lot_rows(
        client=client, symbols=sorted({_symbol(r.get("symbol")) for r in pending})
    )
    lineages = _lineages(prior_lot_rows)
    lot_execution_ids = _execution_ids_with_lots(prior_lot_rows)
    normalized_marks = {_symbol(k): _decimal(v) for k, v in marks.items()}

    execution_rows: list[dict[str, Any]] = []
    lot_rows: list[dict[str, Any]] = []
    intent_rows: list[dict[str, Any]] = []
    fills: list[Fill] = []
    rejections: list[Rejection] = []
    already_booked: list[str] = []

    # Sorted by (symbol, id), not symbol alone: `_rows_for_date` issues no ORDER BY, so
    # PostgREST's row order is unspecified, and a stable sort on symbol alone preserves
    # whatever order the read happened to return. Two orders on one symbol in one run must
    # consume lots in a fixed sequence — otherwise the same data books an EXIT one day and
    # an OPEN the next, which is precisely the mislabelling this module exists to end.
    for row in sorted(pending, key=lambda r: (_symbol(r.get("symbol")), str(r.get("id")))):
        order_id = str(row["id"])
        symbol = _symbol(row.get("symbol"))
        quantity = _pending_quantity(row.get("quantity"))
        existing = fills_by_order.get(order_id)

        if existing is not None:
            # The fill is already on the record and is immutable. What may be missing is
            # the terminal order status, the lot rows, or both — the writes below are three
            # separate statements, so a crash can land the fill and lose either follower.
            # Appending them now repairs the record instead of leaving a filled order
            # reading ``pending`` forever, or a position with no lot behind it.
            already_booked.append(symbol)
            repair_id = executed_intent_id(UUID(order_id), executed_date)
            if str(repair_id) not in executed_ids:
                intent_rows.append(
                    _executed_intent_row(pending_row=row, executed_date=executed_date, now=now)
                )
            lot_rows.extend(
                _recovered_lot_rows(
                    execution_row=existing,
                    symbol=symbol,
                    action=actions.get(order_id),
                    lot_execution_ids=lot_execution_ids,
                    run_date=run_date,
                    lineages=lineages,
                    now=now,
                )
            )
            continue

        reason = _rejection_reason(
            order_id=order_id,
            stale=stale,
            action=actions.get(order_id),
            quantity=quantity,
            mark=normalized_marks.get(symbol),
        )
        if reason is not None:
            rejections.append(
                Rejection(symbol=symbol, order_intent_id=UUID(order_id), reason=reason)
            )
            intent_rows.append(_rejected_intent_row(pending_row=row, reason=reason, now=now))
            continue

        action = actions[order_id]
        mark = normalized_marks[symbol]
        costs = _zero_cost(price=mark, quantity=quantity)
        execution_id = paper_execution_id(UUID(order_id), executed_date)

        fill = Fill(
            symbol=symbol,
            action=action,
            order_intent_id=UUID(order_id),
            execution_id=execution_id,
            quantity=quantity,
            price=costs.price,
            fee=costs.fee,
            slippage=costs.slippage,
            prior_quantity=_live_quantity(lineages, symbol),
        )
        execution_rows.append(
            PaperExecution(
                id=execution_id,
                order_intent_id=UUID(order_id),
                executed_date=executed_date,
                symbol=symbol,
                quantity=quantity,
                price=costs.price,
                fee=costs.fee,
                slippage=costs.slippage,
                executed_at=now,
                recorded_at=now,
            ).model_dump(mode="json")
        )
        lot_rows.extend(
            _lot_rows_for_fill(
                fill=fill,
                run_date=run_date,
                lineages=lineages,
                now=now,
            )
        )
        intent_rows.append(
            _executed_intent_row(pending_row=row, executed_date=executed_date, now=now)
        )
        # Read the residual back out of the lineages the call above just mutated rather
        # than computing prior ± quantity. The two differ when a sell exceeds the lots on
        # the record: the arithmetic would report a negative position, the measurement
        # reports the zero that is actually there. Two orders on one symbol in a single
        # run also chain correctly this way — the second one's prior is the first one's
        # residual, because both are read from the same running state.
        fills.append(replace(fill, residual_quantity=_live_quantity(lineages, symbol)))

    # FK order: a lot references its executions, so fills land first. The executed and
    # rejected order rows go last because nothing references them. Neither follower is in
    # the same transaction as the fill — PostgREST has no cross-table one — so a failure at
    # either leaves the fill on the record alone, and the repair branch above re-derives
    # whichever is missing on the next run. The window is closed, not merely narrow: the
    # order status is written *last*, so any follower that failed leaves the order pending,
    # and a pending order is exactly what brings the repair branch back to it.
    _insert(client=client, table=PAPER_EXECUTIONS, rows=execution_rows)
    _insert(client=client, table=HOLDING_LOTS, rows=lot_rows)
    _insert(client=client, table=ORDER_INTENTS, rows=intent_rows)

    return ExecutionResult(
        authoritative=True,
        fills=fills,
        rejections=rejections,
        already_booked=already_booked,
    )


def _rejection_reason(
    *,
    order_id: str,
    stale: set[str],
    action: DecisionAction | None,
    quantity: Decimal,
    mark: Decimal | None,
) -> OrderRejectionReason | None:
    """The closed reason code for refusing this order, or None to fill it."""
    if order_id in stale:
        return OrderRejectionReason.STALE_TARGET
    if action is None or action not in (DecisionAction.ADD, *_SELL_ACTIONS):
        # A broken chain, or a no_op/reject decision that nonetheless carries an order.
        # Either way the direction is not derivable from the recorded data, and guessing
        # it would be exactly the read-time reconstruction this task removes.
        return OrderRejectionReason.DATA_UNAVAILABLE
    # is_finite() before any comparison: Decimal NaN/sNaN raises InvalidOperation on
    # ``<=``, and Infinity clears ``<= 0`` then dies later in PaperExecution validation.
    # The marks signature is ``float | Decimal``, so float("nan") is in-bounds and must
    # decline rather than raise (#2497).
    if (
        mark is None
        or not mark.is_finite()
        or mark <= 0
        or not quantity.is_finite()
        or quantity <= 0
    ):
        return OrderRejectionReason.DATA_UNAVAILABLE
    return None


def _executed_intent_row(
    *, pending_row: dict[str, Any], executed_date: date, now: datetime
) -> dict[str, Any]:
    """The terminal ``executed`` row that supersedes ``pending_row``.

    ``run_date`` and ``symbol`` are copied from the pending row, not derived from
    ``executed_date``. That is a hard requirement, not a style choice: 069's supersession
    FK is composite — ``(supersedes_id, run_date, symbol)`` references
    ``(id, run_date, symbol)`` — and the at-open fill normally lands the morning *after*
    the decision, so a row stamped with ``executed_date`` would violate the FK.
    """
    order_id = UUID(str(pending_row["id"]))
    return OrderIntent(
        id=executed_intent_id(order_id, executed_date),
        approved_target_id=UUID(str(pending_row["approved_target_id"])),
        run_date=date.fromisoformat(str(pending_row["run_date"])),
        symbol=_symbol(pending_row.get("symbol")),
        quantity=_intent_quantity(pending_row),
        status=OrderIntentStatus.EXECUTED,
        supersedes_id=order_id,
        effective_at=now,
        recorded_at=now,
    ).model_dump(mode="json")


def _rejected_intent_row(
    *, pending_row: dict[str, Any], reason: OrderRejectionReason, now: datetime
) -> dict[str, Any]:
    """The terminal ``rejected`` row that supersedes ``pending_row``. No fill is written.

    A rejection is a real, typed outcome on the record — not a silently skipped symbol.
    ``ledger_io._frozen_symbols`` deliberately does not freeze on a rejected head, so the
    next commit is free to re-issue the order.
    """
    order_id = UUID(str(pending_row["id"]))
    return OrderIntent(
        id=uuid5(_EXECUTED_INTENT_ID_NAMESPACE, f"rejected:{order_id}:{reason.value}"),
        approved_target_id=UUID(str(pending_row["approved_target_id"])),
        run_date=date.fromisoformat(str(pending_row["run_date"])),
        symbol=_symbol(pending_row.get("symbol")),
        quantity=_intent_quantity(pending_row),
        status=OrderIntentStatus.REJECTED,
        supersedes_id=order_id,
        rejection_reason=reason,
        effective_at=now,
        recorded_at=now,
    ).model_dump(mode="json")


def _lot_rows_for_fill(
    *,
    fill: Fill,
    run_date: date,
    lineages: dict[str, list[_Lineage]],
    now: datetime,
) -> list[dict[str, Any]]:
    """The lot rows one fill produces, and the in-memory lineage bookkeeping it implies.

    A buy opens exactly one lot. A sell appends one ``closed`` row per lot lineage it
    consumes, FIFO, each carrying the *closed* quantity and the original lineage's
    ``open_price`` (its cost basis) and ``opened_at``/``run_date`` — the row describes a
    portion of that original lot, so copying the opening date keeps the lineage coherent,
    and *which* run closed it is recoverable through ``closed_by_execution_id``.

    ``lineages`` is mutated as it goes so two sells of the same symbol in one run cannot
    both consume the same shares.
    """
    if not fill.is_sell:
        lot = HoldingLot(
            id=open_lot_id(fill.execution_id),
            opened_by_execution_id=fill.execution_id,
            run_date=run_date,
            symbol=fill.symbol,
            quantity=fill.quantity,
            open_price=fill.price,
            status=HoldingLotStatus.OPEN,
            opened_at=now,
            recorded_at=now,
        )
        lineages.setdefault(fill.symbol, []).append(
            _Lineage(
                opened_by_execution_id=str(fill.execution_id),
                open_row=lot.model_dump(mode="json"),
                live=fill.quantity,
                opened_at=now.isoformat(),
            )
        )
        return [lot.model_dump(mode="json")]

    remaining = fill.quantity
    rows: list[dict[str, Any]] = []
    available = lineages.get(fill.symbol, [])
    consumed = 0
    for lineage in available:
        if remaining <= 0:
            break
        take = _shares(min(remaining, lineage.live))
        if take <= 0:
            consumed += 1
            continue
        open_price = _decimal(lineage.open_row.get("open_price"))
        opened_at = _parse_ts(lineage.open_row.get("opened_at")) or now
        lot_run_date = _parse_date(lineage.open_row.get("run_date")) or run_date
        if open_price is None or open_price <= 0:
            # open_price is NOT NULL and > 0 in 069; a lineage without one cannot be
            # closed without fabricating a cost basis, so it is skipped and reported.
            logger.error(
                "portfolio ledger: lot lineage %s for %s has no usable open_price — "
                "cannot record its close",
                lineage.opened_by_execution_id,
                fill.symbol,
            )
            consumed += 1
            continue
        rows.append(
            HoldingLot(
                id=close_lot_id(
                    closing_execution_id=fill.execution_id,
                    opened_by_execution_id=UUID(lineage.opened_by_execution_id),
                ),
                opened_by_execution_id=UUID(lineage.opened_by_execution_id),
                closed_by_execution_id=fill.execution_id,
                run_date=lot_run_date,
                symbol=fill.symbol,
                quantity=take,
                open_price=open_price,
                status=HoldingLotStatus.CLOSED,
                opened_at=opened_at,
                closed_at=max(now, opened_at),
                recorded_at=now,
            ).model_dump(mode="json")
        )
        remaining = _shares(remaining - take)
        if take >= lineage.live:
            consumed += 1
        else:
            available[consumed] = _Lineage(
                opened_by_execution_id=lineage.opened_by_execution_id,
                open_row=lineage.open_row,
                live=_shares(lineage.live - take),
                opened_at=lineage.opened_at,
            )
            break
    del available[:consumed]

    if remaining > 0:
        # The sell exceeded the lots on the record. The fill itself is still authoritative
        # — it happened — so this is reported loudly rather than dropped or turned into a
        # negative lot, which the schema's `quantity > 0` CHECK forbids outright.
        logger.error(
            "portfolio ledger: sell of %s %s exceeds recorded open lots by %s — "
            "fill is booked but the surplus has no lot to close",
            fill.quantity,
            fill.symbol,
            remaining,
        )
    return rows


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


__all__ = [
    "ExecutionResult",
    "Fill",
    "FillCosts",
    "HOLDING_LOTS",
    "Rejection",
    "approved_weights",
    "close_lot_id",
    "executed_intent_id",
    "execute_pending_orders",
    "ledger_is_authoritative",
    "open_lot_id",
    "pending_symbols",
]
