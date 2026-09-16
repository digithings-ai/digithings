"""Unit tests for scripts/zammad_mcp (no network)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from scripts.zammad_mcp import formatting
from scripts.zammad_mcp.client import ZammadClient, ZammadError

pytestmark = pytest.mark.unit

BASE = "https://ticket.example.test"
TOKEN = "abc123"

TICKET = {
    "id": 231,
    "number": "28312",
    "title": "Example ticket subject",
    "state": "open",
    "group": "Sitaas",
    "priority": "2 normal",
    "customer": "jane.doe@example.test",
    "owner": "11111111-1111-1111-1111-111111111111",
    "updated_at": "2026-09-15T12:00:00.000Z",
}


class FakeTransport:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.payload


def make_client(payload: Any) -> tuple[ZammadClient, FakeTransport]:
    transport = FakeTransport(payload)
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    return client, transport


def test_search_tickets_builds_exact_request():
    client, transport = make_client([TICKET])
    rows = client.search_tickets("state.name:open", limit=5)
    assert rows == [TICKET]
    call = transport.calls[0]
    assert call["url"] == f"{BASE}/api/v1/tickets/search"
    assert call["params"] == {"query": "state.name:open", "limit": 5, "expand": "true"}
    assert call["headers"]["Authorization"] == f"Token token={TOKEN}"
    assert call["headers"]["Accept"] == "application/json"


def test_token_may_hold_the_full_prefixed_header_value():
    transport = FakeTransport([TICKET])
    client = ZammadClient(base_url=BASE, token=f"Token token={TOKEN}", get_json=transport)
    client.search_tickets("x")
    assert transport.calls[0]["headers"]["Authorization"] == f"Token token={TOKEN}"


def test_search_tickets_caps_limit():
    client, transport = make_client([TICKET])
    client.search_tickets("x", limit=500)
    client.search_tickets("x", limit=0)
    assert transport.calls[0]["params"]["limit"] == 50
    assert transport.calls[1]["params"]["limit"] == 1


def test_search_tickets_rejects_bad_limit():
    client, _ = make_client([TICKET])
    with pytest.raises(ZammadError, match="limit"):
        client.search_tickets("x", limit="many")


def test_search_tickets_empty_query_makes_no_call():
    client, transport = make_client([TICKET])
    with pytest.raises(ZammadError, match="non-empty"):
        client.search_tickets("   ")
    assert transport.calls == []


def test_search_tickets_accepts_wrapped_payload_and_filters_non_dicts():
    client, _ = make_client({"tickets": [TICKET, "junk"], "total_count": 1})
    assert client.search_tickets("x") == [TICKET]


def test_search_tickets_rejects_unexpected_payload():
    client, _ = make_client({"total_count": 0})
    with pytest.raises(ZammadError, match="search payload"):
        client.search_tickets("x")


def test_missing_token_fails_closed_without_http_call():
    transport = FakeTransport([TICKET])
    client = ZammadClient(base_url=BASE, token="", get_json=transport)
    assert client.configured is False
    with pytest.raises(ZammadError, match="ZAMMAD_API_TOKEN"):
        client.search_tickets("state.name:open")
    assert transport.calls == []


def test_get_ticket_builds_exact_request():
    payload = dict(TICKET, state="closed", group="Sitaas", organization="Test-Org")
    client, transport = make_client(payload)
    assert client.get_ticket(231) == payload
    call = transport.calls[0]
    assert call["url"] == f"{BASE}/api/v1/tickets/231"
    assert call["params"] == {"expand": "true"}


def test_get_articles_builds_exact_request():
    article = {"id": 684, "sender": "Customer", "type": "web", "body": "<p>Test123</p>"}
    client, transport = make_client([article])
    assert client.get_articles(231) == [article]
    call = transport.calls[0]
    assert call["url"] == f"{BASE}/api/v1/ticket_articles/by_ticket/231"
    assert call["params"] == {"expand": "true"}


def test_invalid_ticket_ids_raise():
    client, transport = make_client(TICKET)
    with pytest.raises(ZammadError, match="positive integer"):
        client.get_ticket(0)
    with pytest.raises(ZammadError, match="positive integer"):
        client.get_ticket("nope")
    assert transport.calls == []


def test_get_ticket_rejects_unexpected_payload():
    client, _ = make_client(["not-a-ticket"])
    with pytest.raises(ZammadError, match="ticket payload"):
        client.get_ticket(1)


def test_client_reads_env_defaults(monkeypatch):
    monkeypatch.setenv("ZAMMAD_BASE_URL", "https://zammad.env.test/")
    monkeypatch.setenv("ZAMMAD_API_TOKEN", "env-token")
    client = ZammadClient()
    assert client.base_url == "https://zammad.env.test"
    assert client.token == "env-token"
    assert client.configured is True


def test_client_drops_slash_from_base_url():
    client = ZammadClient(base_url="https://zammad.env.test/", token=TOKEN)
    assert client.base_url == "https://zammad.env.test"


def test_client_defaults_without_env(monkeypatch):
    monkeypatch.delenv("ZAMMAD_BASE_URL", raising=False)
    monkeypatch.delenv("ZAMMAD_API_TOKEN", raising=False)
    client = ZammadClient()
    assert client.base_url == "https://ticket.sitaas.de"
    assert client.configured is False


def test_http_status_error_is_translated(monkeypatch):
    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(403, request=request, json={"error": "Forbidden"})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ZammadClient(base_url=BASE, token=TOKEN)
    with pytest.raises(ZammadError, match="403"):
        client.search_tickets("state.name:open")


def test_non_json_response_is_translated(monkeypatch):
    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, text="<html>not json</html>")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = ZammadClient(base_url=BASE, token=TOKEN)
    with pytest.raises(ZammadError, match="non-JSON"):
        client.get_ticket(1)


def test_html_to_text_strips_tags_and_scripts():
    out = formatting.html_to_text(
        "<p>Hello <b>world</b></p><script>drop()</script><p>Second line</p>"
    )
    assert "Hello world" in out
    assert "Second line" in out
    assert "drop" not in out


def test_html_to_text_collapses_whitespace_and_block_tags():
    assert formatting.html_to_text("<div>A</div><div>  B  </div>") == "A\nB"


def test_format_search_results_empty():
    assert formatting.format_search_results("nothing", []) == 'No tickets matched: "nothing"'


def test_format_search_results_lists_tickets():
    out = formatting.format_search_results("state.name:open", [TICKET])
    assert 'Found 1 ticket(s) for: "state.name:open"' in out
    assert "id 231" in out
    assert "#28312" in out
    assert "[open]" in out
    assert "group: Sitaas" in out
    assert "customer: j***@example.test" in out


def test_format_ticket_line_resolves_dict_relations_and_dashes():
    line = formatting.format_ticket_line(
        {"id": 9, "number": "-", "state": {"name": "open"}, "customer": "-"}
    )
    assert "[open]" in line
    assert "customer" not in line
    assert "#" not in line


def test_format_ticket_detail_includes_articles():
    article = {
        "id": 684,
        "sender": "Agent",
        "type": "email",
        "internal": False,
        "from": "support@example.test",
        "body": "<p>Resolution steps</p>",
    }
    out = formatting.format_ticket_detail(TICKET, [article])
    assert "Ticket 231 #28312" in out
    assert "Articles (1)" in out
    assert "--- article 1" in out
    assert "Resolution steps" in out


def test_format_ticket_detail_omits_internal_notes():
    articles = [
        {
            "id": 1,
            "sender": "Agent",
            "type": "note",
            "internal": True,
            "body": "<p>internal-only note body</p>",
        },
        {
            "id": 2,
            "sender": "Customer",
            "type": "web",
            "internal": False,
            "body": "<p>customer-visible reply</p>",
        },
    ]
    out = formatting.format_ticket_detail(TICKET, articles)
    assert "customer-visible reply" in out
    assert "internal-only note body" not in out
    assert "Articles (1)" in out
    assert "... 1 internal note(s) omitted" in out


def test_format_ticket_line_masks_customer_email():
    line = formatting.format_ticket_line({"id": 1, "customer": "jane.doe@example.test"})
    assert "j***@example.test" in line
    assert "jane.doe" not in line


def test_format_ticket_detail_truncates_long_bodies():
    article = {"id": 1, "sender": "Agent", "type": "email", "body": "x" * 5000}
    out = formatting.format_ticket_detail(TICKET, [article])
    assert "[truncated]" in out


def test_format_ticket_detail_limits_article_count():
    articles = [{"id": i, "body": f"body {i}"} for i in range(60)]
    out = formatting.format_ticket_detail(TICKET, articles)
    assert "... 10 more article(s) omitted" in out


def test_server_registers_read_only_tools():
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    sync_names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    async_names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert sync_names == {"search_tickets", "get_ticket", "ticket_report"}
    assert async_names == {"search_tickets", "get_ticket", "ticket_report"}


class PagedTransport:
    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        index = min(len(self.calls) - 1, len(self.payloads) - 1)
        return self.payloads[index]


def test_list_tickets_paginates_until_short_page():
    transport = PagedTransport([[dict(TICKET, id=i) for i in range(100)], [dict(TICKET, id=100)]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    rows = client.list_tickets()
    assert len(rows) == 101
    assert transport.calls[0]["url"] == f"{BASE}/api/v1/tickets"
    assert transport.calls[0]["params"] == {"page": 1, "per_page": 100, "expand": "true"}
    assert transport.calls[1]["params"] == {"page": 2, "per_page": 100, "expand": "true"}


def test_list_tickets_caps_max_tickets():
    transport = PagedTransport([[dict(TICKET, id=i) for i in range(100)]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert len(client.list_tickets(max_tickets=0)) == 1
    with pytest.raises(ZammadError, match="integer"):
        client.list_tickets(max_tickets="many")


def test_list_tickets_rejects_unexpected_payload():
    client, _ = make_client({"total_count": 3})
    with pytest.raises(ZammadError, match="ticket list payload"):
        client.list_tickets()


def test_list_tickets_continues_past_filtered_full_page():
    first_page = [dict(TICKET, id=i) for i in range(99)] + ["junk"]
    transport = PagedTransport([first_page, [dict(TICKET, id=100)]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    rows = client.list_tickets()
    assert len(rows) == 100
    assert len(transport.calls) == 2


def test_list_tickets_caps_at_max_report_tickets():
    full_page = [dict(TICKET, id=i) for i in range(100)]
    transport = PagedTransport([full_page])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    rows = client.list_tickets(max_tickets=500)
    assert len(rows) == 500
    assert len(transport.calls) == 5


def test_parse_timestamp_handles_missing_and_garbage():
    assert formatting._parse_timestamp(None) is None
    assert formatting._parse_timestamp("-") is None
    assert formatting._parse_timestamp("not-a-date") is None
    parsed = formatting._parse_timestamp("2026-09-15T12:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_format_ticket_report_empty():
    expected = "Zammad ticket report: no tickets visible to this token."
    assert formatting.format_ticket_report([]) == expected


def test_format_ticket_report_aggregates():
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    tickets = [
        {
            "state": "open",
            "group": "Sitaas",
            "priority": "2 normal",
            "updated_at": "2026-09-15T10:00:00.000Z",
        },
        {
            "state": "closed",
            "group": "Sitaas",
            "priority": "2 normal",
            "updated_at": "2026-08-01T10:00:00.000Z",
        },
        {
            "state": "warten auf Dev",
            "group": "OCC Devs",
            "priority": "3 high",
            "updated_at": "2026-09-14T10:00:00.000Z",
        },
    ]
    out = formatting.format_ticket_report(tickets, now=now)
    assert "Zammad ticket report (3 ticket(s) visible)" in out
    assert "Unresolved: 2 | Closed: 1" in out
    assert "By state" in out
    assert "By group" in out
    assert "Sitaas" in out
    assert "OCC Devs" in out
    assert "Updated in the last 7 days: 2" in out


def test_allowed_host_patterns_append_port_wildcard():
    from scripts.zammad_mcp import server

    assert server._allowed_host_patterns("zammad-mcp") == ["zammad-mcp:*"]
    assert server._allowed_host_patterns("zammad-mcp:8770, localhost:*") == [
        "zammad-mcp:8770",
        "localhost:*",
    ]
    assert server._allowed_host_patterns(" , ") == []


def test_run_mcp_allowlists_env_hosts(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    allowed = server.mcp.settings.transport_security.allowed_hosts
    before = list(allowed)
    monkeypatch.setenv("ZAMMAD_MCP_ALLOWED_HOSTS", "zammad-mcp")
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: None)
    try:
        server.run_mcp(port=8770)
        assert "zammad-mcp:*" in allowed
        assert server.mcp.settings.transport_security.enable_dns_rebinding_protection is True
    finally:
        allowed[:] = before
