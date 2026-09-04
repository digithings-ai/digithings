"""Append-only persistence for dashboard EOD period accounting (#2597, Task 3.2).

Writes ``dashboard_accounting_{periods,contributions,holdings}`` via service-role
``INSERT`` only — never ``upsert``/``UPDATE``/``DELETE``. Exact same-input retry
reproduces the same primary keys and is a no-op once the full child set exists.
A mid-chain crash leaves an incomplete period that
:func:`select_final_period` refuses; the next retry repairs missing children.

Provisional H9 NAV (``nav_history`` / ``positions``) is continuity data only — it
never appears in these tables and cannot be selected as a final accounting period.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import (
    Any,  # score:allow untyped any — heterogeneous Supabase row dicts
)
from uuid import UUID, uuid5

from digiquant.dashboard.accounting.models import (
    AccountingPeriod,
    ClosingHolding,
    PeriodStatus,
    TickerPeriodResult,
)
from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

PERIODS = "olympus_accounting_periods"
CONTRIBUTIONS = "olympus_accounting_contributions"
HOLDINGS = "olympus_accounting_holdings"

_CONTRIBUTION_ID_NAMESPACE = UUID("d4e82b19-7c50-5a3f-9e61-2f8a4b0c7d93")
_HOLDING_ID_NAMESPACE = UUID("e5f93c2a-8d61-5b40-af72-3a9b5c1d8e04")


@dataclass(frozen=True)
class PersistResult:
    """Outcome of one :func:`persist_period` call."""

    period_id: UUID
    status: PeriodStatus
    wrote: bool
    repaired: bool
    superseded_id: UUID | None


class AccountingPersistError(RuntimeError):
    """Persistence refused or left an inconsistent state."""


def contribution_row_id(period_id: UUID, symbol: str) -> UUID:
    """Deterministic contribution PK so an exact retry cannot duplicate rows."""
    return uuid5(_CONTRIBUTION_ID_NAMESPACE, f"{period_id}:{symbol.strip().upper()}")


def holding_row_id(period_id: UUID, symbol: str) -> UUID:
    """Deterministic holding PK so an exact retry cannot duplicate rows."""
    return uuid5(_HOLDING_ID_NAMESPACE, f"{period_id}:{symbol.strip().upper()}")


def _insert(*, client: SupabaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    """Single INSERT gate — keeps ``upsert`` out of this module.

    T0 (#5-T0): ``workspace_id`` is NOT NULL as of migration 097 with no column
    DEFAULT — this accounting pipeline is single-tenant today, so every row stamps
    the house workspace explicitly here rather than relying on a fallback that does
    not exist.
    """
    if not rows:
        return
    house_id = str(house_workspace_id())
    stamped = [{"workspace_id": house_id, **row} for row in rows]
    client.table(table).insert(stamped).execute()


def _dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


def _period_rows(*, client: SupabaseClient, period_date: date) -> list[dict[str, Any]]:
    resp = client.table(PERIODS).select("*").eq("period_date", period_date.isoformat()).execute()
    return list(getattr(resp, "data", None) or [])


def _heads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Current tips — rows nobody supersedes (not ``supersedes_id IS NULL``)."""
    superseded = {str(r.get("supersedes_id")) for r in rows if r.get("supersedes_id")}
    return [r for r in rows if str(r.get("id")) not in superseded]


def period_head(*, client: SupabaseClient, period_date: date) -> dict[str, Any] | None:
    """Current tip of the accounting supersession chain for ``period_date``."""
    heads = _heads(_period_rows(client=client, period_date=period_date))
    if not heads:
        return None
    if len(heads) > 1:
        raise AccountingPersistError(
            f"forked accounting period chain for {period_date.isoformat()}: "
            f"{[h.get('id') for h in heads]}"
        )
    return heads[0]


def _fetch_period_by_id(*, client: SupabaseClient, period_id: UUID) -> dict[str, Any] | None:
    resp = client.table(PERIODS).select("*").eq("id", str(period_id)).limit(1).execute()
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _child_rows(*, client: SupabaseClient, table: str, period_id: UUID) -> list[dict[str, Any]]:
    resp = client.table(table).select("*").eq("period_id", str(period_id)).execute()
    return list(getattr(resp, "data", None) or [])


def _row_implies_activity(period_row: dict[str, Any]) -> bool:
    """Whether a persisted period row should have at least one contribution child."""
    e0 = _decimal(period_row.get("opening_equity")) or Decimal(0)
    cash0 = _decimal(period_row.get("opening_cash")) or Decimal(0)
    e1 = _decimal(period_row.get("closing_equity")) or Decimal(0)
    cash1 = _decimal(period_row.get("closing_cash")) or Decimal(0)
    net = _decimal(period_row.get("net_pnl_total")) or Decimal(0)
    gross = _decimal(period_row.get("gross_pnl_total")) or Decimal(0)
    return (e0 - cash0) != 0 or (e1 - cash1) != 0 or net != 0 or gross != 0


def period_children_complete(
    *,
    client: SupabaseClient,
    period: AccountingPeriod | None = None,
    period_row: dict[str, Any] | None = None,
) -> bool:
    """True when contribution and holding child sets match the period contract.

    A period row alone is never enough for authoritative selection — a crash after
    the period INSERT must not publish a partial final.
    """
    if period is not None:
        period_id = period.id
        expected_contrib = {t.symbol.strip().upper() for t in period.ticker_results}
        expected_hold = {h.symbol.strip().upper() for h in period.closing_holdings}
        contrib_syms = {
            str(r.get("symbol") or "").strip().upper()
            for r in _child_rows(client=client, table=CONTRIBUTIONS, period_id=period_id)
        }
        hold_syms = {
            str(r.get("symbol") or "").strip().upper()
            for r in _child_rows(client=client, table=HOLDINGS, period_id=period_id)
        }
        return contrib_syms == expected_contrib and hold_syms == expected_hold

    if period_row is None or not period_row.get("id"):
        return False
    period_id = UUID(str(period_row["id"]))
    contribs = _child_rows(client=client, table=CONTRIBUTIONS, period_id=period_id)
    if _row_implies_activity(period_row) and not contribs:
        return False
    hold_syms = {
        str(r.get("symbol") or "").strip().upper()
        for r in _child_rows(client=client, table=HOLDINGS, period_id=period_id)
    }
    # Every contribution with positive closing quantity must have a holding row —
    # a crash between contrib INSERT and holdings INSERT must not select as final.
    for row in contribs:
        qty = _decimal(row.get("closing_quantity")) or Decimal(0)
        if qty <= 0:
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym or sym not in hold_syms:
            return False
    return True


def select_final_period(*, client: SupabaseClient, period_date: date) -> dict[str, Any] | None:
    """Authoritative finalized period for ``period_date``, or None.

    Only a complete head with ``status=final`` qualifies. Provisional H9 NAV rows
    live elsewhere and are never returned here. Incomplete / estimated / failed
    heads remain visible via :func:`period_head` but are not authoritative.
    """
    head = period_head(client=client, period_date=period_date)
    if head is None:
        return None
    if str(head.get("status") or "") != PeriodStatus.FINAL:
        return None
    if not period_children_complete(client=client, period_row=head):
        return None
    return head


def _period_payload_matches(row: dict[str, Any], period: AccountingPeriod) -> bool:
    """Exact-retry identity: same PK must carry the same measured fields."""
    checks: list[tuple[Any, Any]] = [
        (str(row.get("period_date") or "")[:10], period.period_date.isoformat()),
        (str(row.get("policy_version_id") or ""), period.policy_version_id),
        (str(row.get("status") or ""), period.status.value),
        (_decimal(row.get("opening_equity")), period.opening_equity),
        (_decimal(row.get("closing_equity")), period.closing_equity),
        (_decimal(row.get("opening_cash")), period.opening_cash),
        (_decimal(row.get("closing_cash")), period.closing_cash),
        (_decimal(row.get("cash_pnl")), period.cash_pnl),
        (_decimal(row.get("residual")), period.residual),
    ]
    for left, right in checks:
        if left != right:
            return False
    return True


def _period_row(
    period: AccountingPeriod,
    *,
    effective_at: datetime,
    supersedes_id: UUID | None,
) -> dict[str, Any]:
    if effective_at.tzinfo is None or effective_at.utcoffset() != timedelta(0):
        raise ValueError("effective_at must be timezone-aware UTC")
    return {
        "id": str(period.id),
        "period_date": period.period_date.isoformat(),
        "policy_version_id": period.policy_version_id,
        "status": period.status.value,
        "quality_reasons": [r.value for r in period.quality_reasons],
        "opening_equity": _dec_str(period.opening_equity),
        "closing_equity": _dec_str(period.closing_equity),
        "opening_cash": _dec_str(period.opening_cash),
        "closing_cash": _dec_str(period.closing_cash),
        "cash_pnl": _dec_str(period.cash_pnl),
        "cash_contribution": _dec_str(period.cash_contribution),
        "gross_pnl_total": _dec_str(period.gross_pnl_total),
        "net_pnl_total": _dec_str(period.net_pnl_total),
        "fees_total": _dec_str(period.fees_total),
        "slippage_total": _dec_str(period.slippage_total),
        "residual": _dec_str(period.residual),
        "absolute_tolerance": _dec_str(period.absolute_tolerance),
        "relative_tolerance": _dec_str(period.relative_tolerance),
        "benchmark_symbol": period.benchmark_symbol,
        "benchmark_return": _dec_str(period.benchmark_return),
        "supersedes_id": str(supersedes_id) if supersedes_id else None,
        "effective_at": effective_at.isoformat(),
    }


def _contribution_rows(period: AccountingPeriod) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in period.ticker_results:
        rows.append(_contribution_row(period.id, period.period_date, ticker))
    return rows


def _contribution_row(
    period_id: UUID, period_date: date, ticker: TickerPeriodResult
) -> dict[str, Any]:
    return {
        "id": str(contribution_row_id(period_id, ticker.symbol)),
        "period_id": str(period_id),
        "period_date": period_date.isoformat(),
        "symbol": ticker.symbol,
        "opening_quantity": _dec_str(ticker.opening_quantity),
        "closing_quantity": _dec_str(ticker.closing_quantity),
        "opening_mark": _dec_str(ticker.opening_mark),
        "closing_mark": _dec_str(ticker.closing_mark),
        "gross_pnl": _dec_str(ticker.gross_pnl),
        "fees": _dec_str(ticker.fees),
        "slippage": _dec_str(ticker.slippage),
        "net_pnl": _dec_str(ticker.net_pnl),
        "contribution": _dec_str(ticker.contribution),
        "quality_reasons": [r.value for r in ticker.quality_reasons],
    }


def _holding_rows(period: AccountingPeriod) -> list[dict[str, Any]]:
    return [
        _holding_row(period.id, period.period_date, holding) for holding in period.closing_holdings
    ]


def _holding_row(period_id: UUID, period_date: date, holding: ClosingHolding) -> dict[str, Any]:
    return {
        "id": str(holding_row_id(period_id, holding.symbol)),
        "period_id": str(period_id),
        "period_date": period_date.isoformat(),
        "symbol": holding.symbol,
        "quantity": _dec_str(holding.quantity),
        "mark": _dec_str(holding.mark),
        "market_value": _dec_str(holding.market_value),
    }


def _ensure_children(*, client: SupabaseClient, period: AccountingPeriod) -> bool:
    """Insert any missing contribution/holding rows. Returns True if any were written."""
    repaired = False
    existing_contrib = {
        str(r.get("id"))
        for r in _child_rows(client=client, table=CONTRIBUTIONS, period_id=period.id)
    }
    missing_contrib = [
        row for row in _contribution_rows(period) if row["id"] not in existing_contrib
    ]
    if missing_contrib:
        _insert(client=client, table=CONTRIBUTIONS, rows=missing_contrib)
        repaired = True

    existing_hold = {
        str(r.get("id")) for r in _child_rows(client=client, table=HOLDINGS, period_id=period.id)
    }
    missing_hold = [row for row in _holding_rows(period) if row["id"] not in existing_hold]
    if missing_hold:
        _insert(client=client, table=HOLDINGS, rows=missing_hold)
        repaired = True
    return repaired


def persist_period(
    *,
    client: SupabaseClient,
    period: AccountingPeriod,
    effective_at: datetime | None = None,
    supersedes_id: UUID | None = None,
) -> PersistResult:
    """Persist one computed period atomically enough for exact retry.

    * Exact same inputs → same ``period.id`` → no-op (or child repair) success.
    * Different inputs → new ``period.id``; pass ``supersedes_id`` (or let the
      caller resolve the current head) so the chain tip advances.
    * Crash after the period row but before children → incomplete; not selectable
      as final until a retry repairs children.
    """
    stamp = effective_at or datetime.now(UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)

    existing = _fetch_period_by_id(client=client, period_id=period.id)
    if existing is not None:
        if not _period_payload_matches(existing, period):
            raise AccountingPersistError(
                f"period id {period.id} already exists with a different payload — "
                "deterministic id collision; refusing to append"
            )
        repaired = _ensure_children(client=client, period=period)
        if not period_children_complete(client=client, period=period):
            raise AccountingPersistError(
                f"period {period.id} exists but children remain incomplete after repair"
            )
        return PersistResult(
            period_id=period.id,
            status=period.status,
            wrote=False,
            repaired=repaired,
            superseded_id=(
                UUID(str(existing["supersedes_id"])) if existing.get("supersedes_id") else None
            ),
        )

    resolved_supersedes = supersedes_id
    if resolved_supersedes is None:
        head = period_head(client=client, period_date=period.period_date)
        if head is not None and str(head.get("id")) != str(period.id):
            resolved_supersedes = UUID(str(head["id"]))

    try:
        _insert(
            client=client,
            table=PERIODS,
            rows=[_period_row(period, effective_at=stamp, supersedes_id=resolved_supersedes)],
        )
        _ensure_children(client=client, period=period)
    except Exception:
        # Leave whatever landed; exact retry repairs or refuses selection.
        logger.exception(
            "accounting persist failed for period %s (%s) — no partial final published",
            period.id,
            period.period_date.isoformat(),
        )
        raise

    if not period_children_complete(client=client, period=period):
        raise AccountingPersistError(f"period {period.id} persisted without a complete child set")

    return PersistResult(
        period_id=period.id,
        status=period.status,
        wrote=True,
        repaired=False,
        superseded_id=resolved_supersedes,
    )


def period_day_return_pct(period_row: dict[str, Any]) -> float | None:
    """Percent day return from a persisted period row: ``(E1 - E0) / E0 * 100``."""
    e0 = _decimal(period_row.get("opening_equity"))
    e1 = _decimal(period_row.get("closing_equity"))
    if e0 is None or e1 is None or e0 <= 0:
        return None
    return float(((e1 - e0) / e0) * Decimal(100))
