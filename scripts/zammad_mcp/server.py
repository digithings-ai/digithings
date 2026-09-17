"""Read-only Zammad MCP server for the OCC help chat.

Run: ``python -m scripts.zammad_mcp.server`` (streamable HTTP, default
127.0.0.1:8770) or ``--stdio``. Reads ``ZAMMAD_BASE_URL`` and
``ZAMMAD_API_TOKEN`` from the environment, plus optional
``ZAMMAD_MCP_ALLOWED_HOSTS`` (comma-separated Host patterns for
cross-container access); every tool is GET-only.
"""

import argparse
import logging
import os

from mcp.server.fastmcp import FastMCP

from scripts.zammad_mcp.client import ZammadClient, ZammadError, keyword_terms
from scripts.zammad_mcp.formatting import (
    format_search_results,
    format_ticket_detail,
    format_ticket_list,
    format_ticket_report,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("zammad", json_response=True)


def _allowed_host_patterns(raw: str) -> list[str]:
    """Turn ``ZAMMAD_MCP_ALLOWED_HOSTS`` into FastMCP allowed-host patterns.

    Entries without a port get ``:*`` appended, so the compose service name
    ``zammad-mcp`` matches the ``zammad-mcp:8770`` Host header digigraph
    sends. FastMCP matches exact hosts and a literal ``:*`` suffix only, so
    entries with any other wildcard are dropped. Whether FastMCP actually
    enforces the allowlist depends on the mcp build — versions without a
    ``transport_security`` setting accept the configuration but ignore it
    (see ``run_mcp``).
    """
    patterns: list[str] = []
    for item in raw.split(","):
        host = item.strip()
        if not host or ("*" in host and not host.endswith(":*")):
            continue
        patterns.append(host if ":" in host else f"{host}:*")
    return patterns


def _client() -> ZammadClient:
    return ZammadClient()


@mcp.tool()
def search_tickets(query: str, limit: int = 10) -> str:
    """Search Zammad tickets (read-only).

    Plain words always work: a query matches ticket title, number, and
    article body/from/to/subject as a substring. Multi-word queries are
    first matched as one phrase, then retried keyword by keyword.

    Field syntax (``state.name:open``, ``group.name:Sitaas``,
    ``priority.name:"2 normal"``, ``owner.email:``, ``article.body:term``,
    ``tags:``, AND/OR) only works when the Zammad instance has
    Elasticsearch; otherwise it silently matches nothing. For "what's open
    or closed", prefer ticket_report.

    Tickets here are written in German and English; a keyword only matches
    the words actually stored in a ticket, so English terms never find
    German text. When a search comes back empty, retry with German wording
    or browse with list_tickets and read the tickets directly.
    """
    client = _client()
    try:
        tickets = client.search_tickets(query, limit=limit)
        fallback_terms: list[str] = []
        cleaned = (query or "").strip()
        if not tickets and cleaned:
            terms = keyword_terms(cleaned)
            if terms and terms != [cleaned]:
                fallback_terms = terms
                tickets = client.search_tickets_by_terms(terms, limit=limit)
    except ZammadError as exc:
        return f"zammad error: {exc}"
    return format_search_results(query, tickets, fallback_terms=fallback_terms)


@mcp.tool()
def list_tickets(page: int = 1, per_page: int = 50) -> str:
    """Browse the visible Zammad tickets page by page (read-only).

    Use this when keyword search misses. Tickets are written in German and
    English and search is a literal substring match, so an English keyword
    will not find German text; browsing returns titles in their original
    language. Reading German tickets directly is fine — pull a full
    conversation with get_ticket. Newest updated first; keep going while a
    page comes back full.
    """
    try:
        tickets = _client().list_tickets_page(page=page, per_page=per_page)
    except ZammadError as exc:
        return f"zammad error: {exc}"
    return format_ticket_list(tickets, page=page, per_page=per_page)


@mcp.tool()
def get_ticket(ticket_id: int | str) -> str:
    """Fetch one Zammad ticket with all of its articles (read-only).

    Accepts the internal id (``231``) or the ticket number shown as
    ``#28312``; a number is resolved to its internal id automatically.
    """
    client = _client()
    try:
        ticket = client.get_ticket(ticket_id)
        resolved_id = ticket.get("id") or ticket_id
        articles = client.get_articles(resolved_id)
    except ZammadError as exc:
        return f"zammad error: {exc}"
    return format_ticket_detail(ticket, articles)


@mcp.tool()
def ticket_report() -> str:
    """Status report of all visible Zammad tickets (read-only).

    Counts tickets by state, group, and priority plus recent activity —
    "what's open, what's closed". Scans up to 500 tickets via the read-only
    ticket list; "closed" means the state is named closed/merged, any other
    state counts as unresolved.
    """
    try:
        tickets = _client().list_tickets()
    except ZammadError as exc:
        return f"zammad error: {exc}"
    return format_ticket_report(tickets)


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8770,
) -> None:
    """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8770."""
    if not _client().configured:
        logger.warning("ZAMMAD_API_TOKEN is not set — tools will fail closed")
    bind = host or os.environ.get("ZAMMAD_MCP_HOST", "127.0.0.1")
    mcp.settings.host = bind
    mcp.settings.port = port
    extra_hosts = _allowed_host_patterns(os.environ.get("ZAMMAD_MCP_ALLOWED_HOSTS", ""))
    if extra_hosts:
        # Older mcp builds (the stack image resolves 1.9.x) have no
        # transport_security on Settings; host allowlisting then just
        # stays unavailable instead of crashing the program.
        security = getattr(mcp.settings, "transport_security", None)
        if security is not None:
            allowed = security.allowed_hosts
            allowed.extend(pattern for pattern in extra_hosts if pattern not in allowed)
        else:
            logger.warning(
                "ZAMMAD_MCP_ALLOWED_HOSTS is set but this mcp version has no "
                "transport_security; host allowlisting is unavailable"
            )
    mcp.run(transport=transport)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m scripts.zammad_mcp.server [--stdio]``."""
    parser = argparse.ArgumentParser(description="Zammad MCP server (read-only tickets)")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport")
    parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8770, help="Bind port (default 8770)")
    args = parser.parse_args(argv)
    if args.stdio:
        run_mcp(transport="stdio")
    else:
        run_mcp(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
