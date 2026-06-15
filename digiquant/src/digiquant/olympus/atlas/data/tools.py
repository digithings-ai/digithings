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
    get_market_breadth,
    get_price_history,
    get_price_technicals,
    get_sector_relative_strength,
    get_vix_term_structure,
)

logger = logging.getLogger(__name__)

DATA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_price_technicals",
            "description": (
                "Latest technical indicators (sma/rsi/macd/adx/atr/zscore, etc.) plus a "
                "recent daily window for one ticker (e.g. SPY, XLK, TLT). Use to ground "
                "trend, momentum, and relative-strength claims on real data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol, e.g. SPY."},
                    "lookback": {
                        "type": "integer",
                        "description": "Recent trading days (default 20).",
                    },
                },
                "required": ["ticker"],
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
            "name": "get_price_history",
            "description": (
                "Raw daily OHLCV bars (open/high/low/close/volume) for one ticker, newest "
                "first. Use when you need actual price levels, returns, gaps, or volume — "
                "not just the pre-computed indicators."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol, e.g. SPY."},
                    "lookback": {
                        "type": "integer",
                        "description": "Recent trading days (default 60).",
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
]


def build_data_tool_dispatcher(
    client: Any, run_date: date | None = None
) -> Callable[[str, dict[str, Any]], str]:
    """Return an ``execute_tool(name, args) -> json_str`` bound to a Supabase client.

    ``run_date`` anchors the "as of" reads (breadth / relative-strength / VIX) to the
    run's logical date so tool outputs are reproducible and look-ahead-safe for
    backfills and delta runs. Defaults to today for interactive/MCP callers.
    """
    as_of = run_date or date.today()

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "get_price_technicals":
                result = get_price_technicals(
                    client=client, ticker=args["ticker"], lookback=int(args.get("lookback", 20))
                )
            elif name == "get_macro_series":
                result = get_macro_series(
                    client=client,
                    series_ids=list(args.get("series_ids", [])),
                    lookback=int(args.get("lookback", 6)),
                )
            elif name == "get_price_history":
                result = get_price_history(
                    client=client, ticker=args["ticker"], lookback=int(args.get("lookback", 60))
                )
            elif name == "get_market_breadth":
                # Readers filter <= as_of and take the newest row → "as of the run date".
                result = get_market_breadth(client=client, run_date=as_of)
            elif name == "get_sector_relative_strength":
                result = get_sector_relative_strength(client=client, run_date=as_of)
            elif name == "get_vix_term_structure":
                result = get_vix_term_structure(client=client, run_date=as_of)
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — tool errors are returned to the model, not raised
            logger.warning("data tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
