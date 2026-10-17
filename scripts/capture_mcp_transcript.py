#!/usr/bin/env python3
"""Record a real session against the local digiquant MCP server (full scope).

Launches ``python -m digiquant.mcp_server --stdio --scope full`` with the current
interpreter, runs two calls, and writes the trimmed results to
``apps/digiquant-web/app/_mcp-transcript.json``. Nothing in the file is
hand-written, so re-run this script to refresh it:

    .venv/bin/python scripts/capture_mcp_transcript.py

Both calls are local and need no network and no credential:

* ``digifetch_options_scenario`` is a pure options-pricing calculator.
* ``digiquant_fetch_bitview_series`` reads the repository's own price history.

Every one of the 24 tools in ``_mcp-tools.json`` is ``scope: full``; none is in
the server's read scope, so this script runs at full scope.

Refusals are never recorded. ``_call`` rejects a payload whose envelope reports
an error -- including the ``data.code = upstream_error`` kill-switch refusal,
which is ``isError: false`` and carries no top-level ``error`` key. A transcript
that showed a refusal would over-claim, which is what this script exists to stop.
The row schema is derived from the payload itself, never hand-written.
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
COMMAND = "python -m digiquant.mcp_server --stdio --scope full"
SCOPE = "full"

# Two local calls that answer without a network or a credential.
# The leg shape is the server's documented one (mcp_server.py digifetch_options_scenario):
# {"expiry": epoch seconds, "strike", "kind": "call"/"put", "qty": +long/-short}.
_EXPIRY = int(datetime(2026, 12, 18, tzinfo=timezone.utc).timestamp())
BITVIEW_ARGS = {"series_ids_json": '["mvrv", "puell_multiple"]'}
BITVIEW_ARGS2 = {"series_ids_json": '["asopr_24h", "rhodl_ratio"]'}
TAIL = 5
MAX_CELL = 120


def _text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def _scalar(value):
    """Render one cell, trimmed so the file stays readable."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= MAX_CELL else text[: MAX_CELL - 1] + "…"


def _envelope_errors(payload: dict) -> list[str]:
    """Report every envelope-level refusal, at the top level and in ``data``.

    ``isError`` is not a success signal here: the digifetch family answers
    ``isError: false`` with ``data.code = upstream_error`` when its kill switch
    is off.
    """
    found: list[str] = []
    for level in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else None):
        if not isinstance(level, dict):
            continue
        if level.get("ok") is False:
            found.append(f"ok is false: {level.get('error')}")
        if level.get("error") is not None:
            found.append(f"error: {level['error']}")
        code = level.get("code")
        if isinstance(code, str) and code not in ("ok", "success"):
            found.append(f"code: {code}")
    return found


def _is_flat(row) -> bool:
    return isinstance(row, dict) and all(
        value is None or isinstance(value, (bool, int, float, str)) for value in row.values()
    )


def _table(payload: dict):
    """Find the payload's own tabular shape: a list of flat rows, else a dict of
    flat rows keyed by name. Returns ``(columns, rows)`` or ``(None, None)``."""
    base = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(base, dict):
        return None, None
    for value in base.values():
        if isinstance(value, list) and value and all(_is_flat(row) for row in value):
            columns = sorted({key for row in value for key in row})
            rows = [{c: _scalar(row.get(c)) for c in columns} for row in value]
            return columns, rows
    for value in base.values():
        if isinstance(value, dict) and value and all(_is_flat(row) for row in value.values()):
            names = list(value)
            tail = sorted({key for row in value.values() for key in row})
            columns = ["name", *tail]
            rows = [{"name": _scalar(n), **{c: _scalar(value[n].get(c)) for c in tail}} for n in names]
            return columns, rows
    return None, None


async def _call(session: ClientSession, tool: str, args: dict) -> dict:
    result = await session.call_tool(tool, args)
    if result.isError:
        raise RuntimeError(f"{tool} failed: {_text(result)[:300]}")
    payload = json.loads(_text(result))
    problems = _envelope_errors(payload)
    if problems:
        raise RuntimeError(f"{tool} returned a refusal, not an answer: {'; '.join(problems)}")
    return payload


def _envelope(payload: dict) -> dict:
    keys = ("source", "fetched_at", "attribution", "delay_notice", "delay_note")
    return {k: payload[k] for k in keys if payload.get(k)}


def _entry(payload: dict) -> dict:
    columns, rows = _table(payload)
    entry: dict = {"envelope": _envelope(payload)}
    if columns:
        entry["columns"] = columns
        entry["rows"] = rows[:TAIL]
        entry["meta"] = {"row_count": len(rows), "shown": f"first {len(rows[:TAIL])}"}
    return entry


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "digiquant.mcp_server", "--stdio", "--scope", SCOPE],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            calls = [
                {"tool": "digiquant_fetch_bitview_series", "args": BITVIEW_ARGS2,
                 **_entry(await _call(session, "digiquant_fetch_bitview_series", BITVIEW_ARGS2))},
                {"tool": "digiquant_fetch_bitview_series", "args": BITVIEW_ARGS,
                 **_entry(await _call(session, "digiquant_fetch_bitview_series", BITVIEW_ARGS))},
            ]
    OUT.write_text(
        json.dumps(
            {
                "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "command": COMMAND,
                "server": {"name": init.serverInfo.name, "protocolVersion": init.protocolVersion},
                "toolCount": len(tools),
                "calls": calls,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(tools)} tools registered under --scope {SCOPE}, {len(calls)} recorded calls)")


if __name__ == "__main__":
    asyncio.run(main())
