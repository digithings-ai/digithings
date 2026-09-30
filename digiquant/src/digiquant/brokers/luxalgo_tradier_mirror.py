"""Read-only Python mirror of luxalgo broker-sdk Tradier snapshots (#4848).

Mirrors ``@luxalgo/broker-sdk@0.5.1`` (MIT) ``BrokerSnapshot`` shapes in Python and
normalizes one SDK ``Account`` to digiquant broker contracts
(``brokers/contracts.py``). Pure normalization — no I/O, no HTTP, no credential
handling in this module. Mirror only: Tradier is the only other ``supportsBars``
broker besides Alpaca, but bars fetching is out of scope here — this module
takes already-fetched Account/Position/Trade dicts and contains no bars code.

Credential locality: API keys stay local to the caller. This module never sees
keys, never phones home, and never touches the network; the caller fetches the
snapshot (via the TypeScript SDK) and passes the already-fetched dict in.
Snapshots are caller-persisted; nothing here writes into ``positions`` (H9
terminal owns it) or any other table. Tradier's sandbox is the sole
observe-safe orders-evaluation target — that evaluation is a later,
separately-gated decision, NOT in scope here.

Tradier quirks handled upstream by the SDK adapter (never reimplemented here):
the single-position-object quirk (one position arrives as a bare object, not an
array), dividend-event filtering (history mixes trades with dividends — only
``type: trade`` rows become trades), and sell normalization (sells carry
negative quantities upstream and arrive as ``side: sell`` with a positive
quantity). Positions carry no ``marketValue`` because Tradier reports cost
basis, not market value — so it stays unset upstream and maps to zero here
(more honest than a guessed price); ``averageEntryPrice`` is derived upstream
from cost basis per unit.

JS-number precision: SDK floats cross the boundary via ``Decimal(str(x))``,
never float-through — ``0.1 + 0.2`` style artifacts must not become ledger
values. Timestamps normalize to UTC-aware datetimes.

Contract gaps filled with documented defaults (the SDK shape is thinner than
the contracts): ``buying_power`` is absent from the SDK account, so the mirror
sets it to ``max(cash, 0)`` — a conservative floor, never venue truth.
``unrealized_pl`` is absent from SDK positions, so it maps to zero (not a
performance claim). Trades carry no fill id, so the mirror synthesizes a
deterministic ``{account_id}:{index}:{SYMBOL}:{side}`` id. A trade missing
``executedAt`` falls back to the snapshot ``fetchedAt``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping  # score:allow untyped any — heterogeneous SDK snapshot payloads

from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerPosition,
)

SDK_VERSION = "0.5.1"
SDK_LICENSE = "MIT"

__all__ = [
    "SDK_LICENSE",
    "SDK_VERSION",
    "enrich_briefing_with_mirror",
    "snapshot_to_contracts",
    "summarize_mirror",
]


def _decimal(value: object) -> Decimal:
    """Parse a JS number (or numeric string) via ``Decimal(str(...))``."""
    if value is None:
        raise ValueError("expected a decimal value, got None")
    return Decimal(str(value))


def _as_utc(value: object, *, fallback: datetime | None = None) -> datetime:
    """Normalize an ISO string / epoch / datetime to a UTC-aware datetime."""
    if value is None:
        if fallback is not None:
            return fallback
        raise ValueError("expected a timestamp value, got None")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=UTC)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _account_id(account: Mapping[str, Any]) -> str:
    return str(account.get("id") or account.get("accountId") or "unknown")


def snapshot_to_contracts(
    account: Mapping[str, Any],
    *,
    fetched_at: object = None,
) -> tuple[BrokerAccountSnapshot, list[BrokerPosition], list[BrokerFill]]:
    """Map one SDK ``Account`` dict to broker contracts.

    ``fetched_at`` is the parent ``BrokerSnapshot fetchedAt`` — the ``as_of``
    for the account snapshot and the fallback ``executed_at`` for trades that
    carry none. An account-level ``fetchedAt``/``asOf`` key wins when present.
    No FX fabrication: values stay in the account's own currency, never
    converted. No bars code: this function maps positions/trades only.
    """
    stamped_at = _as_utc(account.get("fetchedAt", account.get("asOf", fetched_at)))
    acct_id = _account_id(account)
    cash = _decimal(account.get("cash", 0))

    snapshot = BrokerAccountSnapshot(
        account_id=acct_id,
        equity=_decimal(account.get("equity", 0)),
        cash=cash,
        buying_power=max(cash, Decimal("0")),
        currency=str(account.get("currency") or "USD"),
        as_of=stamped_at,
    )

    positions: list[BrokerPosition] = []
    raw_positions = account.get("positions") or []
    for raw in raw_positions:
        symbol = raw.get("symbol")
        if not symbol:
            raise ValueError("position is missing required field 'symbol'")
        positions.append(
            BrokerPosition(
                symbol=str(symbol),
                quantity=_decimal(raw.get("quantity", 0)),
                avg_entry_price=_decimal(raw.get("averageEntryPrice", 0)),
                market_value=_decimal(raw.get("marketValue", 0)),
                unrealized_pl=Decimal("0"),
            )
        )

    fills: list[BrokerFill] = []
    raw_trades = account.get("trades") or []
    for index, raw in enumerate(raw_trades):
        quantity = _decimal(raw.get("quantity", 0))
        price = _decimal(raw.get("price", 0))
        if quantity <= 0 or price <= 0:
            continue
        symbol = raw.get("symbol")
        if not symbol:
            raise ValueError("trade is missing required field 'symbol'")
        symbol = str(symbol)
        side = str(raw.get("side") or "buy").lower()
        fills.append(
            BrokerFill(
                external_fill_id=f"{acct_id}:{index}:{symbol.upper()}:{side}",
                symbol=symbol,
                quantity=quantity,
                price=price,
                fee=_decimal(raw["fee"]) if raw.get("fee") is not None else None,
                executed_at=_as_utc(raw.get("executedAt"), fallback=stamped_at),
            )
        )
    return snapshot, positions, fills


def summarize_mirror(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Equity-by-account + position counts for the briefing payload.

    JSON-safe (Decimals rendered as strings). Mirrors the SDK ``computeStats``
    shape minimally; no trade-stats port in this issue. Per-account rows keep
    their own currency — never summed across currencies.
    """
    fetched_at = _as_utc(snapshot.get("fetchedAt"))
    rows: list[dict[str, Any]] = []
    total_positions = 0
    for account in snapshot.get("accounts") or []:
        count = len(account.get("positions") or [])
        total_positions += count
        rows.append(
            {
                "account_id": _account_id(account),
                "currency": str(account.get("currency") or "USD").upper(),
                "equity": str(_decimal(account.get("equity", 0))),
                "position_count": count,
            }
        )
    return {
        "broker": str(snapshot.get("broker") or "tradier"),
        "fetched_at": fetched_at.isoformat(),
        "accounts": rows,
        "total_positions": total_positions,
    }


def enrich_briefing_with_mirror(
    briefing: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Append-only briefing enrichment (read consumer for #4848).

    Returns a copy of the ``digest_briefing_for_portfolio`` mapping with a
    read-only broker-mirror section appended to ``body``. The input mapping is
    never mutated; nothing is written into ``positions``.
    """
    summary = summarize_mirror(snapshot)
    lines = [
        "## Broker mirror (Tradier, read-only)",
        "",
        f"Snapshot at {summary['fetched_at']} "
        f"covering {summary['total_positions']} open position(s).",
        "",
    ]
    for row in summary["accounts"]:
        lines.append(
            f"- {row['account_id']} ({row['currency']}): "
            f"equity {row['equity']}, {row['position_count']} position(s)"
        )
    section = "\n".join(lines)
    body = str(briefing.get("body") or "")
    enriched = dict(briefing)
    enriched["body"] = f"{body.rstrip()}\n\n{section}\n" if body.strip() else f"{section}\n"
    return enriched
