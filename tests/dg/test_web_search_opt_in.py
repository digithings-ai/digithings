"""Opt-in web_search tool allowlist (#3420)."""

from __future__ import annotations

from unittest.mock import patch

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


def test_digifetch_web_search_passes_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph import llm_client as client

    calls: dict[str, str] = {}

    def fake_ground(model: str, query: str, *, usage_kind: str = "") -> object:
        calls["model"] = model
        calls["query"] = query
        calls["usage_kind"] = usage_kind
        return ("summary", ["https://ex.com/a"])

    monkeypatch.setattr(client, "_ground_via_completion", fake_ground)
    out = client.digifetch_web_search("test-model", "etf flows", include_domains=["a.com"])
    assert out == ("summary", ["https://ex.com/a"])
    assert calls["model"] == "test-model"
    assert "etf flows" in calls["query"]
    assert "a.com" in calls["query"]
    assert calls["usage_kind"] == "web_search"


def test_handle_web_search_import_error_falls_back_to_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import web_search_tools as mod

    ctx = type("C", (), {"state": {"enable_web_search": True}})()

    def raise_import(*args: object, **kwargs: object) -> object:
        raise ImportError("no web-search extra")

    monkeypatch.setattr(mod, "_call_digisearch_web_search", raise_import)
    with (
        patch("digigraph.model_config.get_grounding_model", return_value="m"),
        patch(
            "digigraph.llm_client.openrouter_web_search",
            return_value=("synth summary", ["https://ex.com/a"]),
        ),
        patch("digigraph.llm_client.web_search", return_value=None),
    ):
        out = mod._handle_web_search({"query": "etf flows"}, ctx)
    assert isinstance(out, dict)
    assert out["content"] == "synth summary"
    assert out["results"][0]["doc_id"] == "https://ex.com/a"
    assert out["name"] == WEB_SEARCH_TOOL_NAME


def test_handle_web_search_tool_error_falls_back_to_no_results(
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
    with (
        patch("digigraph.model_config.get_grounding_model", return_value="m"),
        patch("digigraph.llm_client.openrouter_web_search", return_value=None),
        patch("digigraph.llm_client.web_search", return_value=None),
    ):
        out = mod._handle_web_search({"query": "etf flows"}, ctx)
    assert isinstance(out, dict)
    assert out["content"] == "Web search returned no results."
    assert out["results"] == []
    assert out["rag_sources"] == []
    assert out["name"] == WEB_SEARCH_TOOL_NAME


def test_web_search_handler_labels_external(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True},
        allowed_tool_names=frozenset({WEB_SEARCH_TOOL_NAME}),
    )
    with (
        patch(
            "digigraph.model_config.get_grounding_model", return_value="openrouter/perplexity/sonar"
        ),
        patch(
            "digigraph.llm_client.openrouter_web_search",
            return_value=("summary", ["https://ex.com/a"]),
        ),
        patch("digigraph.llm_client.web_search", return_value=None),
    ):
        out = execute(WEB_SEARCH_TOOL_NAME, {"query": "latest"}, ctx)
    assert isinstance(out, dict)
    sources = out.get("rag_sources") or []
    assert sources
    meta = sources[0].get("metadata") or {}
    assert meta.get("evidence_tier") == "External"
    assert meta.get("source_kind") == "external"
    # Corpus tools are not replaced — web only adds External rows.
    assert out.get("name") == WEB_SEARCH_TOOL_NAME
