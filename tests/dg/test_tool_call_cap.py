"""Hard tool-call cap: ``X-Digi-Max-Tool-Calls`` → state → digillm's tool loop.

The chat-side guardrail notice only *asks* the model to stop; digigraph runs the
actual tool loop inside digillm, bounded by rounds (``max_tool_rounds``) and
never by calls — one round can issue several parallel calls, so 5 rounds is not
5 calls. These tests pin the header parse and every hop from the header to
``run_tools(max_tool_calls=...)``, including the continuation calls and the
nested research-agent call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from digigraph.graph.state import WorkflowState
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit


def _request(headers: dict[str, str] | None = None) -> SimpleNamespace:
    """Minimal stand-in for a Starlette Request (what ``_digi_fields_from_request`` reads)."""
    return SimpleNamespace(
        state=SimpleNamespace(digi_auth=None, digi_bearer=None),
        headers=headers or {},
    )


def _header_updates(value: str | None) -> dict[str, object]:
    from digigraph.http_api.context import _digi_fields_from_request

    headers = {} if value is None else {"X-Digi-Max-Tool-Calls": value}
    return _digi_fields_from_request(_request(headers))


@pytest.mark.parametrize("raw", ["1", "5", "100"])
def test_valid_header_parses_to_an_int(raw: str) -> None:
    assert _header_updates(raw)["max_tool_calls"] == int(raw)


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "101", "abc", "5.5", "1e3"])
def test_absent_or_out_of_range_header_is_ignored(raw: str | None) -> None:
    """Only an integer in 1..100 is a cap; anything else leaves behaviour unchanged."""
    assert _header_updates(raw)["max_tool_calls"] is None


def test_workflow_state_declares_max_tool_calls() -> None:
    assert "max_tool_calls" in WorkflowState.__annotations__


def test_initial_graph_state_carries_max_tool_calls() -> None:
    state = _initial_graph_state(WorkflowRequest(prompt="hi", max_tool_calls=5), "wf-cap")
    assert state["max_tool_calls"] == 5
    cleared = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-cap")
    # Unconditional, like effort/web_search_provider: a prior turn's cap must not stick
    # on the checkpoint.
    assert "max_tool_calls" in cleared
    assert cleared["max_tool_calls"] is None


def _patch_research_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )


@pytest.mark.parametrize("cap", [3, None])
def test_research_node_forwards_the_cap_to_every_run_tools_call(
    monkeypatch: pytest.MonkeyPatch, cap: int | None
) -> None:
    """The main loop and each continuation call must both carry the cap."""
    from digigraph.graph.research import research_node

    _patch_research_settings(monkeypatch)
    seen: list[object] = []

    def fake_run_tools(**kwargs: object) -> str:
        seen.append(kwargs.get("max_tool_calls", "missing"))
        # Ends on a colon → `answer_looks_unfinished` stays True even after the loop
        # concatenates passes, so the full continuation budget runs and this exercises
        # the continuation call site too, not just the main one.
        return "working:"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "hi", "max_tool_calls": cap})

    assert len(seen) == 3, "one main call plus two continuations"
    assert seen == [cap, cap, cap]


def test_llm_client_run_tools_forwards_the_cap_to_digillm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import digigraph.llm_client as llm_client

    captured: dict[str, object] = {}

    def fake_digillm_run_tools(*_args: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(llm_client, "_digillm_run_tools", fake_digillm_run_tools)
    llm_client.run_tools(
        "deepseek/deepseek-v4.1-flash-1017",
        [{"role": "user", "content": "hi"}],
        [],
        lambda *_: "",
        on_tool_step=lambda *_: None,
        max_tool_calls=4,
    )
    assert captured["max_tool_calls"] == 4


def test_research_agent_tool_path_forwards_the_cap_to_the_nested_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nested ``run_research_agent`` tool path must pass the cap down too."""
    import digigraph.graph.research_agent as research_agent
    from pydantic import BaseModel

    class _Out(BaseModel):
        ok: bool

    captured: dict[str, object] = {}

    def fake_run_tools(*_args: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return '{"ok": true}'

    monkeypatch.setattr(research_agent, "run_tools", fake_run_tools)
    out = research_agent.run_research_agent(
        skill_text="s",
        phase_inputs={},
        shared_context={},
        output_model=_Out,
        model="deepseek/deepseek-v4.1-flash-1017",
        tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
        execute_tool=lambda *_a: "result",
        max_tool_calls=4,
    )

    assert out.ok is True
    assert captured["max_tool_calls"] == 4


def test_one_budget_covers_the_main_loop_and_every_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5-call cap is 5 calls for the *turn*, not 5 per ``run_tools`` call.

    The cap is forwarded per invocation, so without a shared counter the main
    loop plus two continuations could spend 15. Count `tool_call` events — one
    per executed call — and pass only what is left.
    """
    from digigraph.graph.research import research_node

    _patch_research_settings(monkeypatch)
    granted: list[object] = []
    executed = 0

    def fake_run_tools(**kwargs: object) -> str:
        nonlocal executed
        allowance = kwargs.get("max_tool_calls", "missing")
        granted.append(allowance)
        step = kwargs["on_tool_step"]
        # Four calls offered per invocation, but never more than the allowance.
        offer = 4 if allowance is None else min(4, int(allowance))
        for index in range(offer):
            step("tool_call", {"name": f"tool_{index}"})
            executed += 1
        # Ends on a colon → the turn is unfinished, so continuations run.
        return "working:"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "hi", "max_tool_calls": 5})

    assert granted == [5, 1, 0], f"each call must get the remaining allowance: {granted}"
    assert executed == 5, f"the turn must not execute more than its cap: {executed}"


def test_zero_remaining_passes_zero_and_that_call_executes_no_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the budget is spent the continuation gets 0 and wraps up tool-free."""
    from digigraph.graph.research import research_node

    _patch_research_settings(monkeypatch)
    granted: list[object] = []
    executed: list[str] = []

    def fake_run_tools(**kwargs: object) -> str:
        allowance = kwargs.get("max_tool_calls", "missing")
        granted.append(allowance)
        step = kwargs["on_tool_step"]
        offer = 2 if allowance is None else min(2, int(allowance))
        for index in range(offer):
            step("tool_call", {"name": f"tool_{index}"})
            executed.append(f"tool_{index}")
        # The spent-budget call has no tools left and answers instead.
        return "working:" if allowance else "final answer"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    out = research_node({"prompt": "hi", "max_tool_calls": 2})

    assert granted[:2] == [2, 0], f"0 must be passed once the cap is spent: {granted}"
    assert executed == ["tool_0", "tool_1"], f"no call may run after the cap: {executed}"
    assert str(out["research_response"]).endswith("final answer")
