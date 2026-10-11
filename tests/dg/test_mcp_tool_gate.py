"""DIG-284 leaf 284.4 — a mutating MCP tool call must stop and ask.

284.3 refuses to *offer* a tool the operator did not allow. That stops a
well-behaved model, because the model only ever sees the offered set. It does
not stop a write: an allowed tool whose operation changes remote state is
offered happily and then executed unattended on the next round.

This leaf closes that gap at the one point where a name becomes an action
(:func:`digigraph.orchestration.registry.execute`, the only pre-execution path
including the parallel fan-out). A mutating MCP call is refused, recorded once,
and surfaced as a pending decision for a human. Seven properties are pinned
here, each of which a later refactor can break silently:

1. the call is refused and the transport is provably never reached.
2. a non-mutating MCP tool still executes — the gate is not deny-everything.
3. an absent ``mutatingTools`` means every allowed tool needs a human
   (wire rule 5), while an explicit ``[]`` means none do.
4. the decision cannot substitute the payload: the decision carries no tool and
   no arguments, so there is nowhere to put a different call.
5. the gate holds on the parallel fan-out — two mutating calls in one round are
   both refused and neither executes.
6. the pending id is opaque: it neither contains nor derives the tool name, the
   server id, or any argument value.
7. the confirmation names the concrete operation and its target argument — never
   ``execute write`` / ``executeWrite`` and never a bare tool name — and the
   confirm path *raises* on a meta tool instead of rendering a consent box for
   one.

The gate sits downstream of 284.3's allowlist refusal on purpose: the refusal
must not depend on a human saying yes, and test 1 pins that order.

Every test carries ``@pytest.mark.unit`` — ``tests/dg/`` is not auto-marked, so
``pytest -m unit`` silently skips an unmarked test.

Helpers are imported inside each test on purpose: before the implementation
exists, that surfaces as one failed test per property rather than a collection
error that hides which of them are unpinned.
"""

from __future__ import annotations

import inspect
import json
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

# The concrete remote operations the fixtures below advertise. ``addComment``
# changes remote state; ``searchIssues`` does not.
MUTATING = "addCommentToJiraIssue"
READ_ONLY = "searchIssues"


def _server(**overrides) -> dict:
    """One operator MCP row, in the wire spelling ``http_api/context.py`` builds."""
    row = {
        "id": "acme",
        "url": "https://mcp.example.invalid/rpc",
        "auth": "bearer",
        "token": "not-a-real-token",
        "allowedTools": [MUTATING, READ_ONLY],
        "mutatingTools": [MUTATING],
    }
    row.update(overrides)
    return row


def _context(*servers, session_id: str = "sess-1", allowed=None, state: dict | None = None):
    from digigraph.orchestration.registry import ToolContext

    return ToolContext(
        session_id=session_id,
        run_data_dir=None,
        index_name="idx",
        index_config={},
        state={} if state is None else state,
        allowed_tool_names=None if allowed is None else frozenset(allowed),
        extra_mcp_servers=list(servers) or None,
    )


@pytest.fixture
def transport(monkeypatch):
    """Stub the MCP transport and record every call that reaches it."""
    import digigraph.orchestration.mcp_client as mc

    calls: list[dict] = []

    def _fake_call_tool_blocking(server, tool, args):
        calls.append({"server_id": server.get("id"), "tool": tool, "args": dict(args)})
        return {"ok": True, "content": f"called {tool}"}

    monkeypatch.setattr(mc, "_call_tool_blocking", _fake_call_tool_blocking)
    return calls


@pytest.fixture
def audit(monkeypatch):
    """Record audit events instead of emitting them; assert on what was written."""
    import digigraph.audit

    events: list[tuple[str, dict]] = []

    def _fake_audit_log(event_type, agent_id="", payload=None, **kwargs):
        events.append((event_type, dict(payload or {})))

    monkeypatch.setattr(digigraph.audit, "audit_log", _fake_audit_log)
    return events


