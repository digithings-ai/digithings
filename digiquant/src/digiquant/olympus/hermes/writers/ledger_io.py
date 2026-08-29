"""H9 authoritative commit chain — append-only portfolio lineage (#2418, #2768).

H9 is the *only* writer of the migration-069 lineage tables. One call to
:func:`append_commit_chain` appends a whole commit: one ``portfolio_ledger_commits``
row, one decision intent / requested target / approved target per symbol, zero or
more ``target_adjustments`` for H8 pct-unit deltas (#2768), and one order intent
per symbol whose weight actually moved.

Three properties shape every line below.

**Append-only.** ``service_role`` holds SELECT + INSERT on these tables and a
per-table trigger rejects UPDATE, DELETE and TRUNCATE. So a correction is never a
mutation — it is a new row whose ``supersedes_id`` points at the row it replaces, and
``upsert`` must not appear anywhere in this module.

**The head is found by exclusion.** ``supersedes_id IS NULL`` marks the permanent
chain *root*, not the current head: attempt 1's row keeps its NULL forever. The head
is the row nobody supersedes (:func:`_heads`).

**Only three tables chain.** ``commits``, ``approved_targets`` and ``order_intents``
carry ``supersedes_id``. ``decision_intents``, ``requested_targets``, and
``target_adjustments`` do not — they are per-commit children, so a changed recommit
appends *fresh* intent / requested / adjustment rows beneath the new commit rather
than superseding the old ones.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)
from uuid import UUID, uuid4

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    PortfolioCommit,
    RequestedTarget,
    TargetAdjustment,
    TargetAdjustmentType,
)
from digiquant.olympus.hermes.sizing import SizingCaps
from digiquant.olympus.hermes.sizing_events import SizingAdjustment
from digiquant.olympus.hermes.turnover import no_trade_band_pp
from digiquant.olympus.tenancy import house_workspace_id

logger = logging.getLogger(__name__)

COMMITS = "portfolio_ledger_commits"
DECISION_INTENTS = "portfolio_ledger_decision_intents"
REQUESTED_TARGETS = "portfolio_ledger_requested_targets"
TARGET_ADJUSTMENTS = "portfolio_ledger_target_adjustments"
APPROVED_TARGETS = "portfolio_ledger_approved_targets"
ORDER_INTENTS = "portfolio_ledger_order_intents"
PAPER_EXECUTIONS = "portfolio_ledger_paper_executions"

_PRICE_HISTORY = "price_history"
_LEDGER_ENV = "OLYMPUS_PORTFOLIO_LEDGER"
_OFF_VALUES = frozenset({"0", "off", "false", "no", "disabled"})
_CASH = "CASH"
_WEIGHT_EPSILON = 1e-9
_CLOSE_LOOKBACK_DAYS = 14
# Supabase caps an unbounded PostgREST response at 1000 rows, and ``price_history``
# carries one row per *calendar* day per ticker (migration 013 forward-fills weekends
# and holidays from the prior close), so one lookback window is up to
# ``_CLOSE_LOOKBACK_DAYS + 1`` rows per ticker. Unbatched, ~72 tickers would silently
# truncate the read, and a truncated ticker is indistinguishable from an unpriced one —
# it lands in ``unpriced_symbols`` and its committed target gets no order intent at all.
# Batch so a full window for every ticker in a request always fits under the cap, and
# derive the batch from the lookback so widening the window cannot reintroduce this.
_CLOSE_ROW_BUDGET = 900
_CLOSE_TICKER_BATCH = max(1, _CLOSE_ROW_BUDGET // (_CLOSE_LOOKBACK_DAYS + 1))
_QUANTUM = Decimal("0.000001")
_POLICY_PREFIX = "hermes-h8-sizing"


def ledger_enabled() -> bool:
    """Whether H9 appends the authoritative chain. Defaults to **on**.

    Note the polarity is the deliberate *inverse* of
    ``commit_io._position_risk_fields_enabled``: that flag opts *in* to an advisory
    enrichment, so an unset env var means off. This one is the Phase-0 rollback switch
    ("turn off authoritative dual-write while retaining legacy projections"), so an
    unset env var must mean **on** — otherwise a deploy that forgets to set it stops
    writing lineage while every projection still looks healthy.
    """
    return os.environ.get(_LEDGER_ENV, "").strip().lower() not in _OFF_VALUES


@dataclass(frozen=True)
class LedgerAppend:
    """What one commit appended, for the H9 manifest."""

    commit_id: str
    frozen_symbols: list[str]
    unpriced_symbols: list[str]


def _insert(*, client: SupabaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    """The single INSERT gate for every ledger table.

    Module-level and keyword-only on purpose. Routing all five writes through one
    resolvable global is what lets a test simulate a mid-chain failure, and keeping
    the verb literally ``insert`` here is what keeps ``upsert`` — which the
    append-only trigger would reject in production — out of this module entirely.

    T0 (#5-T0): ``workspace_id`` is NOT NULL as of migration 097 with no column
    DEFAULT (every writer reaching these tables is expected to stamp it explicitly —
    see migration 097's header). H9 is single-tenant today, so this one gate stamps
    the house workspace on every row that does not already carry one, which covers
    every caller (``append_commit_chain`` here, plus ``opening_snapshot`` and
    ``execution_io`` which both route through this same function).
    """
    if not rows:
        return
    house_id = str(house_workspace_id())
    stamped = [{"workspace_id": house_id, **row} for row in rows]
    client.table(table).insert(stamped).execute()


def _is_cash(ticker: Any) -> bool:
    return isinstance(ticker, str) and ticker.strip().upper() == _CASH


def _symbol(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _rows_for_date(*, client: SupabaseClient, table: str, run_date: date) -> list[dict[str, Any]]:
    resp = client.table(table).select("*").eq("run_date", run_date.isoformat()).execute()
    return list(resp.data or [])


def _heads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows nobody supersedes — the current tips of the chains in ``rows``.

    Not ``supersedes_id IS NULL``: under an append-only ledger that predicate matches
    the permanent root of every chain, which after one recommit is the *stale* row.
    """
    superseded = {str(r.get("supersedes_id")) for r in rows if r.get("supersedes_id")}
    return [r for r in rows if str(r.get("id")) not in superseded]


def _head_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_symbol(r.get("symbol")): r for r in rows if r.get("symbol")}


def _id_of(row: dict[str, Any] | None) -> UUID | None:
    if not row or not row.get("id"):
        return None
    return UUID(str(row["id"]))


def _last_closes(*, client: SupabaseClient, tickers: set[str], run_date: date) -> dict[str, float]:
    """Last close strictly before ``run_date``, per ticker.

    A fixed ``_CLOSE_LOOKBACK_DAYS``-day lookback — deliberately *not* the window
    ``commit_io._interval_price_returns`` builds, which is anchored on the prior book
    date and so spans 8-127 days. Only the most recent close per ticker matters here.
    A read failure is
    deliberately **not** swallowed: a commit that silently booked no orders is exactly
    the false-final-value state Phase-0 invariant 12 forbids, and the sanctioned way to
    stop writing is the kill switch above, not a swallowed exception.
    """
    if not tickers:
        return {}
    floor = (run_date - timedelta(days=_CLOSE_LOOKBACK_DAYS)).isoformat()
    ordered = sorted(tickers)
    latest: dict[str, tuple[str, float]] = {}
    for start in range(0, len(ordered), _CLOSE_TICKER_BATCH):
        resp = (
            client.table(_PRICE_HISTORY)
            .select("date, ticker, close")
            .in_("ticker", ordered[start : start + _CLOSE_TICKER_BATCH])
            .gte("date", floor)
            .lt("date", run_date.isoformat())
            .execute()
        )
        for row in resp.data or []:
            ticker = _symbol(row.get("ticker"))
            day = str(row.get("date") or "")
            try:
                close = float(row.get("close"))
            except (TypeError, ValueError):
                continue
            if not ticker or not day or close <= 0:
                continue
            current = latest.get(ticker)
            if current is None or day > current[0]:
                latest[ticker] = (day, close)
    return {ticker: close for ticker, (_, close) in latest.items()}


def _frozen_symbols(*, client: SupabaseClient, order_rows: list[dict[str, Any]]) -> set[str]:
    """Symbols already executed on this run date — immutable, so they get no new rows.

    Two independent signals, either of which freezes the symbol: its order head is
    already ``executed``, or a ``paper_executions`` row references one of its order
    intents. A ``rejected`` head does *not* freeze — nothing traded, so the next commit
    is free to re-issue. Frozen symbols surface on the manifest as
    ``ledger_frozen_symbols`` rather than silently vanishing.
    """
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in order_rows:
        symbol = _symbol(row.get("symbol"))
        if symbol:
            by_symbol.setdefault(symbol, []).append(row)

    frozen = {
        symbol
        for symbol, rows in by_symbol.items()
        if any(str(h.get("status") or "") == OrderIntentStatus.EXECUTED for h in _heads(rows))
    }

    order_ids = [str(r.get("id")) for r in order_rows if r.get("id")]
    if not order_ids:
        return frozen
    # ``paper_executions`` carries no ``run_date`` column — it is reachable only
    # through the order intents it references, so filter on those ids alone.
    resp = (
        client.table(PAPER_EXECUTIONS)
        .select("order_intent_id")
        .in_("order_intent_id", order_ids)
        .execute()
    )
    filled = {str(r.get("order_intent_id")) for r in resp.data or []}
    frozen.update(
        symbol
        for symbol, rows in by_symbol.items()
        if any(str(r.get("id")) in filled for r in rows)
    )
    return frozen


def _prior_weights(state: AtlasResearchState) -> dict[str, float]:
    """Mark-to-market prior book weights, in percent.

    The same source ``h7_pm_direction`` and ``phase7d_pm`` read. Atlas preflight
    derives it from ``load_prior_book(client, run_date)`` and drifts it by price moves
    since the prior book date (#955), which is the baseline H8 sized its targets
    against — so measuring the ledger's share deltas against it, rather than re-reading
    ``positions`` here, keeps NAV and prior weight on one snapshot. Legitimately empty
    on a seed run with no prior book, which correctly sizes every position as a fresh
    buy from cash.
    """
    raw = state.config.preferences.get("current_weights") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[_symbol(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _decision(
    *,
    symbol: str,
    prior_pct: float,
    target_pct: float,
    preferences: Mapping[str, Any] | None = None,
) -> tuple[DecisionAction, DecisionReason]:
    """Classify one symbol's weight move into the closed action/reason vocabulary.

    Two honest approximations, both inherent to reading this off final weights:
    ``ADD``/``NEW_CONVICTION`` is the *only* pairing the schema offers for a weight
    increase (there is no "increase" action), and a move to zero is recorded as
    ``EXIT``/``THESIS_INVALIDATED`` even when a risk cap rather than a thesis change
    forced it — H9 sees the weight, not the reason. H8's ``TargetAdjustment`` rows are
    where the cap-driven variants belong.
    """
    if symbol == _CASH:
        # Cash is the residual of the sized book, never a conviction: "new_conviction",
        # "conviction_reduced" and "thesis_invalidated" are all meaningless for it.
        return DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE
    delta = target_pct - prior_pct
    if (
        preferences is not None
        and prior_pct > 0
        and target_pct > 0
        and abs(delta) < no_trade_band_pp(prior_pct, dict(preferences))
    ):
        return DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE
    if abs(delta) < _WEIGHT_EPSILON:
        return DecisionAction.NO_OP, DecisionReason.NO_SIGNAL_CHANGE
    if delta > 0:
        return DecisionAction.ADD, DecisionReason.NEW_CONVICTION
    if target_pct <= _WEIGHT_EPSILON:
        return DecisionAction.EXIT, DecisionReason.THESIS_INVALIDATED
    return DecisionAction.TRIM, DecisionReason.CONVICTION_REDUCED


def _weight(pct: float) -> Decimal:
    """Percent → the ``[0, 1]`` fraction migration 069 stores."""
    return Decimal(str(max(0.0, pct) / 100.0)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _shares(*, delta_pct: float, nav: float, close: float) -> Decimal:
    """Absolute share count for a weight move of ``delta_pct``, priced at ``close``.

    ``order_intents`` has no ``side`` column and enforces ``quantity > 0``, so the row
    carries an *absolute* share count; direction is implied by the approved target
    against the holding it replaces, and a zero delta means no row at all. Quantized
    *before* the caller's ``> 0`` test so a delta that rounds away is dropped rather
    than reaching ``PositiveQuantity`` and raising.
    """
    if close <= 0 or nav <= 0:
        return Decimal(0)
    raw = abs(delta_pct) / 100.0 * nav / close
    return Decimal(str(raw)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _policy_version_id(state: AtlasResearchState) -> str:
    """Stable identifier for the sizing policy this commit was produced under.

    ``SizingCaps`` is frozen, so a digest over its fields is a faithful fingerprint:
    two commits sharing a ``policy_version_id`` were sized under identical caps.
    """
    caps = SizingCaps.from_preferences(state.config.preferences)
    payload = json.dumps({k: str(v) for k, v in sorted(asdict(caps).items())}, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{_POLICY_PREFIX}/{caps.sizing_mode}/{digest}"


def _request_pct_for_symbol(
    *,
    symbol: str,
    target_pct: float,
    requested_pct: Mapping[str, float],
    pct_adjustments: Sequence[SizingAdjustment],
) -> float:
    """Pre-cap weight percent for ``symbol``, falling back to the approved target.

    Preference order: explicit H8 ``requested_pct`` map; else the first pct-unit
    adjustment's ``original_pct`` (chain start); else the approved target (no delta).
    """
    if symbol in requested_pct:
        return float(requested_pct[symbol])
    if pct_adjustments:
        return float(pct_adjustments[0].original_pct)
    return float(target_pct)


def _pct_adjustments_by_symbol(
    adjustments: Sequence[SizingAdjustment],
) -> dict[str, list[SizingAdjustment]]:
    """Group weight-percent adjustments; skip conviction-unit events."""
    by_symbol: dict[str, list[SizingAdjustment]] = defaultdict(list)
    for adjustment in adjustments:
        if adjustment.unit != "pct":
            continue
        if _is_cash(adjustment.ticker):
            continue
        by_symbol[_symbol(adjustment.ticker)].append(adjustment)
    return by_symbol


def append_commit_chain(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
    adjustments: Sequence[SizingAdjustment] | None = None,
    requested_pct: Mapping[str, float] | None = None,
) -> LedgerAppend | None:
    """Append one authoritative commit and its lineage. Returns ``None`` when disabled.

    ``weights`` and ``cash_pct`` are H8's final book in percent; ``nav`` is the NAV
    ``commit_io.book_portfolio`` computed from the same prior-book snapshot.
    ``adjustments`` / ``requested_pct`` come from the sized book (#2768): when a
    pre-cap request differs from the approved weight, ``requested_weight`` stores
    the request and matching ``TargetAdjustment`` rows explain the delta.

    Callers must invoke this **before** persisting the commit manifest: a raise here
    has to leave no manifest behind, so the next attempt re-commits instead of
    reporting a false no-op.
    """
    if not ledger_enabled():
        logger.info(
            "ledger_io: %s disables the authoritative chain; legacy projections only",
            _LEDGER_ENV,
        )
        return None

    run_date = state.run_date
    date_str = run_date.isoformat()
    effective_at = datetime.combine(run_date, time(0, 0), tzinfo=UTC)
    recorded_at = datetime.now(UTC)
    h8_adjustments = list(adjustments or ())
    h8_requested = {_symbol(k): float(v) for k, v in (requested_pct or {}).items()}
    adjustments_by_symbol = _pct_adjustments_by_symbol(h8_adjustments)

    prior_commits = _rows_for_date(client=client, table=COMMITS, run_date=run_date)
    prior_approved = _rows_for_date(client=client, table=APPROVED_TARGETS, run_date=run_date)
    prior_orders = _rows_for_date(client=client, table=ORDER_INTENTS, run_date=run_date)

    commit_heads = _heads(prior_commits)
    if len(commit_heads) > 1:
        raise RuntimeError(
            f"{COMMITS} has {len(commit_heads)} heads for {date_str}; the chain forked "
            "and H9 will not extend an ambiguous lineage"
        )
    approved_heads = _head_by_symbol(_heads(prior_approved))
    order_heads = _head_by_symbol(_heads(prior_orders))
    frozen = _frozen_symbols(client=client, order_rows=prior_orders)

    targets = {_symbol(t): float(w) for t, w in weights.items() if not _is_cash(t)}
    targets[_CASH] = float(cash_pct)
    prior = _prior_weights(state)

    # A symbol earns a row if the new book names it, if the prior book still holds it
    # (so an exit is recorded rather than implied by absence), if H8 requested it
    # (even when caps drove it to zero), or if it has an open approved target to
    # supersede. Frozen symbols are excluded outright.
    symbols = set(targets)
    symbols |= {s for s, pct in prior.items() if abs(pct) > _WEIGHT_EPSILON}
    symbols |= set(approved_heads)
    symbols |= set(h8_requested)
    symbols |= set(adjustments_by_symbol)
    symbols -= frozen

    closes = _last_closes(
        client=client, tickers={s for s in symbols if s != _CASH}, run_date=run_date
    )

    commit_id = uuid4()
    commit = PortfolioCommit(
        id=commit_id,
        run_date=run_date,
        policy_version_id=_policy_version_id(state),
        supersedes_id=_id_of(commit_heads[0] if commit_heads else None),
        effective_at=effective_at,
        recorded_at=recorded_at,
    )

    intent_rows: list[dict[str, Any]] = []
    requested_rows: list[dict[str, Any]] = []
    adjustment_rows: list[dict[str, Any]] = []
    approved_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    unpriced: list[str] = []

    for symbol in sorted(symbols):
        target_pct = targets.get(symbol, 0.0)
        prior_pct = prior.get(symbol, 0.0)
        symbol_adjustments = adjustments_by_symbol.get(symbol, [])
        request_pct = _request_pct_for_symbol(
            symbol=symbol,
            target_pct=target_pct,
            requested_pct=h8_requested,
            pct_adjustments=symbol_adjustments,
        )
        action, reason = _decision(
            symbol=symbol,
            prior_pct=prior_pct,
            target_pct=target_pct,
            preferences=state.config.preferences,
        )

        intent = DecisionIntent(
            id=uuid4(),
            portfolio_commit_id=commit_id,
            run_date=run_date,
            symbol=symbol,
            action=action,
            reason=reason,
            effective_at=effective_at,
            recorded_at=recorded_at,
        )
        requested = RequestedTarget(
            id=uuid4(),
            decision_intent_id=intent.id,
            run_date=run_date,
            symbol=symbol,
            requested_weight=_weight(request_pct),
            requested_quantity=None,
            effective_at=effective_at,
            recorded_at=recorded_at,
        )
        for event in symbol_adjustments:
            adjustment_rows.append(
                TargetAdjustment(
                    id=uuid4(),
                    requested_target_id=requested.id,
                    run_date=run_date,
                    symbol=symbol,
                    adjustment_type=TargetAdjustmentType(event.adjustment_type.value),
                    original_value=_weight(event.original_pct),
                    adjusted_value=_weight(event.adjusted_pct),
                    reason=event.reason,
                    effective_at=effective_at,
                    recorded_at=recorded_at,
                ).model_dump(mode="json")
            )
        approved = ApprovedTarget(
            id=uuid4(),
            requested_target_id=requested.id,
            run_date=run_date,
            symbol=symbol,
            approved_weight=_weight(target_pct),
            approved_quantity=None,
            supersedes_id=_id_of(approved_heads.get(symbol)),
            effective_at=effective_at,
            recorded_at=recorded_at,
        )
        intent_rows.append(intent.model_dump(mode="json"))
        requested_rows.append(requested.model_dump(mode="json"))
        approved_rows.append(approved.model_dump(mode="json"))

        if symbol == _CASH:
            continue  # cash is a residual, not a tradeable order
        close = closes.get(symbol)
        if close is None:
            unpriced.append(symbol)
            continue
        quantity = _shares(delta_pct=target_pct - prior_pct, nav=nav, close=close)
        if quantity <= 0:
            continue
        order_rows.append(
            OrderIntent(
                id=uuid4(),
                approved_target_id=approved.id,
                run_date=run_date,
                symbol=symbol,
                quantity=quantity,
                status=OrderIntentStatus.PENDING,
                supersedes_id=_id_of(order_heads.get(symbol)),
                effective_at=effective_at,
                recorded_at=recorded_at,
            ).model_dump(mode="json")
        )

    # FK order: a child cannot reference a parent that is not in yet. Ids are generated
    # client-side precisely so each batch is one INSERT with no read-back between them.
    _insert(client=client, table=COMMITS, rows=[commit.model_dump(mode="json")])
    _insert(client=client, table=DECISION_INTENTS, rows=intent_rows)
    _insert(client=client, table=REQUESTED_TARGETS, rows=requested_rows)
    _insert(client=client, table=TARGET_ADJUSTMENTS, rows=adjustment_rows)
    _insert(client=client, table=APPROVED_TARGETS, rows=approved_rows)
    _insert(client=client, table=ORDER_INTENTS, rows=order_rows)

    if unpriced:
        logger.warning(
            "ledger_io: no close before %s for %s; committed the target without an order",
            date_str,
            ", ".join(unpriced),
        )
    logger.info(
        "ledger_io: commit %s for %s — %d intents, %d adjustments, %d orders, frozen=%s",
        commit_id,
        date_str,
        len(intent_rows),
        len(adjustment_rows),
        len(order_rows),
        ",".join(sorted(frozen)) or "none",
    )
    return LedgerAppend(
        commit_id=str(commit_id),
        frozen_symbols=sorted(frozen),
        unpriced_symbols=sorted(unpriced),
    )
