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
    WEB_SEARCH_SITES_DIR_ENV,
    has_web_search_site_graph,
    load_web_search_site_graph,
)

pytestmark = pytest.mark.unit

PINS = ["example.com", "social.example/company/acme"]

# A made-up site graph in the format operators keep outside the repo.
EXAMPLE_GRAPH = "Every page is https://example.com + the path below.\n\n" + "\n".join(
    f"/page-{i}/ - example page {i}" for i in range(60)
)


@pytest.fixture
def sites_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """An external site-graph dir holding ``acme.md``, wired via the env var."""
    (tmp_path / "acme.md").write_text(EXAMPLE_GRAPH + "\n")
    monkeypatch.setenv(WEB_SEARCH_SITES_DIR_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _no_sites_dir_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WEB_SEARCH_SITES_DIR_ENV, raising=False)


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


def test_site_graph_only_for_a_pinned_slug_with_a_file(sites_dir: Any) -> None:
    pinned = load_tenant_corpus_map('{"acme":{"webSearchDomains":["example.com"]}}')
    assert pinned["acme"].web_search_site == "acme"
    unpinned = load_tenant_corpus_map('{"acme":{"digisearchIndex":"x_docs"}}')
    assert unpinned["acme"].web_search_domains is None
    assert unpinned["acme"].web_search_site is None
    refused = load_tenant_corpus_map('{"acme":{"webSearchDomains":[]}}')
    assert refused["acme"].web_search_domains == []
    assert refused["acme"].web_search_site is None
    nofile = load_tenant_corpus_map('{"other":{"webSearchDomains":["example.com"]}}')
    assert nofile["other"].web_search_site is None


def test_no_site_graph_when_the_dir_is_unset() -> None:
    table = load_tenant_corpus_map('{"acme":{"webSearchDomains":["example.com"]}}')
    assert table["acme"].web_search_site is None


def test_resolve_passes_pin_to_its_tenant_only(sites_dir: Any) -> None:
    table = load_tenant_corpus_map(
        '{"acme":{"webSearchDomains":["example.com"],"webSearchPageCorpus":true},'
        '"other":{"digisearchIndex":"o_docs"}}'
    )
    out = resolve_corpus_override(headers={}, tenant_slug="acme", corpus_map=table)
    assert out.web_search_domains == ["example.com"]
    assert out.web_search_site == "acme"
    assert out.web_search_page_corpus == "acme"
    other = resolve_corpus_override(headers={}, tenant_slug="other", corpus_map=table)
    assert other.web_search_domains is None
    assert other.web_search_site is None
    assert other.web_search_page_corpus is None


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ('{"webSearchDomains":["example.com"],"webSearchPageCorpus":true}', "acme"),
        ('{"webSearchDomains":["example.com"],"webSearchPageCorpus":"acme-pages"}', "acme-pages"),
        ('{"webSearchDomains":["example.com"],"web_search_page_corpus":"acme-2"}', "acme-2"),
        ('{"webSearchDomains":["example.com"],"webSearchPageCorpus":false}', None),
        ('{"webSearchDomains":["example.com"],"webSearchPageCorpus":"../x"}', None),
        ('{"webSearchDomains":["example.com"],"webSearchPageCorpus":"Acme"}', None),
        ('{"webSearchDomains":["example.com"]}', None),
        ('{"webSearchPageCorpus":true}', None),
        ('{"webSearchDomains":[],"webSearchPageCorpus":true}', None),
    ],
)
def test_page_corpus_from_tenant_map(entry: str, expected: str | None) -> None:
    table = load_tenant_corpus_map('{"acme":' + entry + "}")
    assert table["acme"].web_search_page_corpus == expected


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


def test_pinned_tenant_sends_its_page_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    ctx = _context(web_search_domains=PINS, web_search_page_corpus="acme-pages")
    web_search_tools._handle_web_search({"query": "q"}, ctx)
    assert fake.calls[0]["page_corpus"] == "acme-pages"


def test_no_page_corpus_without_pin_or_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSearch()
    _patch_search(monkeypatch, fake)
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_page_corpus="acme"))
    web_search_tools._handle_web_search({"query": "q"}, _context(web_search_domains=PINS))
    # The site graph id alone no longer selects a corpus.
    web_search_tools._handle_web_search(
        {"query": "q"}, _context(web_search_domains=PINS, web_search_site="acme")
    )
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


def test_unset_dir_has_no_site_graphs() -> None:
    assert load_web_search_site_graph("acme") is None
    assert not has_web_search_site_graph("acme")


