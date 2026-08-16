# digigraph Tool-Calling Requirement Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a digigraph deployment (e.g. OCC, which depends on multi-round tool calls for retrieval) mandate `tool_choice="required"` on every tool-calling turn via `agents.require_tool_calls: true` in `digiproject.yaml`, resolved as a **floor** — a request/header can raise the requirement, never lower one the deployment already set.

**Architecture:** A new boolean flows through the exact same pipeline `agents.allowed_tools` already uses (project config → resolver → `WorkflowState` → `research_node` → `run_tools()`), except the resolver combines project/env/request with OR (floor) instead of most-specific-wins (full override) — full override would let any external caller reaching `/v1/chat/completions` (an Open WebUI-compatible endpoint, not digichat-exclusive) send one header and defeat an operator's mandatory tool policy.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic v2, pytest.

## Global Constraints

- Ruff-compliant, line length 100 (`ruff check . && ruff format .`).
- Pydantic v2 strict typing; every new field gets a `Field(..., description=...)`.
- Tests use the existing `@pytest.mark.unit` marker; live at `tests/dg/` (repo-root-relative, per `digigraph/pyproject.toml`'s `testpaths = ["../tests/dg"]`), not inside `digigraph/`.
- This is `component:digigraph` — two-hop branching: `task/201-tool-calling-gate` → `module/digigraph` → `develop`. Before branching, check staleness: `git fetch origin && git rev-list --count origin/module/digigraph..origin/develop` — sync via a `chore/sync-*` PR into `module/digigraph` first if non-zero.
- `llm_auth.py` is not touched by this plan (that's the other plan), but `project_config.py`/`models.py`/`server.py` changes here are still network-exposure-adjacent (a new externally-visible field/header on `/v1/chat/completions`) — this lands under CLAUDE.md's human-gate rule; plan for explicit review before merge, not just a passing `make score`.
- Every commit message stays scoped to what that commit's step actually changed — no bundling.
- Design reference: `docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md`, sections "Tool-calling requirement gate" (Decisions, Data flow, Security considerations). That spec is scoped to the sibling digichat branch (`task/2347-digichat-byok-catalog-live-models`, PR #2357) and doesn't exist in this digigraph-scoped branch's tree — not linked here to avoid a broken relative path.

---

### Task 1: digillm — `run_tools()` accepts a `tool_choice` parameter

**Files:**
- Modify: `digillm/src/digillm/client.py:1969-1981` (signature), `:2041-2049` and `:2050-2059` (the two hardcoded `tool_choice="auto"` inside the nested `_produce_turn` closure)
- Test: `digillm/tests/test_digillm.py`

**Interfaces:**
- Consumes: nothing new (closure captures the new parameter directly — `_produce_turn` is defined *inside* `run_tools`, so no signature change needed on `_produce_turn` itself).
- Produces: `run_tools(..., tool_choice: str | ToolArguments = "auto")` — callers (digigraph's `llm_client.run_tools`, Task 2) pass `tool_choice="required"` to force every turn.

- [ ] **Step 1: Write the failing tests**

Add to `digillm/tests/test_digillm.py`, right after `test_chat_completion_with_tools_loop` (near line 671):

```python
def test_run_tools_forwards_tool_choice_required() -> None:
    """run_tools(tool_choice='required') reaches the underlying completions call."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("final answer")

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool=lambda n, a: "unused",
            tool_choice="required",
        )
    assert out == "final answer"
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == "required"


def test_run_tools_defaults_tool_choice_to_auto() -> None:
    """Unchanged default behavior when tool_choice is not passed."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("final answer")

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool=lambda n, a: "unused",
        )
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd digillm && python -m pytest tests/test_digillm.py -k test_run_tools_forwards_tool_choice_required -v`
Expected: FAIL — `TypeError: run_tools() got an unexpected keyword argument 'tool_choice'`

- [ ] **Step 3: Implement — add the parameter and thread it through the closure**

In `digillm/src/digillm/client.py`, change the `run_tools` signature (currently lines 1969-1981):

```python
def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    tool_choice: str | ToolArguments = "auto",
    on_tool_step: Callable[[str, Any], None] | None = None,
    parallel_safe_tools: set[str] | None = None,
    stream_deltas: bool = False,
    search_parameters: dict[str, Any] | None = None,
) -> str:
```

Add one line to the docstring's `Args:` block, right after the `max_tool_rounds` line:

```
        tool_choice:  Passed to every turn's completion call ("auto" default;
            "required" forces a tool call every round). See :func:`completion`.
```

Then change both hardcoded literals inside the nested `_produce_turn` (the two `tool_choice="auto",` lines) to reference the new outer parameter — since `_produce_turn` is a closure defined inside `run_tools`, no other signature changes anywhere in this function:

```python
            return _stream_completion_one_turn(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice=tool_choice,
                on_content_delta=_on_content,
                on_reasoning_delta=_on_reasoning,
            )
        return _message_from_response(
            completion(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice=tool_choice,
                search_parameters=search_parameters if include_search else None,
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd digillm && python -m pytest tests/test_digillm.py -k "test_run_tools_forwards_tool_choice_required or test_run_tools_defaults_tool_choice_to_auto" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full digillm suite to confirm no regression**

Run: `cd digillm && python -m pytest tests -q`
Expected: all existing tests still pass (57+ before this change, +2 now)

- [ ] **Step 6: Lint**

Run: `ruff check digillm/src digillm/tests && ruff format --check digillm/src digillm/tests`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add digillm/src/digillm/client.py digillm/tests/test_digillm.py
git commit -m "feat(digillm): run_tools accepts tool_choice, default unchanged"
```

---

### Task 2: digigraph — `llm_client.run_tools()` wrapper forwards `tool_choice`

**Files:**
- Modify: `digigraph/src/digigraph/llm_client.py:191-226`
- Test: `tests/dg/test_llm_client.py`

**Interfaces:**
- Consumes: `digillm.run_tools(..., tool_choice=...)` from Task 1.
- Produces: `digigraph.llm_client.run_tools(..., tool_choice: str = "auto")` — this is the name `graph/research.py` (Task 8) actually imports and calls; without this task, Task 8's call raises `TypeError` immediately.

- [ ] **Step 1: Write the failing test**

Add to `tests/dg/test_llm_client.py`, inside the existing `class TestRunTools:` (after `test_no_callback_is_non_streaming_with_parallel_safe`, near line 163):

```python
    def test_forwards_tool_choice_required(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch("digigraph.orchestration.registry.list_tool_names", return_value=[]),
            patch.object(llm_client, "_digillm_run_tools", return_value="done") as rt,
        ):
            llm_client.run_tools(
                "model",
                [{"role": "user", "content": "go"}],
                [],
                execute_tool=lambda n, a: "ok",
                tool_choice="required",
            )
        assert rt.call_args[1]["tool_choice"] == "required"

    def test_defaults_tool_choice_to_auto(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch("digigraph.orchestration.registry.list_tool_names", return_value=[]),
            patch.object(llm_client, "_digillm_run_tools", return_value="done") as rt,
        ):
            llm_client.run_tools(
                "model", [{"role": "user", "content": "go"}], [], execute_tool=lambda n, a: "ok"
            )
        assert rt.call_args[1]["tool_choice"] == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/digithings && python -m pytest tests/dg/test_llm_client.py -k test_forwards_tool_choice_required -v`
Expected: FAIL — `TypeError: run_tools() got an unexpected keyword argument 'tool_choice'`

- [ ] **Step 3: Implement**

In `digigraph/src/digigraph/llm_client.py`, change the `run_tools` wrapper (currently lines 191-226):

```python
def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    tool_choice: str = "auto",
    on_tool_step: Callable[[str, Any], None] | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> str:
    """Run digillm's agentic tool-calling loop with digigraph's parallel-safe set + streaming.

    Streams each assistant turn (``stream_deltas``) whenever ``on_tool_step`` is
    supplied, so the callback also receives ``("content", delta)`` / ``("reasoning",
    delta)`` alongside the tool-call/result steps. ``search_parameters`` forwards an
    xAI Live Search descriptor (first tool round only). ``tool_choice`` forwards to
    every turn ("auto" default; "required" forces a tool call every round — see
    :func:`digigraph.tool_policy.require_tool_calls_for_workflow`). Returns the
    model's final answer.
    """
    with _logical_call_scope(
        CallPurpose.TOOL_SELECTION,
        NoArtifactReason.TOOL_DISPATCH,
        follow_up_purpose=CallPurpose.TOOL_FOLLOW_UP,
        follow_up_no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
    ):
        return _digillm_run_tools(
            resolve_request_model(model),
            messages,
            tools,
            execute_tool,
            temperature=temperature,
            max_tool_rounds=max_tool_rounds,
            tool_choice=tool_choice,
            on_tool_step=on_tool_step,
            parallel_safe_tools=_parallel_safe_tools(),
            stream_deltas=on_tool_step is not None,
            search_parameters=search_parameters,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dg/test_llm_client.py -k "test_forwards_tool_choice_required or test_defaults_tool_choice_to_auto" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full llm_client test file**

Run: `python -m pytest tests/dg/test_llm_client.py -q`
Expected: all pass, no regression

- [ ] **Step 6: Commit**

```bash
git add digigraph/src/digigraph/llm_client.py tests/dg/test_llm_client.py
git commit -m "feat(digigraph): llm_client.run_tools forwards tool_choice to digillm"
```

---

### Task 3: digigraph — `DigiProjectConfig.get_require_tool_calls()`

**Files:**
- Modify: `digigraph/src/digigraph/project_config.py` (add getter beside `get_allowed_tools`, currently at L407-412)
- Test: `tests/dg/test_project_config.py`

**Interfaces:**
- Consumes: `self.agents` dict already available on `DigiProjectConfig` (same as `get_allowed_tools`/`get_planning_mode`).
- Produces: `DigiProjectConfig.get_require_tool_calls() -> bool` — consumed by Task 5's resolver.

- [ ] **Step 1: Write the failing test**

Add to `tests/dg/test_project_config.py`, right after `test_digi_project_config_allowed_tools` (near line 83):

```python
@pytest.mark.unit
def test_digi_project_config_require_tool_calls_true() -> None:
    cfg = DigiProjectConfig({"agents": {"require_tool_calls": True}})
    assert cfg.get_require_tool_calls() is True


@pytest.mark.unit
def test_digi_project_config_require_tool_calls_defaults_false() -> None:
    cfg = DigiProjectConfig({"agents": {}})
    assert cfg.get_require_tool_calls() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/dg/test_project_config.py -k require_tool_calls -v`
Expected: FAIL — `AttributeError: 'DigiProjectConfig' object has no attribute 'get_require_tool_calls'`

- [ ] **Step 3: Implement**

In `digigraph/src/digigraph/project_config.py`, add right after `get_planning_mode` (currently lines 403-405, immediately before `get_allowed_tools`):

```python
    def get_require_tool_calls(self) -> bool:
        """Whether this deployment's tool loop must force tool_choice='required'. From agents.require_tool_calls."""
        return bool(self.agents.get("require_tool_calls"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/dg/test_project_config.py -k require_tool_calls -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/project_config.py tests/dg/test_project_config.py
git commit -m "feat(digigraph): DigiProjectConfig.get_require_tool_calls getter"
```

---

### Task 4: digigraph — `require_tool_calls` field on `WorkflowRequest` and `ChatCompletionRequest`

**Files:**
- Modify: `digigraph/src/digigraph/models.py` (both classes have `model_config = ConfigDict(extra="forbid")` — an undeclared field raises on construction, so this task must land before Tasks 6-7 pass any such kwarg)
- Test: `tests/dg/test_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WorkflowRequest(require_tool_calls: bool | None = None)`, `ChatCompletionRequest(require_tool_calls: bool | None = None)` — consumed by Task 5 (resolver reads `req.require_tool_calls`) and Task 7 (server.py constructs both with this field).

- [ ] **Step 1: Write the failing test**

Add to `tests/dg/test_models.py`:

```python
def test_workflow_request_accepts_require_tool_calls() -> None:
    req = WorkflowRequest(prompt="hi", require_tool_calls=True)
    assert req.require_tool_calls is True


def test_workflow_request_require_tool_calls_defaults_to_none() -> None:
    req = WorkflowRequest(prompt="hi")
    assert req.require_tool_calls is None


def test_chat_completion_request_accepts_require_tool_calls() -> None:
    req = ChatCompletionRequest(messages=[], require_tool_calls=False)
    assert req.require_tool_calls is False
```

(Check the top of `tests/dg/test_models.py` for how `WorkflowRequest`/`ChatCompletionRequest` are already imported — reuse the same import line; do not add a second one.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/dg/test_models.py -k require_tool_calls -v`
Expected: FAIL — `pydantic_core._pydantic_core.ValidationError: ... Extra inputs are not permitted [type=extra_forbidden ...]`

- [ ] **Step 3: Implement**

In `digigraph/src/digigraph/models.py`, add to `ChatCompletionRequest` right after `allowed_tools` (currently lines 66-69):

```python
    require_tool_calls: bool | None = Field(
        None,
        description=(
            "Optional per-request signal that this completion needs tool_choice='required'. "
            "Also accepted via X-Require-Tool-Calls header. Combined with project "
            "agents.require_tool_calls and env DIGI_REQUIRE_TOOL_CALLS as a FLOOR (any true "
            "value wins) — unlike allowed_tools, this can only raise the requirement, never "
            "lower one the deployment already mandates."
        ),
    )
```

And to `WorkflowRequest` right after `allowed_tools` (currently lines 88-94):

```python
    require_tool_calls: bool | None = Field(
        None,
        description=(
            "Optional per-request signal that this workflow needs tool_choice='required'. "
            "Combined with project agents.require_tool_calls and env DIGI_REQUIRE_TOOL_CALLS "
            "as a FLOOR (any true value wins) — unlike allowed_tools, this can only raise the "
            "requirement, never lower one the deployment already mandates."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/dg/test_models.py -k require_tool_calls -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full models test file**

Run: `python -m pytest tests/dg/test_models.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add digigraph/src/digigraph/models.py tests/dg/test_models.py
git commit -m "feat(digigraph): require_tool_calls field on WorkflowRequest/ChatCompletionRequest"
```

---

### Task 5: digigraph — `tool_policy.require_tool_calls_for_workflow()` floor resolver

**Files:**
- Modify: `digigraph/src/digigraph/tool_policy.py`
- Test: `tests/dg/test_tool_allowlist.py`

**Interfaces:**
- Consumes: `WorkflowRequest.require_tool_calls` (Task 4), `DigiProjectConfig.get_require_tool_calls()` (Task 3), `digigraph.policy._env_truthy` (existing helper).
- Produces: `require_tool_calls_for_workflow(req: WorkflowRequest, cfg: DigiProjectConfig | None = None) -> bool` — consumed by Task 6's `_initial_graph_state`.

This is the security-critical function: **floor (OR), not override**. A request/header value can only turn the requirement ON, never OFF, when the deployment or env already mandates it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/dg/test_tool_allowlist.py` (same file as `allowed_tool_names_for_workflow`'s tests — this is its sibling resolver), after the existing `test_state_list_from_frozen` (end of file):

```python
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
```

Update this file's imports (top of `tests/dg/test_tool_allowlist.py`) to add `require_tool_calls_for_workflow`:

```python
from digigraph.tool_policy import (
    allowed_tool_names_for_workflow,
    require_tool_calls_for_workflow,
    state_list_from_frozen,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/dg/test_tool_allowlist.py -k require_tool_calls -v`
Expected: FAIL — `ImportError: cannot import name 'require_tool_calls_for_workflow'`

- [ ] **Step 3: Implement**

In `digigraph/src/digigraph/tool_policy.py`, add the import and the new function:

```python
from digigraph.policy import _env_truthy
```

```python
def require_tool_calls_for_workflow(
    req: WorkflowRequest,
    cfg: DigiProjectConfig | None = None,
) -> bool:
    """Whether this workflow must force tool_choice='required'.

    Resolved as a FLOOR, not an override (deliberately unlike
    allowed_tool_names_for_workflow's most-specific-wins precedence): a
    request-level True can only ADD the requirement, never remove one the
    deployment already mandates via project config or env. allowed_tools is
    safe to fully override per-request because the resolved set is still
    bounded by the tool registry (a caller can't invoke what was never
    wired); require_tool_calls has no such ceiling — it's a bare bool that
    directly controls tool_choice, and digigraph's own /v1/chat/completions
    is reachable by callers outside digichat's control (Open WebUI-compatible
    clients), so a full override would let any caller defeat an operator's
    mandatory tool-forcing policy with one field/header.
    """
    if cfg is None:
        try:
            cfg = DigiProjectConfig.load()
        except PROJECT_CONFIG_ERRORS:
            cfg = None
    if cfg is not None and bool(cfg.get_require_tool_calls()):
        return True
    if _env_truthy("DIGI_REQUIRE_TOOL_CALLS"):
        return True
    return bool(req.require_tool_calls)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/dg/test_tool_allowlist.py -k require_tool_calls -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full tool_allowlist test file**

Run: `python -m pytest tests/dg/test_tool_allowlist.py -q`
Expected: all pass (existing `allowed_tool_names_for_workflow` tests + 6 new)

- [ ] **Step 6: Commit**

```bash
git add digigraph/src/digigraph/tool_policy.py tests/dg/test_tool_allowlist.py
git commit -m "feat(digigraph): require_tool_calls_for_workflow floor resolver

The security-critical piece: floor (OR), not override. A request/header
value can only raise the requirement, never lower one the deployment
already set via agents.require_tool_calls or DIGI_REQUIRE_TOOL_CALLS."
```

---

### Task 6: digigraph — declare `require_tool_calls` on `WorkflowState` and wire `_initial_graph_state`

**Files:**
- Modify: `digigraph/src/digigraph/graph/state.py` (TypedDict declaration — LangGraph silently drops undeclared keys, see #2097; this must land in the same commit as the wiring below, not separately)
- Modify: `digigraph/src/digigraph/workflow.py` (`_initial_graph_state`, currently lines 41-80)
- Test: `tests/dg/test_tool_allowlist.py` (state-declaration + initial-state tests) and a LangGraph round-trip regression test

**Interfaces:**
- Consumes: `require_tool_calls_for_workflow` (Task 5).
- Produces: `WorkflowState["require_tool_calls"]: bool` — consumed by Task 8 (`research_node` reads `state.get("require_tool_calls")`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/dg/test_tool_allowlist.py`:

```python
def test_workflow_state_declares_require_tool_calls() -> None:
    """LangGraph drops undeclared TypedDict keys — see #2097."""
    from digigraph.graph.state import WorkflowState

    assert "require_tool_calls" in WorkflowState.__annotations__


def test_initial_graph_state_carries_require_tool_calls_true() -> None:
    from digigraph.workflow import _initial_graph_state

    cfg = DigiProjectConfig({"agents": {"require_tool_calls": True}})
    with patch("digigraph.workflow.DigiProjectConfig.load", return_value=cfg):
        state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-rtc-1")
    assert state["require_tool_calls"] is True


def test_initial_graph_state_defaults_require_tool_calls_false() -> None:
    from digigraph.workflow import _initial_graph_state

    cfg = DigiProjectConfig({"agents": {}})
    with patch("digigraph.workflow.DigiProjectConfig.load", return_value=cfg):
        state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-rtc-2")
    assert state["require_tool_calls"] is False


def test_langgraph_preserves_require_tool_calls_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip require_tool_calls."""
    from langgraph.graph import END, START, StateGraph

    from digigraph.graph.state import WorkflowState

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
```

Add `from unittest.mock import patch` to this test file's imports if not already present (it already imports `MagicMock, patch` per the file header — reuse it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/dg/test_tool_allowlist.py -k "require_tool_calls_through_invoke or workflow_state_declares_require_tool_calls or initial_graph_state_carries_require_tool_calls or initial_graph_state_defaults_require_tool_calls" -v`
Expected: FAIL — `KeyError: 'require_tool_calls'` (the state/initial-state tests) and a passing-but-meaningless run for the LangGraph one (it silently drops the key today, so `seen["require_tool_calls"]` is `None`, not `True` — write the assertion as shown above so it fails until the declaration exists)

- [ ] **Step 3: Implement — declare on `WorkflowState`**

In `digigraph/src/digigraph/graph/state.py`, add right after the existing `allowed_tool_names` line (currently line 22):

```python
    # Deployment-grain tool_choice="required" mandate — see tool_policy.require_tool_calls_for_workflow.
    require_tool_calls: bool
```

- [ ] **Step 4: Implement — wire `_initial_graph_state`**

In `digigraph/src/digigraph/workflow.py`, update the import line (currently line 17):

```python
from digigraph.tool_policy import (
    allowed_tool_names_for_workflow,
    require_tool_calls_for_workflow,
    state_list_from_frozen,
)
```

Then in `_initial_graph_state` (currently lines 41-80), add right after the `allowed_tool_names` block (after line 60, before `if req.trading_profile:`):

```python
    initial["require_tool_calls"] = require_tool_calls_for_workflow(req, cfg=cfg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/dg/test_tool_allowlist.py -v`
Expected: all pass (existing + Task 5's 6 + this task's 4)

- [ ] **Step 6: Run the full digigraph graph/workflow test suite for regressions**

Run: `python -m pytest tests/dg/test_graph.py tests/dg/test_nodes.py tests/dg/test_languages.py -q`
Expected: all pass — these exercise the same `_initial_graph_state`/`WorkflowState` machinery for other fields (corpus routing, `response_language`); a break here means the new key collided with something.

- [ ] **Step 7: Commit**

```bash
git add digigraph/src/digigraph/graph/state.py digigraph/src/digigraph/workflow.py tests/dg/test_tool_allowlist.py
git commit -m "feat(digigraph): declare + wire require_tool_calls on WorkflowState

Declared on WorkflowState in the same commit as the _initial_graph_state
wiring — LangGraph silently drops undeclared TypedDict keys (#2097), so
these two must never land separately."
```

---

### Task 7: digigraph — `X-Require-Tool-Calls` header resolver, threaded through both chat_completions paths

**Files:**
- Modify: `digigraph/src/digigraph/server.py` (new resolver beside `_resolve_allowed_tools_chat` at L783-790; `chat_completions` at L836-907; `_stream_completions_progressive` at L621-629)
- Test: `tests/dg/test_api.py`

**Interfaces:**
- Consumes: `ChatCompletionRequest.require_tool_calls` (Task 4).
- Produces: `_resolve_require_tool_calls_chat(req, request) -> bool | None`, threaded into `WorkflowRequest(require_tool_calls=...)` on both the streaming and non-streaming paths — consumed by Task 6's already-wired `_initial_graph_state` (which reads `req.require_tool_calls` inside `require_tool_calls_for_workflow`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/dg/test_api.py` (check the file's existing imports/fixtures for how a request-like stub or the FastAPI `TestClient` is constructed there, and match that style):

```python
def test_resolve_require_tool_calls_chat_from_body() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[], require_tool_calls=True)
    assert _resolve_require_tool_calls_chat(req, _Req()) is True


def test_resolve_require_tool_calls_chat_from_header() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return "1" if name == "X-Require-Tool-Calls" else None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[])
    assert _resolve_require_tool_calls_chat(req, _Req()) is True


def test_resolve_require_tool_calls_chat_none_when_absent() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[])
    assert _resolve_require_tool_calls_chat(req, _Req()) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/dg/test_api.py -k resolve_require_tool_calls -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_require_tool_calls_chat'`

- [ ] **Step 3: Implement — the resolver**

In `digigraph/src/digigraph/server.py`, add right after `_resolve_allowed_tools_chat` (currently lines 783-790):

```python
def _resolve_require_tool_calls_chat(req: ChatCompletionRequest, request: Request) -> bool | None:
    """Per-request tool_choice='required' signal from JSON body or X-Require-Tool-Calls header.

    None = no request-level signal; the deployment-grain floor (project config /
    DIGI_REQUIRE_TOOL_CALLS) still applies downstream in require_tool_calls_for_workflow.
    """
    if req.require_tool_calls is not None:
        return req.require_tool_calls
    h = (request.headers.get("X-Require-Tool-Calls") or "").strip().lower()
    if h in ("1", "true", "yes"):
        return True
    if h in ("0", "false", "no"):
        return False
    return None
```

- [ ] **Step 4: Run resolver tests to verify they pass**

Run: `python -m pytest tests/dg/test_api.py -k resolve_require_tool_calls -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Thread into `chat_completions`**

In `digigraph/src/digigraph/server.py`, in `chat_completions` (currently starting line 836), add right after `allowed_tools = _resolve_allowed_tools_chat(req, request)` (currently line 857):

```python
    require_tool_calls = _resolve_require_tool_calls_chat(req, request)
```

Then update the non-streaming `WorkflowRequest(...)` construction (currently lines 901-906):

```python
        wf = WorkflowRequest(
            prompt=prompt,
            session_id=session_id,
            allowed_tools=allowed_tools,
            require_tool_calls=require_tool_calls,
            request_id=request_id,
        )
```

And the streaming call to `_stream_completions_progressive(...)` (currently lines 878-888) — add the new kwarg:

```python
        return StreamingResponse(
            _stream_completions_progressive(
                req,
                prompt,
                session_id,
                openwebui_format=openwebui_format,
                allowed_tools=allowed_tools,
                require_tool_calls=require_tool_calls,
                request_id=request_id,
                workflow_extras=wf_extras,
                suppress_tool_stream=suppress_tool_stream,
            ),
            ...
```

- [ ] **Step 6: Thread through `_stream_completions_progressive`'s own signature**

In `digigraph/src/digigraph/server.py`, update `_stream_completions_progressive`'s signature (currently lines 621-629):

```python
def _stream_completions_progressive(
    req: ChatCompletionRequest,
    prompt: str,
    session_id: str | None,
    openwebui_format: bool = False,
    allowed_tools: list[str] | None = None,
    require_tool_calls: bool | None = None,
    request_id: str | None = None,
    workflow_extras: dict | None = None,
    suppress_tool_stream: bool = False,
):
```

And its internal `wf_kw` dict (currently lines 636-641):

```python
    wf_kw: dict = {
        "prompt": prompt,
        "session_id": session_id,
        "allowed_tools": allowed_tools,
        "require_tool_calls": require_tool_calls,
        "request_id": request_id,
    }
```

- [ ] **Step 7: Write and run an integration test threading a header through to `WorkflowRequest`**

Add to `tests/dg/test_api.py`:

```python
def test_chat_completions_threads_require_tool_calls_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """X-Require-Tool-Calls: 1 reaches the WorkflowRequest passed to run_digigraph_workflow."""
    captured: dict = {}

    def fake_run_workflow(wf):
        captured["require_tool_calls"] = wf.require_tool_calls
        result = MagicMock()
        result.success = True
        result.content = "ok"
        return result

    monkeypatch.setattr("digigraph.server.run_digigraph_workflow", fake_run_workflow)
    client = TestClient(app)  # reuse this file's existing TestClient/app fixture setup
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "digigraph-rag", "messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Require-Tool-Calls": "1"},
    )
    assert resp.status_code == 200
    assert captured["require_tool_calls"] is True
```

(Check `tests/dg/test_api.py`'s existing imports at the top for the exact `TestClient`/`app` construction already used by neighboring tests — e.g. how `test_gated_endpoints.py` or an existing `chat_completions` test in this same file builds its client/headers/auth bypass — and match that setup exactly rather than re-deriving it; this repo's `TestClient` fixture likely needs an auth override or a `conftest.py` fixture already used elsewhere in this file.)

Run: `python -m pytest tests/dg/test_api.py -k test_chat_completions_threads_require_tool_calls_header -v`
Expected: PASS

- [ ] **Step 8: Run the full API test file for regressions**

Run: `python -m pytest tests/dg/test_api.py -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add digigraph/src/digigraph/server.py tests/dg/test_api.py
git commit -m "feat(digigraph): X-Require-Tool-Calls header threaded through both chat paths"
```

---

### Task 8: digigraph — `research_node` reads the resolved flag and threads `tool_choice` into `run_tools`

**Files:**
- Modify: `digigraph/src/digigraph/graph/research.py:426-436` (the `run_tools(...)` call site, right before `planning_mode = bool(cfg.get_planning_mode()) if cfg else False`)
- Test: `tests/dg/test_languages.py`-style direct `research_node(...)` call (this file is the established precedent for testing this exact function with a plain dict state — see `test_research_node_appends_directive_for_known_language`)

**Interfaces:**
- Consumes: `state.get("require_tool_calls")` (Task 6), `digigraph.llm_client.run_tools(..., tool_choice=...)` (Task 2).
- Produces: nothing further downstream — this is the terminal wiring point.

- [ ] **Step 1: Write the failing tests**

Add to `tests/dg/test_languages.py` is the wrong file (that's language-specific) — instead, create `tests/dg/test_require_tool_calls.py`:

```python
"""Unit tests for the tool-calling requirement gate's terminal wiring: research_node
reads WorkflowState["require_tool_calls"] and threads tool_choice into run_tools.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from digigraph.graph.research import research_node

pytestmark = pytest.mark.unit


def _patch_research_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )


def test_research_node_forces_tool_choice_required_when_state_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy", "require_tool_calls": True})
    assert captured["tool_choice"] == "required"


def test_research_node_defaults_tool_choice_auto_when_state_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy", "require_tool_calls": False})
    assert captured["tool_choice"] == "auto"


def test_research_node_defaults_tool_choice_auto_when_state_key_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workflow invoked before this feature existed (or via a code path that never
    calls _initial_graph_state) has no require_tool_calls key at all — must not crash,
    must default to today's unchanged 'auto' behavior."""
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy"})
    assert captured["tool_choice"] == "auto"
```

Note: if `research_node` takes the quant/augmented path rather than the document-RAG path for this prompt shape (per the "Regression guard" test in `test_languages.py`, which shows a plain strategy-building prompt with no override routes through `_run_quant_or_augmented_path`, not `_run_document_rag_path`), the `run_tools` call this task modifies lives inside whichever path actually reaches it — confirm which by running Step 2 first; if the mock never gets called, check `test_languages.py`'s `test_research_node_takes_quant_path_when_system_prompt_is_default` for the exact monkeypatch shape that reaches the `run_tools` call site, and mirror its patches (it may need `_run_quant_or_augmented_path` mocked instead of/in addition to `_load_research_settings`) instead of the simpler patch set drafted above.

- [ ] **Step 2: Run tests to verify they fail (and confirm the correct code path)**

Run: `python -m pytest tests/dg/test_require_tool_calls.py -v`
Expected: FAIL — either `TypeError: run_tools() got an unexpected keyword argument` (if the mock is reached but the real call site doesn't pass `tool_choice` yet) or the mock never firing (if the wrong path is patched — adjust the monkeypatches per the note above until the failure is specifically about the missing `tool_choice` kwarg, not a routing mismatch)

- [ ] **Step 3: Implement**

In `digigraph/src/digigraph/graph/research.py`, at the `run_tools(...)` call site (currently lines 426-436), add a `tool_choice` kwarg derived from state, right before the closing paren:

```python
    content = run_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        tools=tools_for_llm,
        execute_tool=execute_search,
        max_tool_rounds=4,
        on_tool_step=stream_callback,
        tool_choice="required" if state.get("require_tool_calls") else "auto",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/dg/test_require_tool_calls.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full research/graph test suite for regressions**

Run: `python -m pytest tests/dg/test_graph.py tests/dg/test_nodes.py tests/dg/test_languages.py tests/dg/test_research_json.py tests/dg/test_research_prefetch.py -q`
Expected: all pass

- [ ] **Step 6: Run the complete digigraph suite**

Run: `python -m pytest tests/dg -q`
Expected: all pass (this is the full regression check before moving to docs)

- [ ] **Step 7: Lint**

Run: `ruff check digigraph/src && ruff format --check digigraph/src`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add digigraph/src/digigraph/graph/research.py tests/dg/test_require_tool_calls.py
git commit -m "feat(digigraph): research_node threads require_tool_calls into run_tools

Terminal wiring point: reads the already-resolved WorkflowState boolean
(set once at graph-build time by require_tool_calls_for_workflow, same
pattern as allowed_tool_names/response_language) — no re-resolution here."
```

---

### Task 9: `ARCHITECTURE.md` — document `agents.require_tool_calls`

**Files:**
- Modify: `digigraph/ARCHITECTURE.md` (add beside the existing `agents.allowed_tools` documentation)

**Interfaces:**
- Consumes: nothing (docs only).
- Produces: nothing (docs only) — but required per this repo's standing rule ("Update `{component}/ARCHITECTURE.md` after any interface or behavior change") and per issue #201's AC7.

- [ ] **Step 1: Find the existing `agents.allowed_tools` documentation**

Run: `grep -n 'allowed_tools' digigraph/ARCHITECTURE.md`

- [ ] **Step 2: Add a matching entry for `require_tool_calls`**

Add a paragraph immediately after wherever `agents.allowed_tools` is documented (exact heading/table found in Step 1), following that section's existing style:

```markdown
`agents.require_tool_calls` (bool, default `false`) forces `tool_choice="required"`
on every tool-calling turn in `research_node`'s `run_tools()` call — for deployments
(e.g. OCC) that depend on multi-round tool calls for retrieval and should never
silently answer from parametric knowledge alone. Resolved as a **floor**, not an
override, by `tool_policy.require_tool_calls_for_workflow()`: project config or
`DIGI_REQUIRE_TOOL_CALLS` wins over a request/`X-Require-Tool-Calls` header value
of `false` — deliberately the opposite precedence from `agents.allowed_tools`,
since this flag has no registry-bounded ceiling the way a tool allowlist does.
```

- [ ] **Step 3: Verify internal doc links still resolve**

Run: `make doc-check`
Expected: `check_doc_links: OK (N markdown files scanned)`

- [ ] **Step 4: Commit**

```bash
git add digigraph/ARCHITECTURE.md
git commit -m "docs(digigraph): document agents.require_tool_calls"
```

---

## Final verification (run before opening the PR)

```bash
cd digillm && python -m pytest tests -q && ruff check src tests && ruff format --check src tests
cd .. && python -m pytest tests/dg -q
ruff check digigraph/src && ruff format --check digigraph/src
make doc-check
```

All must pass. Then run `make score` on the staged diff per this repo's scoring gate, and remember: this plan's changes are network-exposure-adjacent (`server.py`) — CLAUDE.md's human-gate rule applies regardless of `make score` passing.
