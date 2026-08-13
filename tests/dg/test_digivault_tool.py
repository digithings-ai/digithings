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
    """Important 1 (#2265 review): the fallback description must name the field the
    model actually receives from a digivault_search_notes hit (doc_id — see
    test_handle_digivault_search_success, whose payload never contains a literal
    "vault_path" key), and must warn off a digisearch hit's doc_id (a repo path,
    not a vault path) so digisearch results don't look loadable when they aren't."""
    from digigraph.orchestration.builtin import _schema_from_digivault_manifest

    with patch(
        "digigraph.orchestration.builtin.fetch_digivault_tool_dicts",
        side_effect=httpx.ConnectError("boom"),
    ):
        schema = _schema_from_digivault_manifest(_ctx(), "digivault_get_note")
    assert schema["function"]["name"] == "digivault_get_note"
    params = schema["function"]["parameters"]
    assert params["required"] == ["path_prefix"]
    assert "vault_path" in params["properties"]
    assert "vault_paths" in params["properties"]
    assert params["properties"]["vault_paths"]["type"] == "array"
    description = schema["function"]["description"]
    assert "doc_id" in description
    assert "digisearch" in description  # warns the model off digisearch's doc_id
    assert "vault_paths" in description


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
def test_search_hit_doc_id_feeds_get_note_vault_path_argument_shape() -> None:
    """Important 1 (#2265 review): the locate-then-load handoff, exercised end to
    end. The literal key "vault_path" never appears in what _handle_digivault_search
    returns to the LLM (confirmed below) — the model is expected to copy the hit's
    doc_id into digivault_get_note's vault_path argument instead (per the corrected
    tool description). Prove that value actually round-trips: a real
    _handle_digivault_search result's doc_id, fed straight into
    _handle_digivault_get_note's argument shape, produces a working call."""
    from digigraph.orchestration.builtin import (
        _handle_digivault_get_note,
        _handle_digivault_search,
    )

    hit = {
        "vault_path": "digigraph/ARCHITECTURE.md",
        "title": "digigraph architecture",
        "body_markdown": "Excerpt only, not the full note.",
        "tags": ["core"],
        "rank": 0.9,
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": [hit]}},
    ):
        search_out = _handle_digivault_search({"query": "digigraph architecture"}, _ctx())

    assert isinstance(search_out, dict)
    preview = json.loads(search_out["content"])["preview"]
    assert "vault_path" not in preview[0]  # the literal key the model is NOT given
    doc_id = search_out["results"][0]["doc_id"]
    assert doc_id == "digigraph/ARCHITECTURE.md"

    note = {
        "vault_path": doc_id,
        "title": "digigraph architecture",
        "summary": "Orchestration layer overview.",
        "body_markdown": "# digigraph\n\nFull note body, not an excerpt.",
        "tags": ["core"],
    }
    ctx = _ctx(vault_path_prefix="clients/digithings")
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ) as mock_invoke:
        # This is the argument shape the model builds from a search hit: doc_id
        # copied verbatim into vault_path.
        get_out = _handle_digivault_get_note({"vault_path": doc_id}, ctx)

    assert isinstance(get_out, dict)
    call_args = mock_invoke.call_args
    assert call_args.args[1] == "digivault_get_note"
    assert call_args.args[2]["vault_path"] == "digigraph/ARCHITECTURE.md"
    assert (
        json.loads(get_out["content"])["body_markdown"]
        == "# digigraph\n\nFull note body, not an excerpt."
    )


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
    # Zero-hit case is a dict (not a bare string) so execute_search can attach
    # hit_count=0/query for the activity trace; the model-facing text is unchanged.
    assert out == {
        "content": "No matching documentation was found in the digivault for that query.",
        "results": [],
        "rag_sources": [],
    }


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
    """Generic ok=False passthrough — distinct from the no-context-prefix case
    below, so this uses a context that *has* a mapped tenant prefix (the
    no-context branch is Important-2's special-cased actionable message, tested
    separately)."""
    from digigraph.orchestration.builtin import _handle_digivault_search

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "vault unavailable"},
    ):
        out = _handle_digivault_search(
            {"query": "anything"}, _ctx(vault_path_prefix="clients/digithings")
        )
    assert json.loads(out)["error"] == "vault unavailable"


