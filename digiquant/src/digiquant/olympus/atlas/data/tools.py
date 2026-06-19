"""Expose the Supabase value queries as research-agent function tools.

Two surfaces share the same query functions: these in-process ToolDefinitions
(for chat_completion_with_tools) and the MCP tools in digiquant.mcp_server.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable  # noqa  # scored-lint suppression: duck-typed client + tool args

from digiquant.olympus.atlas.data.queries import (
    get_macro_series,
    get_etf_flows_proxy,
    get_fed_rate_probabilities,
    get_market_breadth,
    get_sector_relative_strength,
    get_vix_term_structure,
    query_data,
)

logger = logging.getLogger(__name__)

DATA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_data",
            "description": (
                "Generic read of any market-data table to ground a claim in real numbers "
                "(backed by digibase, scoped read-only to the data tables). Allowed tables: "
                "price_history (daily OHLCV — columns: ticker, date, open, high, low, close, volume), "
                "price_technicals (indicators per ticker — columns: ticker, date, sma_20, sma_50, "
                "sma_200, rsi_14, macd, macd_signal, macd_hist, adx_14, atr_14, atr_pct, "
                "bb_upper, bb_lower, bb_pct_b, zscore_200; "
                "NOTE: price_technicals has NO 'close' column — use price_history for OHLCV), "
                "macro_series_observations (FRED macro — columns: series_id, obs_date, value; "
                "NOTE: the date column is 'obs_date' NOT 'date'; filter/sort by obs_date), "
                "positions, nav_history, theses, thesis_vehicles, position_events, "
                "portfolio_metrics, trading_calendar. "
                "Filter with eq/gte/lte/in_, sort with order+desc, cap with limit. Examples: "
                "{table:'price_technicals', eq:{ticker:'XLK'}, order:'date', desc:true, limit:20} "
                "or {table:'macro_series_observations', eq:{series_id:'DGS10'}, "
                "order:'obs_date', desc:true, limit:6} "
                "or {table:'price_history', eq:{ticker:'SPY'}, order:'date', desc:true, limit:5}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "One of the allowed tables."},
                    "columns": {
                        "type": "string",
                        "description": "Comma-separated columns, or '*' (default).",
                    },
                    "eq": {"type": "object", "description": "Equality filters {column: value}."},
                    "gte": {"type": "object", "description": ">= filters {column: value}."},
                    "lte": {"type": "object", "description": "<= filters {column: value}."},
                    "in_": {
                        "type": "object",
                        "description": "Membership filters {column: [values]}.",
                    },
                    "order": {"type": "string", "description": "Column to sort by."},
                    "desc": {"type": "boolean", "description": "Sort descending (default true)."},
                    "limit": {"type": "integer", "description": "Max rows (default 50, max 500)."},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_macro_series",
            "description": (
                "Latest values + recent window for FRED macro series ids (e.g. M2SL, DFF, "
                "DGS10, T10Y2Y, VIXCLS, DTWEXBGS, T10YIE). Use to ground macro-regime claims."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series_ids": {"type": "array", "items": {"type": "string"}},
                    "lookback": {
                        "type": "integer",
                        "description": "Recent observations (default 6).",
                    },
                },
                "required": ["series_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_breadth",
            "description": (
                "Market breadth across all tracked tickers: % above their 50- and 200-day "
                "moving average, the prior reading, and a trend label. Use to ground "
                "'broad vs narrow' / risk-on-off claims with a real participation number."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_relative_strength",
            "description": (
                "Per-sector-ETF excess return vs SPY over 21/63/126 trading days plus a "
                "cross-sectional rank (1.0 = strongest) and leading/lagging label. Use to "
                "ground sector-rotation and relative-strength claims."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vix_term_structure",
            "description": (
                "VIX term structure: spot VIX vs 3-month VIX, their ratio, and the state "
                "(backwardation = acute stress, contango = calm). Use to ground volatility-"
                "regime and hedging claims."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_etf_flows_proxy",
            "description": (
                "Per-sector-ETF volume PROXY for flows: a dollar-volume z-score (unusual "
                "turnover today vs its norm) and an OBV trend (accumulation vs distribution). "
                "This is a free volume-derived proxy, NOT true creations/redemptions — use it "
                "as a participation/turnover hint, and do not overstate it as fund flows."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fed_rate_probabilities",
            "description": (
                "Market-implied FOMC rate-decision odds for the nearest upcoming meeting, from "
                "prediction markets (Kalshi target-rate ladder as a 25bp probability distribution "
                "over the fed-funds upper bound, plus a Polymarket cross-check). Use to ground "
                "monetary-policy / rate-pivot claims; the market actively reprices these and the "
                "broad market pivots around FOMC decisions. Returns {} when no odds are available."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _coerce_bool(value: Any, *, default: bool = True) -> bool:
    """Coerce a tool-call arg to bool. Tool args may arrive as strings, so treat
    'false'/'0'/'no'/'' as False rather than letting ``bool('false')`` be True."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "")


