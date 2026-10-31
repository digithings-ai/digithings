"""Pinned-tenant open-page mode of ``web_search`` (``url`` argument).

Only a pinned tenant's ``web_search`` definition offers ``url``; it reads one
page inside the tenant's sites. The digisearch hub is faked; the fence on every
redirect hop is covered in ``digisearch/tests/test_web_fetch_fence.py``. Here:
the digigraph-side gate, the second check on the final URL and links, the tool
surface, the research node's tool list, and that unpinned tenants are untouched.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any
from unittest.mock import patch
from urllib.parse import SplitResult, urlsplit

import digigraph.orchestration.builtin  # noqa: F401  (registers web_search)
import pytest
from digigraph.orchestration import web_search_tools
from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.web_search_tools import (
    WEB_SEARCH_TOOL,
    WEB_SEARCH_TOOL_NAME,
    _handle_web_search,
    url_within_pins,
    web_search_tool_for_tenant,
)
from digigraph.tool_policy import (
    allowed_tool_names_for_workflow,
    apply_web_search_opt_in,
    expand_disabled_tool_tokens,
    strip_web_search_tools,
)

pytestmark = pytest.mark.unit

PINS = [
    "example-client.test",
    "linkedin.com/company/exampleclient",
    "linkedin.com/posts/exampleclient_*",
    "x.com/exampleclientinc",
    "play.google.com/store/apps/details?id=test.exampleclient.myapp",
]


_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")


def _urls_in(text: str) -> list[SplitResult]:
    """Every absolute http(s) URL in ``text``, parsed."""
    return [urlsplit(m.group(0)) for m in _URL_RE.finditer(text)]


def _context(**state: Any) -> ToolContext:
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True, **state},
    )


class _FakeHub:
    def __init__(self, reply: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.replies = list(reply) if isinstance(reply, list) else None
        self.reply = reply
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, base: str, tool: str, arguments: dict[str, Any], **_: Any) -> Any:
        self.calls.append((tool, arguments))
        if self.replies is not None:
            return self.replies.pop(0)
        return self.reply


def _patch_hub(monkeypatch: pytest.MonkeyPatch, reply: Any) -> _FakeHub:
    import digigraph.vertical_orchestrator.digisearch_hub as hub

    fake = _FakeHub(reply)
    monkeypatch.setattr(hub, "invoke_digisearch_tool", fake)
    monkeypatch.setattr(web_search_tools, "_digisearch_service_base", lambda: "http://ds.test")
    return fake


class _FakeSearch:
    """``digifetch_web_search`` stand-in: one row per URL, url_filter applied."""

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls
        self.calls: list[dict[str, Any]] = []

    def __call__(self, model: str, query: str, **kwargs: Any) -> tuple[str, list[str]]:
        self.calls.append(kwargs)
        keep = kwargs.get("url_filter") or (lambda u: True)
        urls = [u for u in self.urls if keep(u)]
        return "\n".join(f"- page ({u})" for u in urls), urls


def _patch_search(monkeypatch: pytest.MonkeyPatch, fake: _FakeSearch) -> None:
    import digigraph.llm_client as llm_client

    monkeypatch.setattr(llm_client, "digifetch_web_search", fake)


def _page(final_url: str, links: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "url": final_url,
            "final_url": final_url,
            "title": "Academy",
            "content": "Full page text. " * 300,
            "truncated": False,
            "links": links or [],
            "source": "live",
            **extra,
        },
    }


# --- open-page mode ----------------------------------------------------------


def test_open_reads_a_subdomain_page_and_lists_in_fence_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = _patch_hub(
        monkeypatch,
        _page(
            "https://academy.example-client.test/courses",
            links=[
                "https://fr.academy.example-client.test/",
                "https://www.linkedin.com/in/someone",  # dropped: outside the path pin
                "https://evilexample-client.test/",  # dropped: look-alike
            ],
        ),
    )
    ctx = _context(web_search_domains=PINS, web_search_page_corpus="exampleclient")
    out = _handle_web_search({"url": "academy.example-client.test/courses"}, ctx)
    assert isinstance(out, dict) and "error" not in out
    tool, args = hub.calls[0]
    assert tool == WEB_SEARCH_TOOL_NAME
    assert args["url"] == "https://academy.example-client.test/courses"
    assert args["fence"] == PINS
    assert args["page_corpus"] == "exampleclient"
    assert "query" not in args
    assert out["name"] == WEB_SEARCH_TOOL_NAME
    assert out["links"] == ["https://fr.academy.example-client.test/"]
    assert len(out["content"]) > 4000  # the full page, not a snippet
    # Compare parsed hosts and paths, never substrings of the page text: a
    # substring test would also pass for a look-alike host.
    content_urls = {(u.hostname, u.path) for u in _urls_in(out["content"])}
    assert ("fr.academy.example-client.test", "/") in content_urls
    assert ("www.linkedin.com", "/in/someone") not in content_urls
    assert out["rag_sources"]


def test_search_then_open_a_result_then_follow_an_in_fence_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole loop a pinned tenant runs: search, open a hit, follow a link."""
    search = _FakeSearch(
        [
            "https://www.example-client.test/modules/",
            "https://evilexample-client.test/modules/",  # look-alike: filtered out
        ]
    )
    _patch_search(monkeypatch, search)
    hub = _patch_hub(
        monkeypatch,
        [
            _page(
                "https://www.example-client.test/modules/",
                links=[
                    "https://academy.example-client.test/courses/intro",
                    "https://en.wikipedia.org/wiki/Camp",  # out of fence: stripped
                ],
            ),
            _page("https://academy.example-client.test/courses/intro"),
        ],
    )
    ctx = _context(web_search_domains=PINS)

    found = _handle_web_search({"query": "modules"}, ctx)
    assert isinstance(found, dict) and "error" not in found
    hit_hosts = [u.hostname for u in _urls_in(found["content"])]
    assert "www.example-client.test" in hit_hosts
    assert "evilexample-client.test" not in hit_hosts

    opened = _handle_web_search({"url": "https://www.example-client.test/modules/"}, ctx)
    assert isinstance(opened, dict) and "error" not in opened
    assert opened["links"] == ["https://academy.example-client.test/courses/intro"]
    assert ("en.wikipedia.org", "/wiki/Camp") not in {
        (u.hostname, u.path) for u in _urls_in(opened["content"])
    }

    followed = _handle_web_search({"url": opened["links"][0]}, ctx)
    assert isinstance(followed, dict) and "error" not in followed
    assert [a["url"] for _, a in hub.calls] == [
        "https://www.example-client.test/modules/",
        "https://academy.example-client.test/courses/intro",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://example-client.test.evil.com/",
        "https://evilexample-client.test/",
        "https://exampleclient.test/",
        "https://example-client.test.example/",
        "https://en.wikipedia.org/wiki/ExampleClient",
        "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/company/exampleclientx",
        "https://www.linkedin.com/company/exampleclient/../othercorp",
        "https://www.linkedin.com/company/exampleclient/%2e%2e/othercorp",
        "https://twitter.com/exampleclientinc",
    ],
)
def test_open_outside_the_fence_is_refused_without_calling_digisearch(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    hub = _patch_hub(monkeypatch, _page(url))
    out = _handle_web_search({"url": url}, _context(web_search_domains=PINS))
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://example-client.test/",
        "https://www.example-client.test/",
        "https://academy.example-client.test/",
        "https://fr.academy.example-client.test/x",
    ],
)
def test_open_admits_the_pinned_host_and_its_subdomains(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    hub = _patch_hub(monkeypatch, _page(url))
    out = _handle_web_search({"url": url}, _context(web_search_domains=PINS))
    assert isinstance(out, dict) and "error" not in out
    assert len(hub.calls) == 1


def test_final_url_outside_the_fence_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, _page("https://exampleclient.helpdesk-vendor.test/login"))
    out = _handle_web_search(
        {"url": "https://support.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert "redirected" in out["message"]


def test_digisearch_fence_refusal_maps_to_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, {"ok": False, "error": "fence_refused: outside the allowed sites"})
    out = _handle_web_search(
        {"url": "https://support.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"


def test_open_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, {"ok": False, "error": "open page failed: bot challenge"})
    out = _handle_web_search(
        {"url": "https://www.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and out["error"] == "fetch_failed"


def test_saved_copy_is_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, _page("https://www.example-client.test/", source="page_corpus"))
    out = _handle_web_search(
        {"url": "https://www.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and "Saved copy" in out["content"]


def test_empty_pin_refuses_open_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _patch_hub(monkeypatch, _page("https://example.com/"))
    out = _handle_web_search({"url": "https://example.com/"}, _context(web_search_domains=[]))
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


def test_unpinned_session_ignores_url_exactly_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _patch_hub(monkeypatch, _page("https://example.com/"))
    search = _FakeSearch(["https://example.com/a"])
    _patch_search(monkeypatch, search)
    # url alone: still "no query", no page opened.
    assert _handle_web_search({"url": "https://example.com/"}, _context()) == (
        "No search query provided."
    )
    # url with a query: an ordinary open-web search, url ignored.
    out = _handle_web_search({"query": "q", "url": "https://example.com/"}, _context())
    assert isinstance(out, dict) and "error" not in out
    assert hub.calls == []
    assert len(search.calls) == 1 and "url_filter" not in search.calls[0]


def test_open_mode_needs_the_web_search_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _patch_hub(monkeypatch, _page("https://www.example-client.test/"))
    ctx = _context(web_search_domains=PINS)
    ctx.state["enable_web_search"] = False
    out = _handle_web_search({"url": "https://www.example-client.test/"}, ctx)
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


# --- tool surface ------------------------------------------------------------


def test_url_property_only_in_the_pinned_definition() -> None:
    assert "url" not in WEB_SEARCH_TOOL["function"]["parameters"]["properties"]
    assert WEB_SEARCH_TOOL["function"]["parameters"]["required"] == ["query"]
    assert web_search_tool_for_tenant(None, None) is None
    assert web_search_tool_for_tenant([], None) is None
    tool = web_search_tool_for_tenant(PINS, None)
    assert tool is not None
    params = tool["function"]["parameters"]
    assert params["properties"]["url"]["type"] == "string"
    assert params["required"] == []
    desc = tool["function"]["description"]
    assert "subdomains" in desc and "url" in desc and "web_fetch" not in desc
    # The shared definition is never mutated by building a pinned one.
    assert "url" not in WEB_SEARCH_TOOL["function"]["parameters"]["properties"]


def test_site_map_is_a_starting_guide(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.web_search_sites import WEB_SEARCH_SITES_DIR_ENV

    (tmp_path / "acme.md").write_text("/a/ - page a\n")
    monkeypatch.setenv(WEB_SEARCH_SITES_DIR_ENV, str(tmp_path))
    tool = web_search_tool_for_tenant(PINS, "acme")
    assert tool is not None
    desc = tool["function"]["description"]
    assert "starting guide, not a limit" in desc and "/a/ - page a" in desc


def test_one_tool_in_the_policy_and_the_disable_header() -> None:
    names = frozenset({"digisearch", "web_search"})
    # No sibling tool rides along: the allowlist is just web_search.
    assert apply_web_search_opt_in(names, enable_web_search=True) == names
    assert apply_web_search_opt_in(names, enable_web_search=False) == {"digisearch"}
    assert strip_web_search_tools(frozenset({"web_search", "x"})) == {"x"}
    # Disabling web_search (X-Digi-Disabled-Tools) removes open-page mode too:
    # there is no other tool left that could open a page.
    disabled = expand_disabled_tool_tokens(["web_search"])
    assert WEB_SEARCH_TOOL_NAME in disabled


# --- research node: what the model is offered --------------------------------


def _research_tools(state: dict[str, Any]) -> list[dict[str, Any]]:
    from digigraph.graph import research as research_mod
    from digigraph.project_config import DigiProjectConfig

    cfg = DigiProjectConfig({"agents": {"enabled": ["research"]}, "skills": {"enabled": ["web"]}})
    captured: dict[str, Any] = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **kw):
        captured["tools"] = tools
        return "answer"

    with patch.object(research_mod, "run_tools", fake_run_tools):
        research_mod._run_document_rag_path(
            state={"prompt": "p", "session_id": "s", "stored_datasets": {}, **state},
            cfg=cfg,
            system_prompt="sys",
            index_name="default",
            index_display_name="default",
            prompt="p",
        )
    return captured["tools"]


def _by_name(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str((t.get("function") or {}).get("name")): t for t in tools}


def test_research_unpinned_session_gets_the_shared_definition_byte_identical() -> None:
    shared = json.dumps(copy.deepcopy(WEB_SEARCH_TOOL), sort_keys=True)
    unpinned = _by_name(_research_tools({"enable_web_search": True}))
    assert json.dumps(unpinned[WEB_SEARCH_TOOL_NAME], sort_keys=True) == shared
    assert "url" not in unpinned[WEB_SEARCH_TOOL_NAME]["function"]["parameters"]["properties"]
    assert "web_fetch" not in unpinned
    pinned = _by_name(_research_tools({"enable_web_search": True, "web_search_domains": PINS}))
    # Same tool list; only the web_search definition differs (url mode + pins).
    assert sorted(pinned) == sorted(unpinned)
    assert "url" in pinned[WEB_SEARCH_TOOL_NAME]["function"]["parameters"]["properties"]


def test_research_disabled_web_search_offers_no_url_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from digigraph.project_config import DigiProjectConfig

    monkeypatch.delenv("DIGI_ALLOWED_TOOLS", raising=False)
    # The X-Digi-Disabled-Tools path: the request's disabled list narrows the
    # allowlist the research node builds its tools from.
    req = SimpleNamespace(
        allowed_tools=None, enable_web_search=True, disabled_tools=["web_search"], force_tool=None
    )
    allowed = allowed_tool_names_for_workflow(req, DigiProjectConfig({}))  # type: ignore[arg-type]
    assert allowed is not None and WEB_SEARCH_TOOL_NAME not in allowed
    tools = _by_name(
        _research_tools(
            {
                "enable_web_search": True,
                "web_search_domains": PINS,
                "allowed_tool_names": sorted(allowed),
            }
        )
    )
    # web_search is the only tool that can open a page; once disabled it is gone.
    assert WEB_SEARCH_TOOL_NAME not in tools
    assert "web_fetch" not in tools


# --- matcher parity ----------------------------------------------------------


def test_matcher_parity_with_digisearch_fence() -> None:
    fence = pytest.importorskip("digisearch.web_search.fence")
    urls = [
        "https://example-client.test/",
        "https://academy.example-client.test/",
        "https://fr.academy.example-client.test/",
        "https://example-client.test.evil.com/",
        "https://evilexample-client.test/",
        "https://www.linkedin.com/posts/exampleclient_x-1",
        "https://www.linkedin.com/posts/other_exampleclient",
        "https://www.linkedin.com/company/exampleclient/jobs",
        "https://www.linkedin.com/company/exampleclientx",
        "https://x.com/exampleclientinc",
        "https://x.com/other",
        "https://play.google.com/store/apps/details?id=test.exampleclient.myapp",
        "https://play.google.com/store/apps/details?id=other",
        "https://en.wikipedia.org/",
        # Dot segments: resolved identically on both sides.
        "https://www.linkedin.com/company/exampleclient/../othercorp",
        "https://www.linkedin.com/company/exampleclient/./jobs",
        "https://www.linkedin.com/company/other/../exampleclient/jobs",
        "https://www.linkedin.com/company/exampleclient/%2e%2e/othercorp",
        "https://www.linkedin.com/company/exampleclient/%2E%2E/%2e%2E/in/x",
        "https://www.linkedin.com/company/exampleclient%2f..%2fothercorp",
        "https://www.linkedin.com/company/exampleclient/..%5cothercorp",
        "https://www.linkedin.com/../../company/exampleclient",
        "https://x.com/exampleclientinc/..",
        "https://www.linkedin.com/posts/exampleclient_a/../../in/x",
    ]
    for u in urls:
        assert url_within_pins(u, PINS) == fence.url_in_fence(u, PINS), u
    assert not url_within_pins("https://www.linkedin.com/company/exampleclient/../othercorp", PINS)
    assert url_within_pins("https://www.linkedin.com/company/other/../exampleclient/jobs", PINS)