@pytest.mark.unit
def test_handle_digivault_search_no_context_prefix_error_is_actionable() -> None:
    """Important 2 (#2240 final-branch review): when there is no context prefix
    (unmapped tenant slug — e.g. `tenantSlug: "embed"` in
    frontend/digichat/src/lib/embed-chat-tenant.ts, absent from
    DIGI_TENANT_CORPUS_MAP), relaying digivault's raw "path_prefix is required"
    sentence is unactionable: the model already supplied path_prefix (the schema
    marks it required) and this handler is the one that discarded it. Driving the
    real tool loop before this fix cost 5 completions / 4 digivault round-trips
    to produce nothing, because the model kept retrying something outside its
    control. The handler must substitute an instruction the model can actually
    follow: stop retrying, this session has no tenant corpus. Mirrors
    _handle_digivault_get_note's equivalent no-context-prefix test."""
    from digigraph.orchestration.builtin import _handle_digivault_search

    ctx = _ctx(vault_path_prefix=None)
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={
            "ok": False,
            "error": "path_prefix is required when the D1 backend is configured",
        },
    ) as mock_invoke:
        out = _handle_digivault_search(
            {"query": "anything", "path_prefix": "clients/digithings"}, ctx
        )

    call_args = mock_invoke.call_args
    assert call_args.args[2]["path_prefix"] is None
    error = json.loads(out)["error"]
    assert "path_prefix is required when the D1 backend is configured" not in error
    assert "no tenant corpus" in error.lower()
    assert "do not retry" in error.lower()


@pytest.mark.unit
def test_handle_digivault_search_no_context_prefix_but_different_error_passes_through() -> None:
    """#2295 review: the "no tenant corpus" substitution must key on digivault's
    actual returned error, not on `context.vault_path_prefix is None` alone — a
    digivault outage, an expired D1 token, or a malformed D1_DATABASE_MAP can also
    return ok=False while vault_path_prefix happens to be None (an unmapped tenant
    session hitting a broken backend). That must surface its own error so whoever
    debugs it isn't misdirected toward "add a tenant mapping" for an infra fault."""
    from digigraph.orchestration.builtin import _handle_digivault_search

    ctx = _ctx(vault_path_prefix=None)
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "d1 search failed (503): upstream timeout"},
    ):
        out = _handle_digivault_search({"query": "anything"}, ctx)

    error = json.loads(out)["error"]
    assert error == "d1 search failed (503): upstream timeout"
    assert "no tenant corpus" not in error.lower()


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
    """Generic ok=False passthrough — distinct from the no-context-prefix case
    below, so this uses a context that *has* a mapped tenant prefix (the
    no-context branch is Minor-7's special-cased actionable message, tested
    separately)."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "vault unavailable"},
    ):
        out = _handle_digivault_get_note(
            {"vault_path": "digigraph/ARCHITECTURE.md"},
            _ctx(vault_path_prefix="clients/digithings"),
        )
    assert json.loads(out)["error"] == "vault unavailable"


@pytest.mark.unit
def test_handle_digivault_get_note_overwrites_model_supplied_path_prefix() -> None:
    """Security: a model-supplied path_prefix must never reach digivault. Like
    `_handle_digivault_search` (see
    `test_handle_digivault_search_overwrites_model_supplied_path_prefix`), this
    handler overwrites path_prefix unconditionally from
    `context.vault_path_prefix` so a model cannot pick its own tenant scope —
    #2240 extended the search handler to match this handler's mandatory
    overwrite, replacing its earlier default-if-missing behavior."""
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
    refuses the read (ok=False), not a client-side fallback.

    Minor 7 (#2265 review): digivault's own "path_prefix is required" sentence is
    unactionable here — the model *did* supply path_prefix (the schema marks it
    required); this handler is the one that discarded it. Relaying that sentence
    verbatim would make the model retry against something it cannot control,
    burning the 4-round tool budget. The handler must substitute an instruction the
    model can actually follow: stop trying, this session has no tenant corpus."""
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
    error = json.loads(out)["error"]
    assert "path_prefix is required for digivault_get_note" not in error
    assert "no tenant corpus" in error.lower()
    assert "do not retry" in error.lower()


