"""DIG-284 leaf 284.1 — the MCP tool-allowlist contract across the HTTP boundary.

The BFF owns the operator allowlist: ``allowedTools`` (full remote names, exact
match, deny-by-default) and ``mutatingTools`` (the subset that changes state)
ride in on ``X-Digi-Mcp-Servers``. Three properties are pinned here, each of
which a future refactor can break silently:

1. both lists survive header → :class:`McpServerRef` →
   ``WorkflowState["mcp_servers"]`` unchanged. A row field dropped in transit is
   not a safe default, it is a deny-everything that still looks configured.
2. an allowlist match is equality against the *raw* remote name — never a glob,
   prefix, or case-folded match (wire rule 2, CTO bar item 8).
3. the raw remote name stays recoverable before :func:`prefixed_tool_name`
   substitutes and truncates it (CTO bar item 6), so the gate added in 284.3 can
   decide on the name the operator actually wrote.

Which tools reach the model is 284.3's business, not this leaf's: the last test
pins that this leaf leaves the model-facing payload byte-identical.

Every test carries ``@pytest.mark.unit`` — ``tests/dg/`` is not auto-marked, so
``pytest -m unit`` silently skips an unmarked test.

Helpers are imported inside each test on purpose: before the implementation
exists, that surfaces as one failed test per property rather than a collection
error that hides which of them are unpinned.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

# Mirrors apps/digichat/src/lib/deploy-config/mcp-servers.ts (leaf 284.2). Kept
# literal here on purpose: a drift in either bound is a contract break, not a
# refactor.
MAX_TOOL_ENTRIES = 256
MAX_TOOL_NAME_LENGTH = 64

# A remote name longer than the truncation width in ``prefixed_tool_name``, in
# Atlassian's namespaced camelCase style, so the record below cannot recover its
# own raw name from the offered name.
LONG_ATLASSIAN_NAME = "atlassian." + "searchIssuesOnProjectByJqlAndExpand" * 2 + "WithCursor"


def _request(*servers: dict) -> SimpleNamespace:
    """A minimal Starlette-ish request carrying an X-Digi-Mcp-Servers header."""
    return SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={"X-Digi-Mcp-Servers": json.dumps(list(servers))},
    )


@pytest.mark.unit
def test_mcp_allowed_tools_survives_http_boundary(monkeypatch):
    """The operator's two lists reach graph state intact, in wire spelling."""
    from digigraph.http_api.context import _digi_fields_from_request, _with_digi_request_context
    from digigraph.models import WorkflowRequest
    from digigraph.orchestration.mcp_client import mcp_server_allows_raw_tool

    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    request = _request(
        {
            "id": "datatap",
            "url": "https://mcp.datatap.example/mcp",
            "allowedTools": ["get_ticket", "create_ticket"],
            "mutatingTools": ["create_ticket"],
        },
        {"id": "digivault", "url": "http://digivault-mcp:8769/mcp", "allowedTools": ["search_tag"]},
    )

    refs = _digi_fields_from_request(request)["mcp_servers"]
    assert [r.id for r in refs] == ["datatap", "digivault"]
    assert refs[0].allowed_tools == ["get_ticket", "create_ticket"]
    assert refs[0].mutating_tools == ["create_ticket"]
    assert refs[1].allowed_tools == ["search_tag"]
    assert refs[1].mutating_tools is None

    # workflow.py:386 projects refs with model_dump(exclude_none=True,
    # by_alias=True) into graph state; research.py hands that list to execute →
    # call_prefixed_tool. Wire spelling, values unchanged, no key invented.
    copied = _with_digi_request_context(request, WorkflowRequest(prompt="hi"))
    state_servers = [r.model_dump(exclude_none=True, by_alias=True) for r in copied.mcp_servers]
    assert state_servers[0]["allowedTools"] == ["get_ticket", "create_ticket"]
    assert state_servers[0]["mutatingTools"] == ["create_ticket"]
    assert state_servers[1]["allowedTools"] == ["search_tag"]
    # An absent mutatingTools must stay absent: that absence is what rule 5 reads
    # as "every allowed tool is mutating". exclude_none dropping it is the point.
    assert "mutatingTools" not in state_servers[1]

    # The gate helper reads the same row shape, so the decision 284.3 makes is
    # made on the header's own spelling rather than on a re-projection.
    assert mcp_server_allows_raw_tool(state_servers[0], "get_ticket") is True
    assert mcp_server_allows_raw_tool(state_servers[0], "delete_ticket") is False
    assert mcp_server_allows_raw_tool(state_servers[1], "search_tag") is True


