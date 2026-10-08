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


# =====================================================================
# DIG-284 leaf 284.3 — the brake: deny-by-default intersection.
# =====================================================================
#
# 284.1 carried the contract. 284.3 is where it bites: of everything a remote MCP
# server advertises, the operator's allowlist decides what the model is shown.
# Every test below drives the chain research_node actually runs —
# ``extra_tool_names_for_servers`` → ``apply_mcp_extra_tools`` →
# ``get_tools_for_skills`` → the payload a provider receives — with only the
# network call faked. Faking the policy function instead would pin the test to
# the policy function rather than to the behaviour.

# The four meta tools, refused before the allowlist is read at all.
META_TOOL_NAMES = ("discover", "executeRead", "executeWrite", "executeDestructive")

# Atlassian's published write surface. Four of these are marked primary in the
# shipped catalog; the brake must not care, so the fixture marks all fifteen.
WRITE_JIRA_TOOL_NAMES = (
    "createJiraIssue",
    "editJiraIssue",
    "transitionJiraIssue",
    "addOrEditJiraIssueComment",
    "addOrEditJiraIssueWorklog",
    "createJiraIssueLink",
    "manageJiraProjectVersion",
    "manageJiraProjectVersionRelatedWork",
    "manageJiraSprint",
    "createJiraBoard",
    "watchJiraIssue",
    "uploadAttachmentToJiraIssue",
    "editJiraEntityProperty",
    "createJiraIssueRemoteIssueLink",
    "convertJiraIssueHierarchy",
)

ATLASSIAN_READ_TOOL = "getJiraIssue"


def _records(server_id: str, raw_names: tuple[str, ...]) -> list[dict]:
    """Listed-tool records for a fake server, every one carrying the same marker.

    ``digi_primary`` mirrors the annotation the shipped catalog uses to separate
    headline tools from the long tail. Publishing it on *every* tool means a brake
    built from catalog shape ("primary tools minus the meta four") has nothing to
    separate and cannot produce the expected answer. It is not a schema key and
    never reaches a provider; it is here so the adversarial condition is legible.
    """
    from digigraph.orchestration.mcp_client import _tool_record

    out = []
    for raw in raw_names:
        rec = _tool_record(
            server_id, raw, f"{raw} description", {"type": "object", "properties": {}}
        )
        rec["annotations"] = {"digi_primary": True}
        out.append(rec)
    return out


def _install_catalog(monkeypatch, catalogs: dict[str, list[dict]]) -> None:
    """Serve *catalogs* (keyed by server id) in place of the network call.

    Patches ``_list_tools_blocking`` — the one call behind ``list_tools_cached``,
    the chokepoint the policy path and ``get_tools`` both read through — so the
    cache, the brake, and the allowlist intersection all execute for real. The
    module cache is replaced so one test's catalog cannot answer the next.
    """
    from digigraph.orchestration import mcp_client

    monkeypatch.setattr(mcp_client, "_cache", {})
    monkeypatch.setattr(
        mcp_client,
        "_list_tools_blocking",
        lambda server: list(catalogs.get(server.get("id"), [])),
    )


def _atlassian_row(**overrides) -> dict:
    """One operator MCP row: the operator's URL, their token, one allowed tool."""
    row = {
        "id": "atlassian",
        "url": "https://mcp.atlassian.com/v1/sse",
        "authHeader": "Authorization",
        "token": "operator-token",
        "allowedTools": [ATLASSIAN_READ_TOOL],
    }
    row.update(overrides)
    return row


def _atlassian_catalog() -> list[dict]:
    return _records("atlassian", (ATLASSIAN_READ_TOOL, *META_TOOL_NAMES, *WRITE_JIRA_TOOL_NAMES))


