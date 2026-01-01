"""Unit tests for retrieval helpers: force-tool aliases, vault paths, query display."""

from __future__ import annotations

import json

import pytest
from digigraph.retrieval import (
    GET_NOTE_BATCH_MAX,
    GET_NOTE_TOOL,
    force_tool_messages,
    query_from_tool_args,
    resolve_force_tool,
    vault_paths_from_retrieval,
)

pytestmark = pytest.mark.unit


def test_resolve_force_tool_public_aliases() -> None:
    assert resolve_force_tool("search") == "digisearch"
    assert resolve_force_tool("digisearch") == "digisearch"
    assert resolve_force_tool("docs") == "digivault_search_notes"
    assert resolve_force_tool("digivault") == "digivault_search_notes"
    assert resolve_force_tool("/search") == "digisearch"
    assert resolve_force_tool("DIGISEARCH") == "digisearch"


def test_resolve_force_tool_rejects_unknown() -> None:
    assert resolve_force_tool(None) is None
    assert resolve_force_tool("") is None
    assert resolve_force_tool("web_search") is None
    assert resolve_force_tool("digivault_get_note") is None


def test_query_from_tool_args_prefers_query_then_paths() -> None:
    assert query_from_tool_args({"query": "RS256 JWT"}) == "RS256 JWT"
    assert query_from_tool_args({"vault_path": "clients/x/p001"}) == "clients/x/p001"
    assert query_from_tool_args({"vault_paths": ["a", "b", "c"]}) == "3 notes"
    assert query_from_tool_args({}) is None


def test_vault_paths_from_digisearch_use_metadata_vault_path_not_doc_id() -> None:
    result = {
        "rag_sources": [
            {
                "doc_id": "repo://digithings/docs/auth.md",
                "metadata": {"vault_path": "clients/digithings/auth__p001"},
            },
            {
                "doc_id": "repo://digithings/docs/jwt.md",
                "metadata": {"vault_path": "clients/digithings/jwt__p001"},
            },
        ]
    }
    assert vault_paths_from_retrieval("digisearch", result) == [
        "clients/digithings/auth__p001",
        "clients/digithings/jwt__p001",
    ]


def test_vault_paths_from_digivault_search_use_doc_id() -> None:
    result = {
        "rag_sources": [
            {"doc_id": "clients/x/p001", "metadata": {"title": "A"}},
            {"doc_id": "clients/x/p002", "metadata": {"title": "B"}},
        ]
    }
    assert vault_paths_from_retrieval("digivault_search_notes", result) == [
        "clients/x/p001",
        "clients/x/p002",
    ]


def test_vault_paths_cap_at_batch_max_and_dedupe() -> None:
    sources = [
        {"doc_id": f"clients/x/p{i:03d}", "metadata": {}} for i in range(GET_NOTE_BATCH_MAX + 5)
    ]
    sources.append({"doc_id": "clients/x/p000", "metadata": {}})
    paths = vault_paths_from_retrieval("digivault_search_notes", {"rag_sources": sources})
    assert len(paths) == GET_NOTE_BATCH_MAX
    assert paths[0] == "clients/x/p000"
    assert len(set(paths)) == GET_NOTE_BATCH_MAX


def test_vault_paths_empty_when_search_has_no_loadable_path() -> None:
    result = {
        "rag_sources": [
            {"doc_id": "repo://digithings/docs/auth.md", "metadata": {"title": "Auth"}},
        ]
    }
    assert vault_paths_from_retrieval("digisearch", result) == []


def test_force_tool_messages_use_the_user_string_as_the_tool_argument() -> None:
    msgs = force_tool_messages(
        "digisearch",
        "RS256 token exchange",
        {"content": '{"preview": []}', "rag_sources": []},
    )
    assert msgs[0]["role"] == "assistant"
    call = msgs[0]["tool_calls"][0]
    assert call["function"]["name"] == "digisearch"
    assert '"RS256 token exchange"' in call["function"]["arguments"]
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["tool_call_id"] == call["id"]
    # No instruction text — the user string is the argument, nothing else.
    assert "please" not in call["function"]["arguments"].lower()
    assert GET_NOTE_TOOL not in call["function"]["name"]


def test_auto_load_notes_calls_get_note_with_batch_and_distinct_query() -> None:
    from digigraph.retrieval import auto_load_notes

    emitted: list[tuple[str, dict]] = []
    locate = {
        "content": '{"preview": [{"doc_id": "clients/x/p001"}]}',
        "rag_sources": [{"doc_id": "clients/x/p001", "metadata": {}}],
    }

    def execute_fn(name: str, args: dict):
        assert name == GET_NOTE_TOOL
        assert args == {"vault_paths": ["clients/x/p001"]}
        return {
            "content": '{"notes": [{"vault_path": "clients/x/p001", "body_markdown": "# Hi"}]}',
            "rag_sources": [{"doc_id": "clients/x/p001"}],
        }

    merged = auto_load_notes(
        locate_tool="digivault_search_notes",
        locate_result=locate,
        execute_fn=execute_fn,
        emit=lambda t, d: emitted.append((t, d)),
        allowed_names=None,
    )
    assert emitted[0][0] == "tool_call"
    assert emitted[0][1]["name"] == GET_NOTE_TOOL
    assert emitted[1][0] == "tool_result"
    assert emitted[1][1]["query"] == "1 note"
    parsed = json.loads(merged["content"])
    assert parsed["notes_already_loaded"] is True


