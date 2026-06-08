"""Expose the Supabase value queries as research-agent function tools.

Two surfaces share the same query functions: these in-process ToolDefinitions
(for chat_completion_with_tools) and the MCP tools in digiquant.mcp_server.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable  # noqa  # scored-lint suppression: duck-typed client + tool args

from digiquant.olympus.atlas.data.queries import get_macro_series, get_price_technicals

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
]


def build_data_tool_dispatcher(client: Any) -> Callable[[str, dict[str, Any]], str]:
    """Return an ``execute_tool(name, args) -> json_str`` bound to a Supabase client."""

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
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — tool errors are returned to the model, not raised
            logger.warning("data tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
