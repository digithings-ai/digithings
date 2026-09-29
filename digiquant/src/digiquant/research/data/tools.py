"""Expose the Supabase value queries as research-agent function tools.

Two surfaces share the same query functions: these in-process ToolDefinitions
(for chat_completion_with_tools) and the MCP tools in digiquant.mcp_server.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import (  # score:allow untyped any — scored-lint suppression: duck-typed client + tool args
    Any,
    Callable,
)

from digiquant.research.data.queries import (
    get_etf_flows_proxy,
    get_fed_rate_probabilities,
    get_macro_series,
    get_market_breadth,
    get_price_technicals,
    get_sector_relative_strength,
    get_vix_term_structure,
)
from digiquant.supabase_retry import run_with_supabase_retry

logger = logging.getLogger(__name__)


class _UnknownToolError(ValueError):
    """Unknown tool name — returned as Error:, never retried."""


DATA_TOOLS: list[dict[str, Any]] = [
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
            "name": "get_price_technicals",
            "description": (
                "Recent computed technical indicators for one ticker, newest first — "
                "sma/rsi/macd/adx/atr/zscore and friends. Use to ground trend, momentum, "
                "and relative-strength claims with real values. Reads the maintained "
                "price_technicals reader (the R2 cache under the cutover flag, #3780); "
                "price_history/price_technicals are NOT readable through query_research."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol, e.g. SPY."},
                    "lookback": {
                        "type": "integer",
                        "description": "Recent rows to return (default 20, max 500).",
                    },
                },
                "required": ["ticker"],
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


def build_data_tool_dispatcher(
    client: Any,
    run_date: date | None = None,
    allowed_tables: frozenset[str] | None = None,
) -> Callable[[str, dict[str, Any]], str]:
    """Return an ``execute_tool(name, args) -> json_str`` bound to a Supabase client.

    ``run_date`` anchors the "as of" reads (breadth / relative-strength / VIX) to the
    run's logical date so tool outputs are reproducible and look-ahead-safe for
    backfills and delta runs. Defaults to today for interactive/MCP callers.

    ``allowed_tables`` is retained for callers that narrow the (typed-reader) data
    surface; ``None`` keeps the full read whitelist.
    """
    as_of = run_date or datetime.now(UTC).date()

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            result = run_with_supabase_retry(
                lambda: _dispatch(name, args),
                operation=f"data tool {name}",
            )
        except _UnknownToolError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # tool errors are returned to the model, not raised
            logger.warning("data tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"
        if isinstance(result, str):
            return result  # already an Error: string (e.g. missing table arg)
        return json.dumps(result, default=str)

    def _dispatch(name: str, args: dict[str, Any]) -> Any:
        if name == "get_macro_series":
            return get_macro_series(
                client=client,
                series_ids=list(args.get("series_ids", [])),
                lookback=int(args.get("lookback", 6)),
                as_of=as_of,
            )
        if name == "get_price_technicals":
            ticker = str(args.get("ticker") or "").strip()
            if not ticker:
                return "Error: get_price_technicals requires a 'ticker' argument."
            return get_price_technicals(
                client=client,
                ticker=ticker,
                lookback=int(args.get("lookback", 20)),
                as_of=as_of,
            )
        if name == "get_market_breadth":
            # Readers filter <= as_of and take the newest row → "as of the run date".
            return get_market_breadth(client=client, run_date=as_of)
        if name == "get_sector_relative_strength":
            return get_sector_relative_strength(client=client, run_date=as_of)
        if name == "get_vix_term_structure":
            return get_vix_term_structure(client=client, run_date=as_of)
        if name == "get_etf_flows_proxy":
            return get_etf_flows_proxy(client=client, run_date=as_of)
        if name == "get_fed_rate_probabilities":
            return get_fed_rate_probabilities(client=client, run_date=as_of)
        raise _UnknownToolError(f"unknown tool {name!r}")

    return execute_tool
