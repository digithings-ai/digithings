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
    base = frozenset({"digisearch", "digivault_search_notes"})
    assert WEB_SEARCH_TOOL_NAME not in apply_web_search_opt_in(base, enable_web_search=False)
    assert WEB_SEARCH_TOOL_NAME in apply_web_search_opt_in(base, enable_web_search=True)


def test_apply_web_search_opt_in_unrestricted_stays_none() -> None:
    assert apply_web_search_opt_in(None, enable_web_search=False) is None
    assert apply_web_search_opt_in(None, enable_web_search=True) is None


def test_allowed_tools_union_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ALLOWED_TOOLS", raising=False)
    req_off = WorkflowRequest(prompt="x", allowed_tools=["digisearch"], enable_web_search=False)
    assert WEB_SEARCH_TOOL_NAME not in (allowed_tool_names_for_workflow(req_off) or frozenset())
    req_on = WorkflowRequest(prompt="x", allowed_tools=["digisearch"], enable_web_search=True)
    assert WEB_SEARCH_TOOL_NAME in (allowed_tool_names_for_workflow(req_on) or frozenset())


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
