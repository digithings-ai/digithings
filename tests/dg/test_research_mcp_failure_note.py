"""The note that tells the model an integration is unreachable (DIG-5187)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from digigraph.graph import research as research_mod
from digigraph.graph.research import mcp_failure_note
from digigraph.orchestration import mcp_client
from digigraph.project_config import DigiProjectConfig


@pytest.mark.unit
def test_mcp_failure_note_names_the_unreachable_server() -> None:
    note = mcp_failure_note({"helpdesk": "RuntimeError: connection refused"})
    assert "helpdesk" in note
    assert "unavailable" in note.lower()


@pytest.mark.unit
def test_mcp_failure_note_keeps_the_reason_out_of_the_prompt() -> None:
    note = mcp_failure_note({"helpdesk": "RuntimeError: https://internal.example/mcp"})
    assert "internal.example" not in note


# --- The turn path: the note only exists if the wiring exists --------------
#
# The two tests below are the acceptance of DIG-5187 on the request path. A
# server that cannot be listed must reach the model as an outage, and a healthy
# server must leave the turn byte-identical. They fail if the note is not
# prepended to the user message, and if the failure is read before the listing
# that records it.


_SERVER = {"id": "helpdesk", "url": "https://mcp.example.test/mcp"}
_PROMPT = "How many open tickets are there?"


def _catalog() -> list[dict[str, Any]]:
    """What a healthy list_tools answers: the offered name plus its raw sidecar."""
    return [
        {
            "type": "function",
            "function": {
                "name": "helpdesk_search",
                "description": "search the helpdesk",
                "parameters": {"type": "object", "properties": {}},
            },
            mcp_client._RAW_TOOL_NAME_KEY: "search",
        }
    ]


def _mcp_tools_for_skills(skill_ids, context, *args: object, **kwargs: object):
    """The registry's own MCP merge (registry.get_tools), nothing else.

    Only the operator MCP servers are of interest here; the corpus skills are
    irrelevant to the question and would need a live digisearch.
    """
    from digigraph.orchestration.mcp_client import openai_tools_for_servers

    return list(openai_tools_for_servers(context.extra_mcp_servers or []))


def _run_turn(state: dict[str, Any]) -> dict[str, Any]:
    cfg = DigiProjectConfig({"agents": {"enabled": ["research"]}})
    captured: dict[str, Any] = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **kw):
        captured["tools"] = tools
        captured["user"] = "\n\n".join(
            str(m.get("content") or "")
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        )
        return "answer"

    def exploding_execute(name, args, context=None):
        raise AssertionError(f"no tool may run in this test: {name}")

    with (
        patch("digigraph.skills.get_tools_for_skills", _mcp_tools_for_skills),
        patch.object(research_mod, "run_tools", fake_run_tools),
        patch("digigraph.orchestration.execute", exploding_execute),
    ):
        research_mod._run_document_rag_path(
            state=state,
            cfg=cfg,
            system_prompt="You are the helpdesk assistant.",
            index_name="default",
            index_display_name="default",
            prompt=_PROMPT,
        )
    return captured


def _tool_names(tools: list[dict[str, Any]]) -> list[str]:
    return [str((t.get("function") or {}).get("name") or "") for t in tools]


def _state_with_server(server: dict[str, str]) -> dict[str, Any]:
    return {
        "prompt": _PROMPT,
        "session_id": "sess-1",
        "stored_datasets": {},
        "mcp_servers": [dict(server)],
    }


@pytest.mark.unit
def test_an_unreachable_mcp_server_is_named_in_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The request path must say the integration is down, not that data is absent."""
    monkeypatch.setattr("digigraph.run_storage.get_run_data_dir", lambda: None)

    def boom(_server: dict[str, str]) -> list[dict[str, Any]]:
        raise RuntimeError("HTTP 421 Misdirected Request")

    monkeypatch.setattr(mcp_client, "_list_tools_async", boom)
    monkeypatch.setattr(mcp_client, "_cache", {})
    monkeypatch.setattr(mcp_client, "_failures", {})

    captured = _run_turn(_state_with_server(_SERVER))

    user = captured["user"]
    assert "Unreachable integrations" in user
    assert "helpdesk" in user
    # The reason stays in the log: a prompt must never carry an internal URL.
    assert "421" not in user
    # The server offered no tool, so the note is the only signal there is.
    assert "helpdesk_search" not in _tool_names(captured["tools"])


@pytest.mark.unit
def test_a_healthy_mcp_server_leaves_the_turn_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server that answers must not cost the turn a single character."""
    monkeypatch.setattr("digigraph.run_storage.get_run_data_dir", lambda: None)

    async def healthy(_server: dict[str, str]) -> list[dict[str, Any]]:
        return _catalog()

    monkeypatch.setattr(mcp_client, "_list_tools_async", healthy)
    monkeypatch.setattr(mcp_client, "_cache", {})
    monkeypatch.setattr(mcp_client, "_failures", {})

    server = dict(_SERVER)
    server["allowedTools"] = ["search"]
    captured = _run_turn(_state_with_server(server))

    assert captured["user"] == _PROMPT
    assert "Unreachable integrations" not in captured["user"]
    assert "helpdesk_search" in _tool_names(captured["tools"])