@pytest.mark.unit
def test_handle_digivault_get_note_no_context_prefix_but_different_error_passes_through() -> None:
    """#2295 review: the "no tenant corpus" substitution must key on digivault's
    actual returned error, not on `context.vault_path_prefix is None` alone — a
    digivault outage, an expired D1 token, or a malformed D1_DATABASE_MAP can also
    return ok=False while vault_path_prefix happens to be None (an unmapped tenant
    session hitting a broken backend). That must surface its own error so whoever
    debugs it isn't misdirected toward "add a tenant mapping" for an infra fault."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    ctx = _ctx(vault_path_prefix=None)
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": False, "error": "d1 query failed (503): upstream timeout"},
    ):
        out = _handle_digivault_get_note({"vault_path": "digigraph/ARCHITECTURE.md"}, ctx)

    error = json.loads(out)["error"]
    assert error == "d1 query failed (503): upstream timeout"
    assert "no tenant corpus" not in error.lower()


@pytest.mark.unit
def test_handle_digivault_search_marks_truncated_excerpts() -> None:
    """#2306: a clipped excerpt must be labelled as data, not implied by a trailing
    "...". In production the model got the right note back, saw its body cut at 300
    chars immediately before the STRIDE table's first row, judged the excerpt
    sufficient, never called digivault_get_note, and answered wrong. The ellipsis is
    the only signal the old payload carried and it is indistinguishable from ordinary
    prose punctuation, so a model cannot act on it."""
    from digigraph.orchestration.builtin import _LLM_SEARCH_PREVIEW_CHARS, _handle_digivault_search

    long_body = "### STRIDE table\n\n" + ("x" * (_LLM_SEARCH_PREVIEW_CHARS + 500))
    hit = {
        "vault_path": "clients/digithings/security__stride",
        "title": "Security",
        "body_markdown": long_body,
        "tags": ["security"],
        "rank": 0.9,
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": {"hits": [hit]}},
    ):
        out = _handle_digivault_search({"query": "stride table"}, _ctx())

    assert isinstance(out, dict)
    payload = json.loads(out["content"])
    assert payload["excerpts_truncated"] is True
    # The row the model reads must carry the flag, next to the doc_id it needs to pass.
    row = payload["preview"][0]
    assert row["truncated"] is True
    assert row["doc_id"] == "clients/digithings/security__stride"
    # And the payload must name the required follow-up action explicitly.
    assert "digivault_get_note" in payload["next_step"]
    assert "doc_id" in payload["next_step"]
    # results/ rag_sources keep the FULL body -- only the LLM preview is clipped.
    assert out["results"][0]["content"] == long_body


@pytest.mark.unit
def test_handle_digivault_search_does_not_mark_untruncated_excerpts() -> None:
    """The truncation signal must not cry wolf: a note that fits inside the preview
    budget is complete, and flagging it would push the model into a pointless second
    round on every short note, burning its 4-round budget."""
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
    ):
        out = _handle_digivault_search({"query": "what does digigraph orchestrate"}, _ctx())

    assert isinstance(out, dict)
    payload = json.loads(out["content"])
    assert "excerpts_truncated" not in payload
    assert "next_step" not in payload
    assert "truncated" not in payload["preview"][0]


@pytest.mark.unit
def test_handle_digivault_get_note_surfaces_segment_identity() -> None:
    """#2306, one layer down: most of this corpus is not whole documents.

    1190/1279 digithings notes and 300/328 OCC notes are one page or section of a larger
    source. Loading "the whole note" therefore routinely hands the model one page of
    forty with nothing saying so, and a table continuing onto the next page reads as a
    complete table — the same wrong-answer shape as the excerpt bug. Surface the segment
    identity so the model can tell, and so "go read the neighbouring page" is actionable.
    """
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    note = {
        "vault_path": "clients/online-compliance-center/handbook__p013",
        "title": "Handbook",
        "summary": "Page 13",
        "tags": ["occ"],
        "body_markdown": "| step | action |\n| 1 | begin |",
        "parent_doc": "clients/online-compliance-center/handbook",
        "segment_index": 13,
        "segment_label": "p013",
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ):
        out = _handle_digivault_get_note({"vault_path": note["vault_path"]}, _ctx())

    payload = json.loads(out["content"])
    assert payload["parent_doc"] == "clients/online-compliance-center/handbook"
    assert payload["segment_index"] == 13
    assert payload["segment_label"] == "p013"


@pytest.mark.unit
def test_handle_digivault_get_note_omits_segment_keys_for_whole_documents() -> None:
    """A note that is a whole document must not gain empty segment keys — their presence
    is the signal, so emitting them as null would make every note look like a fragment."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    note = {
        "vault_path": "clients/digithings/readme",
        "title": "Readme",
        "summary": "",
        "tags": [],
        "body_markdown": "Whole document.",
        "parent_doc": None,
        "segment_index": None,
        "segment_label": None,
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ):
        out = _handle_digivault_get_note({"vault_path": note["vault_path"]}, _ctx())

    payload = json.loads(out["content"])
    for key in ("parent_doc", "segment_index", "segment_label"):
        assert key not in payload


