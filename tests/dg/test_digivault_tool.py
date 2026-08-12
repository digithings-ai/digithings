"""Unit tests for the digivault_search_notes orchestrator tool (builtin.py wiring)."""

from __future__ import annotations

import json
from pathlib import Path
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
def test_digivault_available_reads_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from digigraph.orchestration.builtin import _digivault_available

    empty_cfg = tmp_path / "no-vault.yaml"
    empty_cfg.write_text("services:\n  digivault_url: ''\n")
    monkeypatch.delenv("DIGIVAULT_URL", raising=False)
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(empty_cfg))
    assert _digivault_available(_ctx()) is False

    monkeypatch.setenv("DIGIVAULT_URL", "http://digivault:8004")
    assert _digivault_available(_ctx()) is True


@pytest.mark.unit
def test_digivault_available_reads_project_config_when_env_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from digigraph.orchestration.builtin import _digivault_available

    cfg_file = tmp_path / "dogfood.yaml"
    cfg_file.write_text("services:\n  digivault_url: http://from-project:8004\n")
    monkeypatch.delenv("DIGIVAULT_URL", raising=False)
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg_file))
    assert _digivault_available(_ctx()) is True


@pytest.mark.unit
def test_digivault_skill_hidden_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from digigraph.orchestration import builtin  # noqa: F401 - ensures skills are registered

    empty_cfg = tmp_path / "no-vault.yaml"
    empty_cfg.write_text("services:\n  digivault_url: ''\n")
    monkeypatch.delenv("DIGIVAULT_URL", raising=False)
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(empty_cfg))
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
            },
            "digivault_get_note": {
                "type": "function",
                "function": {
                    "name": "digivault_get_note",
                    "description": "get note",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        },
    ):
        tools = get_tools(["digivault"], _ctx(), mode=ToolExposureMode.DETAILED)
    assert [t["function"]["name"] for t in tools] == [
        "digivault_search_notes",
        "digivault_get_note",
    ]


@pytest.mark.unit
def test_schema_from_digivault_manifest_falls_back_on_error() -> None:
    from digigraph.orchestration.builtin import _schema_from_digivault_manifest

    with patch(
        "digigraph.orchestration.builtin.fetch_digivault_tool_dicts",
        side_effect=httpx.ConnectError("boom"),
    ):
        schema = _schema_from_digivault_manifest(_ctx(), "digivault_search_notes")
    assert schema["function"]["name"] == "digivault_search_notes"
    assert schema["function"]["parameters"]["required"] == ["query"]


@pytest.mark.unit
def test_digivault_get_note_is_registered() -> None:
    from digigraph.orchestration import builtin  # noqa: F401 - triggers registration

    assert has_tool("digivault_get_note")


@pytest.mark.unit
def test_schema_from_digivault_manifest_get_note_falls_back_on_error() -> None:
    from digigraph.orchestration.builtin import _schema_from_digivault_manifest

    with patch(
        "digigraph.orchestration.builtin.fetch_digivault_tool_dicts",
        side_effect=httpx.ConnectError("boom"),
    ):
        schema = _schema_from_digivault_manifest(_ctx(), "digivault_get_note")
    assert schema["function"]["name"] == "digivault_get_note"
    assert schema["function"]["parameters"]["required"] == ["vault_path", "path_prefix"]


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
        "title": "digigraph",
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
            "metadata": {"title": "digigraph", "tags": ["core"]},
        }
    ]
    assert json.loads(out["content"])["total"] == 1
    assert out["rag_sources"][0]["doc_id"] == "digigraph"
    mock_invoke.assert_called_once()
    call_kwargs = mock_invoke.call_args
    assert call_kwargs.args[1] == "digivault_search_notes"
    assert call_kwargs.args[2] == {
        "query": "what does digigraph orchestrate",
        "path_prefix": None,
    }


@pytest.mark.unit
def test_handle_digivault_search_overwrites_model_supplied_path_prefix() -> None:
    """Security (#2265): a model-supplied path_prefix must never reach digivault
    unchecked. This mirrors the mandatory fix on _handle_digivault_get_note — the
    judgement call in the task brief was made in favor of closing this the same way
    here, since this is the tool actually reachable today."""
    from digigraph.orchestration.builtin import _handle_digivault_search

    ctx = _ctx(vault_path_prefix="clients/digithings")
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": []}},
    ) as mock_invoke:
        _handle_digivault_search(
            {"query": "anything", "path_prefix": "clients/online-compliance-center"}, ctx
        )

    call_args = mock_invoke.call_args
    assert call_args.args[2]["path_prefix"] == "clients/digithings"


@pytest.mark.unit
def test_handle_digivault_search_no_context_prefix_passes_none() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    ctx = _ctx(vault_path_prefix=None)
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": []}},
    ) as mock_invoke:
        _handle_digivault_search({"query": "anything", "path_prefix": "clients/digithings"}, ctx)

    call_args = mock_invoke.call_args
    assert call_args.args[2]["path_prefix"] is None


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
    assert "digivault orchestrator invoke failed" in out


@pytest.mark.unit
def test_handle_digivault_search_not_ok_response() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_search

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "vault unavailable"},
    ):
        out = _handle_digivault_search({"query": "anything"}, _ctx())
    assert json.loads(out)["error"] == "vault unavailable"


