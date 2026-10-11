#!/usr/bin/env python3
"""Record a real session against the local digiquant MCP server (read scope).

Launches ``python -m digiquant.mcp_server --stdio --scope read`` with the current
interpreter, runs a few calls, and writes the trimmed results to
``apps/digiquant-web/app/_mcp-transcript.json``. The digiquant.io home renders
that file as a dated "recorded session" — nothing in it is hand-written, so
re-run this script to refresh it:

    uv venv .venv && uv pip install -e "digiquant[mcp,research]"
    .venv/bin/python scripts/capture_mcp_transcript.py

Needs network (digifetch_* reads go through Gloomberb Cloud, anonymous,
free-tier delayed). Values are trimmed to a few fields per row; the envelope's
attribution and delay notice are carried through verbatim.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT = Path(__file__).resolve().parent.parent / "apps" / "digiquant-web" / "app" / "_mcp-transcript.json"
COMMAND = "python -m digiquant.mcp_server --stdio --scope read"
QUOTE_SYMBOLS = ["SPY", "QQQ", "BTC-USD"]
HISTORY_ARGS = {"symbol": "SPY", "resolution": "1d", "range": "1M"}
HISTORY_TAIL = 5


def _text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


async def _call(session: ClientSession, tool: str, args: dict) -> dict:
    result = await session.call_tool(tool, args)
    if result.isError:
        raise RuntimeError(f"{tool} failed: {_text(result)[:300]}")
    payload = json.loads(_text(result))
    if "error" in payload:
        raise RuntimeError(f"{tool} returned error: {payload['error']}")
    return payload


def _envelope(payload: dict) -> dict:
    keys = ("source", "fetched_at", "attribution", "delay_notice", "delay_note")
    return {k: payload[k] for k in keys if payload.get(k)}


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "digiquant.mcp_server", "--stdio", "--scope", "read"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools

            quotes = await _call(session, "digifetch_quotes_batch", {"symbols": QUOTE_SYMBOLS})
            quote_rows = []
            for item in quotes["data"]["quotes"]:
                q = item.get("quote") or {}
                quote_rows.append(
                    {
                        "symbol": item["symbol"],
                        "status": item["status"],
                        "price": q.get("price"),
                        "change_percent": q.get("change_percent"),
                        "market_state": q.get("market_state"),
                        "data_source": q.get("data_source"),
                    }
                )

            history = await _call(session, "digifetch_price_history", HISTORY_ARGS)
            bars = history["data"]["bars"]
            bar_rows = [{"date": b["date"], "close": b["close"], "volume": b["volume"]} for b in bars[-HISTORY_TAIL:]]

    transcript = {
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": COMMAND,
        "server": {"name": init.serverInfo.name, "protocolVersion": init.protocolVersion},
        "toolCount": len(tools),
        "calls": [
            {
                "tool": "digifetch_quotes_batch",
                "args": {"symbols": QUOTE_SYMBOLS},
                "envelope": _envelope(quotes),
                "columns": ["symbol", "price", "change_percent", "market_state", "data_source"],
                "rows": quote_rows,
            },
            {
                "tool": "digifetch_price_history",
                "args": HISTORY_ARGS,
                "envelope": _envelope(history),
                "columns": ["date", "close", "volume"],
                "rows": bar_rows,
                "meta": {"bar_count": history["data"]["metadata"]["bar_count"], "shown": f"last {len(bar_rows)}"},
            },
        ],
    }
    OUT.write_text(json.dumps(transcript, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