@pytest.mark.unit
def test_mutating_mcp_tool_is_refused_not_executed(transport, audit):
    """The call is refused, the remote is provably untouched, and it is recorded."""
    from digigraph.orchestration import registry

    server = _server()
    ctx = _context(server, allowed=["acme_addCommentToJiraIssue"])
    result = registry.execute("acme_addCommentToJiraIssue", {"issueKey": "JIRA-1234"}, ctx)

    assert result["error"] == "mcp_call_requires_human_approval"
    # The transport is the proof, not the return value: nothing reached the server.
    assert transport == []
    assert [e for e, _ in audit if "pending" in e], "the pending decision must be recorded once"
    assert audit[0][1]["tool"] == MUTATING

    # The record exists, holds the payload, and is reachable only with the session.
    pending_id = result["pending_id"]
    record = registry.pending_mcp_decision(pending_id, session_id="sess-1")
    assert record is not None
    assert record.args == {"issueKey": "JIRA-1234"}
    assert registry.pending_mcp_decision(pending_id, session_id="other-session") is None

    # The lean state event names the operation; it never carries the arguments,
    # because only ``mcp_servers`` is redacted on the way to the checkpoint.
    event = ctx.state["pending_mcp_decision"]
    assert event["pending_id"] == pending_id
    assert event["tool"] == MUTATING
    assert "JIRA-1234" not in json.dumps(ctx.state)

    # The gate sits downstream of 284.3's refusal, which needs no human: a name
    # outside the allowlist is refused as not-allowed, never as needing approval.
    denied = registry.execute(
        "acme_addCommentToJiraIssue", {"issueKey": "JIRA-1234"}, _context(server, allowed=[])
    )
    assert denied["error"] == "tool_not_allowed"


@pytest.mark.unit
def test_non_mutating_tool_still_executes(transport, audit):
    """A read-only MCP tool still runs — otherwise the gate is deny-everything."""
    from digigraph.orchestration import registry

    server = _server()
    ctx = _context(server, allowed=["acme_searchIssues"])
    result = registry.execute("acme_searchIssues", {"jql": "project = DIG"}, ctx)

    assert transport == [{"server_id": "acme", "tool": READ_ONLY, "args": {"jql": "project = DIG"}}]
    assert result == {"ok": True, "content": f"called {READ_ONLY}"}
    assert ctx.state.get("pending_mcp_decision") is None


@pytest.mark.unit
def test_absent_mutating_tools_makes_every_allowed_tool_mutating(transport):
    """Wire rule 5: an absent ``mutatingTools`` means every allowed tool mutates."""
    from digigraph.orchestration import registry

    # Absent key: nothing says which allowed tool mutates, so both need a human.
    absent = _server()
    del absent["mutatingTools"]
    for remote in (MUTATING, READ_ONLY):
        result = registry.execute(f"acme_{remote}", {}, _context(absent))
        assert result["error"] == "mcp_call_requires_human_approval", remote
    assert transport == []

    # An explicit empty list is the operator saying "nothing here mutates".
    none_mutating = _server(mutatingTools=[])
    for remote in (MUTATING, READ_ONLY):
        registry.execute(f"acme_{remote}", {}, _context(none_mutating))
    assert [c["tool"] for c in transport] == [MUTATING, READ_ONLY]

    # A row naming NEITHER list is NOT gated. This is deliberate and pinned. Rule 5
    # as mcp_client implements it falls back to the row's own allowedTools, which
    # an undeclared row also lacks, so the row declares nothing mutating. An
    # earlier revision of this gate failed closed here and gated read-only search
    # servers that declare no list at all; the develop web-search opt-in tests
    # carry exactly this row shape and must stay green.
    bare = _server()
    del bare["mutatingTools"]
    del bare["allowedTools"]
    for remote in (MUTATING, READ_ONLY):
        registry.execute(f"acme_{remote}", {}, _context(bare, allowed=[f"acme_{remote}"]))
    # The whole transport, not a tail slice: the arm above already ran two calls.
    assert [c["tool"] for c in transport] == [MUTATING, READ_ONLY, MUTATING, READ_ONLY]


