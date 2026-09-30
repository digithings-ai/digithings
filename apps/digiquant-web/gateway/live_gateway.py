"""Local read-only gateway: static digiquant.io -> digiquant MCP server (stdio).

Local only. No secret ever reaches the browser: the MCP server runs as a child
process with a scrubbed environment (anonymous free tier), over stdio (no port).
There is NO generic tool passthrough; every route maps to an entry in PROBES.

Run:  python apps/digiquant-web/gateway/live_gateway.py   (see README.md)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Protocol

import httpx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

HOST = "127.0.0.1"
DEFAULT_PORT = 8792
DEFAULT_ORIGINS = ("http://localhost:3910", "http://127.0.0.1:3910")
MARKET_UPSTREAM = "https://graph.digithings.ai/v1/market"
MARKET_TTL = 300.0
MAX_PAYLOAD_BYTES = 200_000
RATE_LIMIT = 30  # requests per IP per window
RATE_WINDOW = 60.0
MAX_CONCURRENT_TOOLS = 4
SYMBOL_RE = re.compile(r"^[A-Za-z0-9.^=-]{1,12}$")
QUARTER_RE = re.compile(r"^\d{4}Q[1-4]$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUERY_RE = re.compile(r"^[A-Za-z0-9 .,&'_-]{1,60}$")
EMPTY_BAD = "Upstream returned no rows for these parameters."


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Bridge(Protocol):
    async def call(self, tool: str, args: dict[str, Any], timeout: float) -> dict[str, Any]: ...

    async def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# MCP stdio bridge (one long-lived session, reconnect on failure)
# --------------------------------------------------------------------------- #


def scrubbed_env() -> dict[str, str]:
    """PATH, HOME, PYTHONPATH, LANG and nothing else (no cookies, no keys)."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    env["LANG"] = os.environ.get("LANG", "en_US.UTF-8")
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    return env


class StdioBridge:
    def __init__(self) -> None:
        self._session: Any = None
        self._runner: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._dead = asyncio.Event()
        self._stop = asyncio.Event()
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_TOOLS)
        self._start_lock = asyncio.Lock()

    async def _run(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "digiquant.mcp_server", "--stdio", "--scope", "read"],
            env=scrubbed_env(),
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    waiters = [
                        asyncio.ensure_future(self._dead.wait()),
                        asyncio.ensure_future(self._stop.wait()),
                    ]
                    await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                    for w in waiters:
                        w.cancel()
        except Exception:
            pass
        finally:
            self._session = None
            self._ready.clear()

    async def _ensure(self) -> Any:
        async with self._start_lock:
            if self._runner is None or self._runner.done():
                self._dead.clear()
                self._ready.clear()
                self._runner = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._ready.wait(), 30)
        except asyncio.TimeoutError as exc:
            raise ToolError("upstream_error", "MCP server did not start") from exc
        if self._session is None:
            raise ToolError("upstream_error", "MCP server unavailable")
        return self._session

    async def call(self, tool: str, args: dict[str, Any], timeout: float) -> dict[str, Any]:
        async with self._sem:
            session = await self._ensure()
            try:
                res = await asyncio.wait_for(session.call_tool(tool, args), timeout)
            except asyncio.TimeoutError as exc:
                raise ToolError("timeout", f"{tool} timed out after {timeout:.0f}s") from exc
            except Exception as exc:  # transport failure: reconnect next call
                self._dead.set()
                raise ToolError(
                    "upstream_error", f"MCP transport error ({type(exc).__name__})"
                ) from exc
        return _parse_result(res)

    async def close(self) -> None:
        self._stop.set()
        if self._runner is not None:
            try:
                await asyncio.wait_for(self._runner, 5)
            except Exception:
                self._runner.cancel()


