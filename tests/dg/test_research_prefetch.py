"""Unit tests for the document-RAG tool loop (model-driven retrieval, no prefetch)
and research_brief gating."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digigraph.graph import research as research_mod
from digigraph.graph.research_brief import research_brief_builder_node
from digigraph.project_config import DigiProjectConfig


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
def test_document_rag_hands_tools_to_the_model_and_does_not_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model must choose retrieval itself: no prefetch call before run_tools,
    no injected "already fetched" context, and an explicit 4-round budget.

    ``always_retrieve_tools`` is still set here (matching production digiproject.yaml
    configs) precisely so that, against the old prefetch code, this reproduces the
    exact regression: ``execute`` would be called for "digisearch" before the model
    ever asked. ``research_node`` itself swallows that AssertionError in its broad
    except-Exception wrapper, so this calls ``_run_document_rag_path`` directly
    (as the tests it replaces already did) to let the assertion surface.
    """
    monkeypatch.delenv("DIGI_RESEARCH_BRIEF", raising=False)
    cfg = DigiProjectConfig(
        {
            "agents": {
                "enabled": ["research"],
                "always_retrieve_tools": ["digisearch"],
            }
        }
    )
    state = {"prompt": "How is digichat built?", "session_id": "sess-1", "stored_datasets": {}}
    captured: dict = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **kw):
        captured["tools"] = tools
        captured["user"] = messages[1]["content"]
        captured["max_tool_rounds"] = kw.get("max_tool_rounds")
        return "answer"

    def exploding_execute(name, args, context=None):
        raise AssertionError(f"no retrieval may run before the model asks: {name}")

    with (
        patch(
            "digigraph.skills.get_tools_for_skills",
            return_value=[
                {"type": "function", "function": {"name": "digisearch"}},
                {"type": "function", "function": {"name": "digivault_search_notes"}},
            ],
        ),
        patch.object(research_mod, "run_tools", fake_run_tools),
        patch("digigraph.orchestration.execute", exploding_execute),
    ):
        research_mod._run_document_rag_path(
            state=state,
            config=None,
            cfg=cfg,
            system_prompt="You have digisearch. Use it and summarize.",
            index_name="default",
            index_display_name="default",
            prompt="How is digichat built?",
        )

    names = [research_mod._tool_name(t) for t in captured["tools"]]
    assert "digisearch" in names
    assert "digivault_search_notes" in names
    # The prefetch used to paste results into the user turn; nothing may do that now.
    assert "already fetched" not in captured["user"]
    assert captured["max_tool_rounds"] == 4