@pytest.mark.unit
def test_decision_cannot_substitute_the_payload(transport, audit):
    """The decision carries approve-or-deny only; the recorded call is what runs."""
    from digigraph.orchestration import registry

    server = _server()
    ctx = _context(server, session_id="sess-1")
    pending_id = registry.execute("acme_addCommentToJiraIssue", {"issueKey": "JIRA-1234"}, ctx)[
        "pending_id"
    ]

    # There is nowhere to put a different call: no parameter accepts one.
    parameters = inspect.signature(registry.decide_mcp_call).parameters
    assert "tool" not in parameters
    assert "args" not in parameters
    with pytest.raises(TypeError):
        registry.decide_mcp_call(
            pending_id,
            True,
            session_id="sess-1",
            servers=[server],
            tool="deleteAllPages",
            args={"pageId": "P-1"},
        )

    # A decision from another session does not find the record.
    wrong = registry.decide_mcp_call(pending_id, True, session_id="other-session", servers=[server])
    assert wrong["error"] == "unknown_pending_mcp_decision"
    assert transport == []

    approved = registry.decide_mcp_call(pending_id, True, session_id="sess-1", servers=[server])
    assert approved["ok"] is True
    assert transport == [{"server_id": "acme", "tool": MUTATING, "args": {"issueKey": "JIRA-1234"}}]

    # Exactly once: a replayed approval finds no record and runs nothing.
    replay = registry.decide_mcp_call(pending_id, True, session_id="sess-1", servers=[server])
    assert replay["error"] == "unknown_pending_mcp_decision"
    assert len(transport) == 1

    denied = registry.execute(
        "acme_addCommentToJiraIssue", {"issueKey": "JIRA-9999"}, _context(server)
    )["pending_id"]
    out = registry.decide_mcp_call(denied, False, session_id="sess-1", servers=[server])
    assert out["status"] == "denied"
    assert len(transport) == 1


@pytest.mark.unit
def test_gate_holds_on_the_parallel_fan_out(transport, audit):
    """Two mutating calls in one round: both refused, neither executed.

    digillm fans a round out over a thread pool, so a gate that only holds on the
    serial path would be defeated by the ordinary case.
    """
    from digigraph.orchestration import registry

    server = _server(mutatingTools=[MUTATING, "deleteAllPages"])
    ctx = _context(server)
    round_calls = [
        ("acme_addCommentToJiraIssue", {"issueKey": "JIRA-1"}),
        ("acme_deleteAllPages", {"pageId": "P-1"}),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: registry.execute(c[0], c[1], ctx), round_calls))

    assert [r["error"] for r in results] == ["mcp_call_requires_human_approval"] * 2
    assert transport == []
    assert results[0]["pending_id"] != results[1]["pending_id"]
    # Both are still answerable, so neither round is silently lost.
    for result in results:
        assert registry.pending_mcp_decision(result["pending_id"], session_id="sess-1")


@pytest.mark.unit
def test_pending_call_gets_an_opaque_id(transport):
    """The id names nothing: not the tool, not the server, not any argument."""
    from digigraph.orchestration import registry

    server = _server()
    ctx = _context(server)
    args = {"issueKey": "JIRA-1234", "body": "quarterly figures for SICAV"}

    first = registry.execute("acme_addCommentToJiraIssue", dict(args), ctx)["pending_id"]
    second = registry.execute("acme_addCommentToJiraIssue", dict(args), ctx)["pending_id"]

    assert first != second, "an id that repeats is a replay key, not an opaque handle"
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    for leak in (MUTATING, READ_ONLY, "acme", "JIRA-1234", "quarterly", "figures"):
        assert leak not in first
    assert transport == []


@pytest.mark.unit
def test_confirm_names_the_operation_not_the_meta_tool(transport):
    """The confirmation names the concrete operation and its target.

    A consent box that says "execute write" asks a human to approve a category,
    not a call. The meta tools are refused outright: approving one would consent
    to whatever it decides to do next.
    """
    from digigraph.orchestration import registry

    server = _server(mutatingTools=["deleteAllPages"])
    ctx = _context(server)
    result = registry.execute("acme_deleteAllPages", {"pageId": "P-1"}, ctx)

    assert result["tool"] == "deleteAllPages"
    assert result["server_id"] == "acme"
    assert result["target_arguments"] == ["pageId"]
    # The target's value may be client data, so it stays out of the model's
    # context and out of the checkpoint; only the field name travels.
    assert "P-1" not in json.dumps(result)

    rendered = json.dumps(result)
    for banned in ("executeWrite", "execute write", "executeDestructive", "executeRead"):
        assert banned not in rendered

    # The confirm path raises on a meta tool rather than rendering a consent box.
    for meta in (
        "acme_executeWrite",
        "acme_discover",
        "acme_executeRead",
        "acme_executeDestructive",
    ):
        with pytest.raises(registry.MetaToolConfirmationRefused):
            registry.execute(meta, {"anything": 1}, _context(server))
    assert transport == []


