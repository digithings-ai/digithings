"""Unit tests for scripts/zammad_mcp (no network)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from scripts.zammad_mcp import formatting
from scripts.zammad_mcp.client import ZammadClient, ZammadError, keyword_terms

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
    assert sync_names == {"search_tickets", "list_tickets", "get_ticket", "ticket_report"}
    assert async_names == {"search_tickets", "list_tickets", "get_ticket", "ticket_report"}


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


class NumberLookupTransport:
    """Serve GET /tickets/{number} as a 404, then answer the search lookup."""

    def __init__(
        self,
        number: int,
        rows: list[dict[str, Any]],
        resolved: dict[str, Any] | None = None,
    ) -> None:
        self.number = number
        self.rows = rows
        self.resolved = resolved
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url.endswith(f"/api/v1/tickets/{self.number}"):
            raise ZammadError("Zammad HTTP 404: not found")
        if url.endswith("/api/v1/tickets/search"):
            return self.rows
        if self.resolved is not None and url.endswith(f"/api/v1/tickets/{self.resolved['id']}"):
            return self.resolved
        raise AssertionError(f"unexpected url {url}")


class StatusTransport:
    def __init__(self, status: int) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        raise ZammadError(f"Zammad HTTP {self.status}: error")


def test_keyword_terms_keeps_plain_words():
    assert keyword_terms("Rechnung Zahlung") == ["Rechnung", "Zahlung"]


def test_keyword_terms_extracts_field_values_and_strips_noise():
    terms = keyword_terms('state.name:open AND article.body:"big invoice" ~rechnung*')
    assert terms == ["open", "big", "invoice", "rechnung"]


def test_keyword_terms_drops_short_stopword_and_duplicate_terms():
    assert keyword_terms("invoice ~INVOICE* and to or") == ["invoice"]
    assert keyword_terms("a I ?") == []
    assert keyword_terms("one two three four five six seven") == [
        "one",
        "two",
        "three",
        "four",
        "five",
    ]


def test_search_tickets_accepts_records_and_objects_envelopes():
    client, _ = make_client({"records": [TICKET, "junk"], "total_count": 1})
    assert client.search_tickets("x") == [TICKET]
    client, _ = make_client({"objects": [TICKET]})
    assert client.search_tickets("x") == [TICKET]


def test_search_tickets_by_terms_merges_dedupes_and_limits():
    oldest = dict(TICKET, id=1, updated_at="2026-09-12T00:00:00.000Z")
    newest = dict(TICKET, id=2, updated_at="2026-09-16T00:00:00.000Z")
    middle = dict(TICKET, id=3, updated_at="2026-09-14T00:00:00.000Z")
    transport = PagedTransport([[oldest, newest], [dict(TICKET, id=2), middle]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    rows = client.search_tickets_by_terms(["rechnung", "zahlung"], limit=2)
    assert [row["id"] for row in rows] == [2, 3]
    assert transport.calls[0]["params"] == {"query": "rechnung", "limit": 2, "expand": "true"}
    assert transport.calls[1]["params"] == {"query": "zahlung", "limit": 2, "expand": "true"}


def test_search_tickets_by_terms_sorts_rows_without_timestamp_last():
    missing = dict(TICKET, id=1, updated_at="")
    dated = dict(TICKET, id=2, updated_at="2026-09-01T00:00:00.000Z")
    transport = PagedTransport([[missing, dated]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    rows = client.search_tickets_by_terms(["rechnung"], limit=5)
    assert [row["id"] for row in rows] == [2, 1]


def test_get_ticket_hash_number_resolves_through_search_first():
    searched = dict(TICKET, id=999, number="231", title="Number-first ticket")
    transport = NumberLookupTransport(231, [searched], searched)
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert client.get_ticket("#231") == searched
    assert transport.calls[0]["url"].endswith("/api/v1/tickets/search")
    assert transport.calls[0]["params"] == {"query": "231", "limit": 50, "expand": "true"}
    assert [call["url"].rsplit("/", 1)[-1] for call in transport.calls] == ["search", "999"]


def test_get_ticket_missing_hash_number_raises_without_id_lookup():
    transport = NumberLookupTransport(99999, [dict(TICKET, id=1, number="28312")])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    with pytest.raises(ZammadError, match="no ticket with number 99999"):
        client.get_ticket("#99999")
    assert len(transport.calls) == 1
    assert transport.calls[0]["url"].endswith("/api/v1/tickets/search")


def test_get_ticket_resolves_ticket_number_after_404():
    resolved = dict(TICKET, id=999, title="Resolved by number")
    transport = NumberLookupTransport(28312, [dict(TICKET, id=999)], resolved)
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert client.get_ticket("28312") == resolved
    assert [call["url"].rsplit("/", 1)[-1] for call in transport.calls] == [
        "28312",
        "search",
        "999",
    ]


def test_get_ticket_reraises_404_when_number_lookup_finds_nothing():
    transport = NumberLookupTransport(28312, [])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    with pytest.raises(ZammadError, match="404"):
        client.get_ticket("28312")
    assert len(transport.calls) == 2


def test_get_ticket_does_not_look_up_numbers_on_other_errors():
    transport = StatusTransport(403)
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    with pytest.raises(ZammadError, match="403"):
        client.get_ticket(231)
    assert len(transport.calls) == 1


def test_format_search_results_notes_keyword_fallback():
    empty = formatting.format_search_results("state.name:open", [], fallback_terms=["open"])
    assert empty == 'No tickets matched: "state.name:open" (also tried keywords: open)'
    found = formatting.format_search_results("big invoice", [TICKET], fallback_terms=["big"])
    assert found.splitlines()[0] == (
        'Found 1 ticket(s) for: "big invoice" (matched via keywords: big)'
    )


def test_server_search_falls_back_to_keywords(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    class StubClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Any]] = []

        def search_tickets(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
            self.calls.append(("query", query))
            return []

        def search_tickets_by_terms(
            self, terms: list[str], limit: int = 10
        ) -> list[dict[str, Any]]:
            self.calls.append(("terms", list(terms)))
            return [dict(TICKET, id=7)]

    stub = StubClient()
    monkeypatch.setattr(server, "_client", lambda: stub)
    out = server.search_tickets("state.name:open")
    assert 'Found 1 ticket(s) for: "state.name:open" (matched via keywords: open)' in out
    assert stub.calls == [("query", "state.name:open"), ("terms", ["open"])]


def test_server_search_skips_fallback_for_single_keyword(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    class StubClient:
        def search_tickets(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
            return [TICKET]

        def search_tickets_by_terms(
            self, terms: list[str], limit: int = 10
        ) -> list[dict[str, Any]]:
            raise AssertionError("fallback should not run")

    monkeypatch.setattr(server, "_client", lambda: StubClient())
    out = server.search_tickets("rechnung")
    assert out.splitlines()[0] == 'Found 1 ticket(s) for: "rechnung"'


def test_keyword_terms_strips_hash_from_numbers():
    terms = keyword_terms("Bitte Ticket #28312 pruefen")
    assert "28312" in terms
    assert "#28312" not in terms


def test_keyword_terms_drops_german_function_words():
    assert keyword_terms("Paket ist zu spat") == ["Paket", "spat"]


def test_list_tickets_page_sorts_newest_updated_first_and_slices():
    older = dict(TICKET, id=1, number="1", updated_at="2026-01-01T00:00:00.000Z")
    newer = dict(TICKET, id=2, number="2", updated_at="2026-02-01T00:00:00.000Z")
    transport = PagedTransport([[older, newer]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert [t["id"] for t in client.list_tickets_page(page=1, per_page=1)] == [2]
    assert [t["id"] for t in client.list_tickets_page(page=2, per_page=1)] == [1]
    assert client.list_tickets_page(page=3, per_page=1) == []


def test_list_tickets_page_clamps_page_and_page_size():
    tickets = [dict(TICKET, id=i, number=str(i)) for i in range(1, 5)]
    transport = PagedTransport([tickets])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert len(client.list_tickets_page(page=0, per_page=2)) == 2
    assert len(client.list_tickets_page(page=1, per_page=0)) == 1


def test_list_tickets_page_rejects_bad_numbers_without_http_call():
    transport = PagedTransport([[dict(TICKET, id=1)]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    with pytest.raises(ZammadError, match="page must be an integer"):
        client.list_tickets_page(page="many")
    with pytest.raises(ZammadError, match="per_page must be an integer"):
        client.list_tickets_page(per_page="many")
    assert transport.calls == []


def test_format_ticket_list_empty_and_page_hint():
    assert formatting.format_ticket_list([], page=1) == "No tickets visible to this token."
    assert formatting.format_ticket_list([], page=2) == "No tickets on page 2; try earlier pages."


def test_format_ticket_list_pages_and_trailer():
    out = formatting.format_ticket_list([dict(TICKET), dict(TICKET, id=232)], page=2, per_page=2)
    lines = out.splitlines()
    assert lines[0] == "Visible tickets (page 2, 2 shown):"
    assert lines[1].startswith("- id 231 #28312 [open] Example ticket subject")
    assert lines[-2] == "Page is full; continue with page 3."
    assert lines[-1] == "Read a full conversation with get_ticket(id or #number)."


def test_server_lists_browsable_tickets(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    class StubClient:
        def list_tickets_page(self, page=1, per_page=50):
            assert (page, per_page) == (2, 5)
            return [dict(TICKET, id=1, number="1", title="Hallo Welt")]

    monkeypatch.setattr(server, "_client", lambda: StubClient())
    out = server.list_tickets(page=2, per_page=5)
    assert out.splitlines()[0] == "Visible tickets (page 2, 1 shown):"
    assert "Hallo Welt" in out


def test_format_ticket_list_clamps_page_and_page_size():
    tickets = [dict(TICKET, id=i, number=str(i)) for i in range(1, 101)]
    out = formatting.format_ticket_list(tickets, page=0, per_page=500)
    lines = out.splitlines()
    assert lines[0] == "Visible tickets (page 1, 100 shown):"
    assert lines[-2] == "Page is full; continue with page 2."


def test_format_ticket_line_collapses_title_newlines():
    sneaky = dict(TICKET, title="real title\n- id 999 #999 [open] injected")
    line = formatting.format_ticket_line(sneaky)
    assert "\n" not in line
    assert "real title - id 999 #999 [open] injected" in line


def test_list_tickets_page_unknown_updated_at_last():
    known = dict(TICKET, id=1, number="1")
    unknown = dict(TICKET, id=2, number="2")
    unknown.pop("updated_at")
    transport = PagedTransport([[known, unknown]])
    client = ZammadClient(base_url=BASE, token=TOKEN, get_json=transport)
    assert [t["id"] for t in client.list_tickets_page(page=1, per_page=10)] == [1, 2]
