"""Pinned-tenant ``web_fetch``: open one page inside the tenant's sites.

The digisearch hub is faked; the fence on every redirect hop is covered in
``digisearch/tests/test_web_fetch_fence.py``. Here: the digigraph-side gate,
the second check on the final URL and links, the tool surface, and that
unpinned tenants (other tenants, house) are untouched.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import SplitResult, urlsplit

import pytest
from digigraph.orchestration import web_search_tools
from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.web_search_tools import (
    WEB_FETCH_TOOL_NAME,
    _handle_web_fetch,
    url_within_pins,
    web_fetch_tool_for_tenant,
    web_search_tool_for_tenant,
)
from digigraph.tool_policy import apply_web_search_opt_in, strip_web_search_tools

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
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, base: str, tool: str, arguments: dict[str, Any], **_: Any) -> Any:
        self.calls.append((tool, arguments))
        return self.reply


def _patch_hub(monkeypatch: pytest.MonkeyPatch, reply: dict[str, Any]) -> _FakeHub:
    import digigraph.vertical_orchestrator.digisearch_hub as hub

    fake = _FakeHub(reply)
    monkeypatch.setattr(hub, "invoke_digisearch_tool", fake)
    monkeypatch.setattr(web_search_tools, "_digisearch_service_base", lambda: "http://ds.test")
    return fake


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


def test_fetch_reads_a_subdomain_page_and_lists_in_fence_links(
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
    out = _handle_web_fetch({"url": "academy.example-client.test/courses"}, ctx)
    assert isinstance(out, dict) and "error" not in out
    tool, args = hub.calls[0]
    assert tool == WEB_FETCH_TOOL_NAME
    assert args["url"] == "https://academy.example-client.test/courses"
    assert args["fence"] == PINS
    assert args["page_corpus"] == "exampleclient"
    assert out["links"] == ["https://fr.academy.example-client.test/"]
    assert len(out["content"]) > 4000  # the full page, not a snippet
    # Compare parsed hosts and paths, never substrings of the page text: a
    # substring test would also pass for a look-alike host.
    content_urls = {(u.hostname, u.path) for u in _urls_in(out["content"])}
    assert ("fr.academy.example-client.test", "/") in content_urls
    assert ("www.linkedin.com", "/in/someone") not in content_urls
    assert out["rag_sources"]


@pytest.mark.parametrize(
    "url",
    [
        "https://example-client.test.evil.com/",
        "https://evilexample-client.test/",
        "https://en.wikipedia.org/wiki/ExampleClient",
        "https://www.linkedin.com/feed/",
        "https://twitter.com/exampleclientinc",
    ],
)
def test_fetch_outside_the_fence_is_refused_without_calling_digisearch(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    hub = _patch_hub(monkeypatch, _page(url))
    out = _handle_web_fetch({"url": url}, _context(web_search_domains=PINS))
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


def test_final_url_outside_the_fence_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, _page("https://exampleclient.helpdesk-vendor.test/login"))
    out = _handle_web_fetch(
        {"url": "https://support.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert "redirected" in out["message"]


def test_digisearch_fence_refusal_maps_to_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, {"ok": False, "error": "fence_refused: outside the allowed sites"})
    out = _handle_web_fetch(
        {"url": "https://support.example-client.test/"}, _context(web_search_domains=PINS)
    )
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"


def test_fetch_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, {"ok": False, "error": "web_fetch failed: bot challenge"})
    out = _handle_web_fetch({"url": "https://www.example-client.test/"}, _context(web_search_domains=PINS))
    assert isinstance(out, dict) and out["error"] == "fetch_failed"


def test_saved_copy_is_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, _page("https://www.example-client.test/", source="page_corpus"))
    out = _handle_web_fetch({"url": "https://www.example-client.test/"}, _context(web_search_domains=PINS))
    assert isinstance(out, dict) and "Saved copy" in out["content"]


@pytest.mark.parametrize("state", [{}, {"web_search_domains": []}])
def test_unpinned_or_empty_pin_has_no_web_fetch(
    monkeypatch: pytest.MonkeyPatch, state: dict[str, Any]
) -> None:
    hub = _patch_hub(monkeypatch, _page("https://example.com/"))
    out = _handle_web_fetch({"url": "https://example.com/"}, _context(**state))
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


def test_web_fetch_needs_the_web_search_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _patch_hub(monkeypatch, _page("https://www.example-client.test/"))
    ctx = _context(web_search_domains=PINS)
    ctx.state["enable_web_search"] = False
    out = _handle_web_fetch({"url": "https://www.example-client.test/"}, ctx)
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert hub.calls == []


def test_tool_definitions() -> None:
    assert web_fetch_tool_for_tenant(None) is None
    assert web_fetch_tool_for_tenant([]) is None
    tool = web_fetch_tool_for_tenant(PINS)
    assert tool is not None and tool["function"]["name"] == WEB_FETCH_TOOL_NAME
    described = set(re.findall(r"[a-z0-9][a-z0-9.-]*\.[a-z]+", tool["function"]["description"]))
    assert "example-client.test" in described
    search = web_search_tool_for_tenant(PINS, None)
    assert search is not None
    desc = search["function"]["description"]
    assert "subdomains" in desc and "web_fetch" in desc


def test_site_map_is_a_starting_guide(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.web_search_sites import WEB_SEARCH_SITES_DIR_ENV

    (tmp_path / "acme.md").write_text("/a/ - page a\n")
    monkeypatch.setenv(WEB_SEARCH_SITES_DIR_ENV, str(tmp_path))
    tool = web_search_tool_for_tenant(PINS, "acme")
    assert tool is not None
    desc = tool["function"]["description"]
    assert "starting guide, not a limit" in desc and "/a/ - page a" in desc


def test_web_fetch_rides_with_web_search_through_the_allowlist() -> None:
    names = frozenset({"digisearch", "web_search"})
    assert "web_fetch" in apply_web_search_opt_in(names, enable_web_search=True)
    assert "web_fetch" not in apply_web_search_opt_in(
        frozenset({"digisearch"}), enable_web_search=True
    )
    assert strip_web_search_tools(frozenset({"web_search", "web_fetch", "x"})) == {"x"}
    assert apply_web_search_opt_in(names | {"web_fetch"}, enable_web_search=False) == {"digisearch"}


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
    ]
    for u in urls:
        assert url_within_pins(u, PINS) == fence.url_in_fence(u, PINS), u