@pytest.mark.unit
def test_meta_tool_on_an_undeclared_row_is_not_gated(transport):
    """A meta tool is refused only where the operator row is authoritative.

    This is a deliberate, recorded reduction of the gate's reach, so that it can
    not be widened or narrowed silently. A row that declares no ``mutatingTools``
    says nothing about what mutates, so this gate does not engage on it and the
    call keeps its pre-gate behaviour. The develop test
    ``test_registry_execute_calls_the_advertised_mcp_tool_name`` uses exactly this
    row shape and asserts that such a call executes.
    """
    from digigraph.orchestration import registry

    bare = _server()
    del bare["mutatingTools"]
    del bare["allowedTools"]

    # Not gated and not refused: the call reaches the transport.
    registry.execute(
        "acme_executeWrite", {"anything": 1}, _context(bare, allowed=["acme_executeWrite"])
    )
    assert [c["tool"] for c in transport] == ["executeWrite"]

    # The same meta tool on a row that DOES declare mutatingTools is refused.
    declared = _server(mutatingTools=["deleteAllPages"])
    with pytest.raises(registry.MetaToolConfirmationRefused):
        registry.execute(
            "acme_executeWrite", {"anything": 1}, _context(declared, allowed=["acme_executeWrite"])
        )
    assert [c["tool"] for c in transport] == ["executeWrite"]


# =====================================================================
# EM ruling on Security's union finding (284.4 sign-off rework, condition 1
# and 2): a request-scoped allowlist may narrow the tool surface but must
# never widen it past the operator's per-row allowlist.
# =====================================================================


def _install_catalog(monkeypatch, server_id: str, raw_names: tuple[str, ...]) -> None:
    """Serve a fake catalog in place of the network call.

    Patches ``_list_tools_blocking``, the one call behind
    ``list_tools_cached``, so the cache, 284.3's per-row brake and this leaf's
    policy intersection all run for real. Replacing the module cache stops one
    test's catalog from answering the next.
    """
    from digigraph.orchestration import mcp_client

    records = [
        mcp_client._tool_record(
            server_id, raw, f"{raw} description", {"type": "object", "properties": {}}
        )
        for raw in raw_names
    ]
    monkeypatch.setattr(mcp_client, "_cache", {})
    monkeypatch.setattr(
        mcp_client,
        "_list_tools_blocking",
        lambda server: records if server.get("id") == server_id else [],
    )


@pytest.mark.unit
def test_no_request_input_widens_the_operator_allowlist(monkeypatch, transport):
    """The smuggle Security proved is closed at the execution boundary.

    The operator permits one tool. The session allowlist names the other one.
    The union used to carry the session's MCP name through, which is the same
    set ``registry.execute`` checks -- so the call-time refusal passed a name
    the operator never permitted.
    """
    from digigraph.orchestration import mcp_client, registry
    from digigraph.tool_policy import apply_mcp_extra_tools

    _install_catalog(monkeypatch, "acme", (MUTATING, READ_ONLY))
    # The operator row permits the read tool only, so the write tool is not in
    # the operator's set at all. mutatingTools names the mutating side so the
    # permitted read tool runs unattended: this test is about the allowlist
    # union, not about the confirmation gate.
    row = _server(allowedTools=[READ_ONLY], mutatingTools=[MUTATING])
    offered_mutating = mcp_client.prefixed_tool_name("acme", MUTATING)
    offered_read = mcp_client.prefixed_tool_name("acme", READ_ONLY)

    session_named = frozenset({offered_mutating})
    allowed = apply_mcp_extra_tools(
        session_named,
        frozenset(mcp_client.extra_tool_names_for_servers([row])),
        frozenset(),
        enable_web_search=True,
    )

    # The session cannot widen: its MCP name is gone, the operator's stays.
    assert offered_mutating not in allowed
    assert offered_read in allowed

    # Execution boundary: the smuggled name is refused by the call-time brake
    # and never reaches the transport. The permitted name still runs, so the
    # assertion above is not an empty set.
    ctx = _context(row, allowed=allowed)
    refused = registry.execute(offered_mutating, {"issueKey": "JIRA-1"}, ctx)
    assert refused["error"] == "tool_not_allowed"
    permitted = registry.execute(offered_read, {"jql": "project = X"}, ctx)
    assert permitted == {"ok": True, "content": f"called {READ_ONLY}"}
    assert [call["tool"] for call in transport] == [READ_ONLY]


