"""Orchestrator tool allowlist: registry execute + get_tools, policy resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.models import WorkflowRequest
from digigraph.orchestration.registry import ToolContext, execute, get_tools
from digigraph.project_config import DigiProjectConfig
from digigraph.tool_policy import allowed_tool_names_for_workflow, state_list_from_frozen


@pytest.mark.unit
def test_execute_denies_when_tool_not_in_allowlist() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        allowed_tool_names=frozenset({"digisearch"}),
        request_id="req-audit-test",
        workflow_id="wf-audit-test",
    )
    with patch("digigraph.audit.audit_log") as audit_mock:
        out = execute("visualization_agent", {}, ctx)
    audit_mock.assert_called_once()
    assert audit_mock.call_args[0][0] == "tool_denied"
    payload = audit_mock.call_args[1]["payload"]
    assert payload["tool"] == "visualization_agent"
    assert payload["request_id"] == "req-audit-test"
    assert payload["workflow_id"] == "wf-audit-test"
    assert isinstance(out, dict)
    assert out.get("error") == "tool_not_allowed"
    assert out.get("tool") == "visualization_agent"


@pytest.mark.unit
def test_execute_allows_when_unrestricted() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        allowed_tool_names=None,
    )
    with patch("digigraph.orchestration.builtin.run_visualization_agent") as m:
        m.return_value = {"content": "ok"}
        out = execute(
            "visualization_agent",
            {"task": "x", "dataset_ref": "d"},
            ctx,
        )
    assert isinstance(out, dict)


@pytest.mark.unit
def test_get_tools_filters_by_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://example.invalid:8002")
    ctx = ToolContext(
        session_id="s",
        run_data_dir="/tmp",
        index_name="default",
        index_config={},
        state={},
        allowed_tool_names=frozenset({"digisearch"}),
    )
    tools = get_tools(["search", "sitaas_rag"], ctx)
    names = []
    for t in tools:
        fn = t.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            names.append(fn["name"])
    assert "digisearch" in names
    assert "visualization_agent" not in names


@pytest.mark.unit
def test_policy_request_override_wins() -> None:
    req = WorkflowRequest(prompt="hi", allowed_tools=["todo"])
    fs = allowed_tool_names_for_workflow(req, cfg=MagicMock())
    assert fs == frozenset({"todo"})


@pytest.mark.unit
def test_policy_empty_request_list_means_no_tools() -> None:
    req = WorkflowRequest(prompt="hi", allowed_tools=[])
    fs = allowed_tool_names_for_workflow(req)
    assert fs == frozenset()


@pytest.mark.unit
def test_policy_project_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ALLOWED_TOOLS", raising=False)
    cfg = DigiProjectConfig({"agents": {"allowed_tools": ["a", "b"]}})
    req = WorkflowRequest(prompt="hi")
    fs = allowed_tool_names_for_workflow(req, cfg=cfg)
    assert fs == frozenset({"a", "b"})


@pytest.mark.unit
def test_policy_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_ALLOWED_TOOLS", "foo, bar")
    req = WorkflowRequest(prompt="hi")
    fs = allowed_tool_names_for_workflow(req, cfg=DigiProjectConfig({}))
    assert fs == frozenset({"foo", "bar"})


@pytest.mark.unit
def test_state_list_from_frozen() -> None:
    assert state_list_from_frozen(None) is None
    assert state_list_from_frozen(frozenset({"b", "a"})) == ["a", "b"]
