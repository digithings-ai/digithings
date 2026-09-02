"""get_note rag_sources must carry capped ``body`` for digichat DocumentPane (#3419)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from digigraph.orchestration.registry import ToolContext
from digigraph.trace_events import (
    MAX_RAG_SOURCE_BODY_CHARS,
    rag_sources_from_results,
)

pytestmark = pytest.mark.unit


def _ctx(**overrides: object) -> ToolContext:
    defaults: dict[str, object] = {
        "session_id": "sess-1",
        "run_data_dir": None,
        "index_name": "default",
        "index_config": {},
        "state": {},
        "request_id": "rid-1",
        "vault_path_prefix": "clients/x",
    }
    defaults.update(overrides)
    return ToolContext(**defaults)  # type: ignore[arg-type]


def test_rag_sources_default_is_snippet_only() -> None:
    long = "# Note\n\n" + ("paragraph text. " * 40)
    items = rag_sources_from_results(
        [{"content": long, "doc_id": "clients/x/p001", "metadata": {"title": "Note"}}]
    )
    assert len(items) == 1
    assert items[0]["doc_id"] == "clients/x/p001"
    assert "body" not in items[0]
    assert items[0]["snippet"].endswith("…")
    assert len(items[0]["snippet"]) <= 400


def test_rag_sources_include_body_for_get_note_shape() -> None:
    """Real digivault_get_note result rows use content=body_markdown; include_body stamps it."""
    body = "# Auth plane\n\nRS256 tokens for digikey.\n\n" + ("more. " * 100)
    items = rag_sources_from_results(
        [
            {
                "content": body,
                "doc_id": "clients/digithings/auth__p001",
                "metadata": {"title": "Auth plane"},
            }
        ],
        include_body=True,
    )
    assert len(items) == 1
    hit = items[0]
    assert hit["doc_id"] == "clients/digithings/auth__p001"
    assert hit["body"] == body.strip()
    assert len(hit["body"]) > 400
    assert hit["snippet"].endswith("…")
    assert len(hit["snippet"]) <= 400


def test_rag_sources_body_is_capped() -> None:
    huge = "x" * (MAX_RAG_SOURCE_BODY_CHARS + 500)
    items = rag_sources_from_results(
        [{"content": huge, "doc_id": "clients/x/big"}],
        include_body=True,
    )
    assert len(items[0]["body"]) == MAX_RAG_SOURCE_BODY_CHARS


def test_get_note_handler_rag_sources_carry_body() -> None:
    """End-to-end: digivault_get_note return dict must expose body on rag_sources, not a UI stub."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    note = {
        "vault_path": "clients/x/p001",
        "title": "Hi",
        "body_markdown": "# Hi\n\nFull note body for the pane.",
        "tags": [],
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ):
        out = _handle_digivault_get_note({"vault_path": "clients/x/p001"}, _ctx())

    assert isinstance(out, dict)
    sources = out["rag_sources"]
    assert len(sources) == 1
    assert sources[0]["doc_id"] == "clients/x/p001"
    assert sources[0]["body"] == "# Hi\n\nFull note body for the pane."
    assert "snippet" in sources[0]
    # LLM payload still carries body_markdown; the trace item uses ``body``.
    payload = json.loads(out["content"])
    assert payload["body_markdown"] == "# Hi\n\nFull note body for the pane."