def _research_chain(servers: list[dict], session_allowed: frozenset[str] | None = None) -> list[str]:
    """Tool names a provider would be sent, through research_node's real sequence.

    ``session_allowed`` stands in for whatever ``allowed_tool_names_for_workflow``
    resolved for the request; the default ``None`` is the unrestricted session,
    which is the case a brake has to survive.
    """
    from digigraph.orchestration import mcp_client
    from digigraph.orchestration.registry import ToolContext, ToolExposureMode
    from digigraph.skills.registry import get_tools_for_skills
    from digigraph.tool_policy import apply_mcp_extra_tools

    context = ToolContext(
        session_id="s-1",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"mcp_servers": servers},
        extra_mcp_servers=servers,
    )
    # research.py:390-413 — discovery, policy, then the model-facing projection.
    context.allowed_tool_names = apply_mcp_extra_tools(
        session_allowed,
        frozenset(mcp_client.extra_tool_names_for_servers(servers)),
        frozenset(),
        enable_web_search=False,
    )
    tools = get_tools_for_skills([], context, ToolExposureMode.DETAILED)
    return [t["function"]["name"] for t in tools if isinstance(t, dict) and t.get("function")]


@pytest.mark.unit
def test_only_the_allowlisted_tool_reaches_the_model_from_a_full_atlassian_catalog(monkeypatch):
    """The decisive test: 4 meta + 15 write tools published, one allowed, one offered.

    Everything here is marked primary and every write tool is identically shaped,
    so the only thing that can separate ``getJiraIssue`` from the other nineteen
    is the operator's allowlist. A brake keyed on the offered name — prefixed,
    substituted, truncated — cannot match ``getJiraIssue`` at all, and one built
    from catalog shape has nothing to go on.
    """
    _install_catalog(monkeypatch, {"atlassian": _atlassian_catalog()})
    assert _research_chain([_atlassian_row()]) == ["atlassian_getJiraIssue"]


@pytest.mark.unit
def test_meta_tools_are_refused_even_when_the_operator_allowlists_them(monkeypatch):
    """Rule 3 runs before and regardless of the allowlist — a separate check.

    Security's correction to the acceptance bar: a literal deny-set does not
    hold, because the brake keys on the raw remote name and ``atlassian.executeWrite``
    is not byte-equal to ``executeWrite``. The ruled shape — segment deny on the
    same substitution that builds the offered name, then case-folded — refuses
    all eight spellings below, including the five a naive normalisation misses.
    """
    aliases = (
        "executeWrite",
        "ExecuteWrite",
        "executewrite",
        "atlassian.executeWrite",
        "jira.executeWrite",
        "confluence-executeWrite",
        " executeWrite ",
        "x.y.discover",
    )
    _install_catalog(
        monkeypatch,
        {"atlassian": _records("atlassian", (ATLASSIAN_READ_TOOL, *aliases, "getChangelog"))},
    )

    # The operator allowlists the aliases explicitly, alongside a legitimate tool
    # as the positive control. That is precisely the case the separate check
    # exists for: the allowlist grants them, and the gate still refuses them.
    row = _atlassian_row(allowedTools=[*aliases, "getChangelog"])
    assert _research_chain([row]) == ["atlassian_getChangelog"]


@pytest.mark.parametrize(
    "request_allowed",
    [
        pytest.param(None, id="tools-all-or-absent"),
        pytest.param([], id="request-denies-everything"),
        pytest.param(["atlassian_createJiraIssue"], id="request-names-a-refused-tool"),
        pytest.param(["atlassian_executeWrite"], id="request-names-a-refused-meta-tool"),
        pytest.param(["atlassian_getJiraIssue"], id="request-names-the-allowed-tool"),
    ],
)
@pytest.mark.unit
def test_no_request_input_widens_the_operator_allowlist(monkeypatch, request_allowed):
    """Session input never grants: ``?tools=all``, a deny-all request, a request
    naming a refused tool all resolve to the same single offered tool.

    A request is session input; the allowlist is operator configuration. The
    request's opinion is an input to the native allowlist and never a grant
    against the operator row.
    """
    from digigraph.models import WorkflowRequest
    from digigraph.project_config import DigiProjectConfig
    from digigraph.tool_policy import allowed_tool_names_for_workflow

    _install_catalog(monkeypatch, {"atlassian": _atlassian_catalog()})
    # Pin both non-request inputs to "unset" so the request is the only variable:
    # an empty project config and an absent env var.
    monkeypatch.delenv("DIGI_ALLOWED_TOOLS", raising=False)
    empty_cfg = DigiProjectConfig()

    session_allowed = allowed_tool_names_for_workflow(
        WorkflowRequest(prompt="hi", allowed_tools=request_allowed), cfg=empty_cfg
    )
    assert _research_chain([_atlassian_row()], session_allowed) == ["atlassian_getJiraIssue"]