def _parse_result(res: Any) -> dict[str, Any]:
    payload: Any = getattr(res, "structuredContent", None)
    if not payload:
        text = res.content[0].text if getattr(res, "content", None) else ""
        if getattr(res, "isError", False):
            raise ToolError("invalid_input", text[:200] or "tool error")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ToolError("upstream_error", "tool returned non-JSON") from exc
    if getattr(res, "isError", False):
        raise ToolError("invalid_input", "tool error")
    if not isinstance(payload, dict):
        raise ToolError("upstream_error", "unexpected tool payload")
    # FastMCP wraps plain-string returns as {"result": "<json>"}
    if set(payload) == {"result"} and isinstance(payload["result"], str):
        try:
            payload = json.loads(payload["result"])
        except ValueError as exc:
            raise ToolError("upstream_error", "tool returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise ToolError("upstream_error", "unexpected tool payload")
    return payload


# --------------------------------------------------------------------------- #
# Param validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Param:
    kind: str  # symbol | int | enum | quarter | slug | query | year
    default: Any = None
    required: bool = False
    lo: int = 1
    hi: int = 50
    choices: tuple[str, ...] = ()
    doc: str = ""

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "required": self.required, "doc": self.doc}
        if self.default is not None:
            out["default"] = self.default
        if self.kind == "int":
            out.update(min=self.lo, max=self.hi)
        if self.choices:
            out["choices"] = list(self.choices)
        return out

    def parse(self, name: str, raw: str | None) -> Any:
        if raw is None or raw == "":
            if self.required and self.default is None:
                raise ToolError("invalid_input", f"missing param '{name}'")
            return self.default
        if self.kind == "symbol":
            if not SYMBOL_RE.match(raw):
                raise ToolError("invalid_input", f"'{name}' must match {SYMBOL_RE.pattern}")
            return raw.upper()
        if self.kind == "int":
            try:
                n = int(raw)
            except ValueError as exc:
                raise ToolError("invalid_input", f"'{name}' must be an integer") from exc
            return max(self.lo, min(self.hi, n))  # clamp
        if self.kind == "enum":
            if raw not in self.choices:
                raise ToolError("invalid_input", f"'{name}' must be one of {list(self.choices)}")
            return raw
        if self.kind == "quarter":
            if not QUARTER_RE.match(raw):
                raise ToolError("invalid_input", f"'{name}' must look like 2026Q2")
            return raw
        if self.kind == "slug":
            if not SLUG_RE.match(raw):
                raise ToolError("invalid_input", f"'{name}' must match {SLUG_RE.pattern}")
            return raw
        if self.kind == "query":
            if not QUERY_RE.match(raw):
                raise ToolError("invalid_input", f"'{name}' must match {QUERY_RE.pattern}")
            return raw
        raise ToolError("invalid_input", f"bad param kind for '{name}'")


# --------------------------------------------------------------------------- #
# Trimmers: upstream envelope -> small typed data. Return (data, extra_attrib).
# --------------------------------------------------------------------------- #


def _num(v: Any) -> float | int | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _s(v: Any, n: int = 240) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


def _d(o: dict[str, Any]) -> dict[str, Any]:
    d = o.get("data")
    return d if isinstance(d, dict) else {}


