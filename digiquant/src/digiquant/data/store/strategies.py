"""Polars-friendly accessor for the DigiQuant strategy store (#1064).

Read/write helpers over the dedicated DigiQuant Supabase project (see
:mod:`digiquant.data.store.client`). Writers use the service role (which bypasses
RLS); public read helpers project only the non-sensitive columns. Fitted
calibration params live in the private ``strategy_calibrations`` sidecar and are
reachable only via the service-role helpers here — never exposed to anon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any  # noqa: ANN401 — JSONB payloads and driver rows are dynamic at the DB boundary

import polars as pl

from digibase.audit import redact_mapping

from digiquant.data.prices._utils import call_with_retry as _call_with_retry
from digiquant.data.store.client import SupabaseLike

# Non-sensitive ``strategies`` columns — safe to expose / project on public reads.
# Deliberately excludes anything from the private ``strategy_calibrations`` sidecar.
PUBLIC_STRATEGY_COLUMNS: tuple[str, ...] = (
    "id",
    "symbol",
    "label",
    "engine",
    "config",
    "enabled",
    "version",
    "created_at",
    "updated_at",
)

DEFAULT_CHUNK = 500


@dataclass(frozen=True)
class WriteResult:
    table: str
    rows: int


def _chunks(rows: list[dict[str, Any]], chunk: int):
    for i in range(0, len(rows), chunk):
        yield rows[i : i + chunk]


def _iso(value: Any) -> Any:
    """Coerce date/datetime to an ISO string for PostgREST; pass through otherwise."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _emit_audit(table: str, rows: int, operation: str) -> None:
    """Redacted audit hook (no row bodies — payloads may carry licensed data)."""
    redact_mapping({"table": table, "rows": rows, "operation": operation})


def _write(
    client: SupabaseLike,
    table: str,
    rows: list[dict[str, Any]],
    *,
    op: str = "upsert",
    chunk: int = DEFAULT_CHUNK,
) -> WriteResult:
    """Chunked ``upsert``/``insert`` with retry + a redacted audit record.

    Empty ``rows`` is a no-op. Each chunk is a blocking PostgREST round-trip
    wrapped in :func:`call_with_retry`; ``op`` selects the PostgREST verb.
    """
    if not rows:
        return WriteResult(table=table, rows=0)
    total = 0
    for batch in _chunks(rows, chunk):
        _call_with_retry(lambda b=batch: getattr(client.table(table), op)(b).execute())
        total += len(batch)
    _emit_audit(table, total, op)
    return WriteResult(table=table, rows=total)


# ─── Strategies (public) ──────────────────────────────────────────────────────


def upsert_strategies(
    client: SupabaseLike,
    rows: list[dict[str, Any]],
    *,
    chunk: int = DEFAULT_CHUNK,
) -> WriteResult:
    """Upsert ``strategies`` rows (keyed on ``id``)."""
    return _write(client, "strategies", rows, op="upsert", chunk=chunk)


def read_strategies(client: SupabaseLike, *, enabled_only: bool = False) -> pl.DataFrame:
    """Read the public ``strategies`` columns into a Polars frame."""
    query = client.table("strategies").select(",".join(PUBLIC_STRATEGY_COLUMNS))
    if enabled_only:
        query = query.eq("enabled", True)
    resp = query.execute()
    return pl.DataFrame(resp.data or [])


# ─── Calibrations (private sidecar — service-role only) ─────────────────────────


def upsert_calibration(
    client: SupabaseLike,
    strategy_id: str,
    calibration: dict[str, Any],
    *,
    as_of: Any | None = None,
) -> WriteResult:
    """Write the private fitted calibration for a strategy (service-role only)."""
    row: dict[str, Any] = {"strategy_id": strategy_id, "calibration": calibration}
    if as_of is not None:
        row["as_of"] = _iso(as_of)
    return _write(client, "strategy_calibrations", [row], op="upsert")


def read_calibration(client: SupabaseLike, strategy_id: str) -> dict[str, Any] | None:
    """Read a strategy's private calibration (requires the service-role client)."""
    resp = (
        client.table("strategy_calibrations")
        .select("calibration")
        .eq("strategy_id", strategy_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0].get("calibration") if rows else None


# ─── Signals + tearsheets (public) ──────────────────────────────────────────────


def upsert_signal(
    client: SupabaseLike,
    *,
    strategy_id: str,
    position: str,
    as_of: Any,
    last_signal_date: Any | None = None,
    last_price: float | None = None,
) -> WriteResult:
    """Upsert the current signal/state for a strategy (one row per strategy)."""
    row: dict[str, Any] = {
        "strategy_id": strategy_id,
        "position": position,
        "as_of": _iso(as_of),
    }
    if last_signal_date is not None:
        row["last_signal_date"] = _iso(last_signal_date)
    if last_price is not None:
        row["last_price"] = last_price
    return _write(client, "strategy_signals", [row], op="upsert")


def read_signals(client: SupabaseLike) -> pl.DataFrame:
    """Read all current strategy signals into a Polars frame."""
    resp = client.table("strategy_signals").select("*").execute()
    return pl.DataFrame(resp.data or [])


def upsert_tearsheet(
    client: SupabaseLike,
    *,
    strategy_id: str,
    metrics: dict[str, Any],
    as_of: Any,
    equity_curve: Any | None = None,
) -> WriteResult:
    """Upsert the latest tearsheet payload for a strategy (one row per strategy)."""
    row: dict[str, Any] = {
        "strategy_id": strategy_id,
        "metrics": metrics,
        "as_of": _iso(as_of),
    }
    if equity_curve is not None:
        row["equity_curve"] = equity_curve
    return _write(client, "strategy_tearsheets", [row], op="upsert")


# ─── Trades ─────────────────────────────────────────────────────────────────────


def _coerce_trade(row: dict[str, Any]) -> dict[str, Any]:
    """Copy a trade row, ISO-coercing the entry/exit timestamps when present."""
    out = dict(row)
    for key in ("entry_ts", "exit_ts"):
        if key in out:
            out[key] = _iso(out[key])
    return out


def record_trades(
    client: SupabaseLike,
    rows: list[dict[str, Any]],
    *,
    chunk: int = DEFAULT_CHUNK,
) -> WriteResult:
    """Insert executed-trade rows for one or more strategies."""
    payload = [_coerce_trade(r) for r in rows]
    return _write(client, "strategy_trades", payload, op="insert", chunk=chunk)


__all__ = [
    "DEFAULT_CHUNK",
    "PUBLIC_STRATEGY_COLUMNS",
    "WriteResult",
    "read_calibration",
    "read_signals",
    "read_strategies",
    "record_trades",
    "upsert_calibration",
    "upsert_signal",
    "upsert_strategies",
    "upsert_tearsheet",
]