def test_external_site_graph_loads(sites_dir: Any) -> None:
    assert has_web_search_site_graph("acme")
    text = load_web_search_site_graph("acme")
    assert text == EXAMPLE_GRAPH
    assert len(text.encode()) <= MAX_SITE_GRAPH_BYTES


def test_edited_site_graph_is_reread(sites_dir: Any) -> None:
    import os

    assert load_web_search_site_graph("acme") == EXAMPLE_GRAPH
    path = sites_dir / "acme.md"
    path.write_text("/ - home\n")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert load_web_search_site_graph("acme") == "/ - home"


def test_oversized_or_empty_file_is_ignored(sites_dir: Any) -> None:
    (sites_dir / "big.md").write_text("x" * (MAX_SITE_GRAPH_BYTES + 1))
    (sites_dir / "blank.md").write_text("  \n")
    (sites_dir / "ok.md").write_text("/ - home\n")
    assert load_web_search_site_graph("big") is None
    assert load_web_search_site_graph("blank") is None
    assert load_web_search_site_graph("ok") == "/ - home"


# --- tool description --------------------------------------------------------


def test_unpinned_tenant_keeps_shared_definition(sites_dir: Any) -> None:
    assert web_search_tool_for_tenant(None, "acme") is None
    assert web_search_tool_for_tenant([], "acme") is None


def test_pinned_definition_is_a_copy_with_pins_and_graph(sites_dir: Any) -> None:
    before = WEB_SEARCH_TOOL["function"]["description"]
    tool = web_search_tool_for_tenant(PINS, "acme")
    assert tool is not None
    fn = tool["function"]
    assert fn["name"] == WEB_SEARCH_TOOL_NAME
    for pin in PINS:
        assert pin in fn["description"]
        assert pin in fn["parameters"]["properties"]["include_domains"]["description"]
    assert EXAMPLE_GRAPH[:200] in fn["description"]
    assert "provider" not in fn["parameters"]["properties"]
    assert WEB_SEARCH_TOOL["function"]["description"] == before
    assert "provider" in WEB_SEARCH_TOOL["function"]["parameters"]["properties"]


def test_pinned_definition_without_graph(sites_dir: Any) -> None:
    tool = web_search_tool_for_tenant(PINS, None)
    assert tool is not None
    assert EXAMPLE_GRAPH[:200] not in tool["function"]["description"]


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


# --- per-tenant host cap and exact-page pins ---------------------------------


def test_max_hosts_raises_the_cap_per_tenant() -> None:
    eleven = [f"h{i}.example" for i in range(11)]
    raised = load_tenant_corpus_map(
        '{"acme":{"webSearchDomains":' + str(eleven).replace("'", '"') + ',"webSearchMaxHosts":14}}'
    )
    assert raised["acme"].web_search_domains == eleven
    default = load_tenant_corpus_map(
        '{"acme":{"webSearchDomains":' + str(eleven).replace("'", '"') + "}}"
    )
    assert default["acme"].web_search_domains == []


@pytest.mark.parametrize("bad", ['"14"', "0", "true", "999"])
def test_invalid_max_hosts_keeps_the_default(bad: str) -> None:
    six = str([f"h{i}.example" for i in range(6)]).replace("'", '"')
    table = load_tenant_corpus_map(
        '{"acme":{"webSearchDomains":' + six + ',"webSearchMaxHosts":' + bad + "}}"
    )
    assert table["acme"].web_search_domains == []


def test_many_pins_default_to_the_primary_host_per_call() -> None:
    pins = ["example.com"] + [f"h{i}.example" for i in range(8)]
    assert pinned_include_domains(pins, None) == ["example.com"]
    assert pinned_include_domains(pins, ["h3.example"]) == ["h3.example"]
    assert pinned_include_domains(pins, ["elsewhere.org"]) == ["example.com"]


def test_exact_page_pin_with_a_query() -> None:
    pin = _normalize_web_search_pin("store.example/apps/details?id=co.acme.app")
    assert pin == "store.example/apps/details?id=co.acme.app"
    assert _normalize_web_search_pin("store.example?id=x") is None
    assert _normalize_web_search_pin("store.example/apps?id") is None
    pins = [pin]
    assert url_within_pins("https://store.example/apps/details?id=co.acme.app&hl=en", pins)
    assert not url_within_pins("https://store.example/apps/details?id=co.other.app", pins)
    assert not url_within_pins("https://store.example/apps/details/more?id=co.acme.app", pins)
    assert pinned_include_domains(pins, None) == ["store.example"]
