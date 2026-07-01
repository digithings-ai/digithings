"""Unit tests for the declarative pipeline builder."""

from __future__ import annotations

# The noqa below is read by repo-local `scripts/score.py` (not ruff) — that
# gate flags unscoped `Any` imports. Here Any matches LangGraph node updates.
from typing import Annotated, Any  # noqa  # scored-lint suppression

import pytest
from pydantic import BaseModel, Field

from digigraph.graph.pipeline_builder import (
    FanOutPhase,
    NodeSpec,
    PipelinePhase,
    build_pipeline,
)


class _State(BaseModel):
    """Each node writes into its own field — parallel nodes must write disjoint keys."""

    a_out: str | None = None
    b_out: str | None = None
    c_out: str | None = None
    final: str | None = None


def _make_node(name: str, field: str) -> NodeSpec:
    def _run(_state: _State) -> dict[str, Any]:
        return {field: f"{name}-ran"}

    return NodeSpec(name=name, run=_run)


@pytest.mark.unit
class TestBuildPipeline:
    def test_empty_phases_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one phase"):
            build_pipeline(_State, [])

    def test_duplicate_phase_name_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate phase"):
            build_pipeline(
                _State,
                [
                    PipelinePhase("p", [_make_node("a", "a_out")]),
                    PipelinePhase("p", [_make_node("b", "b_out")]),
                ],
            )

    def test_duplicate_node_name_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate node name"):
            build_pipeline(
                _State,
                [
                    PipelinePhase("p1", [_make_node("x", "a_out")]),
                    PipelinePhase("p2", [_make_node("x", "b_out")]),
                ],
            )

    def test_empty_phase_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one node"):
            build_pipeline(_State, [PipelinePhase("p", [])])

    def test_reserved_barrier_prefix_rejected_on_phase(self) -> None:
        with pytest.raises(ValueError, match="reserved prefix"):
            build_pipeline(
                _State,
                [PipelinePhase("__barrier__0__x", [_make_node("a", "a_out")])],
            )

    def test_reserved_barrier_prefix_rejected_on_node(self) -> None:
        def _noop(_s: _State) -> dict[str, Any]:
            return {}

        with pytest.raises(ValueError, match="reserved prefix"):
            build_pipeline(
                _State,
                [PipelinePhase("p", [NodeSpec("__barrier__sneaky", _noop)])],
            )

    def test_sequential_phases_run_in_order(self) -> None:
        compiled = build_pipeline(
            _State,
            [
                PipelinePhase("p1", [_make_node("a", "a_out")]),
                PipelinePhase("p2", [_make_node("b", "b_out")]),
                PipelinePhase("p3", [_make_node("c", "c_out")]),
            ],
        )
        result = compiled.invoke(_State())
        out = _State.model_validate(result) if isinstance(result, dict) else result
        assert out.a_out == "a-ran"
        assert out.b_out == "b-ran"
        assert out.c_out == "c-ran"

    def test_parallel_phase_fans_out_and_in(self) -> None:
        """Fan-out nodes write disjoint fields; a downstream node reads both."""

        def finalizer(state: _State) -> dict[str, Any]:
            return {"final": f"{state.a_out}|{state.b_out}"}

        compiled = build_pipeline(
            _State,
            [
                PipelinePhase("start", [_make_node("seed", "c_out")]),
                PipelinePhase(
                    "parallel",
                    [
                        _make_node("a", "a_out"),
                        _make_node("b", "b_out"),
                    ],
                ),
                PipelinePhase("finish", [NodeSpec("finalizer", finalizer)]),
            ],
        )
        result = compiled.invoke(_State())
        out = _State.model_validate(result) if isinstance(result, dict) else result
        assert out.c_out == "seed-ran"
        assert out.a_out == "a-ran"
        assert out.b_out == "b-ran"
        # Both parallel outputs must be visible to the downstream finalizer.
        assert out.final == "a-ran|b-ran"

    def test_single_node_phases_skip_barrier(self) -> None:
        """No extra __barrier__ nodes for purely-sequential pipelines."""
        compiled = build_pipeline(
            _State,
            [
                PipelinePhase("p1", [_make_node("a", "a_out")]),
                PipelinePhase("p2", [_make_node("b", "b_out")]),
            ],
        )
        # CompiledStateGraph exposes .get_graph().nodes — barrier names start with __barrier__.
        node_names = set(compiled.get_graph().nodes.keys())
        assert not any(n.startswith("__barrier__") for n in node_names)


def _merge_seen(left: dict[str, str] | None, right: dict[str, str] | None) -> dict[str, str]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class _FanState(BaseModel):
    """Mimics ``phase_hermes``: a runtime item list + a reducer-merged result dict."""

    items: list[str] = Field(default_factory=list)
    cursor: str | None = None  # transient per-Send fan-out cursor
    seen: Annotated[dict[str, str], _merge_seen] = Field(default_factory=dict)
    joined: str | None = None


@pytest.mark.unit
class TestFanOutPhase:
    """``FanOutPhase`` maps a runtime item list to parallel Send workers, then reduces."""

    @staticmethod
    def _pipeline(items: list[str]) -> Any:
        def _seed(_state: _FanState) -> dict[str, Any]:
            return {"items": items}

        def _worker(state: _FanState) -> dict[str, Any]:
            # Each parallel invocation sees exactly one cursor (its Send payload).
            return {"seen": {str(state.cursor): f"{state.cursor}-ok"}}

        def _join(state: _FanState) -> dict[str, Any]:
            return {"joined": ",".join(sorted(state.seen))}

        return build_pipeline(
            _FanState,
            [
                PipelinePhase("seed", [NodeSpec("seed", _seed)]),
                FanOutPhase(
                    name="fan",
                    worker=NodeSpec("worker", _worker),
                    items=lambda s: s.items,
                    with_item=lambda s, item: s.model_copy(update={"cursor": item}),
                ),
                PipelinePhase("join", [NodeSpec("join", _join)]),
            ],
        )

    def test_fans_out_over_runtime_items_and_reduces(self) -> None:
        compiled = self._pipeline(["x", "y", "z"])
        result = compiled.invoke(_FanState())
        out = _FanState.model_validate(result) if isinstance(result, dict) else result
        # Every item ran in its own worker; the reducer merged all three writes.
        assert out.seen == {"x": "x-ok", "y": "y-ok", "z": "z-ok"}
        # Downstream join sees the fully-merged map (fan-in complete).
        assert out.joined == "x,y,z"

    def test_empty_items_short_circuits_to_join(self) -> None:
        compiled = self._pipeline([])
        result = compiled.invoke(_FanState())
        out = _FanState.model_validate(result) if isinstance(result, dict) else result
        # No workers dispatched, but the graph must not stall — join still runs.
        assert out.seen == {}
        assert out.joined == ""

    def test_worker_node_is_registered_once(self) -> None:
        compiled = self._pipeline(["x", "y"])
        names = set(compiled.get_graph().nodes.keys())
        assert "worker" in names  # single worker node, invoked N times via Send

    def test_fanout_phase_exposes_worker_as_nodes(self) -> None:
        phase = FanOutPhase(
            name="fan",
            worker=NodeSpec("worker", lambda s: {}),
            items=lambda s: [],
            with_item=lambda s, item: s,
        )
        assert [n.name for n in phase.nodes] == ["worker"]