@pytest.mark.unit
def test_handle_digivault_get_note_batch_happy_path() -> None:
    """vault_paths (plural) fetches several notes in one call. content is
    {"notes": [...]}, one payload per note, and results/rag_sources carry one entry
    per note — so a later frontend change can group them, per the design that
    motivated this: the digichat activity UI groups repeated tool calls by
    (toolName, query), and every vault_path is a different query, so N separate
    single-path calls always render as N separate rows no matter what."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    batch_data = {
        "notes": [
            {
                "vault_path": "clients/digithings/arch__p001",
                "title": "Arch p1",
                "summary": "",
                "tags": [],
                "body_markdown": "page one",
                "parent_doc": "clients/digithings/arch",
                "segment_index": 1,
                "segment_label": "p001",
            },
            {
                "vault_path": "clients/digithings/arch__p002",
                "title": "Arch p2",
                "summary": "",
                "tags": [],
                "body_markdown": "page two",
                "parent_doc": "clients/digithings/arch",
                "segment_index": 2,
                "segment_label": "p002",
            },
        ],
        "errors": {},
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": batch_data},
    ) as mock_invoke:
        out = _handle_digivault_get_note(
            {"vault_paths": ["clients/digithings/arch__p001", "clients/digithings/arch__p002"]},
            _ctx(),
        )

    payload = json.loads(out["content"])
    assert "errors" not in payload  # empty errors dict must not be forwarded as noise
    assert [n["vault_path"] for n in payload["notes"]] == [
        "clients/digithings/arch__p001",
        "clients/digithings/arch__p002",
    ]
    assert payload["notes"][0]["segment_label"] == "p001"
    assert len(out["results"]) == 2
    assert len(out["rag_sources"]) == 2
    # digigraph must forward vault_paths as-is, not collapse it back to vault_path.
    call_args = mock_invoke.call_args.args[2]
    assert call_args["vault_paths"] == [
        "clients/digithings/arch__p001",
        "clients/digithings/arch__p002",
    ]
    assert "vault_path" not in call_args


@pytest.mark.unit
def test_handle_digivault_get_note_batch_surfaces_partial_errors() -> None:
    """One bad path in a batch must not hide the notes that DID load — the model
    needs both the good notes and which path(s) failed, in the same message."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    batch_data = {
        "notes": [
            {
                "vault_path": "clients/digithings/arch__p001",
                "title": "Arch p1",
                "summary": "",
                "tags": [],
                "body_markdown": "page one",
            }
        ],
        "errors": {
            "clients/digithings/arch__p999": "note not found: clients/digithings/arch__p999"
        },
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": batch_data},
    ):
        out = _handle_digivault_get_note(
            {"vault_paths": ["clients/digithings/arch__p001", "clients/digithings/arch__p999"]},
            _ctx(),
        )

    payload = json.loads(out["content"])
    assert len(payload["notes"]) == 1
    assert payload["errors"] == {
        "clients/digithings/arch__p999": "note not found: clients/digithings/arch__p999"
    }
    assert len(out["results"]) == 1


@pytest.mark.unit
def test_handle_digivault_get_note_batch_all_paths_failed() -> None:
    """Every path in the batch missing must still return a readable payload (empty
    notes, full errors dict), not a bare unhelpful string — the model needs to know
    WHICH paths failed and why, not just that nothing came back."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    batch_data = {
        "notes": [],
        "errors": {"clients/digithings/x": "note not found: clients/digithings/x"},
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": batch_data},
    ):
        out = _handle_digivault_get_note({"vault_paths": ["clients/digithings/x"]}, _ctx())

    assert isinstance(out, dict)
    payload = json.loads(out["content"])
    assert payload["notes"] == []
    assert payload["errors"] == {"clients/digithings/x": "note not found: clients/digithings/x"}


@pytest.mark.unit
def test_handle_digivault_get_note_single_path_ignores_stray_vault_paths_key() -> None:
    """Regression pin: an absent/empty vault_paths must not accidentally flip a
    normal single-path call into the batch code path."""
    from digigraph.orchestration.builtin import _handle_digivault_get_note

    note = {
        "vault_path": "clients/digithings/arch",
        "title": "Arch",
        "summary": "",
        "tags": [],
        "body_markdown": "hello",
    }
    with patch(
        "digigraph.orchestration.builtin.invoke_digivault_tool",
        return_value={"ok": True, "data": note},
    ) as mock_invoke:
        out = _handle_digivault_get_note(
            {"vault_path": "clients/digithings/arch", "vault_paths": []}, _ctx()
        )

    payload = json.loads(out["content"])
    assert payload["vault_path"] == "clients/digithings/arch"
    assert "notes" not in payload
    call_args = mock_invoke.call_args.args[2]
    assert call_args["vault_path"] == "clients/digithings/arch"
