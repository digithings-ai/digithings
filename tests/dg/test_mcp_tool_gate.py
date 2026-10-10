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
    result = registry.execute(
        "acme_addCommentToJiraIssue", {"issueKey": "JIRA-1234"}, ctx
    )

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

    assert transport == [
        {"server_id": "acme", "tool": READ_ONLY, "args": {"jql": "project = DIG"}}
    ]
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


@pytest.mark.unit
def test_decision_cannot_substitute_the_payload(transport, audit):
    """The decision carries approve-or-deny only; the recorded call is what runs."""
    from digigraph.orchestration import registry

    server = _server()
    ctx = _context(server, session_id="sess-1")
    pending_id = registry.execute(
        "acme_addCommentToJiraIssue", {"issueKey": "JIRA-1234"}, ctx
    )["pending_id"]

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
    wrong = registry.decide_mcp_call(
        pending_id, True, session_id="other-session", servers=[server]
    )
    assert wrong["error"] == "unknown_pending_mcp_decision"
    assert transport == []

    approved = registry.decide_mcp_call(pending_id, True, session_id="sess-1", servers=[server])
    assert approved["ok"] is True
    assert transport == [
        {"server_id": "acme", "tool": MUTATING, "args": {"issueKey": "JIRA-1234"}}
    ]

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
    for meta in ("acme_executeWrite", "acme_discover", "acme_executeRead", "acme_executeDestructive"):
        with pytest.raises(registry.MetaToolConfirmationRefused):
            registry.execute(meta, {"anything": 1}, _context(server))
    assert transport == []