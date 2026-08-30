"""Holding-change and execution-alert event detectors for K5 email."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from digiquant.notify.mailgun import MailgunConfig, unsubscribe_url


class SupabaseReader(Protocol):
    def table(self, name: str) -> Any: ...


@dataclass(frozen=True)
class HoldingChangeEvent:
    workspace_id: str
    run_date: str
    ticker: str
    change_kind: str
    current_weight_pct: float | None
    prior_weight_pct: float | None
    delta_pp: float | None
    unsubscribe_url: str

    @property
    def event_key(self) -> str:
        return f"holding:{self.ticker}:{self.run_date}"


@dataclass(frozen=True)
class ExecutionAlertEvent:
    workspace_id: str
    run_date: str
    symbol: str
    side: str
    quantity: str
    price: str
    executed_at: str
    unsubscribe_url: str
    fill_id: str

    @property
    def event_key(self) -> str:
        return f"execution:{self.fill_id}"


_FLAT_EPSILON_PP = 0.01


def _numeric(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def holding_weight_change(
    current_pct: float | None,
    prior_pct: float | None,
) -> tuple[str, float | None]:
    """Mirror frontend holding-weight-change.ts semantics."""
    now = current_pct
    before = prior_pct
    if now is None and before is None:
        return "gone", None
    if before is None:
        return "new", None
    if now is None:
        return "gone", None
    delta = now - before
    if abs(delta) < _FLAT_EPSILON_PP:
        return "unchanged", 0.0
    return ("increased" if delta > 0 else "decreased"), delta


def detect_holding_changes(
    sb: SupabaseReader,
    workspace_id: str,
    run_date: date,
    mailgun_config: MailgunConfig,
) -> list[HoldingChangeEvent]:
    """Compare book weights between run_date and the prior position date."""
    d = run_date.isoformat()
    current_res = (
        sb.table("positions")
        .select("ticker,weight_pct")
        .eq("workspace_id", workspace_id)
        .eq("date", d)
        .execute()
    )
    current_rows = getattr(current_res, "data", None) or []
    prior_res = (
        sb.table("positions")
        .select("date")
        .eq("workspace_id", workspace_id)
        .lt("date", d)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    prior_date_rows = getattr(prior_res, "data", None) or []
    if not prior_date_rows:
        return []
    prior_d = str(prior_date_rows[0]["date"])[:10]
    prior_pos_res = (
        sb.table("positions")
        .select("ticker,weight_pct")
        .eq("workspace_id", workspace_id)
        .eq("date", prior_d)
        .execute()
    )
    prior_rows = getattr(prior_pos_res, "data", None) or []
    prior_map = {
        str(r["ticker"]): _numeric(r.get("weight_pct")) for r in prior_rows if r.get("ticker")
    }
    unsub = unsubscribe_url(workspace_id, mailgun_config)
    events: list[HoldingChangeEvent] = []
    seen: set[str] = set()
    for row in current_rows:
        ticker = str(row.get("ticker") or "")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        now = _numeric(row.get("weight_pct"))
        before = prior_map.get(ticker)
        kind, delta = holding_weight_change(now, before)
        if kind in ("unchanged", "gone") and before is None and now is None:
            continue
        if kind == "unchanged":
            continue
        events.append(
            HoldingChangeEvent(
                workspace_id=workspace_id,
                run_date=d,
                ticker=ticker,
                change_kind=kind,
                current_weight_pct=now,
                prior_weight_pct=before,
                delta_pp=delta,
                unsubscribe_url=unsub,
            )
        )
    for ticker, before in prior_map.items():
        if ticker in seen:
            continue
        now = None
        kind, delta = holding_weight_change(now, before)
        if kind == "gone":
            events.append(
                HoldingChangeEvent(
                    workspace_id=workspace_id,
                    run_date=d,
                    ticker=ticker,
                    change_kind=kind,
                    current_weight_pct=None,
                    prior_weight_pct=before,
                    delta_pp=delta,
                    unsubscribe_url=unsub,
                )
            )
    return events


def detect_execution_alerts(
    sb: SupabaseReader,
    workspace_id: str,
    run_date: date,
    mailgun_config: MailgunConfig,
) -> list[ExecutionAlertEvent]:
    """New broker mirror fills recorded on run_date (K4 tables)."""
    d = run_date.isoformat()
    start = f"{d}T00:00:00+00:00"
    end = f"{(run_date + timedelta(days=1)).isoformat()}T00:00:00+00:00"
    fills_res = (
        sb.table("broker_executions")
        .select("id,symbol,quantity,price,executed_at,broker_order_id")
        .eq("workspace_id", workspace_id)
        .gte("recorded_at", start)
        .lt("recorded_at", end)
        .execute()
    )
    fill_rows = getattr(fills_res, "data", None) or []
    if not fill_rows:
        return []
    order_ids = [r["broker_order_id"] for r in fill_rows if r.get("broker_order_id")]
    side_map: dict[str, str] = {}
    if order_ids:
        orders_res = sb.table("broker_orders").select("id,side").in_("id", order_ids).execute()
        for row in getattr(orders_res, "data", None) or []:
            side_map[str(row["id"])] = str(row.get("side") or "buy")
    unsub = unsubscribe_url(workspace_id, mailgun_config)
    events: list[ExecutionAlertEvent] = []
    for row in fill_rows:
        fill_id = str(row.get("id") or "")
        if not fill_id:
            continue
        order_id = str(row.get("broker_order_id") or "")
        events.append(
            ExecutionAlertEvent(
                workspace_id=workspace_id,
                run_date=d,
                symbol=str(row.get("symbol") or ""),
                side=side_map.get(order_id, "buy"),
                quantity=str(row.get("quantity") or ""),
                price=str(row.get("price") or ""),
                executed_at=str(row.get("executed_at") or ""),
                unsubscribe_url=unsub,
                fill_id=fill_id,
            )
        )
    return events


__all__ = [
    "ExecutionAlertEvent",
    "HoldingChangeEvent",
    "detect_execution_alerts",
    "detect_holding_changes",
    "holding_weight_change",
]
