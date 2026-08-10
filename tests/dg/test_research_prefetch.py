"""Unit tests for always_retrieve prefetch injection and research_brief gating."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from digigraph.graph import research as research_mod
from digigraph.graph.research_brief import research_brief_builder_node
from digigraph.project_config import DigiProjectConfig


@pytest.mark.unit
def test_format_prefetch_context_dict_and_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TOOL_MESSAGE_MAX_CHARS", "80")
    block = research_mod._format_prefetch_context(
        "digisearch",
        {"results": [{"content": "x" * 200}], "rag_sources": [{"source_id": "a"}]},
    )
    assert block.startswith("[digisearch results]\n")
    assert "truncated for LLM context" in block


@pytest.mark.unit
def test_strip_tools_by_name_openai_and_summary() -> None:
    tools = [
        {"type": "function", "function": {"name": "digisearch", "parameters": {}}},
        {"type": "function", "function": {"name": "todo", "parameters": {}}},
        "digivault_search_notes: vault search",
        "other: keep me",
    ]
    kept = research_mod._strip_tools_by_name(tools, {"digisearch", "digivault_search_notes"})
    names = [research_mod._tool_definition_name(t) for t in kept]
    assert names == ["todo", "other"]


@pytest.mark.unit
def test_research_brief_builder_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_RESEARCH_BRIEF", "0")
    with patch(
        "digigraph.graph.research_brief.completion_text",
        side_effect=AssertionError("brief LLM must not run"),
    ):
        out = research_brief_builder_node(
            {
                "research_response": "answer text",
                "rag_sources": [{"source_id": "s1"}],
                "prompt": "q",
            }
        )
    assert out == {}


@pytest.mark.unit
def test_document_rag_injects_prefetch_and_strips_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_RESEARCH_BRIEF", raising=False)
    cfg = DigiProjectConfig(
        {
            "agents": {
                "always_retrieve_tools": ["digisearch", "digivault_search_notes"],
                "enabled": ["research"],
            }
        }
    )
    state = {
        "prompt": "How is digichat built?",
        "session_id": "sess-1",
        "stored_datasets": {},
    }
    captured: dict = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **_kw):
        captured["tools"] = tools
        captured["user"] = messages[1]["content"]
        return "Grounded answer."

    mock_ctx = MagicMock()
    with (
        patch("digigraph.orchestration.ToolContext", return_value=mock_ctx),
        patch(
            "digigraph.skills.get_tools_for_skills",
            return_value=[
                {"type": "function", "function": {"name": "digisearch"}},
                {"type": "function", "function": {"name": "digivault_search_notes"}},
                {"type": "function", "function": {"name": "todo"}},
            ],
        ),
        patch("digigraph.orchestration.registry.has_tool", return_value=True),
        patch(
            "digigraph.orchestration.execute",
            side_effect=lambda name, args, context: {
                "content": f"hits from {name}",
                "rag_sources": [{"source_id": name}],
            },
        ),
        patch.object(research_mod, "run_tools", side_effect=fake_run_tools),
        patch.object(research_mod, "get_model_for_mode", return_value="test-model"),
    ):
        out = research_mod._run_document_rag_path(
            state=state,
            config=None,
            cfg=cfg,
            system_prompt="sys",
            index_name="digithings_docs",
            index_display_name="digithings_docs",
            prompt="How is digichat built?",
        )

    assert out["research_response"] == "Grounded answer."
    assert "[digisearch results]" in captured["user"]
    assert "[digivault_search_notes results]" in captured["user"]
    assert "User question:" in captured["user"]
    assert "How is digichat built?" in captured["user"]
    tool_names = [research_mod._tool_definition_name(t) for t in captured["tools"]]
    assert "digisearch" not in tool_names
    assert "digivault_search_notes" not in tool_names
    assert "todo" in tool_names
    assert out.get("rag_sources")


@pytest.mark.unit
def test_document_rag_empty_tools_still_calls_run_tools() -> None:
    cfg = DigiProjectConfig(
        {"agents": {"always_retrieve_tools": ["digisearch"], "enabled": ["research"]}}
    )
    state = {"prompt": "q", "session_id": "s", "stored_datasets": {}}
    captured: dict = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **_kw):
        captured["tools"] = tools
        return "Answer only."

    with (
        patch("digigraph.orchestration.ToolContext", return_value=MagicMock()),
        patch(
            "digigraph.skills.get_tools_for_skills",
            return_value=[{"type": "function", "function": {"name": "digisearch"}}],
        ),
        patch("digigraph.orchestration.registry.has_tool", return_value=True),
        patch(
            "digigraph.orchestration.execute",
            return_value={"content": "prefetch body", "rag_sources": []},
        ),
        patch.object(research_mod, "run_tools", side_effect=fake_run_tools),
        patch.object(research_mod, "get_model_for_mode", return_value="test-model"),
    ):
        out = research_mod._run_document_rag_path(
            state=state,
            config=None,
            cfg=cfg,
            system_prompt="sys",
            index_name="idx",
            index_display_name="idx",
            prompt="q",
        )

    assert captured["tools"] == []
    assert out["research_response"] == "Answer only."


@pytest.mark.unit
def test_document_rag_empty_allowlist_skips_prefetch() -> None:
    """``allowed_tool_names: []`` is deny-all — must not coerce to unrestricted None."""
    cfg = DigiProjectConfig(
        {
            "agents": {
                "always_retrieve_tools": ["digisearch", "digivault_search_notes"],
                "enabled": ["research"],
            }
        }
    )
    state = {
        "prompt": "q",
        "session_id": "s",
        "stored_datasets": {},
        "allowed_tool_names": [],
    }
    captured: dict = {}

    def capture_tools(skill_ids, context):
        captured["allowed"] = context.allowed_tool_names
        return [{"type": "function", "function": {"name": "digisearch"}}]

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **_kw):
        return "Answer only."

    with (
        patch("digigraph.skills.get_tools_for_skills", side_effect=capture_tools),
        patch("digigraph.orchestration.registry.has_tool", return_value=True),
        patch("digigraph.orchestration.execute") as exec_mock,
        patch.object(research_mod, "run_tools", side_effect=fake_run_tools),
        patch.object(research_mod, "get_model_for_mode", return_value="test-model"),
    ):
        out = research_mod._run_document_rag_path(
            state=state,
            config=None,
            cfg=cfg,
            system_prompt="sys",
            index_name="idx",
            index_display_name="idx",
            prompt="q",
        )

    exec_mock.assert_not_called()
    assert captured["allowed"] == frozenset()
    assert captured["allowed"] is not None
    assert out["research_response"] == "Answer only."