def test_auto_load_notes_skips_when_tool_not_allowed() -> None:
    from digigraph.retrieval import auto_load_notes

    locate = {
        "rag_sources": [{"doc_id": "clients/x/p001", "metadata": {}}],
        "content": "{}",
    }
    called: list[str] = []
    out = auto_load_notes(
        locate_tool="digivault_search_notes",
        locate_result=locate,
        execute_fn=lambda n, a: called.append(n) or {},
        emit=lambda *_: None,
        allowed_names=frozenset({"digisearch"}),
    )
    assert called == []
    assert out is locate


def test_merge_loaded_notes_stamps_body_onto_matching_locate_source() -> None:
    from digigraph.retrieval import merge_loaded_notes

    locate = {
        "content": '{"preview": []}',
        "rag_sources": [
            {
                "doc_id": "clients/x/p001",
                "snippet": "# Hi…",
                "metadata": {"title": "Hi"},
            }
        ],
    }
    note = {
        "content": '{"notes": []}',
        "rag_sources": [
            {
                "doc_id": "clients/x/p001",
                "snippet": "# Hi…",
                "body": "# Hi\n\nFull note for DocumentPane.",
            }
        ],
    }
    merged = merge_loaded_notes(locate, note)
    assert merged["rag_sources"][0]["body"] == "# Hi\n\nFull note for DocumentPane."
    assert merged["rag_sources"][0]["snippet"] == "# Hi…"


def test_workflow_state_declares_force_tool() -> None:
    from digigraph.graph.state import WorkflowState

    assert "force_tool" in WorkflowState.__annotations__


def test_initial_graph_state_carries_force_tool() -> None:
    from digigraph.models import WorkflowRequest
    from digigraph.workflow import _initial_graph_state

    state = _initial_graph_state(WorkflowRequest(prompt="hi", force_tool="digisearch"), "wf-ft")
    assert state["force_tool"] == "digisearch"


def test_initial_graph_state_sets_force_tool_to_none_when_unset() -> None:
    from digigraph.models import WorkflowRequest
    from digigraph.workflow import _initial_graph_state

    state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-ft-2")
    assert "force_tool" in state
    assert state["force_tool"] is None


def test_digi_fields_from_request_reads_force_tool_header() -> None:
    from types import SimpleNamespace

    from digigraph.server import _digi_fields_from_request

    request = SimpleNamespace(state=SimpleNamespace(), headers={"x-digi-force-tool": "docs"})
    updates = _digi_fields_from_request(request)
    assert updates["force_tool"] == "digivault_search_notes"


def test_digi_fields_from_request_omits_unknown_force_tool() -> None:
    from types import SimpleNamespace

    from digigraph.server import _digi_fields_from_request

    request = SimpleNamespace(state=SimpleNamespace(), headers={"x-digi-force-tool": "web_search"})
    updates = _digi_fields_from_request(request)
    assert "force_tool" not in updates


def test_resolve_force_tool_chat_from_body_then_header() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_force_tool_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return "docs" if name == "X-Digi-Force-Tool" else None

    class _Req:
        headers = _Headers()

    body = ChatCompletionRequest(messages=[], force_tool="search")
    assert _resolve_force_tool_chat(body, _Req()) == "digisearch"
    empty = ChatCompletionRequest(messages=[])
    assert _resolve_force_tool_chat(empty, _Req()) == "digivault_search_notes"


