"""Unit tests for the digivault_search_notes orchestrator tool (builtin.py wiring)."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from digigraph.orchestration.registry import ToolContext, ToolExposureMode, get_tools, has_tool


def _ctx(**overrides: object) -> ToolContext:
    defaults: dict[str, object] = {
        "session_id": "sess-1",
        "run_data_dir": None,
        "index_name": "default",
        "index_config": {},
        "state": {},
        "request_id": "rid-1",
    }
    defaults.update(overrides)
    return ToolContext(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
def test_digivault_search_notes_is_registered() -> None:
    from digigraph.orchestration import builtin  # noqa: F401 - triggers registration

    assert has_tool("digivault_search_notes")


@pytest.mark.unit
def test_digivault_available_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration.builtin import _digivault_available

    monkeypatch.delenv("DIGIVAULT_URL", raising=False)
    assert _digivault_available(_ctx()) is False

    monkeypatch.setenv("DIGIVAULT_URL", "http://digivault:8004")
    assert _digivault_available(_ctx()) is True


@pytest.mark.unit
def test_digivault_skill_hidden_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import builtin  # noqa: F401 - ensures skills are registered

    monkeypatch.delenv("DIGIVAULT_URL", raising=False)
    names = get_tools(["digivault"], _ctx(), mode=ToolExposureMode.SUMMARY)
    assert names == []


@pytest.mark.unit
def test_digivault_skill_exposed_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import builtin  # noqa: F401 - ensures skills are registered

    monkeypatch.setenv("DIGIVAULT_URL", "http://digivault:8004")
    with patch(
        "digigraph.orchestration.builtin.fetch_digivault_tool_dicts",
        return_value={
            "digivault_search_notes": {
                "type": "function",
                "function": {
                    "name": "digivault_search_notes",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        },
    ):
        tools = get_tools(["digivault"], _ctx(), mode=ToolExposureMode.DETAILED)
    assert [t["function"]["name"] for t in tools] == ["digivault_search_notes"]


@pytest.mark.unit
def test_schema_from_digivault_manifest_falls_back_on_error() -> None:
    from digigraph.orchestration.builtin import _schema_from_digivault_manifest

    with patch(
        "digigraph.orchestration.builtin.fetch_digivault_tool_dicts",
        side_effect=httpx.ConnectError("boom"),
    ):
        schema = _schema_from_digivault_manifest(_ctx())
    assert schema["function"]["name"] == "digivault_search_notes"
    assert schema["function"]["parameters"]["required"] == ["query"]


@pytest.mark.unit
def test_handle_digivault_search_requires_query() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    assert _handle_digivault_search({}, _ctx()) == "No search query provided."
    assert _handle_digivault_search({"query": "   "}, _ctx()) == "No search query provided."


@pytest.mark.unit
def test_handle_digivault_search_success() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    hit = {
        "vault_path": "digigraph",
        "title": "DigiGraph",
        "body_markdown": "LangGraph-based workflow engine.",
        "tags": ["core"],
        "rank": 0.8,
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": [hit]}},
    ) as mock_invoke:
        out = _handle_digivault_search({"query": "what does digigraph orchestrate"}, _ctx())

    assert isinstance(out, dict)
    assert out["results"] == [
        {
            "content": "LangGraph-based workflow engine.",
            "score": 0.8,
            "doc_id": "digigraph",
            "metadata": {"title": "DigiGraph", "tags": ["core"]},
        }
    ]
    assert json.loads(out["content"])["total"] == 1
    assert out["rag_sources"][0]["doc_id"] == "digigraph"
    mock_invoke.assert_called_once()
    call_kwargs = mock_invoke.call_args
    assert call_kwargs.args[1] == "digivault_search_notes"
    assert call_kwargs.args[2] == {"query": "what does digigraph orchestrate"}


@pytest.mark.unit
def test_handle_digivault_search_no_hits() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": []}},
    ):
        out = _handle_digivault_search({"query": "nonexistent topic"}, _ctx())
    assert out == "No matching documentation was found in the digivault for that query."


@pytest.mark.unit
def test_handle_digivault_search_invoke_error() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        out = _handle_digivault_search({"query": "anything"}, _ctx())
    assert "DigiVault orchestrator invoke failed" in out


@pytest.mark.unit
def test_handle_digivault_search_not_ok_response() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "vault unavailable"},
    ):
        out = _handle_digivault_search({"query": "anything"}, _ctx())
    assert json.loads(out)["error"] == "vault unavailable"
