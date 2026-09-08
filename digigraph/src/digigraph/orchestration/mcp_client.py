"""Remote MCP tool proxy for extra servers declared by a trusted BFF (#3736).

Operator YAML in digichat lists Streamable HTTP MCP URLs. The BFF forwards
allowlisted ``{id, url}`` pairs on ``X-Digi-Mcp-Servers``. This module lists
those tools (prefixed ``{id}__{name}``) and proxies calls. URLs never come
from an untrusted client body.

``DIGI_MCP_SERVERS`` (``id=https://…,id2=https://…``) is the process-wide
fallback from the remote-MCP backlog item.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_METADATA_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal"})
_CACHE_TTL_S = 60.0
_CALL_TIMEOUT_S = 30.0

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="digi-mcp")


def is_allowed_mcp_url(raw: str) -> bool:
    """https/http, no userinfo, no cloud-metadata hosts."""
    try:
        u = urlparse(raw.strip())
    except ValueError:
        return False
    if u.scheme not in ("http", "https"):
        return False
    if u.username or u.password:
        return False
    host = (u.hostname or "").lower()
    if not host or host in {"0.0.0.0", *_METADATA_HOSTS}:
        return False
    if host.endswith(".internal"):
        return False
    return True


def parse_mcp_servers_json(raw: str | None) -> list[dict[str, str]]:
    """Parse the BFF header. Unknown / malformed / oversize → empty."""
    if not raw or not raw.strip() or len(raw) > 8192:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        if not _ID_RE.match(sid) or sid in seen:
            continue
        if not is_allowed_mcp_url(url):
            continue
        seen.add(sid)
        out.append({"id": sid, "url": url})
    return out


def parse_mcp_servers_env(raw: str | None = None) -> list[dict[str, str]]:
    """``DIGI_MCP_SERVERS=id=https://host/mcp,other=https://…``."""
    text = (raw if raw is not None else os.environ.get("DIGI_MCP_SERVERS", "")).strip()
    if not text:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in text.split(","):
        piece = part.strip()
        if not piece or "=" not in piece:
            continue
        sid, url = piece.split("=", 1)
        sid = sid.strip().lower()
        url = url.strip()
        if not _ID_RE.match(sid) or sid in seen or not is_allowed_mcp_url(url):
            continue
        seen.add(sid)
        out.append({"id": sid, "url": url})
    return out


def merge_mcp_servers(
    header_servers: list[dict[str, str]],
    env_servers: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Header wins on id collision; env fills the rest."""
    env = env_servers if env_servers is not None else parse_mcp_servers_env()
    by_id = {s["id"]: s for s in env}
    for s in header_servers:
        by_id[s["id"]] = s
    return list(by_id.values())


def prefixed_tool_name(server_id: str, tool_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)[:64]
    return f"{server_id}__{safe}"


def resolve_mcp_force_id(raw: str | None, servers: list[dict[str, str]]) -> str | None:
    """Return the MCP server id when *raw* names an operator server, else None."""
    token = (raw or "").strip().lstrip("/").lower()
    if not token or not _ID_RE.match(token):
        return None
    return token if any(s.get("id") == token for s in servers) else None


def split_prefixed_tool_name(name: str) -> tuple[str, str] | None:
    if "__" not in name:
        return None
    sid, rest = name.split("__", 1)
    if not _ID_RE.match(sid) or not rest:
        return None
    return sid, rest


def extra_tool_names_for_servers(servers: list[dict[str, str]]) -> list[str]:
    names: list[str] = []
    for s in servers:
        for td in list_tools_cached(s["url"], s["id"]):
            fn = (td.get("function") or {}).get("name")
            if fn:
                names.append(str(fn))
    return names


def expand_mcp_disabled_tokens(
    tokens: list[str] | tuple[str, ...] | None,
    extra_names: list[str],
) -> frozenset[str]:
    """Disable ``id`` and ``id__*`` tools when the catalog MCP id is off."""
    if not tokens:
        return frozenset()
    extra = set(extra_names)
    out: set[str] = set()
    for raw in tokens:
        key = str(raw).strip().lower()
        if not key:
            continue
        prefix = f"{key}__"
        out |= {n for n in extra if n == key or n.startswith(prefix)}
    return frozenset(out)


def list_tools_cached(url: str, server_id: str) -> list[dict[str, Any]]:
    key = f"{server_id}|{url}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    tools = _list_tools_blocking(url, server_id)
    _cache[key] = (now, tools)
    return tools


def openai_tools_for_servers(servers: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in servers:
        out.extend(list_tools_cached(s["url"], s["id"]))
    return out


def call_prefixed_tool(
    name: str,
    args: dict[str, Any],
    servers: list[dict[str, str]],
) -> dict[str, Any]:
    split = split_prefixed_tool_name(name)
    if not split:
        return {"error": "unknown_mcp_tool", "tool": name}
    sid, tool = split
    url = next((s["url"] for s in servers if s["id"] == sid), None)
    if not url:
        return {"error": "unknown_mcp_server", "tool": name}
    return _call_tool_blocking(url, tool, args)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    fut = _pool.submit(asyncio.run, coro)
    return fut.result(timeout=_CALL_TIMEOUT_S + 5)


def _list_tools_blocking(url: str, server_id: str) -> list[dict[str, Any]]:
    try:
        return _run_async(_list_tools_async(url, server_id))
    except Exception as exc:
        log.warning("remote MCP list_tools failed for %s: %s", server_id, exc)
        return []


def _call_tool_blocking(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return _run_async(_call_tool_async(url, tool, args))
    except Exception as exc:
        log.warning("remote MCP call failed for %s: %s", tool, exc)
        return {"error": "mcp_call_failed", "tool": tool, "message": str(exc)}


async def _list_tools_async(url: str, server_id: str) -> list[dict[str, Any]]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    out: list[dict[str, Any]] = []
    for t in listed.tools:
        if isinstance(t.inputSchema, dict):
            schema = t.inputSchema
        else:
            schema = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": prefixed_tool_name(server_id, t.name),
                    "description": (t.description or "")[:2000],
                    "parameters": schema,
                },
            }
        )
    return out


async def _call_tool_async(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
    text_parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            text_parts.append(str(text))
    if result.isError:
        return {
            "error": "mcp_tool_error",
            "tool": tool,
            "message": "\n".join(text_parts) or "error",
        }
    if text_parts:
        return {"ok": True, "text": "\n".join(text_parts)}
    return {"ok": True, "result": str(result)}