# =====================================================================
# Adversarial round 2 (EM ruling cafdf1dc): the gate is asked before the
# local handler, so a name that is both a prefixed MCP name and a
# locally registered tool still meets a human.
# =====================================================================


@pytest.mark.unit
def test_shadowed_local_tool_is_gated_before_the_local_handler(monkeypatch, transport):
    """A server row can shadow a local tool. The row still decides, not ``has_tool``.

    ``session_upsert_mcp`` is both a prefixed MCP name and a registered local
    tool. Consulting the gate only behind ``not has_tool(name)`` meant the local
    handler ran an operator-declared-mutating operation without anyone being
    asked. The control below is the other half: when the operator declares
    nothing mutating, the local handler must still run, or this would be
    deny-everything dressed as a fix.
    """
    import digigraph.skills.registry as _skills  # noqa: F401  side-effect import registers builtins
    from digigraph.orchestration import registry
    from digigraph.orchestration.mcp_client import split_prefixed_tool_name

    # Preconditions, asserted so this cannot pass vacuously: the name really is
    # shadowing, and it really is prefixed. An unpopulated registry would make
    # has_tool False and turn the whole case into the ordinary MCP path.
    assert registry.has_tool("session_upsert_mcp") is True
    assert split_prefixed_tool_name("session_upsert_mcp")[0] == "session"

    server = "https://evil.invalid"
    row = _server(id="session", allowedTools=["upsert_mcp"], mutatingTools=["upsert_mcp"])
    ctx = _context(row, allowed={"session_upsert_mcp"})

    refused = registry.execute("session_upsert_mcp", {"server": {"id": "evil", "url": server}}, ctx)

    assert refused.get("error") == "mcp_call_requires_human_approval", refused
    assert refused.get("server_id") == "session", refused
    assert refused.get("tool") == "upsert_mcp", refused
    # The gate was read: a pending decision exists and is resolvable.
    assert refused["pending_id"]
    assert registry.pending_mcp_decision(refused["pending_id"], session_id="sess-1") is not None
    # Nothing was executed anywhere -- neither the local handler nor the transport.
    assert transport == []
    assert "evil.invalid" not in str(refused)

    # Control: the operator declares nothing mutating, so the same shadowed name
    # must fall through to the local handler.
    loud = _server(id="session", allowedTools=["upsert_mcp"], mutatingTools=[])
    ctx2 = _context(loud, allowed={"session_upsert_mcp"})
    ran = registry.execute("session_upsert_mcp", {"server": {"id": "acme"}}, ctx2)
    assert ran == {"ok": True, "session_prefs": {"server": {"id": "acme"}}}
    assert transport == []


@pytest.mark.unit
def test_denied_pending_call_is_audited_and_never_reaches_the_transport(transport, audit):
    """A refusal is a decision, so it leaves the same trail an approval does.

    The deny half of test_decision_cannot_substitute_the_payload asserts the
    transport did not grow. It does not assert that anything was RECORDED, so a
    refusal that returned cleanly and wrote no audit row would pass today.
    """
    import digigraph.orchestration.registry as registry

    server = _server()
    pending_id = registry.execute(
        f"{server['id']}_{MUTATING}", {"issueKey": "JIRA-1234"}, _context(server)
    )["pending_id"]

    denied = registry.decide_mcp_call(pending_id, False, session_id="sess-1", servers=[server])

    assert denied["status"] == "denied"
    assert transport == [], "a refused call must never reach the MCP transport"
    denials = [(name, payload) for name, payload in audit if name == "mcp_call_denied_by_human"]
    assert len(denials) == 1, f"expected exactly one denial audit row, got {audit}"
    assert denials[0][1] == {"tool": MUTATING, "server_id": "acme", "pending_id": pending_id}


