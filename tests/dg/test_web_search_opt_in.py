"""Opt-in web_search tool allowlist (#3420)."""

from __future__ import annotations

import pytest
from digigraph.models import WorkflowRequest
from digigraph.orchestration import builtin  # noqa: F401 - registration
from digigraph.orchestration.registry import ToolContext, execute, get_tools
from digigraph.tool_policy import (
    WEB_SEARCH_TOOL_NAME,
    allowed_tool_names_for_workflow,
    apply_web_search_opt_in,
)

pytestmark = pytest.mark.unit


def test_apply_web_search_opt_in_default_off() -> None:
    base = frozenset({"digisearch", "digivault_search_notes", WEB_SEARCH_TOOL_NAME})
    assert WEB_SEARCH_TOOL_NAME not in apply_web_search_opt_in(base, enable_web_search=False)
    # Opt-in does not escalate — only keeps tools already allowlisted.
    assert WEB_SEARCH_TOOL_NAME in apply_web_search_opt_in(base, enable_web_search=True)
    no_web = frozenset({"digisearch"})
    assert WEB_SEARCH_TOOL_NAME not in apply_web_search_opt_in(no_web, enable_web_search=True)


def test_apply_web_search_opt_in_unrestricted_stays_none() -> None:
    assert apply_web_search_opt_in(None, enable_web_search=False) is None
    assert apply_web_search_opt_in(None, enable_web_search=True) is None


def test_allowed_tools_does_not_escalate_when_enabled() -> None:
    req = WorkflowRequest(prompt="x", allowed_tools=["digisearch"], enable_web_search=True)
    names = allowed_tool_names_for_workflow(req) or frozenset()
    assert WEB_SEARCH_TOOL_NAME not in names
    req2 = WorkflowRequest(
        prompt="x",
        allowed_tools=["digisearch", WEB_SEARCH_TOOL_NAME],
        enable_web_search=True,
    )
    assert WEB_SEARCH_TOOL_NAME in (allowed_tool_names_for_workflow(req2) or frozenset())
    req3 = WorkflowRequest(
        prompt="x",
        allowed_tools=["digisearch", WEB_SEARCH_TOOL_NAME],
        enable_web_search=False,
    )
    assert WEB_SEARCH_TOOL_NAME not in (allowed_tool_names_for_workflow(req3) or frozenset())


def test_web_search_handler_denies_when_disabled() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": False},
        allowed_tool_names=frozenset({WEB_SEARCH_TOOL_NAME}),
    )
    out = execute(WEB_SEARCH_TOOL_NAME, {"query": "news"}, ctx)
    assert isinstance(out, dict)
    assert out.get("error") == "tool_not_allowed"


def test_web_search_skill_hidden_unless_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://example.invalid:8002")
    ctx_off = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": False},
        allowed_tool_names=frozenset({"digisearch", WEB_SEARCH_TOOL_NAME}),
    )
    names_off = []
    for t in get_tools(["search", "web"], ctx_off):
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names_off.append(fn["name"])
    assert WEB_SEARCH_TOOL_NAME not in names_off

    ctx_on = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True},
        allowed_tool_names=frozenset({"digisearch", WEB_SEARCH_TOOL_NAME}),
    )
    names_on = []
    for t in get_tools(["search", "web"], ctx_on):
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names_on.append(fn["name"])
    assert WEB_SEARCH_TOOL_NAME in names_on


def test_handle_web_search_prefers_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import web_search_tools as mod

    ctx = type("C", (), {"state": {"enable_web_search": True}})()
    monkeypatch.setattr(
        mod,
        "_call_digisearch_web_search",
        lambda q, **k: {
            "content": "md bullets",
            "results": [
                {
                    "doc_id": "https://a.com/1",
                    "content": "md",
                    "rank": 0,
                    "metadata": {
                        "title": "A",
                        "source_url": "https://a.com/1",
                        "evidence_tier": "External",
                        "source_kind": "external",
                    },
                }
            ],
        },
    )
    out = mod._handle_web_search({"query": "etf flows"}, ctx)
    assert out["results"][0]["doc_id"] == "https://a.com/1"


def test_digifetch_web_search_forwards_tool_params(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import web_search_tools as ws_mod

    from digigraph import llm_client as client

    seen: dict[str, object] = {}

    def fake_tool(query: str, **kwargs: object) -> dict[str, object]:
        seen["query"] = query
        seen.update(kwargs)
        return {
            "content": "- [t](https://ex.com/a)",
            "results": [{"doc_id": "https://ex.com/a", "content": "s"}],
        }

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_tool)
    out = client.digifetch_web_search("test-model", "etf flows", include_domains=["a.com"])
    assert out == ("- s (https://ex.com/a)", ["https://ex.com/a"])
    assert seen["query"] == "etf flows"
    assert seen.get("include_domains") == ["a.com"]


def test_handle_web_search_import_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import web_search_tools as mod

    ctx = type("C", (), {"state": {"enable_web_search": True}})()

    def raise_import(*args: object, **kwargs: object) -> object:
        raise ImportError("no web-search extra")

    monkeypatch.setattr(mod, "_call_digisearch_web_search", raise_import)
    with pytest.raises(ImportError):
        mod._handle_web_search({"query": "etf flows"}, ctx)


def test_handle_web_search_tool_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import web_search_tools as mod
    from digigraph.vertical_orchestrator import digisearch_hub as hub

    ctx = type("C", (), {"state": {"enable_web_search": True}})()
    monkeypatch.setattr(
        hub,
        "invoke_digisearch_tool",
        lambda *args, **kwargs: {"ok": False, "error": "unavailable", "status": 503},
    )
    with pytest.raises(RuntimeError):
        mod._handle_web_search({"query": "etf flows"}, ctx)


def test_public_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import web_search_tools as mod

    seen: dict[str, object] = {}

    def fake_tool(query: str, **kwargs: object) -> dict[str, object]:
        seen["query"] = query
        seen.update(kwargs)
        return {"content": "ok", "results": []}

    monkeypatch.setattr(mod, "_call_digisearch_web_search", fake_tool)
    out = mod.call_digisearch_web_search(
        "etf flows",
        include_domains=["a.com"],
        exclude_domains=["b.com"],
        max_results=7,
    )
    assert out == {"content": "ok", "results": []}
    assert seen["query"] == "etf flows"
    assert seen.get("include_domains") == ["a.com"]
    assert seen.get("exclude_domains") == ["b.com"]
    assert seen.get("max_results") == 7


def test_web_search_handler_labels_external(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration import web_search_tools as mod

    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True},
        allowed_tool_names=frozenset({WEB_SEARCH_TOOL_NAME}),
    )
    monkeypatch.setattr(
        mod,
        "_call_digisearch_web_search",
        lambda *args, **kwargs: {
            "content": "- [t](https://ex.com/a)",
            "results": [{"doc_id": "https://ex.com/a", "content": "summary"}],
        },
    )
    out = execute(WEB_SEARCH_TOOL_NAME, {"query": "latest"}, ctx)
    assert isinstance(out, dict)
    sources = out.get("rag_sources") or []
    assert sources
    meta = sources[0].get("metadata") or {}
    assert meta.get("evidence_tier") == "External"
    assert meta.get("source_kind") == "external"
    # Corpus tools are not replaced — web only adds External rows.
    assert out.get("name") == WEB_SEARCH_TOOL_NAME
