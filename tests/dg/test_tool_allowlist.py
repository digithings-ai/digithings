"""Orchestrator tool allowlist: registry execute + get_tools, policy resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from digigraph.models import WorkflowRequest
from digigraph.orchestration import builtin  # noqa: F401 - triggers registration
from digigraph.orchestration.registry import ToolContext, execute, get_tools
from digigraph.project_config import DigiProjectConfig
from digigraph.tool_policy import (
    allowed_tool_names_for_workflow,
    frozen_from_state_list,
    require_tool_calls_for_workflow,
    state_list_from_frozen,
)


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
    tools = get_tools(["search", "project_rag"], ctx)
    names = []
    for t in tools:
        fn = t.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            names.append(fn["name"])
    assert "digisearch" in names
    assert "visualization_agent" not in names


@pytest.mark.unit
def test_get_tools_warns_on_unknown_skill_id(caplog: pytest.LogCaptureFixture) -> None:
    """An unregistered skill id (e.g. a stale `sitaas_rag` from before #2426's
    rename to `project_rag`) contributes zero tools silently -- get_tools()
    doesn't raise. Assert it at least logs, so a stale project config doesn't
    lose its whole toolset without a trace."""
    ctx = ToolContext(
        session_id="s",
        run_data_dir="/tmp",
        index_name="default",
        index_config={},
        state={},
    )
    with caplog.at_level("WARNING", logger="digigraph.orchestration.registry"):
        tools = get_tools(["not_a_real_skill_id"], ctx)
    assert tools == []
    assert any("not_a_real_skill_id" in r.message for r in caplog.records)


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
    assert state_list_from_frozen(frozenset()) == []


@pytest.mark.unit
def test_frozen_from_state_list_distinguishes_none_from_empty() -> None:
    """Empty allowlist is deny-all; missing allowlist is unrestricted.

    Regression: ``frozenset(raw) if raw else None`` treated ``[]`` as
    unrestricted and opened every tool despite the documented deny-all contract
    (WorkflowRequest.allowed_tools=[], ARCHITECTURE § tool allowlist).
    """
    assert frozen_from_state_list(None) is None
    assert frozen_from_state_list([]) == frozenset()
    assert frozen_from_state_list(["digisearch", "digivault"]) == frozenset(
        {"digisearch", "digivault"}
    )


@pytest.mark.unit
def test_empty_allowlist_round_trip_stays_deny_all() -> None:
    """Policy → state list → research deserialize must not reopen tools."""
    req = WorkflowRequest(prompt="hi", allowed_tools=[])
    frozen = allowed_tool_names_for_workflow(req)
    assert frozen == frozenset()
    serialized = state_list_from_frozen(frozen)
    assert serialized == []
    assert frozen_from_state_list(serialized) == frozenset()


@pytest.mark.unit
def test_execute_denies_all_tools_under_empty_allowlist() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        allowed_tool_names=frozenset(),
    )
    with patch("digigraph.audit.audit_log") as audit_mock:
        out = execute("digisearch", {"query": "x"}, ctx)
    audit_mock.assert_called_once()
    assert audit_mock.call_args[0][0] == "tool_denied"
    assert isinstance(out, dict)
    assert out.get("error") == "tool_not_allowed"


@pytest.mark.unit
def test_require_tool_calls_project_true_wins_even_if_request_false() -> None:
    """The floor: a request-level False cannot lower a project-mandated True."""
    cfg = DigiProjectConfig({"agents": {"require_tool_calls": True}})
    req = WorkflowRequest(prompt="hi", require_tool_calls=False)
    assert require_tool_calls_for_workflow(req, cfg=cfg) is True


@pytest.mark.unit
def test_require_tool_calls_request_true_raises_it_when_project_unset() -> None:
    cfg = DigiProjectConfig({"agents": {}})
    req = WorkflowRequest(prompt="hi", require_tool_calls=True)
    assert require_tool_calls_for_workflow(req, cfg=cfg) is True


@pytest.mark.unit
def test_require_tool_calls_defaults_false_when_nothing_set() -> None:
    cfg = DigiProjectConfig({"agents": {}})
    req = WorkflowRequest(prompt="hi")
    assert require_tool_calls_for_workflow(req, cfg=cfg) is False


@pytest.mark.unit
def test_require_tool_calls_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_REQUIRE_TOOL_CALLS", "1")
    cfg = DigiProjectConfig({"agents": {}})
    req = WorkflowRequest(prompt="hi")
    assert require_tool_calls_for_workflow(req, cfg=cfg) is True


@pytest.mark.unit
def test_require_tool_calls_env_true_wins_even_if_request_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env floor mirrors project floor: request-level False cannot opt out of
    DIGI_REQUIRE_TOOL_CALLS. Project=True+request=False is covered above; this
    pins the env half of the same OR-floor contract."""
    monkeypatch.setenv("DIGI_REQUIRE_TOOL_CALLS", "1")
    cfg = DigiProjectConfig({"agents": {}})
    req = WorkflowRequest(prompt="hi", require_tool_calls=False)
    assert require_tool_calls_for_workflow(req, cfg=cfg) is True


@pytest.mark.unit
def test_require_tool_calls_env_false_does_not_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_REQUIRE_TOOL_CALLS", raising=False)
    cfg = DigiProjectConfig({"agents": {}})
    req = WorkflowRequest(prompt="hi", require_tool_calls=False)
    assert require_tool_calls_for_workflow(req, cfg=cfg) is False


@pytest.mark.unit
def test_require_tool_calls_loads_cfg_when_none_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors allowed_tool_names_for_workflow's cfg=None -> DigiProjectConfig.load() fallback."""
    monkeypatch.setattr(
        "digigraph.tool_policy.DigiProjectConfig.load",
        staticmethod(lambda: DigiProjectConfig({"agents": {"require_tool_calls": True}})),
    )
    req = WorkflowRequest(prompt="hi")
    assert require_tool_calls_for_workflow(req) is True


@pytest.mark.unit
def test_workflow_state_declares_require_tool_calls() -> None:
    """LangGraph drops undeclared TypedDict keys — see #2097."""
    from digigraph.graph.state import WorkflowState

    assert "require_tool_calls" in WorkflowState.__annotations__


@pytest.mark.unit
def test_initial_graph_state_carries_require_tool_calls_true() -> None:
    from digigraph.workflow import _initial_graph_state

    cfg = DigiProjectConfig({"agents": {"require_tool_calls": True}})
    with patch("digigraph.workflow.DigiProjectConfig.load", return_value=cfg):
        state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-rtc-1")
    assert state["require_tool_calls"] is True


@pytest.mark.unit
def test_initial_graph_state_defaults_require_tool_calls_false() -> None:
    from digigraph.workflow import _initial_graph_state

    cfg = DigiProjectConfig({"agents": {}})
    with patch("digigraph.workflow.DigiProjectConfig.load", return_value=cfg):
        state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-rtc-2")
    assert state["require_tool_calls"] is False


@pytest.mark.unit
def test_langgraph_preserves_require_tool_calls_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip require_tool_calls."""
    from digigraph.graph.state import WorkflowState
    from langgraph.graph import END, START, StateGraph

    seen: dict[str, bool | None] = {}

    def _capture(state: WorkflowState) -> dict:
        seen["require_tool_calls"] = state.get("require_tool_calls")
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile()
    graph.invoke({"prompt": "x", "require_tool_calls": True})
    assert seen["require_tool_calls"] is True
