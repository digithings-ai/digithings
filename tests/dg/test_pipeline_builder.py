"""Unit tests for the declarative pipeline builder."""

from __future__ import annotations

# `# noqa` below is read by repo-local `scripts/score.py` (not ruff) — that
# gate flags unscoped `Any` imports. Here Any matches LangGraph node updates.
from typing import Any  # noqa: scored-lint suppression

import pytest
from pydantic import BaseModel

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase, build_pipeline


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