def build_data_tool_dispatcher(
    client: Any,
    run_date: date | None = None,
    allowed_tables: frozenset[str] | None = None,
) -> Callable[[str, dict[str, Any]], str]:
    """Return an ``execute_tool(name, args) -> json_str`` bound to a Supabase client.

    ``run_date`` anchors the "as of" reads (breadth / relative-strength / VIX) to the
    run's logical date so tool outputs are reproducible and look-ahead-safe for
    backfills and delta runs. Defaults to today for interactive/MCP callers.

    ``allowed_tables`` narrows the tables ``query_data`` may read (e.g. market-data
    only for blinded analyst nodes); ``None`` keeps the full read whitelist.
    """
    as_of = run_date or date.today()

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "query_data":
                table = args.get("table")
                if not table:
                    return (
                        "Error: query_data requires a 'table' argument. "
                        "Allowed tables: price_history, price_technicals, "
                        "macro_series_observations, positions, nav_history, theses, "
                        "thesis_vehicles, position_events, portfolio_metrics, trading_calendar."
                    )
                # Server-side rewrite: the LLM sometimes sorts/filters macro_series_observations
                # by 'date' (the generic name) instead of 'obs_date' (the real column). Silently
                # correct it so the model gets useful data rather than a Postgres 42703 error (#814).
                if table == "macro_series_observations":
                    for filter_arg in ("eq", "gte", "lte"):
                        filt = args.get(filter_arg)
                        if isinstance(filt, dict) and "date" in filt:
                            filt = dict(filt)
                            filt["obs_date"] = filt.pop("date")
                            args = {**args, filter_arg: filt}
                    if args.get("order") == "date":
                        args = {**args, "order": "obs_date"}
                result = query_data(
                    client=client,
                    table=table,
                    columns=str(args.get("columns", "*")),
                    eq=args.get("eq"),
                    gte=args.get("gte"),
                    lte=args.get("lte"),
                    in_=args.get("in_"),
                    order=args.get("order"),
                    desc=_coerce_bool(args.get("desc", True)),
                    limit=int(args.get("limit", 50)),
                    allowed_tables=allowed_tables,
                )
            elif name == "get_macro_series":
                result = get_macro_series(
                    client=client,
                    series_ids=list(args.get("series_ids", [])),
                    lookback=int(args.get("lookback", 6)),
                )
            elif name == "get_market_breadth":
                # Readers filter <= as_of and take the newest row → "as of the run date".
                result = get_market_breadth(client=client, run_date=as_of)
            elif name == "get_sector_relative_strength":
                result = get_sector_relative_strength(client=client, run_date=as_of)
            elif name == "get_vix_term_structure":
                result = get_vix_term_structure(client=client, run_date=as_of)
            elif name == "get_etf_flows_proxy":
                result = get_etf_flows_proxy(client=client, run_date=as_of)
            elif name == "get_fed_rate_probabilities":
                result = get_fed_rate_probabilities(client=client, run_date=as_of)
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — tool errors are returned to the model, not raised
            logger.warning("data tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
