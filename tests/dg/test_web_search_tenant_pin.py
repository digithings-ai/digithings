"""Per-tenant web_search pin (corpus map ``webSearchDomains``) and site graph."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from digigraph.corpus_routing import (
    _normalize_web_search_pin,
    _parse_web_search_domains,
    load_tenant_corpus_map,
    resolve_corpus_override,
)
from digigraph.orchestration import web_search_tools
from digigraph.orchestration.registry import ToolContext, execute
from digigraph.orchestration.web_search_tools import (
    PINNED_RECENCY_DAYS,
    WEB_SEARCH_TOOL,
    WEB_SEARCH_TOOL_NAME,
    pinned_include_domains,
    url_within_pins,
    web_search_tool_for_tenant,
)
from digigraph.web_search_sites import (
    MAX_SITE_GRAPH_BYTES,
    WEB_SEARCH_SITES_DIR,
    has_web_search_site_graph,
    load_web_search_site_graph,
)

from digigraph import web_search_sites

pytestmark = pytest.mark.unit

PINS = ["example.com", "social.example/company/acme"]


def _context(**state: Any) -> ToolContext:
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True, **state},
    )


# --- pin parsing -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("WWW.Example.com", "example.com"),
        ("example.com.", "example.com"),
        ("example.com/company/acme/", "example.com/company/acme"),
        ("sub.example.com", "sub.example.com"),
    ],
)
def test_normalize_pin_accepts(raw: str, expected: str) -> None:
    assert _normalize_web_search_pin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["https://example.com", "example.com?x=1", "example.com#a", "localhost", "", "   ", 5, None],
)
def test_normalize_pin_rejects(raw: Any) -> None:
    assert _normalize_web_search_pin(raw) is None


def test_parse_absent_is_unpinned() -> None:
    assert _parse_web_search_domains(None, "t") is None


def test_parse_collapses_duplicates_and_accepts_a_bare_string() -> None:
    assert _parse_web_search_domains(["example.com", "www.example.com"], "t") == ["example.com"]
    assert _parse_web_search_domains("example.com", "t") == ["example.com"]


def test_parse_fails_closed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert _parse_web_search_domains({"a": 1}, "t") == []
        assert _parse_web_search_domains(["https://x.example", "nope"], "t") == []
        six = [f"h{i}.example" for i in range(6)]
        assert _parse_web_search_domains(six, "t") == []
    assert "more than 5 hosts" in caplog.text


def test_parse_counts_hosts_not_paths() -> None:
    five = [f"h{i}.example" for i in range(5)] + ["h0.example/a", "h0.example/b"]
    assert len(_parse_web_search_domains(five, "t") or []) == 7


# --- corpus map --------------------------------------------------------------


def test_map_entry_with_only_pins_parses() -> None:
    table = load_tenant_corpus_map('{"acme":{"webSearchDomains":["example.com"]}}')
    assert table["acme"].web_search_domains == ["example.com"]
    assert table["acme"].web_search_site is None  # no site file for this slug
    snake = load_tenant_corpus_map('{"acme":{"web_search_domains":["example.com"]}}')
    assert snake["acme"].web_search_domains == ["example.com"]


def test_site_graph_only_for_a_pinned_slug_with_a_file() -> None:
    pinned = load_tenant_corpus_map('{"nomadis":{"webSearchDomains":["example.com"]}}')
    assert pinned["nomadis"].web_search_site == "nomadis"
    unpinned = load_tenant_corpus_map('{"nomadis":{"digisearchIndex":"x_docs"}}')
    assert unpinned["nomadis"].web_search_domains is None
    assert unpinned["nomadis"].web_search_site is None
    refused = load_tenant_corpus_map('{"nomadis":{"webSearchDomains":[]}}')
    assert refused["nomadis"].web_search_domains == []
    assert refused["nomadis"].web_search_site is None


def test_resolve_passes_pin_to_its_tenant_only() -> None:
    table = load_tenant_corpus_map(
        '{"nomadis":{"webSearchDomains":["example.com"]},"other":{"digisearchIndex":"o_docs"}}'
    )
    out = resolve_corpus_override(headers={}, tenant_slug="nomadis", corpus_map=table)
    assert out.web_search_domains == ["example.com"]
    assert out.web_search_site == "nomadis"
    other = resolve_corpus_override(headers={}, tenant_slug="other", corpus_map=table)
    assert other.web_search_domains is None
    assert other.web_search_site is None


# --- include_domains clamp and URL check -----------------------------------


def test_pinned_include_domains_defaults_to_pin_hosts() -> None:
    assert pinned_include_domains(PINS, None) == ["example.com", "social.example"]
    assert pinned_include_domains(PINS, []) == ["example.com", "social.example"]


def test_pinned_include_domains_narrows_never_widens() -> None:
    assert pinned_include_domains(PINS, ["docs.example.com"]) == ["docs.example.com"]
    assert pinned_include_domains(PINS, ["other.org"]) == ["example.com", "social.example"]
    many = [f"h{i}.example.com" for i in range(9)]
    assert len(pinned_include_domains(PINS, many)) <= 5


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://www.example.com/about",
        "http://academy.example.com/x?y=1",
        "https://social.example/company/acme",
        "https://www.social.example/company/acme/posts",
    ],
)
def test_url_within_pins_admits(url: str) -> None:
    assert url_within_pins(url, PINS)


@pytest.mark.parametrize(
    "url",
    [
        "https://evilexample.com/",
        "https://example.com.evil.net/",
        "https://social.example/company/acmecorp",
        "https://social.example/company/other",
        "https://social.example/",
        "ftp://example.com/",
        "not a url",
        "",
    ],
)
def test_url_within_pins_rejects(url: str) -> None:
    assert not url_within_pins(url, PINS)


# --- the native handler ------------------------------------------------------


class _FakeSearch:
    def __init__(self, exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.exc = exc

    def __call__(self, model: str, query: str, **kwargs: Any) -> tuple[str, list[str]]:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return "- page (https://example.com/a)", ["https://example.com/a"]


def _patch_search(monkeypatch: pytest.MonkeyPatch, fake: _FakeSearch) -> None:
    import digigraph.llm_client as llm_client

    monkeypatch.setattr(llm_client, "digifetch_web_search", fake)


def test_pinned_call_is_clamped_widened_and_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    ctx = _context(web_search_domains=PINS, web_search_provider="internal")
    out = web_search_tools._handle_web_search(
        {"query": "q", "include_domains": ["other.org"], "provider": "paid-engine"}, ctx
    )
    assert isinstance(out, dict) and "error" not in out
    kw = fake.calls[0]
    assert kw["include_domains"] == ["example.com", "social.example"]
    assert kw["recency_days"] == PINNED_RECENCY_DAYS
    assert kw["provider"] == "internal"  # the model cannot pick the engine
    assert kw["url_filter"]("https://example.com/x")
    assert not kw["url_filter"]("https://other.org/x")


def test_unpinned_call_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    web_search_tools._handle_web_search(
        {"query": "q", "include_domains": ["other.org"], "provider": "internal"}, _context()
    )
    kw = fake.calls[0]
    assert kw["include_domains"] == ["other.org"]
    assert kw["provider"] == "internal"
    assert "recency_days" not in kw
    assert "url_filter" not in kw


def test_pinned_tenant_with_site_names_its_page_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    ctx = _context(web_search_domains=PINS, web_search_site="acme")
    web_search_tools._handle_web_search({"query": "q"}, ctx)
    assert fake.calls[0]["page_corpus"] == "acme"


def test_no_page_corpus_without_pin_or_site(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_site="acme"))
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_domains=PINS))
    assert all("page_corpus" not in kw for kw in fake.calls)


def test_empty_pin_refuses_without_searching(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    out = web_search_tools._handle_web_search({"query": "q"}, _context(web_search_domains=[]))
    assert isinstance(out, dict) and out["error"] == "tool_not_allowed"
    assert fake.calls == []


def test_pinned_no_rows_is_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    no_rows = RuntimeError("web_search tool returned no rows for query='q'")
    _patch_search(monkeypatch, _FakeSearch(no_rows))
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_domains=PINS))


def test_no_rows_still_raises_when_unpinned(monkeypatch: pytest.MonkeyPatch) -> None:
    no_rows = RuntimeError("web_search tool returned no rows for query='q'")
    _patch_search(monkeypatch, _FakeSearch(no_rows))
    with pytest.raises(RuntimeError, match="no rows"):
        web_search_tools._handle_web_search({"query": "q"}, _context())


def test_pinned_hub_failure_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_search(monkeypatch, _FakeSearch(RuntimeError("digisearch circuit open")))
    with pytest.raises(RuntimeError, match="circuit open"):
        web_search_tools._handle_web_search({"query": "q"}, _context(web_search_domains=PINS))


# --- digifetch_web_search url_filter ----------------------------------------


def _patch_hub(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, str]]) -> list[dict]:
    seen: list[dict[str, Any]] = []

    def fake(query: str, **kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs)
        return {"results": rows}

    monkeypatch.setattr(web_search_tools, "call_digisearch_web_search", fake)
    return seen


def test_url_filter_drops_row_before_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.llm_client import digifetch_web_search

    seen = _patch_hub(
        monkeypatch,
        [
            {"doc_id": "https://example.com/a", "content": "on-site fact"},
            {"doc_id": "https://other.org/b", "content": "OFF-PIN SNIPPET"},
        ],
    )
    summary, sources = digifetch_web_search(
        "", "q", recency_days=365, url_filter=lambda u: url_within_pins(u, PINS)
    )
    assert sources == ["https://example.com/a"]
    assert "OFF-PIN SNIPPET" not in summary and "other.org" not in summary
    assert seen[0]["recency_days"] == 365


def test_recency_forwarded_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.llm_client import digifetch_web_search

    seen = _patch_hub(monkeypatch, [{"doc_id": "https://example.com/a", "content": "x"}])
    digifetch_web_search("", "q")
    assert "recency_days" not in seen[0]


def test_page_corpus_forwarded_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.llm_client import digifetch_web_search

    seen = _patch_hub(monkeypatch, [{"doc_id": "https://example.com/a", "content": "x"}])
    digifetch_web_search("", "q")
    digifetch_web_search("", "q", page_corpus="acme")
    assert "page_corpus" not in seen[0]
    assert seen[1]["page_corpus"] == "acme"


def test_url_filter_dropping_everything_is_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.llm_client import digifetch_web_search

    _patch_hub(monkeypatch, [{"doc_id": "https://other.org/b", "content": "x"}])
    with pytest.raises(RuntimeError, match="no rows"):
        digifetch_web_search("", "q", url_filter=lambda u: url_within_pins(u, PINS))


# --- site graph loader -------------------------------------------------------


@pytest.mark.parametrize("site_id", ["../x", "A", "", "x/y", "-x", None])
def test_loader_rejects_bad_ids(site_id: Any) -> None:
    assert load_web_search_site_graph(site_id) is None
    assert not has_web_search_site_graph(site_id)


def test_loader_unknown_id_is_none() -> None:
    assert load_web_search_site_graph("no-such-site") is None


def test_shipped_site_graph_loads() -> None:
    assert (WEB_SEARCH_SITES_DIR / "nomadis.md").is_file()
    text = load_web_search_site_graph("nomadis")
    assert text
    assert len(text.encode()) <= MAX_SITE_GRAPH_BYTES
    paths = [ln for ln in text.splitlines() if ln.startswith("/")]
    assert len(paths) > 50
    assert all(" - " in ln for ln in paths)  # every page carries a description


def test_oversized_or_empty_file_is_ignored(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_sites, "WEB_SEARCH_SITES_DIR", tmp_path)
    (tmp_path / "big.md").write_text("x" * (MAX_SITE_GRAPH_BYTES + 1))
    (tmp_path / "blank.md").write_text("  \n")
    (tmp_path / "ok.md").write_text("/ - home\n")
    load_web_search_site_graph.cache_clear()
    try:
        assert load_web_search_site_graph("big") is None
        assert load_web_search_site_graph("blank") is None
        assert load_web_search_site_graph("ok") == "/ - home"
    finally:
        load_web_search_site_graph.cache_clear()


# --- tool description --------------------------------------------------------


def test_unpinned_tenant_keeps_shared_definition() -> None:
    assert web_search_tool_for_tenant(None, "nomadis") is None
    assert web_search_tool_for_tenant([], "nomadis") is None


def test_pinned_definition_is_a_copy_with_pins_and_graph() -> None:
    before = WEB_SEARCH_TOOL["function"]["description"]
    tool = web_search_tool_for_tenant(PINS, "nomadis")
    assert tool is not None
    fn = tool["function"]
    assert fn["name"] == WEB_SEARCH_TOOL_NAME
    for pin in PINS:
        assert pin in fn["description"]
        assert pin in fn["parameters"]["properties"]["include_domains"]["description"]
    assert (load_web_search_site_graph("nomadis") or "")[:200] in fn["description"]
    assert "provider" not in fn["parameters"]["properties"]
    assert WEB_SEARCH_TOOL["function"]["description"] == before
    assert "provider" in WEB_SEARCH_TOOL["function"]["parameters"]["properties"]


def test_pinned_definition_without_graph() -> None:
    tool = web_search_tool_for_tenant(PINS, None)
    assert tool is not None
    graph = load_web_search_site_graph("nomadis") or ""
    assert graph[:200] not in tool["function"]["description"]


# --- proxied web_search ------------------------------------------------------


def _proxied_context(**state: Any) -> ToolContext:
    ctx = _context(**state)
    ctx.extra_mcp_servers = [{"id": "ext", "url": "https://mcp.example.test"}]
    return ctx


def test_proxied_web_search_refused_for_pinned_tenant() -> None:
    out = execute("ext_web_search", {"query": "q"}, _proxied_context(web_search_domains=PINS))
    assert isinstance(out, dict)
    assert out["error"] == "tool_not_allowed"
    assert "pinned" in out["message"]


def test_proxied_web_search_not_refused_by_pin_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import digigraph.orchestration.mcp_client as mcp_client

    monkeypatch.setattr(mcp_client, "call_prefixed_tool", lambda *a, **k: "proxied")
    try:
        out = execute("ext_web_search", {"query": "q"}, _proxied_context())
    except Exception:  # later stages may fail offline; only the pin branch matters
        return
    assert not (isinstance(out, dict) and "pinned" in str(out.get("message", "")))
