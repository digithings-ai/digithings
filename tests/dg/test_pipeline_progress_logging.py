"""Progress narration for the shared pipeline builder (#4116).

A book run takes hours; without narration a CI log is silent until it fails. Each
phase and each fan-out item must announce itself at INFO so an operator can watch
the run move, and the chatter must stay at INFO (never WARNING) so WARNING+ still
means trouble.
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated, Any

import pytest
from digigraph.graph.pipeline_builder import FanOutPhase, NodeSpec, PipelinePhase, build_pipeline
from pydantic import BaseModel

pytestmark = pytest.mark.unit

LOGGER = "digigraph.graph.pipeline_builder"


class _State(BaseModel):
    topic: str = "seed"
    a_out: str = ""
    b_out: str = ""
    notes: Annotated[list[str], operator.add] = []


def _node(name: str, field: str) -> NodeSpec:
    def run(state: _State) -> dict[str, Any]:
        return {field: name}

    return NodeSpec(name=name, run=run)


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == LOGGER]


def test_phases_and_nodes_are_narrated(caplog: pytest.LogCaptureFixture) -> None:
    phases = [
        PipelinePhase(name="preflight", nodes=[_node("preflight", "a_out")]),
        PipelinePhase(name="analysts", nodes=[_node("analyst", "b_out")]),
    ]
    graph = build_pipeline(_State, phases)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        graph.invoke(_State())

    messages = _messages(caplog)
    assert any("[1/2 preflight]" in message and "preflight" in message for message in messages)
    assert any("[2/2 analysts]" in message and "done in" in message for message in messages)


def test_fanout_items_are_narrated_and_the_phase_reports_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fan_out = FanOutPhase(
        name="grounding",
        worker=NodeSpec(
            name="ground_segment",
            run=lambda state: {"notes": [state.topic]},
        ),
        items=lambda state: ["macro", "alt-credit"],
        with_item=lambda state, item: state.model_copy(update={"topic": item}),
        item_key=lambda state: state.topic,
    )
    graph = build_pipeline(
        _State,
        [PipelinePhase(name="preflight", nodes=[_node("preflight", "a_out")]), fan_out],
    )

    with caplog.at_level(logging.INFO, logger=LOGGER):
        graph.invoke(_State())

    messages = _messages(caplog)
    assert any("(macro)" in message for message in messages)
    assert any("(alt-credit)" in message for message in messages)
    assert any("[2/2 grounding]" in message and "complete in" in message for message in messages)


def test_reused_graph_times_each_run_separately(caplog: pytest.LogCaptureFixture) -> None:
    fan_out = FanOutPhase(
        name="second",
        worker=NodeSpec(name="worker", run=lambda state: {"notes": [state.topic]}),
        items=lambda state: ["done"],
        with_item=lambda state, item: state.model_copy(update={"topic": item}),
        item_key=lambda state: state.topic,
    )
    graph = build_pipeline(
        _State,
        [PipelinePhase(name="first", nodes=[_node("a", "a_out")]), fan_out],
    )

    with caplog.at_level(logging.INFO, logger=LOGGER):
        graph.invoke(_State())
        caplog.clear()
        graph.invoke(_State())

    completes = [message for message in _messages(caplog) if "complete in" in message]
    assert len(completes) == 1
    elapsed = float(completes[0].split("complete in ")[1].removesuffix("s"))
    assert elapsed < 1.0


def test_progress_narration_never_reaches_warning(caplog: pytest.LogCaptureFixture) -> None:
    # Built inside the block: the compile-time line is INFO, so capturing it must
    # not depend on whatever level an earlier test left on the root logger.
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        graph = build_pipeline(_State, [PipelinePhase(name="solo", nodes=[_node("solo", "a_out")])])
        graph.invoke(_State())

    assert _messages(caplog) == []