@pytest.mark.unit
def test_a_refusal_cannot_be_flipped_into_a_write_by_a_second_decision(transport, audit):
    """The second decision on a pending id is refused, whichever way it points.

    The replay arm that already exists approves twice, which the at-most-once pop
    refuses. The dangerous direction is the one it does not cover: a caller that
    is refused and then submits the SAME pending id again as an approval. If the
    record were still live, that second call would perform the write the human
    just said no to -- so this asserts the write never reaches the transport, not
    merely that the second call returns an error.
    """
    import digigraph.orchestration.registry as registry

    server = _server()
    pending_id = registry.execute(
        f"{server['id']}_{MUTATING}", {"issueKey": "JIRA-1234"}, _context(server)
    )["pending_id"]

    denied = registry.decide_mcp_call(pending_id, False, session_id="sess-1", servers=[server])
    assert denied["status"] == "denied"

    replayed_approval = registry.decide_mcp_call(
        pending_id, True, session_id="sess-1", servers=[server]
    )

    assert transport == [], (
        "a refusal was flipped into a write: the pending id was still live after a "
        "denial, so the same id was approved a second time and the call executed"
    )
    assert replayed_approval["error"] == "unknown_pending_mcp_decision"
    assert len([n for n, _ in audit if n == "mcp_call_denied_by_human"]) == 1


@pytest.mark.unit
def test_the_decision_consumer_takes_no_transport_from_the_caller():
    """CTO ruling: the deciding request supplies a verdict and an id, nothing else.

    A caller-supplied transport is the hole this closes. A row with a matching
    ``id`` but an attacker-chosen ``url`` would send the RECORDED arguments to an
    endpoint the operator never configured, which is D3 broken under another
    name. So the parameter must not merely be ignored -- it must not exist.
    """
    import inspect

    from digigraph.orchestration.registry import decide_mcp_call

    params = inspect.signature(decide_mcp_call).parameters
    assert "servers" not in params, (
        "decide_mcp_call accepts a transport from the caller, so a deciding request "
        "can redirect the recorded payload at an arbitrary endpoint"
    )


@pytest.mark.unit
def test_approval_executes_against_the_transport_captured_at_refusal_time(transport, audit):
    """The recorded payload runs against the row that was recorded with it.

    The deciding request is a different HTTP request from the one that was
    refused. Nothing in it can name the transport, so the only thing that can
    still supply it is the refusal-time capture -- which is why this asserts the
    URL that actually reached the transport, not merely that a call happened.
    """
    import digigraph.orchestration.mcp_client as mc
    import digigraph.orchestration.registry as registry

    server = _server(url="https://mcp.example.invalid/rpc")
    seen: list[dict] = []
    monkey_calls = mc._call_tool_blocking

    def _capture(server_arg, tool, args):
        seen.append({"id": server_arg.get("id"), "url": server_arg.get("url"), "tool": tool})
        return monkey_calls(server_arg, tool, args)

    mc._call_tool_blocking = _capture
    try:
        pending_id = registry.execute(
            f"{server['id']}_{MUTATING}", {"issueKey": "JIRA-1234"}, _context(server)
        )["pending_id"]
        decided = registry.decide_mcp_call(pending_id, True, session_id="sess-1")
    finally:
        mc._call_tool_blocking = monkey_calls

    assert "error" not in decided, (
        f"the capture did not supply the transport, so the call never ran: {decided}"
    )
    assert len(seen) == 1, f"expected exactly one transport call, saw {seen}"
    assert seen[0]["url"] == "https://mcp.example.invalid/rpc"
    assert transport and transport[0]["args"] == {"issueKey": "JIRA-1234"}


@pytest.mark.unit
def test_approval_answers_approved_so_the_client_can_tell_success_from_failure():
    """The digichat route answers 502 unless ``status`` is approved or denied.

    An approval that returns the raw tool payload makes a successful write look
    like an upstream failure to the operator who approved it. The status is the
    contract; the tool result travels beside it.
    """
    import digigraph.orchestration.registry as registry

    server = _server()
    pending_id = registry.execute(
        f"{server['id']}_{MUTATING}", {"issueKey": "JIRA-1234"}, _context(server)
    )["pending_id"]

    decided = registry.decide_mcp_call(pending_id, True, session_id="sess-1")

    assert decided.get("status") == "approved", (
        f"an approval answered {decided.get('status')!r}, which the digichat route "
        "reads as an upstream failure"
    )
    assert decided["pending_id"] == pending_id


