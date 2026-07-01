"""Checkpoint/resume semantics for build_pipeline (#665).

MemorySaver has the same resume semantics as PostgresSaver, so these prove the
design offline: a failed run re-invoked with the same thread_id skips completed
nodes, and distinct thread_ids isolate independent graph lineages.
"""

from __future__ import annotations

from typing import Any, TypedDict  # noqa  # scored-lint suppression: test graph node state

import pytest

pytest.importorskip("langgraph")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase, build_pipeline  # noqa: E402


class _S(TypedDict, total=False):
    a: str
    b: str


@pytest.mark.unit
def test_resume_skips_completed_node():
    calls = {"n1": 0, "n2": 0}
    fail_once = {"v": True}

    def n1(_state: _S) -> dict[str, Any]:
        calls["n1"] += 1
        return {"a": "1"}

    def n2(_state: _S) -> dict[str, Any]:
        calls["n2"] += 1
        if fail_once["v"]:
            fail_once["v"] = False
            raise RuntimeError("boom")
        return {"b": "2"}

    phases = [
        PipelinePhase(name="p1", nodes=[NodeSpec(name="n1", run=n1)]),
        PipelinePhase(name="p2", nodes=[NodeSpec(name="n2", run=n2)]),
    ]
    graph = build_pipeline(_S, phases, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    with pytest.raises(RuntimeError):
        graph.invoke({"a": ""}, cfg)
    # Resume the SAME thread with None — completed node n1 must not re-run.
    out = graph.invoke(None, cfg)

    assert calls["n1"] == 1  # checkpoint preserved its write; not re-executed
    assert calls["n2"] == 2  # only the failed node re-ran
    assert out["a"] == "1" and out["b"] == "2"


@pytest.mark.unit
def test_distinct_thread_ids_isolate_lineages():
    seen: list[str] = []

    def only(_state: _S) -> dict[str, Any]:
        seen.append("run")
        return {"a": "x"}

    graph = build_pipeline(
        _S,
        [PipelinePhase(name="p", nodes=[NodeSpec(name="only", run=only)])],
        checkpointer=MemorySaver(),
    )
    graph.invoke({"a": ""}, {"configurable": {"thread_id": "run-1::atlas"}})
    graph.invoke({"a": ""}, {"configurable": {"thread_id": "run-1::hermes"}})
    assert len(seen) == 2  # different thread_ids => independent runs, both execute


@pytest.mark.unit
def test_no_checkpointer_keeps_plain_compile():
    # Without a checkpointer, invoke needs no thread_id (back-compat for tests/callers).
    def only(_state: _S) -> dict[str, Any]:
        return {"a": "ok"}

    graph = build_pipeline(_S, [PipelinePhase(name="p", nodes=[NodeSpec(name="only", run=only)])])
    assert graph.invoke({"a": ""})["a"] == "ok"