def t_quote(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    q = _d(o).get("quote") or {}
    if not q:
        return None, True
    return {
        "symbol": q.get("symbol"),
        "name": _s(q.get("name")),
        "price": _num(q.get("price")),
        "currency": q.get("currency"),
        "change": _num(q.get("change")),
        "changePct": _num(q.get("change_percent")),
        "previousClose": _num(q.get("previous_close")),
        "high52w": _num(q.get("high52w")),
        "low52w": _num(q.get("low52w")),
        "marketCap": _num(q.get("market_cap")),
        "volume": _num(q.get("volume")),
    }, False


def t_history(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    bars = _d(o).get("bars") or []
    out = [
        {
            "date": b.get("date"),
            "open": _num(b.get("open")),
            "high": _num(b.get("high")),
            "low": _num(b.get("low")),
            "close": _num(b.get("close")),
            "volume": _num(b.get("volume")),
        }
        for b in bars[-400:]
        if isinstance(b, dict)
    ]
    return {"symbol": p["symbol"], "range": p["range"], "resolution": "1d", "bars": out}, not out


def t_financials(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    f = _d(o).get("financials") or {}
    if not f:
        return None, True
    q, prof, fu = f.get("quote") or {}, f.get("profile") or {}, f.get("fundamentals") or {}
    pe = fu.get("trailing_pe") if fu.get("trailing_pe") is not None else fu.get("trailingPE")
    fpe = fu.get("forward_pe") if fu.get("forward_pe") is not None else fu.get("forwardPE")
    return {
        "symbol": q.get("symbol") or p["symbol"],
        "name": _s(q.get("name")),
        "sector": _s(prof.get("sector")),
        "industry": _s(prof.get("industry")),
        "description": _s(prof.get("description"), 400),
        "price": _num(q.get("price")),
        "changePct": _num(q.get("change_percent")),
        "currency": f.get("financial_currency"),
        "fundamentals": {
            "marketCap": _num(fu.get("market_cap")),
            "trailingPE": _num(pe),
            "forwardPE": _num(fpe),
            "eps": _num(fu.get("eps")),
            "revenue": _num(fu.get("revenue")),
            "netIncome": _num(fu.get("net_income")),
            "operatingMargin": _num(fu.get("operating_margin")),
            "profitMargin": _num(fu.get("profit_margin")),
            "freeCashFlow": _num(fu.get("free_cash_flow")),
            "dividendYield": _num(fu.get("dividend_yield")),
            "sharesOutstanding": _num(fu.get("shares_outstanding")),
        },
    }, False


def t_congress(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("trades") or []
    out = [
        {
            "id": r.get("id"),
            "member": _s(r.get("member_name"), 80),
            "ticker": r.get("ticker") if isinstance(r.get("ticker"), str) else None,
            "asset": _s(r.get("asset_name"), 120),
            "side": r.get("side") if r.get("side") in ("BUY", "SELL") else None,
            "transactionDate": r.get("transaction_date"),
            "filingDate": r.get("filing_date"),
            "amount": _s(r.get("amount"), 40),
            "sourceUrl": _s(r.get("source_url"), 300),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"trades": out}, not out


def t_predictions(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    now = datetime.now(timezone.utc).isoformat()
    rows = _d(o).get("markets") or []
    live = [
        r
        for r in rows
        if isinstance(r, dict)
        and (_num(r.get("yes_prob")) or 0) > 0
        and isinstance(r.get("ends_at"), str)
        and r["ends_at"] > now
    ]
    live.sort(key=lambda r: _num(r.get("volume_24h")) or 0, reverse=True)
    out = [
        {
            "title": _s(r.get("title"), 160),
            "venue": r.get("venue"),
            "yesProb": _num(r.get("yes_prob")),
            "volume24h": _num(r.get("volume_24h")),
            "endsAt": r.get("ends_at"),
            "category": _s(r.get("category"), 60),
            "url": _s(r.get("venue_url"), 300),
        }
        for r in live[: p["limit"]]
    ]
    return {"markets": out, "scanned": len(rows)}, not out


def t_funds(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("top_funds") or []
    out = [
        {
            "cik": r.get("cik"),
            "name": _s(r.get("name"), 100),
            "periodOfReport": r.get("period_of_report"),
            "pnl": _num(r.get("pnl")),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"quarter": p["quarter"], "funds": out}, not out


def t_yield(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("points") or []
    out = [
        {
            "maturity": r.get("maturity"),
            "years": _num(r.get("maturity_years")),
            "yield": _num(r.get("yield_") if "yield_" in r else r.get("yield")),
            "asOf": r.get("as_of"),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"points": out}, not out


def t_econ(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    d = _d(o)
    info = d.get("info") or {}
    obs = [
        {"date": r.get("date"), "value": _num(r.get("value"))}
        for r in (d.get("observations") or [])
        if isinstance(r, dict)
    ]
    return {
        "seriesId": p["series_id"],
        "title": _s(info.get("title"), 160),
        "units": _s(info.get("units"), 80),
        "frequency": _s(info.get("frequency"), 40),
        "observations": obs,
    }, not obs


def t_news(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("items") or []
    out = [
        {
            "id": r.get("id"),
            "headline": _s(r.get("headline"), 200),
            "summary": _s(r.get("summary"), 240),
            "topic": r.get("topic"),
            "sentiment": r.get("sentiment"),
            "publishedAt": r.get("first_published_at"),
            "source": _s(r.get("primary_source"), 60),
            "url": _s(r.get("primary_url"), 400),
        }
        for r in rows[: p["limit"]]
        if isinstance(r, dict)
    ]
    return {"symbol": p.get("symbol"), "items": out}, not out


def t_search(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("results") or []
    out = [
        {
            "symbol": r.get("symbol"),
            "name": _s(r.get("name"), 100),
            "exchange": r.get("exchange"),
            "type": r.get("type"),
            "currency": r.get("currency"),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"results": out}, not out


def t_filings(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("filings") or []
    out = [
        {
            "form": r.get("form"),
            "filingDate": r.get("filing_date"),
            "company": _s(r.get("company_name"), 100),
            "description": _s(r.get("primary_doc_description"), 100),
            "url": _s(r.get("primary_document_url"), 400),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"symbol": p["symbol"], "filings": out}, not out


def t_lux_search(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("results") or []
    out = [
        {
            "kind": r.get("kind"),
            "slug": r.get("slug"),
            "name": _s(r.get("name"), 100),
            "family": r.get("family"),
            "url": _s(r.get("url"), 300),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"query": p["query"], "results": out}, not out


def t_lux_families(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    rows = _d(o).get("families") or []
    out = [
        {
            "key": r.get("key"),
            "name": _s(r.get("name"), 60),
            "conceptCount": _num(r.get("concept_count")),
            "url": _s(r.get("url"), 300),
        }
        for r in rows
        if isinstance(r, dict)
    ]
    return {"families": out}, not out


def t_lux_presets(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    d = _d(o)
    out = [
        {
            "id": r.get("id"),
            "title": _s(r.get("title"), 100),
            "category": r.get("category"),
            "summary": _s(r.get("summary"), 240),
        }
        for r in (d.get("presets") or [])
        if isinstance(r, dict)
    ][: p["limit"]]
    cats = [c for c in (d.get("categories") or []) if isinstance(c, str)][:30]
    return {"categories": cats, "presets": out}, not out


def t_lux_trackers(o: dict[str, Any], p: dict[str, Any]) -> tuple[Any, bool]:
    d = _d(o)
    rows = []
    for r in (d.get("rows") or [])[: p["limit"]]:
        if not isinstance(r, dict):
            continue
        m = r.get("member") if isinstance(r.get("member"), dict) else {}
        amt = r.get("amountRange") if isinstance(r.get("amountRange"), dict) else {}
        prov = r.get("provenance") if isinstance(r.get("provenance"), dict) else {}
        rows.append(
            {
                "id": r.get("id"),
                "chamber": r.get("chamber"),
                "member": _s(m.get("name"), 80),
                "party": m.get("party"),
                "state": m.get("state"),
                "asset": _s(r.get("assetDescription"), 120),
                "side": r.get("side"),
                "transactedAt": r.get("transactedAt"),
                "filedAt": r.get("filedAt"),
                "amount": _s(amt.get("text"), 40),
                "sourceUrl": _s(prov.get("sourceUrl"), 300),
            }
        )
    return {
        "dataset": d.get("dataset") or p["dataset"],
        "title": _s(d.get("title"), 80),
        "lastIngestedAt": d.get("lastIngestedAt"),
        "matched": _num(d.get("matched")),
        "rows": rows,
    }, not rows


@dataclass(frozen=True)
class Probe:
    id: str
    tool: str
    purpose: str
    params: dict[str, Param]
    build: Callable[[dict[str, Any]], dict[str, Any]]
    trim: Callable[[dict[str, Any], dict[str, Any]], tuple[Any, bool]]
    ttl: float = 60.0
    timeout: float = 15.0
    # Extra attribution when the upstream envelope carries none (honest wording).
    fallback_attribution: tuple[str, ...] = ()
    delay_note: str | None = None  # used only when the envelope has no delay notice


def _prev_quarter(today: date | None = None) -> str:
    t = today or datetime.now(timezone.utc).date()
    q = (t.month - 1) // 3  # 0..3 = current quarter index
    y = t.year
    if q == 0:
        return f"{y - 1}Q4"
    return f"{y}Q{q}"


SYM = Param("symbol", required=True, doc="Ticker, ^[A-Za-z0-9.^=-]{1,12}$")
RANGES = ("1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "ALL")

PROBES: dict[str, Probe] = {
    p.id: p
    for p in [
        Probe(
            "quote",
            "digifetch_quote",
            "Delayed quote for one symbol",
            {"symbol": SYM},
            lambda a: {"symbol": a["symbol"]},
            t_quote,
            ttl=30,
        ),
        Probe(
            "history",
            "digifetch_price_history",
            "Daily bars for one symbol",
            {
                "symbol": SYM,
                "range": Param("enum", default="1M", choices=RANGES, doc="history range"),
            },
            lambda a: {"symbol": a["symbol"], "range": a["range"], "resolution": "1d"},
            t_history,
            ttl=300,
        ),
        Probe(
            "financials",
            "digifetch_ticker_financials",
            "Profile + key fundamentals (trimmed)",
            {"symbol": SYM},
            lambda a: {"symbol": a["symbol"]},
            t_financials,
            ttl=300,
        ),
        Probe(
            "congress",
            "digifetch_congress_trades",
            "Latest US House disclosure trades (market-wide tape)",
            {
                "limit": Param("int", default=10, lo=1, hi=25),
                "year": Param("int", default=None, lo=2012, hi=2100, doc="optional filing year"),
            },
            lambda a: {
                k: v
                for k, v in {"limit": a["limit"], "year": a.get("year")}.items()
                if v is not None
            },
            t_congress,
            ttl=300,
        ),
        Probe(
            "predictions",
            "digifetch_prediction_markets",
            "Polymarket markets, open, by 24h volume",
            {"limit": Param("int", default=8, lo=1, hi=20)},
            lambda a: {"venue": "polymarket", "limit": 100},
            t_predictions,
            ttl=120,
            fallback_attribution=(
                "Polymarket public API (venue-direct, anonymous); quotes may lag the order book",
            ),
            delay_note="Polled anonymously; prices may lag the venue order book",
        ),
        Probe(
            "funds13f",
            "digifetch_13f_funds",
            "Top 13F funds for a quarter",
            {
                "quarter": Param("quarter", default=_prev_quarter()),
                "limit": Param("int", default=10, lo=1, hi=25),
            },
            lambda a: {"what": "top", "quarter": a["quarter"], "limit": a["limit"]},
            t_funds,
            ttl=300,
        ),
        Probe(
            "yieldcurve",
            "digifetch_yield_curve",
            "US Treasury yield curve",
            {},
            lambda a: {},
            t_yield,
            ttl=300,
        ),
        Probe(
            "econ",
            "digifetch_econ_series",
            "FRED-style macro series (latest observations)",
            {
                "series_id": Param("symbol", required=True, doc="FRED id e.g. CPIAUCSL"),
                "limit": Param("int", default=24, lo=1, hi=120),
            },
            lambda a: {"series_id": a["series_id"], "limit": a["limit"], "sort_order": "desc"},
            t_econ,
            ttl=300,
        ),
        Probe(
            "news",
            "digifetch_news",
            "Market news headlines, optionally per ticker",
            {"symbol": Param("symbol"), "limit": Param("int", default=8, lo=1, hi=20)},
            lambda a: (
                {"feed": "ticker", "ticker": a["symbol"], "limit": a["limit"]}
                if a.get("symbol")
                else {"feed": "latest", "limit": a["limit"]}
            ),
            t_news,
            ttl=60,
        ),
        Probe(
            "search",
            "digifetch_search",
            "Symbol search across venues",
            {"query": Param("query", required=True), "limit": Param("int", default=8, lo=1, hi=10)},
            lambda a: {"query": a["query"], "limit": a["limit"]},
            t_search,
            ttl=120,
        ),
        Probe(
            "filings",
            "digifetch_sec_filings",
            "Recent SEC filings for a symbol",
            {"symbol": SYM, "limit": Param("int", default=8, lo=1, hi=15)},
            lambda a: {"ticker": a["symbol"], "what": "filings", "count": a["limit"]},
            t_filings,
            ttl=300,
        ),
        Probe(
            "luxalgoSearch",
            "luxalgo_library_search",
            "LuxAlgo Library concept search (metadata only)",
            {"query": Param("query", required=True), "limit": Param("int", default=8, lo=1, hi=20)},
            lambda a: {"query": a["query"], "limit": a["limit"]},
            t_lux_search,
            ttl=300,
        ),
        Probe(
            "luxalgoFamilies",
            "luxalgo_library_list_families",
            "LuxAlgo Library concept families",
            {},
            lambda a: {},
            t_lux_families,
            ttl=300,
        ),
        Probe(
            "luxalgoEdgePresets",
            "luxalgo_edge_presets",
            "LuxAlgo Edge Stats session-statistic presets",
            {"limit": Param("int", default=12, lo=1, hi=50)},
            lambda a: {},
            t_lux_presets,
            ttl=300,
        ),
        Probe(
            "luxalgoTrackers",
            "luxalgo_trackers_latest",
            "LuxAlgo Market Trackers latest rows (CC0)",
            {
                "dataset": Param("slug", default="congress-trades"),
                "limit": Param("int", default=10, lo=1, hi=25),
            },
            lambda a: {"dataset": a["dataset"]},
            t_lux_trackers,
            ttl=300,
        ),
    ]
}


# --------------------------------------------------------------------------- #
# Envelope + runtime
# --------------------------------------------------------------------------- #


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_envelope(
    probe_id: str, tool: str | None, args: dict[str, Any], **kw: Any
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "id": probe_id,
        "tool": tool,
        "args": args,
        "ok": False,
        "latencyMs": 0,
        "cached": False,
        "fetchedAt": now_iso(),
        "attribution": [],
        "delayNote": None,
        "empty": None,
        "data": None,
        "error": None,
    }
    env.update(kw)
    return env


def error_env(
    probe_id: str, tool: str | None, args: dict[str, Any], code: str, msg: str, ms: int = 0
) -> dict[str, Any]:
    return make_envelope(
        probe_id, tool, args, latencyMs=ms, error={"code": code, "message": msg[:300]}
    )


def upstream_error(o: dict[str, Any]) -> tuple[str, str] | None:
    """Typed errors: top-level {"error"} or data={code,message,...} with ok-looking isError=false."""
    err = o.get("error")
    if err:
        if isinstance(err, dict):
            return str(err.get("code") or "upstream_error"), str(err.get("message") or "error")
        return "upstream_error", str(err)
    d = o.get("data")
    if (
        isinstance(d, dict)
        and isinstance(d.get("code"), str)
        and isinstance(d.get("message"), str)
        and len(set(d) - {"code", "message", "retryable", "details"}) == 0
    ):
        return d["code"], d["message"]
    return None


@dataclass
class Gateway:
    bridge: Bridge
    http: httpx.AsyncClient
    origins: tuple[str, ...] = DEFAULT_ORIGINS
    cache: dict[Any, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    hits: dict[str, deque[float]] = field(default_factory=dict)
    locks: dict[Any, asyncio.Lock] = field(default_factory=dict)
    clock: Callable[[], float] = time.monotonic

    # -- helpers
    def rate_ok(self, ip: str) -> bool:
        t = self.clock()
        if len(self.hits) > 1024:
            self.hits = {k: v for k, v in self.hits.items() if v and t - v[-1] < RATE_WINDOW}
        q = self.hits.setdefault(ip, deque())
        while q and t - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(t)
        return True

    def _cget(self, key: Any) -> Any:
        hit = self.cache.get(key)
        if hit and hit[0] > self.clock():
            return hit[1]
        self.cache.pop(key, None)
        return None

    def _cput(self, key: Any, ttl: float, value: Any) -> None:
        if len(self.cache) > 512:
            now = self.clock()
            self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
        self.cache[key] = (self.clock() + ttl, value)

    # -- probes
    async def run_probe(self, probe: Probe, query: dict[str, str]) -> tuple[int, dict[str, Any]]:
        t0 = time.monotonic()
        unknown = set(query) - set(probe.params)
        try:
            if unknown:
                raise ToolError("invalid_input", f"unknown params: {sorted(unknown)}")
            parsed = {n: prm.parse(n, query.get(n)) for n, prm in probe.params.items()}
            args = probe.build(parsed)
        except ToolError as e:
            return 400, error_env(probe.id, probe.tool, {}, e.code, e.message)
        key = (probe.id, json.dumps(parsed, sort_keys=True, default=str))
        cached = self._cget(key)
        if cached is not None:
            return 200, {**cached, "cached": True, "latencyMs": int((time.monotonic() - t0) * 1000)}
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cget(key)
            if cached is not None:
                return 200, {
                    **cached,
                    "cached": True,
                    "latencyMs": int((time.monotonic() - t0) * 1000),
                }
            try:
                raw = await self.bridge.call(probe.tool, args, probe.timeout)
            except ToolError as e:
                self.locks.pop(key, None)
                return 502, error_env(
                    probe.id,
                    probe.tool,
                    args,
                    e.code,
                    e.message,
                    int((time.monotonic() - t0) * 1000),
                )
            self.locks.pop(key, None)
        ms = int((time.monotonic() - t0) * 1000)
        err = upstream_error(raw)
        if err:
            return 200, error_env(probe.id, probe.tool, args, err[0], err[1], ms)
        data, empty = probe.trim(raw, parsed)
        attribution: list[str] = []
        for k in ("attribution", "license_note"):
            v = raw.get(k)
            if isinstance(v, str) and v and v not in attribution:
                attribution.append(v)
        if not attribution:
            attribution = list(probe.fallback_attribution)
        delay = raw.get("delay_notice") or raw.get("delay_note") or probe.delay_note
        env = make_envelope(
            probe.id,
            probe.tool,
            args,
            ok=True,
            latencyMs=ms,
            attribution=attribution,
            delayNote=delay if isinstance(delay, str) else None,
            empty=EMPTY_BAD if empty else None,
            data=None if empty and data is None else data,
            fetchedAt=raw.get("fetched_at")
            if isinstance(raw.get("fetched_at"), str)
            else now_iso(),
        )
        if len(json.dumps(env, default=str)) > MAX_PAYLOAD_BYTES:
            return 502, error_env(
                probe.id, probe.tool, args, "payload_too_large", "trimmed payload exceeds cap", ms
            )
        self._cput(key, probe.ttl, env)
        return 200, env

    # -- market proxy
    async def market(self, path: str, params: dict[str, str]) -> Response:
        key = ("market", path, tuple(sorted(params.items())))
        hit = self._cget(key)
        if hit is not None:
            return Response(hit[0], media_type=hit[1], headers={"x-cache": "hit"})
        try:
            r = await self.http.get(f"{MARKET_UPSTREAM}/{path}", params=params, timeout=15)
        except httpx.HTTPError:
            return JSONResponse(
                {"error": {"code": "upstream_error", "message": "market upstream unreachable"}}, 502
            )
        if r.status_code != 200:
            return JSONResponse(
                {
                    "error": {
                        "code": "upstream_error",
                        "message": f"market upstream HTTP {r.status_code}",
                    }
                },
                502,
            )
        if len(r.content) > 2_000_000:
            return JSONResponse(
                {"error": {"code": "payload_too_large", "message": "market payload too large"}}, 502
            )
        ctype = r.headers.get("content-type", "application/json")
        self._cput(key, MARKET_TTL, (r.content, ctype))
        return Response(r.content, media_type=ctype, headers={"x-cache": "miss"})


def build_app(gw: Gateway, lifespan: Any = None) -> Starlette:
    def guard(request: Request) -> Response | None:
        origin = request.headers.get("origin")
        if origin and origin not in gw.origins:
            return JSONResponse(
                {"error": {"code": "forbidden_origin", "message": "origin not allowed"}}, 403
            )
        ip = request.client.host if request.client else "unknown"
        if not gw.rate_ok(ip):
            return JSONResponse(
                {"error": {"code": "rate_limited", "message": "too many requests"}},
                429,
                headers={"Retry-After": "60"},
            )
        return None

    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True, "probes": len(PROBES)})

    async def catalog(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        items = [
            {
                "id": p.id,
                "tool": p.tool,
                "purpose": p.purpose,
                "ttlSeconds": p.ttl,
                "params": {n: prm.schema() for n, prm in p.params.items()},
            }
            for p in PROBES.values()
        ]
        items.append(
            {
                "id": "market",
                "tool": None,
                "purpose": "Read-only proxy of the shared market-data worker",
                "ttlSeconds": MARKET_TTL,
                "params": {
                    "tickers": {"kind": "symbols", "required": True, "max": 25},
                    "from": {"kind": "date"},
                    "to": {"kind": "date"},
                },
            }
        )
        return JSONResponse({"probes": items})

    async def probe(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        p = PROBES.get(request.path_params["pid"])
        if p is None:
            return JSONResponse(
                error_env(request.path_params["pid"][:40], None, {}, "not_found", "unknown probe"),
                404,
            )
        status, env = await gw.run_probe(p, dict(request.query_params))
        return JSONResponse(env, status, headers={"Cache-Control": "no-store"})

    async def market_closes(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        q = request.query_params
        raw = q.get("tickers", "")
        tickers = [t for t in raw.split(",") if t]
        if not tickers or len(tickers) > 25 or not all(SYMBOL_RE.match(t) for t in tickers):
            return JSONResponse(
                {"error": {"code": "invalid_input", "message": "tickers: 1-25 symbols"}}, 400
            )
        params = {"tickers": ",".join(tickers)}
        for k in ("from", "to"):
            v = q.get(k)
            if v:
                try:
                    if not DATE_RE.match(v):
                        raise ValueError
                    date.fromisoformat(v)
                except ValueError:
                    return JSONResponse(
                        {"error": {"code": "invalid_input", "message": f"{k}: YYYY-MM-DD"}}, 400
                    )
                params[k] = v
        if set(q) - {"tickers", "from", "to"}:
            return JSONResponse(
                {"error": {"code": "invalid_input", "message": "unknown params"}}, 400
            )
        return await gw.market("closes", params)

    async def market_tickers(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        if request.query_params:
            return JSONResponse(
                {"error": {"code": "invalid_input", "message": "no params accepted"}}, 400
            )
        return await gw.market("tickers", {})

    routes = [
        Route("/healthz", healthz),
        Route("/v1/catalog", catalog),
        Route("/v1/probe/{pid}", probe),
        Route("/v1/market/closes", market_closes),
        Route("/v1/market/tickers", market_tickers),
    ]
    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=list(gw.origins),
                allow_methods=["GET"],
                allow_headers=[],
                allow_credentials=False,
                max_age=600,
            )
        ],
    )


def origins_from_env() -> tuple[str, ...]:
    raw = os.environ.get("DQ_GATEWAY_ORIGINS", "").strip()
    return tuple(o.strip() for o in raw.split(",") if o.strip()) or DEFAULT_ORIGINS


def make_default_app() -> Starlette:
    bridge = StdioBridge()
    http = httpx.AsyncClient(follow_redirects=False)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> Any:
        try:
            yield
        finally:
            await bridge.close()
            await http.aclose()

    return build_app(
        Gateway(bridge=bridge, http=http, origins=origins_from_env()), lifespan=lifespan
    )


def main() -> None:
    import uvicorn

    port = int(os.environ.get("DQ_GATEWAY_PORT", DEFAULT_PORT))
    uvicorn.run(make_default_app(), host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
