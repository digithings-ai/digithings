"""Per-call web_search engine choice threaded through digigraph (#4722).

digisearch's hub ``web_search`` tool accepts ``provider`` (auto / internal /
exa / tavily / parallel / firecrawl / tinyfish), but digigraph never sent it —
every call ran ``auto`` (in-house). These tests pin the passthrough at every
seam: model tool-call arg → hub arguments, session default → tool call,
request ingress (body or X-Digi-Search-Engine) → graph state.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from digigraph.http_api.chat_resolve import _resolve_search_engine_chat
from digigraph.models import ChatCompletionRequest, WorkflowRequest
from digigraph.orchestration import web_search_tools
from digigraph.orchestration.registry import ToolContext
from digigraph.vertical_orchestrator import digisearch_hub
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit


def _context(**state: Any) -> ToolContext:
    base: dict[str, Any] = {"digi_bearer": "svc-jwt", "enable_web_search": True}
    base.update(state)
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state=base,
    )


def _capture_arguments(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the hub call and capture the outbound tool ``arguments``."""
    monkeypatch.setenv("DIGISEARCH_URL", "https://search.example.test")
    captured: dict[str, Any] = {}

    def _invoke(
        base_url: str, tool: str, arguments: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        captured.update(arguments)
        return {
            "ok": True,
            "data": {"results": [{"url": "https://a.com/1", "title": "t", "snippet": "s"}]},
        }

    monkeypatch.setattr(digisearch_hub, "invoke_digisearch_tool", _invoke)
    return captured


def test_provider_reaches_the_hub_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_arguments(monkeypatch)
    web_search_tools.call_digisearch_web_search("news", provider="exa", context=_context())
    assert captured["provider"] == "exa"


def test_provider_omitted_when_unset_auto_or_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent means hub default (auto); auto/blank are skipped, not forwarded."""
    for provider in (None, "auto", "AUTO", "  auto  ", "", "   "):
        captured = _capture_arguments(monkeypatch)
        web_search_tools.call_digisearch_web_search("news", provider=provider, context=_context())
        assert "provider" not in captured, provider


def test_tool_schema_advertises_provider() -> None:
    props = web_search_tools.WEB_SEARCH_TOOL["function"]["parameters"]["properties"]
    assert props["provider"]["type"] == "string"
    assert "auto" in props["provider"]["description"]


def test_handle_web_search_forwards_model_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph import llm_client as client

    seen: dict[str, object] = {}

    def fake_fetch(model: str, query: str, **kwargs: object) -> tuple[str, list[str]]:
        seen.update(kwargs)
        return "summary", ["https://a.com/1"]

    monkeypatch.setattr(client, "digifetch_web_search", fake_fetch)
    out = web_search_tools._handle_web_search({"query": "q", "provider": "tavily"}, _context())
    assert seen.get("provider") == "tavily"
    assert out["name"] == "web_search"


def test_handle_web_search_falls_back_to_session_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph import llm_client as client

    seen: dict[str, object] = {}

    def fake_fetch(model: str, query: str, **kwargs: object) -> tuple[str, list[str]]:
        seen.update(kwargs)
        return "summary", ["https://a.com/1"]

    monkeypatch.setattr(client, "digifetch_web_search", fake_fetch)
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_provider="exa"))
    assert seen.get("provider") == "exa"


def test_handle_web_search_passes_no_provider_when_neither_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph import llm_client as client

    seen: dict[str, object] = {}

    def fake_fetch(model: str, query: str, **kwargs: object) -> tuple[str, list[str]]:
        seen.update(kwargs)
        return "summary", ["https://a.com/1"]

    monkeypatch.setattr(client, "digifetch_web_search", fake_fetch)
    web_search_tools._handle_web_search({"query": "q"}, _context())
    assert seen.get("provider") is None


def test_digifetch_web_search_forwards_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import web_search_tools as ws_mod

    from digigraph import llm_client as client

    seen: dict[str, object] = {}

    def fake_tool(query: str, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"content": "c", "results": [{"doc_id": "https://ex.com/a", "content": "s"}]}

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_tool)
    client.digifetch_web_search("m", "q", provider="firecrawl")
    assert seen.get("provider") == "firecrawl"


def test_workflow_state_declares_web_search_provider() -> None:
    from digigraph.graph.state import WorkflowState

    assert "web_search_provider" in WorkflowState.__annotations__


def test_initial_graph_state_carries_web_search_provider() -> None:
    state = _initial_graph_state(WorkflowRequest(prompt="hi", search_engine="firecrawl"), "wf-wsp")
    assert state["web_search_provider"] == "firecrawl"
    cleared = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-wsp-2")
    assert cleared["web_search_provider"] is None


def _chat_req(**kwargs: Any) -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[{"role": "user", "content": "hi"}], **kwargs)


def test_resolve_search_engine_body_wins_over_header() -> None:
    req = _chat_req(search_engine="tavily")
    http = SimpleNamespace(headers={"X-Digi-Search-Engine": "exa"})
    assert _resolve_search_engine_chat(req, http) == "tavily"


def test_resolve_search_engine_falls_back_to_header() -> None:
    req = _chat_req()
    http = SimpleNamespace(headers={"X-Digi-Search-Engine": "exa"})
    assert _resolve_search_engine_chat(req, http) == "exa"


def test_resolve_search_engine_none_when_unset() -> None:
    req = _chat_req()
    assert _resolve_search_engine_chat(req, SimpleNamespace(headers={})) is None
    blank = _chat_req(search_engine="   ")
    assert _resolve_search_engine_chat(blank, SimpleNamespace(headers={})) is None