@pytest.mark.unit
def test_mcp_server_allows_raw_tool_matches_exactly():
    """Rule 2 / CTO bar item 8 — equality only, on the raw remote name."""
    from digigraph.orchestration.mcp_client import mcp_server_allows_raw_tool

    server = {
        "id": "datatap",
        "url": "https://mcp.datatap.example/mcp",
        "allowedTools": ["get_ticket", "create_ticket"],
    }
    assert mcp_server_allows_raw_tool(server, "get_ticket") is True
    assert mcp_server_allows_raw_tool(server, "create_ticket") is True

    # No glob, no prefix, no case folding, no "starts with", no fuzzy tail. Each
    # of these is the near-miss that turns one operator-approved tool into a
    # whole family of unapproved ones.
    assert mcp_server_allows_raw_tool(server, "datatap_*") is False
    assert mcp_server_allows_raw_tool(server, "datatap_x") is False
    assert mcp_server_allows_raw_tool(server, "Get_Ticket") is False
    assert mcp_server_allows_raw_tool(server, "get_ticket_v2") is False
    assert mcp_server_allows_raw_tool(server, "get_tickets") is False
    assert mcp_server_allows_raw_tool(server, "atlassian.executeWrite") is False
    assert mcp_server_allows_raw_tool(server, "") is False

    # Deny-by-default (rule 1): absent and empty both deny everything.
    assert mcp_server_allows_raw_tool({"id": "datatap"}, "get_ticket") is False
    assert mcp_server_allows_raw_tool({"id": "datatap", "allowedTools": []}, "get_ticket") is False


@pytest.mark.unit
def test_raw_tool_names_for_server_returns_untruncated_names():
    """CTO bar item 6 — the raw name, not the prefixed/truncated one."""
    from digigraph.orchestration.mcp_client import (
        _tool_record,
        raw_tool_names_for_server,
    )

    dotted = "atlassian.executeWrite"
    long_name = LONG_ATLASSIAN_NAME
    assert len(long_name) > MAX_TOOL_NAME_LENGTH

    records = [
        _tool_record("atlassian", dotted, "Write through the meta tool", {"type": "object"}),
        _tool_record("atlassian", long_name, None, None),
    ]

    # Precondition, and the reason the sidecar exists: the offered name the model
    # sees has lost both the dot and everything past 64 safe characters, so it
    # cannot be matched back to what the operator wrote.
    offered = [r["function"]["name"] for r in records]
    assert offered[0] == "atlassian_atlassian_executeWrite"
    assert dotted not in offered[0]
    assert offered[1].startswith("atlassian_")
    assert len(offered[1]) < len(f"atlassian_{long_name}")
    assert long_name not in offered[1]

    assert raw_tool_names_for_server("atlassian", records) == [dotted, long_name]
    # Order-preserving and de-duplicated: a server that lists a name twice offers
    # it once, and 284.3 must not double-count it.
    assert raw_tool_names_for_server("atlassian", [records[0], records[0]]) == [dotted]
    # Names from another server are not this server's.
    assert raw_tool_names_for_server("datatap", records) == []
    # No sidecar, no guess. A record whose raw name was not observed comes back
    # absent rather than reconstructed from the lossy offered name.
    assert raw_tool_names_for_server("atlassian", [{"function": {"name": "atlassian_x"}}]) == []


