"""§7 attribution preservation when generic tool results are clipped (#4131)."""

from __future__ import annotations

import json
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest
from digigraph.models import WorkflowRequest
from digigraph.workflow import (
    _MAX_TOOL_RESULT_CHARS,
    _clip_tool_result,
    _render_clipped_tool_result,
    run_digigraph_workflow_streaming,
)

# Mirrors digiquant/src/digiquant/data/gloomberb/attribution.py:21-23. digigraph
# never imports digiquant packages, so the strings are inlined (the digiweb
# parity test reads the Python file instead — gloomberb.test.ts:120-141).
_ATTRIBUTION = "Sourced from Gloomberb"
_DELAY_NOTICE = "Data delayed up to 15 minutes"
_SOURCE_URL = "https://term.gloom.sh/?ticker=AAPL"


def _envelope_text(rows: int = 120) -> str:
    """A digifetch_price_history envelope as ``gloomberb_envelope_json`` emits it.

    The §7 block is appended LAST (agent_tools.py:161-166) — the ordering that
    loses it to the 2,000-char scalar cap once the MCP client wraps the string
    in ``{"ok": true, "text": ...}`` (mcp_client.py:657-669).
    """
    payload: dict = {
        "data": {
            "bars": [
                {"date": f"2025-01-{(i % 28) + 1:02d}", "close": 100.0 + i} for i in range(rows)
            ]
        },
        "stale": False,
    }
    payload["attribution"] = _ATTRIBUTION
    payload["delay_notice"] = _DELAY_NOTICE
    payload["source_url"] = _SOURCE_URL
    return json.dumps(payload, indent=2, default=str)


def _tool_result_traces(queue: Queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get())
    return [e[1] for e in events if e[0] == "trace" and e[1].get("type") == "tool_result"]


@pytest.mark.unit
def test_clipped_digifetch_envelope_keeps_attribution_in_the_trace() -> None:
    queue: Queue = Queue()
    tool_payload = {
        "name": "digiquant_digifetch_price_history",
        "ok": True,
        "text": _envelope_text(),
    }

    def fake_stream(
        initial, config=None, stream_mode=None, version=None, durability=None, subgraphs=None
    ):
        # digillm's run_tools fires this shape via on_tool_step; the research
        # node forwards it as a stream_mode=["updates", "custom"] custom part.
        yield {"type": "custom", "ns": (), "data": ("tool_result", tool_payload)}

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = fake_stream
    mock_graph.get_state.return_value = MagicMock(values={})

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="AAPL history"), queue)

    traces = _tool_result_traces(queue)
    assert len(traces) == 1
    result = traces[0]["payload"]["result"]
    assert result["attribution"] == _ATTRIBUTION
    assert result["delay_notice"] == _DELAY_NOTICE
    assert result["source_url"] == _SOURCE_URL
    # Caps unchanged: the string scalar is still cut at 2,000 chars and the
    # whole emitted record stays within the 12,000-char trace cap.
    assert len(result["text"]) == 2000
    assert len(json.dumps(result)) <= _MAX_TOOL_RESULT_CHARS


@pytest.mark.unit
def test_small_envelope_keeps_attribution() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": _envelope_text(rows=2)})
    assert rendered["attribution"] == _ATTRIBUTION
    assert rendered["delay_notice"] == _DELAY_NOTICE
    assert rendered["source_url"] == _SOURCE_URL
    assert rendered["ok"] is True


@pytest.mark.unit
def test_structured_hub_envelope_keeps_attribution() -> None:
    raw = {
        "ok": True,
        "service": "digiquant",
        "tool": "digifetch_quote",
        "data": {
            "data": {"quote": {"symbol": "AAPL", "price": 200.0}},
            "attribution": _ATTRIBUTION,
            "delay_notice": _DELAY_NOTICE,
            "source_url": _SOURCE_URL,
        },
    }
    rendered = _render_clipped_tool_result(raw)
    assert rendered["attribution"] == _ATTRIBUTION
    assert rendered["delay_notice"] == _DELAY_NOTICE
    assert rendered["source_url"] == _SOURCE_URL


@pytest.mark.unit
def test_large_non_json_scalar_is_capped_without_attribution() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": "x" * 50_000})
    assert rendered == {"ok": True, "text": "x" * 2000}


@pytest.mark.unit
def test_malformed_json_string_does_not_raise() -> None:
    rendered = _render_clipped_tool_result({"ok": True, "text": '{"attribution": '})
    assert rendered == {"ok": True, "text": '{"attribution":'}


@pytest.mark.unit
def test_unattributed_result_is_unchanged() -> None:
    raw = {"connections": [{"name": "a", "id": "1"}]}
    assert _render_clipped_tool_result(raw) == _clip_tool_result(raw)


@pytest.mark.unit
def test_truncated_structured_record_stays_within_the_cap() -> None:
    raw = {
        "attribution": _ATTRIBUTION,
        "delay_notice": _DELAY_NOTICE,
        "source_url": _SOURCE_URL,
        "rows": ["row-" + "x" * 400 for _ in range(50)],
    }
    rendered = _render_clipped_tool_result(raw)
    assert rendered["truncated"] is True
    assert rendered["preview"].endswith("… [truncated]")
    assert rendered["attribution"] == _ATTRIBUTION
    # The preview slice is itself JSON text: its quote characters escape again
    # when the record is re-serialized, so the bound must hold on the
    # re-serialized record (12,023 chars pre-fix), not on the raw slice.
    assert len(json.dumps(rendered)) <= _MAX_TOOL_RESULT_CHARS
