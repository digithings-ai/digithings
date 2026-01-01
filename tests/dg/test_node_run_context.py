"""Run/node execution context propagation through the shared pipeline builder (#1978).

These tests assert on what a node observes *inside its own body*, not on reduced graph
output. The distinction matters: the pre-existing fan-out tests in ``test_pipeline_builder.py``
assert only on merged results and would pass even if context never propagated at all.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Annotated, Any

import pytest
from digigraph.graph.pipeline_builder import FanOutPhase, NodeSpec, PipelinePhase, build_pipeline
from pydantic import BaseModel

from digigraph import usage
from digillm import NodeRunOutcome

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean():
    usage.reset()
    yield
    usage.reset()


def _merge(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    return (left or []) + (right or [])


class _State(BaseModel):
    cursor: str | None = None
    seen: Annotated[list[Any], _merge] = []


def _fanout(worker_run: Any, *, item_key: Any = None, name: str = "worker") -> FanOutPhase:
    return FanOutPhase(
        name="fan",
        worker=NodeSpec(name=name, run=worker_run),
        items=lambda state: ["AAPL", "MSFT", "NVDA"],
        with_item=lambda state, item: state.model_copy(update={"cursor": item}),
        item_key=item_key,
    )


def test_worker_body_observes_run_node_and_fanout_context() -> None:
    observed: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def _run(state: _State) -> dict[str, Any]:
        with lock:
            observed.append((state.cursor or "", usage.provider_call_metadata()[0]))
        return {"seen": [state.cursor]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [_fanout(_run, item_key=lambda s: s.cursor)])
    graph.invoke(_State())

    assert len(observed) == 3
    assert all(node_run_id is not None for _, node_run_id in observed)
    records = {record.node_run_id: record for record in usage.node_runs_snapshot()}
    assert len(records) == 3
    for ticker, node_run_id in observed:
        record = records[node_run_id]
        assert record.fanout_key == ticker
        assert record.node_name == "worker"
        assert record.run_id == "gha-1978"


def test_two_fanout_workers_cannot_leak_context() -> None:
    observed: list[tuple[Any, Any]] = []
    lock = threading.Lock()

    def _run(state: _State) -> dict[str, Any]:
        first = usage.provider_call_metadata()[0]
        time.sleep(0.05)  # force overlap between concurrent workers
        second = usage.provider_call_metadata()[0]
        with lock:
            observed.append((first, second))
        return {"seen": [state.cursor]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [_fanout(_run, item_key=lambda s: s.cursor)])
    graph.invoke(_State())

    assert all(first is not None and first == second for first, second in observed)
    ids = [first for first, _ in observed]
    assert len(set(ids)) == len(ids), "a worker observed a sibling's node identity"
    keys = [record.fanout_key for record in usage.node_runs_snapshot()]
    assert sorted(keys) == ["AAPL", "MSFT", "NVDA"]


def test_raising_node_records_failed_and_leaves_no_bleed() -> None:
    def _run(state: _State) -> dict[str, Any]:
        if state.cursor == "MSFT":
            raise RuntimeError("boom")
        return {"seen": [state.cursor]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [_fanout(_run, item_key=lambda s: s.cursor)])
    with pytest.raises(RuntimeError, match="boom"):
        graph.invoke(_State())

    records = usage.node_runs_snapshot()
    failed = [r for r in records if r.outcome is NodeRunOutcome.FAILED]
    assert len(failed) == 1
    assert failed[0].fanout_key == "MSFT"
    assert failed[0].finished_at is not None
    # No context bleeds back into the caller's thread.
    assert usage.provider_call_metadata()[0] is None


def test_nested_call_context_inside_a_node_preserves_the_node_run_id() -> None:
    captured: dict[str, Any] = {}

    def _run(state: _State) -> dict[str, Any]:
        captured["outer"] = usage.provider_call_metadata()[0]
        with usage.call_context(phase="p", operation="o"):
            captured["inner"] = usage.provider_call_metadata()[0]
        return {"seen": [state.cursor]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [PipelinePhase(name="solo", nodes=(NodeSpec("n", _run),))])
    graph.invoke(_State())

    assert captured["inner"] is not None
    assert captured["inner"] == captured["outer"]


def test_topology_unchanged_and_barriers_emit_no_records() -> None:
    def _a(state: _State) -> dict[str, Any]:
        return {"seen": ["a"]}

    def _b(state: _State) -> dict[str, Any]:
        return {"seen": ["b"]}

    phases = [PipelinePhase(name="par", nodes=(NodeSpec("a", _a), NodeSpec("b", _b)))]
    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, phases)
    node_names = set(graph.get_graph().nodes)
    graph.invoke(_State())

    assert {"a", "b"} <= node_names
    # Exactly two real node executions: the synthetic barrier runs no user code and must not
    # inflate reconciliation counts.
    assert len(usage.node_runs_snapshot()) == 2
    assert {r.node_name for r in usage.node_runs_snapshot()} == {"a", "b"}


def test_node_declaring_runnable_config_still_receives_it() -> None:
    """The wrapper must stay signature-transparent.

    LangGraph decides what to inject from ``inspect.signature(func).parameters``, matched by
    parameter name and annotation. A ``(state)``-only wrapper — with or without
    ``functools.wraps`` — breaks a node that declares ``config``, which is a supported and
    currently-working node shape. This is the guard for that regression.
    """
    from langchain_core.runnables import RunnableConfig

    captured: dict[str, Any] = {}

    def _node(state: _State, config: RunnableConfig) -> dict[str, Any]:
        captured["config"] = config
        return {"seen": ["ok"]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [PipelinePhase(name="solo", nodes=(NodeSpec("n", _node),))])
    graph.invoke(_State())

    assert isinstance(captured.get("config"), dict)
    assert "configurable" in captured["config"]


def test_a_raising_item_key_leaves_the_node_unchanged() -> None:
    def _run(state: _State) -> dict[str, Any]:
        return {"seen": [state.cursor]}

    def _boom(_state: Any) -> Any:
        raise RuntimeError("extractor is broken")

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [_fanout(_run, item_key=_boom)])
    result = graph.invoke(_State())

    # A telemetry label must never change a node's behaviour.
    assert sorted(result["seen"]) == ["AAPL", "MSFT", "NVDA"]
    records = usage.node_runs_snapshot()
    assert len(records) == 3
    assert all(record.fanout_key is None for record in records)


def test_an_async_node_stays_async_and_is_still_scoped() -> None:
    """A coroutine node needs a coroutine wrapper.

    ``functools.wraps`` copies the inner signature, so a sync wrapper around an ``async def``
    looks synchronous to LangGraph while handing back an un-awaited coroutine — the node dies
    with ``InvalidUpdateError: Expected dict, got <coroutine>``. Nothing registers an async node
    today, so this guards a capability rather than a live path: without it, adding one would be
    impossible rather than merely unused.

    Driven through ``asyncio.run`` rather than ``@pytest.mark.asyncio`` on purpose: the digigraph
    CI lane installs ``digigraph[dev]``, which has no ``pytest-asyncio``, so a marked coroutine
    test collects locally and fails in CI with "async def functions are not natively supported".
    """
    captured: dict[str, Any] = {}

    async def _anode(state: _State) -> dict[str, Any]:
        captured["node_run_id"] = usage.provider_call_metadata()[0]
        return {"seen": ["async"]}

    usage.start(run_id="gha-1978")
    graph = build_pipeline(_State, [PipelinePhase(name="solo", nodes=(NodeSpec("n", _anode),))])
    result = asyncio.run(graph.ainvoke(_State()))

    assert result["seen"] == ["async"]
    assert captured["node_run_id"] is not None
    (record,) = usage.node_runs_snapshot()
    assert record.node_name == "n"
    assert record.outcome is NodeRunOutcome.SUCCEEDED