@pytest.mark.unit
def test_allowlist_follows_the_row_not_the_server_id(monkeypatch):
    """A re-pointed row is judged on its own allowlist; the id grants nothing.

    There is deliberately no id-keyed allowlist table. If the gate remembered
    "atlassian allows getJiraIssue" from the first row it saw, then re-pointing
    the row at another host — or tightening the allowlist on the same host —
    would keep serving the earlier, wider answer for the whole 60s cache TTL. The
    allowlist is a property of the row, so each row is read on its own.
    """
    _install_catalog(monkeypatch, {"atlassian": _atlassian_catalog()})

    operator = [_atlassian_row()]
    assert _research_chain(operator) == ["atlassian_getJiraIssue"]

    # Same id, same auth header, same operator token — the attacker just moved
    # the URL, and their row carries an allowlist naming none of what they publish.
    attacker = [
        _atlassian_row(
            url="https://mcp.attacker.example/v1/sse",
            allowedTools=["createJiraIssue"],
        )
    ]
    assert _research_chain(attacker) == ["atlassian_createJiraIssue"]

    # Tightened on the original host: the wider answer must not survive the cache.
    tightened = [_atlassian_row(allowedTools=["createJiraIssue"])]
    assert _research_chain(tightened) == ["atlassian_createJiraIssue"]

    # And the first row still resolves on its own allowlist, not the last one seen.
    assert _research_chain(operator) == ["atlassian_getJiraIssue"]


@pytest.mark.unit
def test_offered_name_collision_offers_zero_tools_and_audits(monkeypatch):
    """Two allowlisted raw names that collapse to one offered name offer neither.

    ``prefixed_tool_name`` is lossy — it substitutes every character outside
    ``[a-zA-Z0-9_-]`` — so ``read.jira.issue`` and ``read_jira_issue`` are two
    distinct operator-approved tools wearing one name. Picking either would hand
    the choice of which approved tool runs to whichever the server listed first,
    so the gate refuses the name outright and records it.

    ``getJiraIssue`` is allowlisted too, and it is the control: it shares no
    offered name with the pair, so it must survive untouched. A collision is a
    fact about one name, not a reason to distrust the row.
    """
    from unittest.mock import patch

    _install_catalog(
        monkeypatch,
        {
            "atlassian": _records(
                "atlassian", ("read.jira.issue", "read_jira_issue", ATLASSIAN_READ_TOOL)
            )
        },
    )
    row = _atlassian_row(
        allowedTools=["read.jira.issue", "read_jira_issue", ATLASSIAN_READ_TOOL]
    )

    with patch("digigraph.audit.audit_log") as audit:
        offered = _research_chain([row])

    # The colliding name is offered by neither tool; the third survives, so the
    # refusal is confined to the one unresolvable name.
    assert offered == [f"atlassian_{ATLASSIAN_READ_TOOL}"]

    reasons = {
        (c.kwargs.get("payload") or {}).get("tool"): (c.kwargs.get("payload") or {}).get("reason")
        for c in audit.call_args_list
        if c.args and c.args[0] == "tool_denied"
    }
    # Both participants, not just the one that happened to be listed second.
    assert reasons.get("read.jira.issue") == "offered_name_collision"
    assert reasons.get("read_jira_issue") == "offered_name_collision"
    assert ATLASSIAN_READ_TOOL not in reasons, (
        "the collision must not drag down an unrelated allowed tool"
    )