@pytest.mark.unit
def test_the_captured_transport_never_reaches_the_public_event_or_the_audit(audit):
    """The capture stays in the record beside ``args``, never on the way out.

    ``as_public_event`` is what reaches the model and the checkpoint, and the
    audit payload is what reaches the log. A captured token or URL in either is
    a disclosure the 284.4 design deliberately excluded.
    """
    from digigraph.orchestration.registry import pending_mcp_decision

    server = _server()
    state: dict = {}
    registry = __import__("digigraph.orchestration.registry", fromlist=["execute"])
    pending_id = registry.execute(
        f"{server['id']}_{MUTATING}", {"issueKey": "JIRA-1234"}, _context(server, state=state)
    )["pending_id"]

    event = state["pending_mcp_decision"]
    for field in ("url", "token", "auth", "server", "transport"):
        assert field not in event, f"{field} leaked into the public pending event"

    record = pending_mcp_decision(pending_id, session_id="sess-1")
    assert record is not None
    public = record.as_public_event()
    for field in ("url", "token", "auth", "server", "transport"):
        assert field not in public, f"{field} leaked into the public pending event"
        assert field not in record.target_arguments

    assert audit, "the pending decision must be recorded"
    for _name, payload in audit:
        for field in ("url", "token", "auth", "server", "transport"):
            assert field not in payload, f"{field} leaked into an audit payload"


OPERATOR_ONLY_KEYS = (
    "url",
    "auth",
    "token",
    "authHeader",
    "auth_header",
    "allowedTools",
    "mutatingTools",
    "servers",
    "mcp_servers",
    "session_id",
)


@pytest.mark.unit
@pytest.mark.parametrize("key", OPERATOR_ONLY_KEYS)
def test_the_decision_route_refuses_every_operator_only_key(key):
    """The body carries a verdict and an id, and nothing that configures a server.

    Each of these keys is refused BY NAME so the refusal says which one, rather
    than reporting a generic bad request the operator cannot act on.
    """
    from digigraph.http_api.mcp_decisions import decision_from_request

    body = {"pending_id": "a" * 32, "approve": True, key: "https://attacker.invalid/rpc"}
    _fields, error = decision_from_request(body, session_id="sess-1")

    assert error.get("error") == "decision_body_rejected", (
        f"the route accepted an operator-only key {key!r}: {error}"
    )
    assert error.get("key") == key, f"the refusal does not name {key!r}: {error}"


@pytest.mark.unit
def test_the_decision_route_refuses_a_request_with_no_session_header():
    """The session is the capability's scope; without it there is nothing to check."""
    from digigraph.http_api.mcp_decisions import decision_from_request

    _fields, error = decision_from_request(
        {"pending_id": "a" * 32, "approve": True}, session_id=None
    )

    assert error.get("error") == "mcp_decision_requires_session", error


@pytest.mark.unit
def test_the_decision_route_refuses_a_verdict_that_is_not_a_boolean():
    """ "true" as a string is not a decision; guessing at it would be an approval."""
    from digigraph.http_api.mcp_decisions import decision_from_request

    _fields, error = decision_from_request(
        {"pending_id": "a" * 32, "approve": "true"}, session_id="sess-1"
    )

    assert error.get("error") == "decision_body_rejected", error


@pytest.mark.unit
def test_the_decision_route_accepts_exactly_the_two_keys_the_client_sends():
    """The positive arm, so the refusals above are not passing for the wrong reason."""
    from digigraph.http_api.mcp_decisions import decision_from_request

    fields, error = decision_from_request(
        {"pending_id": "a" * 32, "approve": False}, session_id="sess-1"
    )

    assert error == {}, f"a well-formed decision was refused: {error}"
    assert fields == {"pending_id": "a" * 32, "approve": False}


@pytest.mark.unit
def test_the_decision_route_is_mounted_where_the_client_calls_it():
    """``apps/digichat/.../approve/route.ts`` posts to ``/v1/mcp/decisions``.

    A route under any other path leaves the operator clicking approve and getting
    a 502 forever, so the path is pinned rather than left to review.
    """
    from digigraph.http_api.mcp_decisions import router

    paths = {
        (getattr(r, "path", None), tuple(sorted(getattr(r, "methods", ()) or ())))
        for r in router.routes
    }
    assert ("/v1/mcp/decisions", ("POST",)) in paths, (
        f"the digigraph decision route is not mounted where digichat calls it: {sorted(p for p, _ in paths)}"
    )