@pytest.mark.unit
def test_invoke_digivault_tool_ok_false_message_survives_the_http_hop() -> None:
    """#2239 second review: `invoke_digivault_tool` calls `raise_for_status()`, and
    `str(httpx.HTTPStatusError)` drops the response body — so a *raised* 400 from
    digivault's `path_prefix is required` case would reach the model as a bare status
    code, never the actionable sentence (see `_handle_digivault_search`'s
    `except _ORCHESTRATOR_CLIENT_ERRORS` branch, which only has `str(e)` to work
    with). This exercises the real `httpx` call — via `MockTransport`, not a mock of
    `invoke_digivault_tool` itself — to prove digivault's `ok=False`-over-HTTP-200
    convention is what actually gets the reason string through this hop: 200 never
    triggers `raise_for_status()`, so the JSON body (and its `error` string) survives
    intact."""
    from digigraph.vertical_orchestrator import digivault_hub

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": False,
                "service": "digivault",
                "tool": "digivault_search_notes",
                "error": "path_prefix is required when the D1 backend is configured",
            },
        )

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    with patch.object(digivault_hub, "sync_client", fake_sync_client):
        result = digivault_hub.invoke_digivault_tool(
            "http://digivault:8004",
            "digivault_search_notes",
            {"query": "jwt"},
            bearer_token=None,
            request_id="rid-1",
        )

    assert result["ok"] is False
    assert result["error"] == "path_prefix is required when the D1 backend is configured"


@pytest.mark.unit
def test_handle_digivault_get_note_requires_vault_path() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    assert _handle_digivault_get_note({}, _ctx()) == "vault_path is required."
    assert _handle_digivault_get_note({"vault_path": "   "}, _ctx()) == "vault_path is required."


@pytest.mark.unit
def test_handle_digivault_get_note_success() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    note = {
        "vault_path": "digigraph/ARCHITECTURE.md",
        "title": "digigraph architecture",
        "summary": "Orchestration layer overview.",
        "body_markdown": "# digigraph\n\nFull note body, not an excerpt.",
        "tags": ["core"],
        "wikilinks": [],
    }
    ctx = _ctx(vault_path_prefix="clients/digithings")
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ) as mock_invoke:
        out = _handle_digivault_get_note({"vault_path": "digigraph/ARCHITECTURE.md"}, ctx)

    assert isinstance(out, dict)
    content = json.loads(out["content"])
    assert content["body_markdown"] == "# digigraph\n\nFull note body, not an excerpt."
    assert out["results"] == [
        {
            "content": "# digigraph\n\nFull note body, not an excerpt.",
            "score": None,
            "doc_id": "digigraph/ARCHITECTURE.md",
            "metadata": {"title": "digigraph architecture", "tags": ["core"]},
        }
    ]
    assert out["rag_sources"][0]["doc_id"] == "digigraph/ARCHITECTURE.md"
    mock_invoke.assert_called_once()
    call_args = mock_invoke.call_args
    assert call_args.args[1] == "digivault_get_note"
    assert call_args.args[2] == {
        "vault_path": "digigraph/ARCHITECTURE.md",
        "path_prefix": "clients/digithings",
    }


@pytest.mark.unit
def test_handle_digivault_get_note_not_found() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": None},
    ):
        out = _handle_digivault_get_note(
            {"vault_path": "nope"}, _ctx(vault_path_prefix="clients/digithings")
        )
    assert out == "Note not found."


@pytest.mark.unit
def test_handle_digivault_get_note_invoke_error() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        out = _handle_digivault_get_note(
            {"vault_path": "digigraph/ARCHITECTURE.md"},
            _ctx(vault_path_prefix="clients/digithings"),
        )
    assert "digivault orchestrator invoke failed" in out


@pytest.mark.unit
def test_handle_digivault_get_note_not_ok_response() -> None:
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "path_prefix is required for digivault_get_note"},
    ):
        out = _handle_digivault_get_note({"vault_path": "digigraph/ARCHITECTURE.md"}, _ctx())
    assert json.loads(out)["error"] == "path_prefix is required for digivault_get_note"


@pytest.mark.unit
def test_handle_digivault_get_note_overwrites_model_supplied_path_prefix() -> None:
    """Security: a model-supplied path_prefix must never reach digivault. Unlike
    `_handle_digivault_search`, which only *defaults* the prefix when the model omits
    it (leaving a model-supplied value free to cross tenants), this handler must
    overwrite unconditionally so a model cannot pick its own tenant scope."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    ctx = _ctx(vault_path_prefix="clients/digithings")
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"vault_path": "x", "body_markdown": "y"}},
    ) as mock_invoke:
        _handle_digivault_get_note(
            {
                "vault_path": "digigraph/ARCHITECTURE.md",
                "path_prefix": "clients/online-compliance-center",
            },
            ctx,
        )

    call_args = mock_invoke.call_args
    assert call_args.args[2]["path_prefix"] == "clients/digithings"


@pytest.mark.unit
def test_handle_digivault_get_note_no_context_prefix_does_not_fall_back_unscoped() -> None:
    """When there is no context prefix (unmapped tenant slug), the handler must still
    overwrite — passing None through — rather than leaving a model-supplied prefix in
    place or inventing an unscoped default. digivault's own handler is the one that
    refuses the read (ok=False), not a client-side fallback."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    ctx = _ctx(vault_path_prefix=None)
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "path_prefix is required for digivault_get_note"},
    ) as mock_invoke:
        out = _handle_digivault_get_note(
            {"vault_path": "digigraph/ARCHITECTURE.md", "path_prefix": "clients/digithings"},
            ctx,
        )

    call_args = mock_invoke.call_args
    assert call_args.args[2]["path_prefix"] is None
    assert json.loads(out)["error"] == "path_prefix is required for digivault_get_note"
