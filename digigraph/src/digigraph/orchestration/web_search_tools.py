"""Web search built-in tool (External evidence tier)."""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.tool_common import (
    _digi_bearer_from_context,
    _digisearch_service_base,
)
from digigraph.trace_events import rag_sources_from_results

EXTERNAL_EVIDENCE_TIER = "External"
WEB_SEARCH_TOOL_NAME = "web_search"

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": WEB_SEARCH_TOOL_NAME,
        "description": (
            "Search the public web for current information with the first-party "
            "digisearch web_search tool. Results are "
            "External citations — they supplement digisearch/digivault corpus hits and "
            "must never replace them. Prefer digisearch/digivault first; use web_search "
            "only when the corpus cannot answer and live public facts are required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Web search query (short, factual).",
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict results to these domains.",
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Never return results from these domains.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max rows to return (default 4).",
                },
                "provider": {
                    "type": "string",
                    "description": (
                        "Search engine to use: auto (default, in-house), internal, "
                        "exa, tavily, parallel, firecrawl, or tinyfish. Omit for auto."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


def web_search_tool_for_tenant(pins: Any, site_id: Any) -> dict[str, Any] | None:
    """The ``web_search`` tool definition for a pinned tenant, or ``None``.

    Same name and parameters as :data:`WEB_SEARCH_TOOL`; only the description
    changes. It states the pin (enforced in :func:`_handle_web_search`, so the
    text is guidance, not the guard) and appends the tenant's site graph
    (``$DIGIGRAPH_WEB_SEARCH_SITES_DIR/<id>.md``) when one exists. An unpinned
    tenant keeps the shared definition: ``None``.
    """
    pin_list = _as_str_list(pins)
    if pins is None or not pin_list:
        return None
    import copy

    from digigraph.web_search_sites import load_web_search_site_graph

    tool = copy.deepcopy(WEB_SEARCH_TOOL)
    fn = tool["function"]
    parts = [
        "Search this tenant's own public web presence with the first-party digisearch "
        "web_search tool. Results are restricted server-side to: "
        + ", ".join(pin_list)
        + ". Other domains and other search engines are refused. Each call is one "
        "search: to search a listed site other than the first, pass that site's host "
        "in include_domains (it can only narrow this list). Cite the page URL of "
        "every fact you use."
    ]
    graph = load_web_search_site_graph(site_id) if isinstance(site_id, str) else None
    if graph:
        parts.append(graph)
    fn["description"] = "\n\n".join(parts)
    props = fn["parameters"]["properties"]
    props.pop("provider", None)
    props["include_domains"] = {
        **props["include_domains"],
        "description": "Optional narrowing within: " + ", ".join(pin_list) + ".",
    }
    return tool


class DigisearchHubError(RuntimeError):
    """The digisearch hub call itself failed (#4106).

    Distinct from an empty result set: a rate limit, auth rejection, open circuit,
    or malformed envelope must never be reported downstream as "web_search
    returned no rows" — on 2026-09-15 that masking hid a `/v1/orchestrator_invoke`
    429 and failed the daily digiquant book run three times. Carries the hub's own
    error text.
    """


def _web_search_available(context: ToolContext) -> bool:
    """web_search is request-opt-in only (#3420) — never ambient on corpus RAG."""
    return bool(context.state.get("enable_web_search"))


def web_search_disabled_payload(tool_name: str) -> dict[str, Any]:
    """Denial payload for a web_search surface (native or MCP) when not opted in (#3420)."""
    return {
        "error": "tool_not_allowed",
        "tool": tool_name,
        "message": (
            "web_search is opt-in and disabled for this session. "
            "Enable via X-Digi-Enable-Web-Search / enable_web_search."
        ),
    }


def _as_str_list(value: Any) -> list[str]:
    """Coerce an optional tool arg to a clean string list (a bare string becomes one entry)."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


#: Search window for a pinned tenant. digisearch defaults to the last 7 days,
#: which suits news but finds almost nothing on a company website whose pages
#: change a few times a year; 365 is the widest window digisearch accepts.
PINNED_RECENCY_DAYS = 365


def _domain_within(domain: str, pin: str) -> bool:
    return domain == pin or domain.endswith("." + pin)


def _split_pin(pin: str) -> tuple[str, str]:
    """``host/path`` -> ``(host, "/path")``; a bare host has an empty path.

    An exact-page query (``host/path?k=v``) is dropped here; see :func:`_pin_query`.
    """
    host, sep, path = pin.strip().lower().split("?", 1)[0].rstrip("/").partition("/")
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host, ("/" + path if sep and path else "")


def _pin_query(pin: str) -> list[tuple[str, str]]:
    """The ``k=v`` pairs of an exact-page pin (``host/path?k=v``), else empty."""
    _, sep, query = pin.strip().lower().partition("?")
    if not sep:
        return []
    from urllib.parse import parse_qsl

    return parse_qsl(query, keep_blank_values=False)


#: digisearch's WebSearchRequest takes at most this many include_domains.
ENGINE_MAX_INCLUDE_DOMAINS = 5


def _pin_hosts(pinned: Any) -> list[str]:
    hosts: list[str] = []
    for pin in _as_str_list(pinned):
        host, _ = _split_pin(pin)
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def pinned_include_domains(pinned: Any, requested: Any) -> list[str]:
    """Clamp a model's ``include_domains`` to the hosts of the tenant's pins.

    The pin is an allowlist the model aims ONE search at, never a fan-out. No
    request: every pinned host when they fit one engine call, otherwise the
    first (primary) pin's host alone. A request: only the requested domains
    that sit inside a pinned host (equal or a subdomain). Anything else is
    dropped, so the result is never wider than the pin; when nothing the model
    asked for survives, the default is used. Path prefixes are not expressible
    as engine domains, so :func:`url_within_pins` enforces them on the results.
    """
    hosts = _pin_hosts(pinned)
    if not hosts:
        return []
    wanted = []
    for raw in _as_str_list(requested):
        d = raw.lower().split("://", 1)[-1].split("/", 1)[0].rstrip(".")
        if d.startswith("www."):
            d = d[4:]
        if d and any(_domain_within(d, h) for h in hosts) and d not in wanted:
            wanted.append(d)
    if wanted:
        return wanted[:ENGINE_MAX_INCLUDE_DOMAINS]
    if len(hosts) <= ENGINE_MAX_INCLUDE_DOMAINS:
        return hosts
    return hosts[:1]


def url_within_pins(url: Any, pins: Any) -> bool:
    """True when ``url`` falls inside one pin: host equal or a subdomain, and,
    for a ``host/path`` pin, a path equal to or under that path."""
    if not isinstance(url, str):
        return False
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return False
    path = (parts.path or "/").lower().rstrip("/")
    for pin in _as_str_list(pins):
        pin_host, pin_path = _split_pin(pin)
        if not pin_host or not _domain_within(host, pin_host):
            continue
        pin_query = _pin_query(pin)
        if pin_query:
            # Exact page: same path and every pinned k=v present in the URL.
            from urllib.parse import parse_qsl

            have = set(parse_qsl((parts.query or "").lower(), keep_blank_values=False))
            if path == pin_path and all(kv in have for kv in pin_query):
                return True
            continue
        if not pin_path or path == pin_path or path.startswith(pin_path + "/"):
            return True
    return False


def call_digisearch_web_search(
    query: str,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 4,
    recency_days: int | None = None,
    provider: str | None = None,
    context: ToolContext | None = None,
    timeout: float = 120.0,
    page_corpus: str | None = None,
) -> dict[str, Any]:
    """Public entry point for the digisearch ``web_search`` tool call.

    Thin delegation to :func:`_call_digisearch_web_search` — external callers
    (digiquant pipeline grounding) import this, never the private name.
    ``timeout`` bounds the single hub HTTP call. ``recency_days`` is forwarded
    only when set, so ``None`` keeps digisearch's own default window (#4165).
    ``provider`` names the search engine (auto/internal/exa/tavily/parallel/
    firecrawl/tinyfish) and is likewise omitted when unset or ``auto`` (#4722).
    """
    return _call_digisearch_web_search(
        query,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        max_results=max_results,
        recency_days=recency_days,
        provider=provider,
        context=context,
        timeout=timeout,
        page_corpus=page_corpus,
    )


def _call_digisearch_web_search(
    query: str,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 4,
    recency_days: int | None = None,
    provider: str | None = None,
    context: ToolContext | None = None,
    timeout: float = 120.0,
    page_corpus: str | None = None,
) -> dict[str, Any]:
    """Invoke digisearch ``web_search`` via the vertical-orchestrator hub.

    Never ``import digisearch`` — the call goes through
    :func:`digigraph.vertical_orchestrator.digisearch_hub.invoke_digisearch_tool`
    (``POST /v1/orchestrator_invoke``). Normalizes the hub envelope
    (``{"ok", "data": {"results": [{url, title, snippet}]}}``) into the digigraph
    tool shape (``{"content", "results": [{doc_id, ...}]}``). Returns ``{}`` only
    for a genuinely empty result set; a hub failure raises
    :class:`DigisearchHubError` carrying the hub's error text, so a 429 or a dead
    service can never be reported as "returned no rows" (#4106). Callers fail
    hard either way (no synthesis fallback, #3859).
    """
    from digigraph.vertical_orchestrator.digisearch_hub import invoke_digisearch_tool

    index_name = getattr(context, "index_name", None) or "default"
    arguments: dict[str, Any] = {
        "query": query,
        "include_domains": _as_str_list(include_domains),
        "exclude_domains": _as_str_list(exclude_domains),
        "max_results": max_results,
    }
    if recency_days is not None:
        # Omitted when unset: digisearch's WebSearchRequest defaults to 7, so a
        # caller that never asked keeps the default window — the hub skips a
        # JSON null rather than forwarding it (#4165).
        arguments["recency_days"] = recency_days
    provider_arg = str(provider or "").strip()
    if provider_arg and provider_arg.lower() != "auto":
        # Omitted when unset or auto: the hub defaults to the in-house engine,
        # and an explicit in-house name (internal) still forwards (#4722).
        # Unknown names are the hub's call to reject (no digigraph registry).
        arguments["provider"] = provider_arg
    if page_corpus:
        # Pinned tenant with a pre-crawled corpus: digisearch still fetches the
        # live page first and uses the corpus only for a challenge or a failure.
        arguments["page_corpus"] = page_corpus
    inv = invoke_digisearch_tool(
        _digisearch_service_base(),
        "web_search",
        arguments,
        default_index_name=index_name,
        bearer_token=_digi_bearer_from_context(context) if context is not None else None,
        request_id=getattr(context, "request_id", None),
        timeout=timeout,
    )
    if not isinstance(inv, dict):
        raise DigisearchHubError("digisearch web_search returned a non-object response")
    # #4198: only a real JSON ``true`` counts as success — a malformed envelope whose
    # ``ok`` is a truthy non-boolean (e.g. ``"false"``) must fail the pre-flight gate.
    if inv.get("ok") is not True:
        raise DigisearchHubError(
            f"digisearch web_search failed: {inv.get('error') or 'unknown error'}"
        )
    data = inv.get("data")
    if not isinstance(data, dict):
        raise DigisearchHubError("digisearch web_search envelope carried no data object")
    hits = data.get("results") or []
    rows: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("url") or "").strip()
        if not url:
            continue
        title = str(hit.get("title") or url).strip() or url
        snippet = str(hit.get("snippet") or "")
        rows.append(
            {
                "doc_id": url,
                "content": snippet,
                "rank": len(rows),
                "metadata": {
                    "title": title,
                    "source_url": url,
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    if not rows:
        return {}
    lines = []
    for row in rows:
        line = f"- [{row['metadata']['title']}]({row['doc_id']})"
        if row["content"]:
            line += f" — {row['content']}"
        lines.append(line)
    return {"content": "\n".join(lines), "results": rows}


def _handle_web_search(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """digisearch web_search tool only — fail hard, never synthesize (#3859)."""
    if not _web_search_available(context):
        return {
            "error": "tool_not_allowed",
            "tool": WEB_SEARCH_TOOL_NAME,
            "message": (
                "web_search is opt-in and disabled for this session. "
                "Enable via X-Digi-Enable-Web-Search / enable_web_search."
            ),
        }
    include_domains = args.get("include_domains")
    pinned = context.state.get("web_search_domains")
    if pinned is not None:
        # Tenant pin (corpus map webSearchDomains): the model may narrow it,
        # never widen it. A pin that leaves nothing refuses the call.
        include_domains = pinned_include_domains(pinned, include_domains)
        if not include_domains:
            return {
                "error": "tool_not_allowed",
                "tool": WEB_SEARCH_TOOL_NAME,
                "message": "web_search is not available for this tenant.",
            }
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    query = str(q).strip()
    from digigraph.llm_client import digifetch_web_search

    # Tool path needs no model — "" keeps the (model, query) shape for callers.
    # The model's per-call engine wins; the session default covers silence (#4722).
    provider = args.get("provider") or context.state.get("web_search_provider")
    if pinned is not None:
        # A pinned tenant's engine is the operator's choice (gate.searchEngine),
        # never the model's: it cannot switch a free tenant onto a paid engine.
        provider = context.state.get("web_search_provider")
    search_kwargs: dict[str, Any] = {
        "include_domains": include_domains,
        "exclude_domains": args.get("exclude_domains"),
        "max_results": int(args.get("max_results", 4)),
        "provider": provider,
        "context": context,
    }
    if pinned is not None:
        # A pinned tenant searches its own site, not the news: widen the window.
        search_kwargs["recency_days"] = PINNED_RECENCY_DAYS
        # An engine that ignores include_domains, or a pin with a path prefix,
        # still cannot hand a pinned tenant an off-pin row: it is dropped before
        # the summary is built, so neither its URL nor its snippet survives.
        search_kwargs["url_filter"] = lambda u: url_within_pins(u, pinned)
        # Tenant map webSearchPageCorpus (digisearch page_corpus): a live page
        # behind a bot challenge falls back to the pre-crawled copy. Unpinned
        # tenants never send one.
        corpus = context.state.get("web_search_page_corpus")
        if isinstance(corpus, str) and corpus.strip():
            search_kwargs["page_corpus"] = corpus.strip()
    try:
        summary, urls = digifetch_web_search("", query, **search_kwargs)
    except RuntimeError as exc:
        if pinned is None or "returned no rows" not in str(exc):
            raise
        # Pinned and nothing on-site matched: an honest empty answer, not a
        # tool failure the model would retry against the open web.
        summary, urls = "", []
    results: list[dict[str, Any]] = []
    for i, url in enumerate(urls[:8]):
        if not isinstance(url, str) or not url.strip():
            continue
        u = url.strip()
        results.append(
            {
                "doc_id": u,
                "content": summary if i == 0 else "",
                "rank": i,
                "metadata": {
                    "title": u,
                    "source_url": u,
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    if not results and summary:
        # Summary without parseable URLs — still surface as one External cite.
        results.append(
            {
                "doc_id": "web://search",
                "content": summary,
                "rank": 0,
                "metadata": {
                    "title": "Web search",
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    return {
        "content": summary or "Web search returned no results.",
        "results": results,
        "rag_sources": rag_sources_from_results(results),
        "name": WEB_SEARCH_TOOL_NAME,
    }