@pytest.mark.unit
def test_offered_name_is_a_function_of_one_approved_raw_name(monkeypatch):
    """CTO bar item 10 — naming a different tool must be unrepresentable.

    Not "the brake does not implement it" but "there is no value in which a
    second name could be written": every tool that leaves the gate carries a name
    that is ``prefixed_tool_name(server_id, raw)`` for a raw name the operator
    listed, and nothing else in the payload can disagree about which tool it is.
    """
    from digigraph.orchestration import mcp_client
    from digigraph.orchestration.mcp_client import prefixed_tool_name

    _install_catalog(monkeypatch, {"atlassian": _atlassian_catalog()})
    servers = [_atlassian_row()]

    offered = mcp_client.openai_tools_for_servers(servers)
    assert [t["function"]["name"] for t in offered] == ["atlassian_getJiraIssue"]

    # The tool definition a provider receives is fixed-shape: three fields, the
    # name being one value derived from one approved raw name. There is no second
    # field that could name a different tool, and no template plus override.
    record = offered[0]
    assert set(record["function"]) == {"name", "description", "parameters"}
    assert record["function"]["name"] == prefixed_tool_name("atlassian", ATLASSIAN_READ_TOOL)

    # The catalog's own decorations ride along on the record but decide nothing:
    # dropping the primary marker from every tool changes nothing about the
    # outcome. This is the same property CTO item 9 asks for — a brake built from
    # catalog shape would answer differently here.
    _install_catalog(
        monkeypatch,
        {
            "atlassian": [
                {k: v for k, v in rec.items() if k != "annotations"}
                for rec in _atlassian_catalog()
            ]
        },
    )
    undecorated = mcp_client.openai_tools_for_servers(servers)
    assert [t["function"]["name"] for t in undecorated] == ["atlassian_getJiraIssue"]

    # Same one-to-one property at the gate itself, read back off the sidecar:
    # every offered name maps back to exactly one operator-written raw name, and
    # two different approved tools can never collapse to one offered name.
    kept = mcp_client.filter_tools_for_server(servers[0], _atlassian_catalog())
    assert mcp_client.raw_tool_names_for_server("atlassian", kept) == [ATLASSIAN_READ_TOOL]


@pytest.mark.unit
@pytest.mark.parametrize("allowlist", [None, []], ids=["key-absent", "explicit-empty"])
def test_missing_or_empty_allowlist_denies_every_tool_and_warns_loudly(
    monkeypatch, caplog, allowlist
):
    """EM ruling: deny *and* fail loudly — id, host, and the count refused.

    Silence is the failure mode. A row that reaches the gate without a usable
    ``allowedTools`` still has a URL, a token and an auth header, so it looks
    configured; a quiet denial then presents as "the server offered nothing" and
    nobody goes looking for the config mistake that caused it.

    Both spellings are the same deny. ``absent == empty`` is the wire rule: an
    operator who omits the key and an operator who writes ``[]`` get the same
    refusal, so a missing key cannot read as "unrestricted" to anyone reading
    the config.
    """
    import logging
    from unittest.mock import patch

    catalog = _atlassian_catalog()
    _install_catalog(monkeypatch, {"atlassian": catalog})
    row = _atlassian_row()
    if allowlist is not None:
        row["allowedTools"] = allowlist
    else:
        row.pop("allowedTools")

    with patch("digigraph.audit.audit_log") as audit:
        with caplog.at_level(logging.WARNING, logger="digigraph.orchestration.mcp_client"):
            assert _research_chain([row]) == []

    warning = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "atlassian" in warning
    assert "mcp.atlassian.com" in warning
    assert str(len(catalog)) in warning

    # One denial per discovered tool, not one per server: the operator needs to
    # see that fifteen write tools went dark, not that "something" was refused.
    denials = [c for c in audit.call_args_list if c.args and c.args[0] == "tool_denied"]
    assert len(denials) == len(catalog)
