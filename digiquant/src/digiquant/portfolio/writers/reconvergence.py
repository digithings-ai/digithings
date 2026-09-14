"""Ledger reconvergence — plan (and deliberately apply) the trades that bring the
live paper ledger back onto the committed book (#4010).

Dry-run first by design: :func:`plan_convergence` only reads. :func:`apply_catch_up`
writes one labeled ``ledger_reconvergence`` recovery chain; backdated plans are
refused in v1 because restating finalized accounting is a separate, deliberate step.
Applying is not transactional: the commit row is written first, so a failure mid-chain
leaves a partial recovery that refuses a plain re-run and needs an operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any  # score:allow untyped any — heterogeneous ledger row scalars
from uuid import UUID, uuid5

from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.portfolio.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    PaperExecution,
    PortfolioCommit,
    RequestedTarget,
    paper_execution_id,
)
from digiquant.portfolio.writers.execution_io import (
    HOLDING_LOTS,
    Fill,
    _lineages,
    _live_quantity,
    _lot_rows_for_fill,
    open_lot_id,
)
from digiquant.portfolio.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
    _heads,
    _id_of,
    _insert,
    _last_closes,
    _rows_for_date,
)
from digiquant.research.supabase_io import SupabaseClient

POLICY_VERSION_ID = "ledger_reconvergence"
CASH = "CASH"

_QTY = Decimal("0.000001")
_MONEY = Decimal("0.01")
_ZERO = Decimal("0")
_ZERO_MONEY = Decimal("0.00")
_DEFAULT_MIN_NOTIONAL = Decimal("1.00")
_RECON_ID_NAMESPACE = UUID("5f8d2c1b-9a3e-4b7c-8d1f-2e6b0a4c7d91")

_POSITIONS = "positions"
_NAV_HISTORY = "nav_history"
_LOT_PAGE_SIZE = 1000

__all__ = [
    "CASH",
    "POLICY_VERSION_ID",
    "ReconPlan",
    "TradeLeg",
    "apply_catch_up",
    "open_lot_id",
    "plan_convergence",
    "render_plan",
]


@dataclass(frozen=True)
class TradeLeg:
    """One planned trade that converges the live book toward the committed book."""

    book_date: date
    symbol: str
    side: str
    quantity: Decimal
    mark: Decimal
    notional: Decimal
    live_quantity_before: Decimal
    target_quantity: Decimal


@dataclass(frozen=True)
class ReconPlan:
    """A dry-run reconvergence plan; nothing here has been written."""

    mode: str
    book_date: date
    exec_date: date
    legs: tuple[TradeLeg, ...]
    buy_notional: Decimal
    sell_notional: Decimal
    warnings: tuple[str, ...] = ()


def _recon_id(kind: str, day: date, symbol: str = "") -> UUID:
    return uuid5(_RECON_ID_NAMESPACE, f"{kind}:{day.isoformat()}:{symbol}")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _quantize_qty(value: Decimal) -> Decimal:
    return value.quantize(_QTY, rounding=ROUND_HALF_UP)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _read_lots(client: SupabaseClient) -> list[dict[str, Any]]:
    """Read every house lot, paging past the PostgREST 1000-row response cap.

    The live-quantity read drives both the plan and the apply-side FIFO consume,
    so a silently truncated page would understate holdings and over-buy.
    """
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        resp = (
            client.table(HOLDING_LOTS)
            .select("*")
            .eq("workspace_id", str(house_workspace_id()))
            .order("id")
            .range(start, start + _LOT_PAGE_SIZE - 1)
            .execute()
        )
        page = list(resp.data or [])
        rows.extend(page)
        if len(page) < _LOT_PAGE_SIZE:
            return rows
        start += _LOT_PAGE_SIZE


def _read_live_quantities(client: SupabaseClient) -> dict[str, Decimal]:
    lineages = _lineages(_read_lots(client))
    return {symbol: _live_quantity(lineages, symbol) for symbol in lineages}


def _read_book(client: SupabaseClient, *, book_date: date) -> dict[str, Decimal]:
    resp = (
        client.table(_POSITIONS)
        .select("date, ticker, weight_pct")
        .eq("workspace_id", str(house_workspace_id()))
        .eq("date", book_date.isoformat())
        .execute()
    )
    weights: dict[str, Decimal] = {}
    for row in resp.data or []:
        symbol = str(row.get("ticker") or "").upper()
        raw = row.get("weight_pct")
        if not symbol or symbol == CASH or raw is None:
            continue
        weights[symbol] = _decimal(raw)
    return weights


def _read_nav(client: SupabaseClient, *, day: date) -> Decimal:
    resp = (
        client.table(_NAV_HISTORY)
        .select("date, nav")
        .eq("workspace_id", str(house_workspace_id()))
        .eq("date", day.isoformat())
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows or rows[0].get("nav") is None:
        raise ValueError(f"no nav_history row for {day.isoformat()}")
    return _decimal(rows[0]["nav"])


def _marks(client: SupabaseClient, *, day: date, symbols: set[str]) -> dict[str, Decimal]:
    cutoff = day + timedelta(days=1)
    raw = _last_closes(client=client, tickers=symbols, run_date=cutoff)
    marks: dict[str, Decimal] = {}
    for symbol, close in raw.items():
        if close and close > 0:
            marks[symbol] = _decimal(close)
    return marks


def _legs_for_day(
    *,
    client: SupabaseClient,
    book_date: date,
    mark_day: date,
    weights: dict[str, Decimal],
    nav: Decimal,
    running: dict[str, Decimal],
    min_notional: Decimal,
) -> tuple[list[TradeLeg], list[str], dict[str, Decimal]]:
    symbols = set(weights) | set(running)
    marks = _marks(client, day=mark_day, symbols=symbols)
    legs: list[TradeLeg] = []
    dust: list[str] = []
    for symbol in sorted(symbols):
        weight = weights.get(symbol, _ZERO)
        target_qty = _ZERO
        if weight > 0:
            mark = marks.get(symbol)
            if mark is None:
                raise ValueError(
                    f"{symbol}: no price_history close on or before {mark_day.isoformat()} "
                    "— cannot size a reconvergence leg"
                )
            target_qty = _quantize_qty(weight / 100 * nav / mark)
        live_qty = running.get(symbol, _ZERO)
        delta = _quantize_qty(target_qty - live_qty)
        if delta == 0:
            continue
        mark = marks.get(symbol)
        if mark is None:
            raise ValueError(
                f"{symbol}: no price_history close on or before {mark_day.isoformat()} "
                "— cannot size a reconvergence leg"
            )
        notional = _quantize_money(abs(delta) * mark)
        if notional < min_notional:
            dust.append(f"{book_date.isoformat()}:{symbol}")
            continue
        legs.append(
            TradeLeg(
                book_date=book_date,
                symbol=symbol,
                side="buy" if delta > 0 else "sell",
                quantity=abs(delta),
                mark=mark,
                notional=notional,
                live_quantity_before=live_qty,
                target_quantity=target_qty,
            )
        )
    return legs, dust, marks


def _assemble_plan(
    *,
    mode: str,
    book_date: date,
    exec_date: date,
    legs: list[TradeLeg],
    dust: list[str],
    min_notional: Decimal,
) -> ReconPlan:
    buy_notional = _quantize_money(sum((leg.notional for leg in legs if leg.side == "buy"), _ZERO))
    sell_notional = _quantize_money(
        sum((leg.notional for leg in legs if leg.side == "sell"), _ZERO)
    )
    warnings: list[str] = []
    if dust:
        warnings.append(
            f"skipped {len(dust)} dust leg(s) below min_notional={min_notional}: "
            f"{', '.join(sorted(dust))}"
        )
    return ReconPlan(
        mode=mode,
        book_date=book_date,
        exec_date=exec_date,
        legs=tuple(legs),
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        warnings=tuple(warnings),
    )


def plan_convergence(
    *,
    client: SupabaseClient,
    book_date: date,
    exec_date: date | None = None,
    mode: str = "catch-up",
    since: date | None = None,
    min_notional: Decimal = _DEFAULT_MIN_NOTIONAL,
) -> ReconPlan:
    """Plan the trades that converge the live ledger book onto the committed book.

    ``catch-up`` books one aggregate trade set at ``exec_date``'s marks; ``backdated``
    walks every book date from ``since`` to ``book_date``, carrying running quantities.
    """
    if mode not in ("catch-up", "backdated"):
        raise ValueError(f"unknown reconvergence mode {mode!r}")
    if not min_notional.is_finite() or min_notional < 0:
        raise ValueError(f"min_notional must be a finite non-negative amount, got {min_notional!r}")
    if mode == "catch-up":
        exec_day = exec_date or book_date
        running = _read_live_quantities(client)
        weights = _read_book(client, book_date=book_date)
        nav = _read_nav(client, day=book_date)
        legs, dust, _ = _legs_for_day(
            client=client,
            book_date=book_date,
            mark_day=exec_day,
            weights=weights,
            nav=nav,
            running=running,
            min_notional=min_notional,
        )
        return _assemble_plan(
            mode=mode,
            book_date=book_date,
            exec_date=exec_day,
            legs=legs,
            dust=dust,
            min_notional=min_notional,
        )

    start = since or book_date
    if start > book_date:
        raise ValueError(
            f"--since {start.isoformat()} is after --book-date {book_date.isoformat()}"
        )
    exec_day = exec_date or book_date
    resp = (
        client.table(_POSITIONS)
        .select("date, ticker, weight_pct")
        .eq("workspace_id", str(house_workspace_id()))
        .gte("date", start.isoformat())
        .lte("date", book_date.isoformat())
        .execute()
    )
    by_day: dict[date, dict[str, Decimal]] = {}
    for row in resp.data or []:
        symbol = str(row.get("ticker") or "").upper()
        raw_weight = row.get("weight_pct")
        raw_day = str(row.get("date") or "")[:10]
        if not symbol or symbol == CASH or raw_weight is None or not raw_day:
            continue
        day = date.fromisoformat(raw_day)
        by_day.setdefault(day, {})[symbol] = _decimal(raw_weight)
    if not by_day:
        raise ValueError(
            f"no positions rows between {start.isoformat()} and {book_date.isoformat()}"
        )
    running = _read_live_quantities(client)
    legs: list[TradeLeg] = []
    dust: list[str] = []
    for day in sorted(by_day):
        weights = by_day[day]
        nav = _read_nav(client, day=day)
        day_legs, day_dust, day_marks = _legs_for_day(
            client=client,
            book_date=day,
            mark_day=day,
            weights=weights,
            nav=nav,
            running=running,
            min_notional=min_notional,
        )
        legs.extend(day_legs)
        dust.extend(day_dust)
        for symbol in set(weights) | set(running):
            weight = weights.get(symbol, _ZERO)
            mark = day_marks.get(symbol)
            if weight > 0 and mark is not None:
                running[symbol] = _quantize_qty(weight / 100 * nav / mark)
            elif weight <= 0:
                running[symbol] = _ZERO
    return _assemble_plan(
        mode=mode,
        book_date=book_date,
        exec_date=exec_day,
        legs=legs,
        dust=dust,
        min_notional=min_notional,
    )


def render_plan(plan: ReconPlan) -> str:
    """Dry-run text for operators: the legs, totals, and any warnings."""
    lines = [
        f"reconvergence dry run ({plan.mode}): "
        f"book_date={plan.book_date.isoformat()} exec_date={plan.exec_date.isoformat()}"
    ]
    for leg in plan.legs:
        lines.append(
            f"  {leg.side} {leg.symbol} {_plain(leg.quantity)} "
            f"@ {_plain(leg.mark)} = {leg.notional} [{leg.book_date.isoformat()}]"
        )
    lines.append(f"  totals: buy {plan.buy_notional} sell {plan.sell_notional}")
    lines.extend(f"  WARN: {warning}" for warning in plan.warnings)
    return "\n".join(lines)


def apply_catch_up(
    *,
    client: SupabaseClient,
    plan: ReconPlan,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Write the labeled catch-up chain, or refuse with a reason.

    Backdated plans are refused in v1: restating finalized accounting is a deliberate
    second step (#4010), never a side effect of a catch-up.
    """
    if plan.mode != "catch-up":
        raise ValueError(f"backdated reconvergence apply is not supported in v1 (mode={plan.mode})")
    existing = _rows_for_date(client=client, table=COMMITS, run_date=plan.exec_date)
    if any(str(row.get("policy_version_id")) == POLICY_VERSION_ID for row in existing):
        return False, (
            f"already applied: a {POLICY_VERSION_ID} commit exists for {plan.exec_date.isoformat()}"
        )
    if not plan.legs:
        return False, "nothing to apply: the plan has no legs"

    stamp = now or datetime.now(UTC)
    effective = datetime.combine(plan.exec_date, time(0, 0), tzinfo=UTC)
    commit_id = _recon_id("commit", plan.exec_date)
    commit_heads = _heads(_rows_for_date(client=client, table=COMMITS, run_date=plan.exec_date))
    approved_heads = {
        str(row.get("symbol")): row
        for row in _heads(
            _rows_for_date(client=client, table=APPROVED_TARGETS, run_date=plan.exec_date)
        )
        if row.get("symbol")
    }
    order_heads = {
        str(row.get("symbol")): row
        for row in _heads(
            _rows_for_date(client=client, table=ORDER_INTENTS, run_date=plan.exec_date)
        )
        if row.get("symbol")
    }
    lineages = _lineages(_read_lots(client))

    commit = PortfolioCommit(
        id=commit_id,
        run_date=plan.exec_date,
        policy_version_id=POLICY_VERSION_ID,
        supersedes_id=_id_of(commit_heads[0]) if commit_heads else None,
        effective_at=effective,
        recorded_at=stamp,
    ).model_dump(mode="json")
    decisions: list[dict[str, Any]] = []
    requested: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    lots: list[dict[str, Any]] = []
    for leg in plan.legs:
        buying = leg.side == "buy"
        action = DecisionAction.ADD if buying else DecisionAction.TRIM
        reason = DecisionReason.NEW_CONVICTION if buying else DecisionReason.CONVICTION_REDUCED
        decision_id = _recon_id("decision", plan.exec_date, leg.symbol)
        requested_id = _recon_id("requested", plan.exec_date, leg.symbol)
        approved_id = _recon_id("approved", plan.exec_date, leg.symbol)
        order_id = _recon_id("order", plan.exec_date, leg.symbol)
        execution_id = paper_execution_id(order_id, plan.exec_date)
        decisions.append(
            DecisionIntent(
                id=decision_id,
                portfolio_commit_id=commit_id,
                run_date=plan.exec_date,
                symbol=leg.symbol,
                action=action,
                reason=reason,
                effective_at=effective,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        requested.append(
            RequestedTarget(
                id=requested_id,
                decision_intent_id=decision_id,
                run_date=plan.exec_date,
                symbol=leg.symbol,
                requested_quantity=leg.quantity,
                effective_at=effective,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        approved.append(
            ApprovedTarget(
                id=approved_id,
                requested_target_id=requested_id,
                run_date=plan.exec_date,
                symbol=leg.symbol,
                approved_quantity=leg.quantity,
                supersedes_id=_id_of(approved_heads.get(leg.symbol)),
                effective_at=effective,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        orders.append(
            OrderIntent(
                id=order_id,
                approved_target_id=approved_id,
                run_date=plan.exec_date,
                symbol=leg.symbol,
                quantity=leg.quantity,
                status=OrderIntentStatus.EXECUTED,
                supersedes_id=_id_of(order_heads.get(leg.symbol)),
                effective_at=effective,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        executions.append(
            PaperExecution(
                id=execution_id,
                order_intent_id=order_id,
                executed_date=plan.exec_date,
                symbol=leg.symbol,
                quantity=leg.quantity,
                price=leg.mark,
                fee=_ZERO_MONEY,
                slippage=_ZERO_MONEY,
                executed_at=stamp,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        fill = Fill(
            symbol=leg.symbol,
            action=action,
            order_intent_id=order_id,
            execution_id=execution_id,
            quantity=leg.quantity,
            price=leg.mark,
            fee=_ZERO_MONEY,
            slippage=_ZERO_MONEY,
        )
        lots.extend(
            _lot_rows_for_fill(
                fill=fill,
                run_date=plan.exec_date,
                lineages=lineages,
                now=stamp,
            )
        )

    _insert(client=client, table=COMMITS, rows=[commit])
    _insert(client=client, table=DECISION_INTENTS, rows=decisions)
    _insert(client=client, table=REQUESTED_TARGETS, rows=requested)
    _insert(client=client, table=APPROVED_TARGETS, rows=approved)
    _insert(client=client, table=ORDER_INTENTS, rows=orders)
    _insert(client=client, table=PAPER_EXECUTIONS, rows=executions)
    _insert(client=client, table=HOLDING_LOTS, rows=lots)
    return True, "applied"