def test_research_node_injects_force_tool_then_synthesizes_with_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#3418: /search injects the user string as the tool argument; the model is
    not hinted. Auto second-hop loads notes so it does not ask permission."""
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    executed: list[tuple[str, dict]] = []

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        executed.append((name, args))
        if name == "digisearch":
            return {
                "content": '{"preview": [{"doc_id": "clients/x/p001"}]}',
                "rag_sources": [
                    {"doc_id": "clients/x/p001", "metadata": {"vault_path": "clients/x/p001"}}
                ],
            }
        if name == "digivault_get_note":
            return {
                "content": '{"notes": [{"vault_path": "clients/x/p001", "body_markdown": "# Hi"}]}',
                "rag_sources": [{"doc_id": "clients/x/p001", "body_markdown": "# Hi"}],
            }
        return {"content": "{}"}

    captured: dict = {}

    def fake_run_tools(*, messages: list, tool_choice: str = "auto", **_kwargs: object) -> str:
        captured["messages"] = messages
        captured["tool_choice"] = tool_choice
        return "RS256 is used for token exchange."

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])

    from digigraph.graph.research import research_node

    out = research_node({"prompt": "RS256 token exchange", "force_tool": "digisearch"})
    assert out.get("research_response") == "RS256 is used for token exchange."
    assert executed[0][0] == "digisearch"
    assert executed[0][1] == {"query": "RS256 token exchange"}
    assert executed[1][0] == "digivault_get_note"
    assert executed[1][1] == {"vault_paths": ["clients/x/p001"]}
    assert captured["tool_choice"] == "auto"
    assistant = next(m for m in captured["messages"] if m.get("role") == "assistant")
    call = assistant["tool_calls"][0]
    assert call["function"]["name"] == "digisearch"
    assert json.loads(call["function"]["arguments"]) == {"query": "RS256 token exchange"}
    assert "please" not in call["function"]["arguments"].lower()
    tool_msg = next(m for m in captured["messages"] if m.get("role") == "tool")
    parsed = json.loads(tool_msg["content"])
    assert parsed["notes_already_loaded"] is True


def test_research_node_force_tool_uses_last_user_turn_not_flattened_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#3418: a follow-up /search must query the current user string, not the
    User:/Assistant: transcript messages_to_workflow_prompt builds for the LLM."""
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    executed: list[tuple[str, dict]] = []

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        executed.append((name, args))
        return {"content": "{}", "rag_sources": []}

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr(
        "digigraph.graph.research.run_tools",
        lambda **_k: "ok",
    )
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])

    from digigraph.chat_prompt import messages_to_workflow_prompt
    from digigraph.graph.research import research_node
    from digigraph.models import ChatMessage

    prompt = messages_to_workflow_prompt(
        [
            ChatMessage(role="user", content="What is RS256?"),
            ChatMessage(role="assistant", content="RS256 is an asymmetric signing algorithm."),
            ChatMessage(role="user", content="RS256 token exchange"),
        ]
    )
    research_node({"prompt": prompt, "force_tool": "digisearch"})
    assert executed[0][0] == "digisearch"
    assert executed[0][1] == {"query": "RS256 token exchange"}
    assert "What is RS256" not in executed[0][1]["query"]
    assert "Assistant:" not in executed[0][1]["query"]


def test_research_node_force_tool_keeps_auto_even_when_require_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    captured: dict = {}

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        return {"content": "{}", "rag_sources": []}

    def fake_run_tools(*, tool_choice: str = "auto", **_kwargs: object) -> str:
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])

    from digigraph.graph.research import research_node

    research_node(
        {
            "prompt": "RS256",
            "force_tool": "digisearch",
            "require_tool_calls": True,
        }
    )
    assert captured["tool_choice"] == "auto"


def test_research_node_skips_force_tool_when_not_in_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenants with an allowlist must not get a fake Searching… row from
    X-Digi-Force-Tool when the forced tool is excluded — even though execute()
    would deny it, the inject path still emitted tool_call + deny blob."""
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    executed: list[str] = []
    stream_events: list[tuple[str, object]] = []

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        executed.append(name)
        return {"error": "tool_not_allowed", "tool": name, "message": "denied"}

    def fake_run_tools(*, messages: list, **_kwargs: object) -> str:
        return "ok"

    def fake_writer(event: tuple[str, object]) -> None:
        stream_events.append(event)

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])
    monkeypatch.setattr("digigraph.graph.research._safe_stream_writer", lambda: fake_writer)

    from digigraph.graph.research import research_node

    research_node(
        {
            "prompt": "RS256 token exchange",
            "force_tool": "digisearch",
            "allowed_tool_names": ["visualization_agent"],
        }
    )
    assert executed == []
    assert not any(kind == "tool_call" for kind, _ in stream_events)


def test_research_node_force_tool_injects_when_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    executed: list[str] = []

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        executed.append(name)
        return {"content": "{}", "rag_sources": []}

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr("digigraph.graph.research.run_tools", lambda **_k: "ok")
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])

    from digigraph.graph.research import research_node

    research_node(
        {
            "prompt": "RS256",
            "force_tool": "digisearch",
            "allowed_tool_names": ["digisearch", "digivault_get_note"],
        }
    )
    assert executed[0] == "digisearch"


def test_research_node_auto_loads_notes_on_model_driven_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    executed: list[str] = []

    def fake_execute(name: str, args: dict, _context: object) -> dict:
        executed.append(name)
        if name == "digivault_search_notes":
            return {
                "content": "{}",
                "rag_sources": [{"doc_id": "clients/x/p001", "metadata": {}}],
            }
        if name == "digivault_get_note":
            return {
                "content": '{"notes": [{"vault_path": "clients/x/p001"}]}',
                "rag_sources": [{"doc_id": "clients/x/p001"}],
            }
        return {"content": "{}"}

    def fake_run_tools(*, execute_tool, **_kwargs: object) -> str:
        result = execute_tool("digivault_search_notes", {"query": "auth"})
        parsed = json.loads(result["content"]) if isinstance(result, dict) else {}
        assert parsed.get("notes_already_loaded") is True
        return "ok"

    monkeypatch.setattr("digigraph.orchestration.execute", fake_execute)
    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    monkeypatch.setattr("digigraph.skills.get_tools_for_skills", lambda *_a, **_k: [])

    from digigraph.graph.research import research_node

    research_node({"prompt": "how does auth work"})
    assert "digivault_search_notes" in executed
    assert "digivault_get_note" in executed