@pytest.mark.unit
def test_absent_and_empty_allowlist_are_distinguishable_but_both_deny(monkeypatch):
    """Rule 1 — both deny everything; rule 5 — but they are not the same answer."""
    from digigraph.http_api.context import _digi_fields_from_request
    from digigraph.orchestration.mcp_client import (
        mcp_server_allows_raw_tool,
        mcp_server_mutating_tools,
    )

    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    request = _request(
        {"id": "empty", "url": "https://mcp.example.com/mcp", "allowedTools": []},
        {"id": "none", "url": "https://mcp.example.com/mcp"},
        {
            "id": "all",
            "url": "https://mcp.example.com/mcp",
            "allowedTools": ["get_ticket", "create_ticket"],
        },
        {
            "id": "open",
            "url": "https://mcp.example.com/mcp",
            "allowedTools": ["get_ticket", "create_ticket"],
            "mutatingTools": [],
        },
    )
    refs = _digi_fields_from_request(request)["mcp_servers"]
    rows = [r.model_dump(exclude_none=True, by_alias=True) for r in refs]

    # An explicit [] survives the boundary as []; an absent key stays absent.
    assert rows[0]["allowedTools"] == []
    assert "allowedTools" not in rows[1]
    assert "mutatingTools" not in rows[2]
    assert rows[3]["mutatingTools"] == []

    # Rule 1: an absent allowlist and an empty one offer exactly the same
    # nothing, so the gate result is identical.
    for row in (rows[0], rows[1]):
        assert mcp_server_allows_raw_tool(row, "get_ticket") is False
    assert mcp_server_mutating_tools(rows[0]) == set()
    assert mcp_server_mutating_tools(rows[1]) == set()

    # Rule 5: an absent mutatingTools means every allowed tool mutates, while an
    # operator-written [] is a real decision that no tool does. Collapsing the
    # two would either prompt for read-only tools or skip a write.
    assert mcp_server_mutating_tools(rows[2]) == {"get_ticket", "create_ticket"}
    assert mcp_server_mutating_tools(rows[3]) == set()
    # And on a row that allows nothing the two happen to agree, which is why the
    # distinction has to be tested on a row that allows something.
    assert mcp_server_mutating_tools({"allowedTools": []}) == set()
    assert mcp_server_mutating_tools({"allowedTools": ["a"], "mutatingTools": []}) == set()
    assert mcp_server_mutating_tools({"allowedTools": ["a"], "mutatingTools": ["a"]}) == {"a"}
    # mutatingTools never widens: a mutating name outside the allowlist is not
    # reachable through the mutating set, because allowedTools is the only list
    # that grants (review #5061 S2 — mutatingTools is deliberately not validated
    # as a subset, precisely because it grants nothing).
    assert mcp_server_mutating_tools({"allowedTools": ["a"], "mutatingTools": ["b"]}) == {"b"}
    assert mcp_server_allows_raw_tool({"allowedTools": ["a"], "mutatingTools": ["b"]}, "b") is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "allowed",
    [
        pytest.param("get_ticket", id="not-a-list"),
        pytest.param(["get_ticket", 7], id="non-string-entry"),
        pytest.param(["get_ticket", ""], id="empty-name"),
        pytest.param(["x" * (MAX_TOOL_NAME_LENGTH + 1)], id="name-too-long"),
        pytest.param([f"tool_{i}" for i in range(MAX_TOOL_ENTRIES + 1)], id="too-many-entries"),
    ],
)
def test_malformed_allowlist_denies_everything(monkeypatch, allowed):
    """Rule 3 — malformed is treated as absent. Refuse, never trim."""
    from digigraph.http_api.context import _digi_fields_from_request
    from digigraph.orchestration.mcp_client import (
        mcp_server_allows_raw_tool,
        mcp_server_mutating_tools,
    )

    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    request = _request(
        {
            "id": "datatap",
            "url": "https://mcp.datatap.example/mcp",
            "allowedTools": ["get_ticket"],
            "mutatingTools": allowed,
        }
    )
    refs = _digi_fields_from_request(request)["mcp_servers"]
    assert refs[0].allowed_tools == ["get_ticket"]
    assert refs[0].mutating_tools is None

    rows = [r.model_dump(exclude_none=True, by_alias=True) for r in refs]
    # A trimmed list would still look configured while silently dropping the
    # tools the operator asked about; denying is the only safe reading.
    assert mcp_server_mutating_tools(rows[0]) == {"get_ticket"}
    assert mcp_server_allows_raw_tool(rows[0], "get_ticket") is True

    # The same refusal applies to the allowlist itself.
    request = _request(
        {
            "id": "datatap",
            "url": "https://mcp.datatap.example/mcp",
            "allowedTools": allowed,
        }
    )
    refs = _digi_fields_from_request(request)["mcp_servers"]
    assert refs[0].allowed_tools is None
    rows = [r.model_dump(exclude_none=True, by_alias=True) for r in refs]
    assert "allowedTools" not in rows[0]
    assert mcp_server_allows_raw_tool(rows[0], "get_ticket") is False
    assert mcp_server_mutating_tools(rows[0]) == set()


@pytest.mark.unit
def test_openai_tools_for_servers_never_leaks_the_raw_name(monkeypatch):
    """This leaf must not change what the model sees, or it is 284.3 by accident."""
    from digigraph.orchestration import mcp_client
    from digigraph.orchestration.mcp_client import _tool_record, openai_tools_for_servers

    schema = {"type": "object", "properties": {}}
    record = _tool_record("datatap", "get_ticket", "Read a ticket", schema)
    monkeypatch.setattr(mcp_client, "list_tools_cached", lambda s: [record])

    offered = openai_tools_for_servers([{"id": "datatap", "url": "https://mcp.example.com/mcp"}])
    assert offered == [
        {
            "type": "function",
            "function": {
                "name": "datatap_get_ticket",
                "description": "Read a ticket",
                "parameters": schema,
            },
        }
    ]

    # The cached record keeps its raw name for the gate, so a second pass over the
    # same cache entry (60s TTL) still sees it.
    assert mcp_client._RAW_TOOL_NAME_KEY in record
    assert (
        openai_tools_for_servers([{"id": "datatap", "url": "https://mcp.example.com/mcp"}])
        == offered
    )
