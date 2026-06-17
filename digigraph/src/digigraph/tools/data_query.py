"""Data-query tool for LLM-driven table access in the Atlas research pipeline.

Provides ``query_data`` — a Supabase SELECT wrapped in a tool so Atlas phase
nodes (and future LLM agents) can fetch live rows without a pre-flight data
dump.

Critical column hints are baked into the tool description so the LLM
(including cheap OpenRouter/auto models) never queries non-existent columns:

  * ``macro_series_observations`` — date column is ``obs_date`` (NOT ``date``).
  * ``price_technicals`` — has NO ``close`` column; use ``price_history`` for
    OHLCV data.

These mismatches were the root cause of repeated Postgres 42703
"column does not exist" errors that degraded grounding under the delta
pipeline's 25-analyst fan-out (#814).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-table column hints injected into the tool description so the LLM picks
# the right column names without querying information_schema.
#
# Format: { table_name: (date_col, note) }.  The note appears verbatim in the
# tool description so the model sees it in every call.
# ---------------------------------------------------------------------------
_TABLE_HINTS: dict[str, dict[str, str]] = {
    "macro_series_observations": {
        "date_col": "obs_date",
        "columns": "series_id, obs_date, value, unit, source",
        "note": "Date column is 'obs_date' (NOT 'date'). Never use 'date' here.",
    },
    "price_history": {
        "date_col": "price_date",
        "columns": "ticker, price_date, open, high, low, close, volume, adj_close",
        "note": "Use this table for OHLCV data. Has 'close' column.",
    },
    "price_technicals": {
        "date_col": "price_date",
        "columns": "ticker, price_date, sma_20, sma_50, sma_200, rsi_14, macd, macd_signal, bb_upper, bb_lower, atr_14",
        "note": (
            "Has NO 'close' column — use price_history for OHLCV. Date column is 'price_date'."
        ),
    },
    "positions": {
        "date_col": "as_of",
        "columns": "ticker, as_of, weight, quantity, market_value, unrealized_pnl, asset_class, sector",
        "note": "Current portfolio positions. Date column is 'as_of'.",
    },
    "daily_snapshots": {
        "date_col": "date",
        "columns": "date, run_type, nav, snapshot_json",
        "note": "Atlas daily run snapshots. Unique on 'date'.",
    },
    "documents": {
        "date_col": "published_at",
        "columns": "document_key, published_at, doc_type, content, ticker, run_date",
        "note": "Research documents. Unique on (run_date, document_key).",
    },
}


def _build_column_hints_text() -> str:
    """Render per-table column hints as a compact reference block."""
    lines: list[str] = []
    for table, info in _TABLE_HINTS.items():
        lines.append(f"  {table}: columns=[{info['columns']}] — {info['note']}")
    return "\n".join(lines)


# Tool schema exposed to the LLM. Column hints are inlined in the description
# so the model always knows the real column names without round-tripping to
# information_schema.
DATA_QUERY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_data",
        "description": (
            "Query a Supabase table and return matching rows as JSON. "
            "Use this to fetch live market data (prices, macro, positions) "
            "during research. Always use the column names listed below.\n\n"
            "COLUMN REFERENCE (use exact names — wrong names cause Postgres 42703 errors):\n"
            + _build_column_hints_text()
            + "\n\n"
            "If you need OHLCV price data (open/high/low/close/volume), "
            "use table='price_history', NOT 'price_technicals'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": (
                        "Table name (e.g. 'macro_series_observations', "
                        "'price_history', 'price_technicals', 'positions'). Required."
                    ),
                },
                "columns": {
                    "type": "string",
                    "description": (
                        "Comma-separated column list (e.g. 'ticker, price_date, close'). "
                        "Default '*'. Use exact column names from the reference above."
                    ),
                    "default": "*",
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Key-value equality filters (e.g. {'ticker': 'SPY'}). "
                        "Values are matched with eq()."
                    ),
                },
                "order_by": {
                    "type": "string",
                    "description": "Column to sort by (ascending). Optional.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default 50, max 500).",
                    "default": 50,
                },
            },
            "required": ["table"],
        },
    },
}


def handle_query_data(args: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """Execute a Supabase SELECT and return rows as ``{"rows": [...], "count": N}``.

    Guards:
    - Missing ``table`` key → returns an actionable error (not a KeyError traceback).
    - Known date-column aliases: ``date`` → ``obs_date`` for
      ``macro_series_observations`` is rewritten silently with a warning so
      a cheap model's column confusion does not hard-fail.
    - Row cap: capped at 500 to avoid context explosion.

    Requires ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` (or
    ``SUPABASE_SERVICE_KEY``) in the environment.
    """
    table = args.get("table")
    if not table or not str(table).strip():
        return {
            "error": (
                "query_data requires a 'table' argument. "
                "Available tables: "
                + ", ".join(_TABLE_HINTS.keys())
                + ". Check the column reference in the tool description."
            )
        }
    table = str(table).strip()

    columns: str = str(args.get("columns") or "*").strip() or "*"
    filters: dict[str, Any] = args.get("filters") or {}
    order_by: str | None = args.get("order_by") or None
    limit: int = min(int(args.get("limit") or 50), 500)

    # Server-side date-column alias rewrite for known mismatches.
    # The cheap OpenRouter/auto model consistently uses 'date' for
    # macro_series_observations; rewrite silently so the query succeeds.
    if table == "macro_series_observations":
        columns = _rewrite_col_alias(columns, "date", "obs_date", table)
        if isinstance(filters, dict) and "date" in filters:
            filters = {("obs_date" if k == "date" else k): v for k, v in filters.items()}
            logger.warning(
                "query_data: rewrote filter key 'date' -> 'obs_date' for table "
                "'macro_series_observations' (#814 column-hint guard)"
            )
        if order_by == "date":
            order_by = "obs_date"
            logger.warning(
                "query_data: rewrote order_by 'date' -> 'obs_date' for "
                "'macro_series_observations' (#814 column-hint guard)"
            )

    try:
        client = _get_supabase_client()
    except Exception as exc:
        return {"error": f"Supabase client init failed: {exc}"}

    try:
        q = client.table(table).select(columns)
        for col, val in (filters or {}).items():
            q = q.eq(str(col), val)
        if order_by:
            q = q.order(order_by)
        q = q.limit(limit)
        result = q.execute()
        rows = getattr(result, "data", None) or []
        return {"rows": rows, "count": len(rows), "table": table}
    except Exception as exc:
        err_msg = str(exc)
        # Surface 42703 column-does-not-exist errors with a hint.
        if "42703" in err_msg or "column" in err_msg.lower():
            hint = _TABLE_HINTS.get(table)
            col_ref = f"Valid columns: {hint['columns']}" if hint else "Check the column reference."
            return {
                "error": (
                    f"query_data: column error on table '{table}': {exc}. "
                    f"{col_ref} See the 'COLUMN REFERENCE' in the tool description."
                )
            }
        return {"error": f"query_data: {exc}"}


def _rewrite_col_alias(columns: str, old: str, new: str, table: str) -> str:
    """Rewrite a known-bad column alias in a SELECT list.

    Only rewrites exact standalone tokens (not substrings like 'update_date').
    """
    import re

    rewritten = re.sub(
        rf"(?<![a-zA-Z_]){re.escape(old)}(?![a-zA-Z_0-9])",
        new,
        columns,
    )
    if rewritten != columns:
        logger.warning(
            "query_data: rewrote column '%s' -> '%s' in SELECT list for table '%s' "
            "(#814 column-hint guard)",
            old,
            new,
            table,
        )
    return rewritten


def _get_supabase_client() -> Any:
    """Return a live Supabase client from environment variables."""
    try:
        from supabase import create_client  # optional dep — not installed in test env
    except ImportError as exc:
        raise RuntimeError(
            "supabase package not installed. "
            "Add 'supabase' to your service's extras or install it directly."
        ) from exc

    url = os.environ.get("SUPABASE_URL", "").strip()
    # Accept either key name used across services.
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.environ.get("SUPABASE_SERVICE_KEY", "")
    ).strip()
    if not url or not key:
        missing = [
            v for v, val in [("SUPABASE_URL", url), ("SUPABASE_SERVICE_ROLE_KEY", key)] if not val
        ]
        raise RuntimeError(f"query_data: missing Supabase env var(s): {', '.join(missing)}")
    return create_client(url, key)


__all__ = [
    "DATA_QUERY_TOOL",
    "_TABLE_HINTS",
    "handle_query_data",
]
