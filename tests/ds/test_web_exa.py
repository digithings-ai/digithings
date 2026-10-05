"""Unit tests for the EXA web-search shim and its leg of the unified route (#4711).

The shim itself (``digisearch.web_exa``) is unchanged by the provider work;
what moved is its HTTP surface — ``POST /v1/digisearch_web_search`` is gone and
``POST /v1/web_search`` with ``provider="exa"`` replaces it. No network, no key.

Transport note (DIG-912 §5.3 / DIG-1072): the EXA POST rides the shared
``digifetch`` fetch seam, so every fake below patches
``digifetch.HttpFetcher.fetch`` — the seam itself — rather than a private
``httpx.post``.
"""

import json as _json
from pathlib import Path

import httpx
import pytest
from digisearch.orchestrator_tools import (
    TOOL_WEB_SEARCH,
    build_first_party_web_search_tool,
    build_orchestrator_tool_manifest,
)
from digisearch.server import app
from fastapi.testclient import TestClient

import digifetch
from digifetch import FetchResult
from digisearch import web_exa
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


def _fake_exa_fetch(monkeypatch, seen: dict, body) -> None:
    """Point the ``digifetch`` fetch seam at a fake EXA response.

    *body* is the JSON EXA would return, or a callable taking the recorded
    ``seen`` dict for fakes that answer from the request payload. Returns a
    :class:`digifetch.FetchResult` so the seam's own contract (status, text
    body) is what the shim has to parse.
    """

    def fake_fetch(
        self,
        url,
        *,
        method="GET",
        params=None,
        data=None,
        json=None,
        headers=None,
        cookies=None,
    ):
        seen["fetcher"] = self
        seen["url"] = url
        seen["method"] = method
        seen["payload"] = json
        seen["headers"] = dict(headers or {})
        seen.setdefault("payloads", []).append(json)
        payload = body(seen) if callable(body) else body
        return FetchResult(
            status_code=200,
            url=url,
            text=_json.dumps(payload),
            content_type="application/json",
        )

    monkeypatch.setattr(digifetch.HttpFetcher, "fetch", fake_fetch)


def test_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    assert web_exa.is_exa_configured() is False


def test_search_without_key_fails_closed(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(web_exa.ExaNotConfiguredError):
        web_exa.exa_search("hello")


def test_search_rejects_empty_query(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    with pytest.raises(ValueError):
        web_exa.exa_search("  ")


def test_search_rejects_bad_type(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    with pytest.raises(ValueError):
        web_exa.exa_search("hello", search_type="neural")  # type: ignore[arg-type]


def test_manifest_always_includes_the_unified_web_search_tool():
    """#4711: one tool, always present; `provider` picks the engine."""
    names = [t["function"]["name"] for t in build_orchestrator_tool_manifest()]
    assert TOOL_WEB_SEARCH in names
    assert build_first_party_web_search_tool()["function"]["name"] == TOOL_WEB_SEARCH


def test_manifest_never_offers_the_removed_web_tools():
    """The Exa-only `digisearch_web_search` is gone; `provider="exa"` replaces it."""
    names = [t["function"]["name"] for t in build_orchestrator_tool_manifest()]
    assert "digisearch_web_search" not in names
    assert "exa_web_search" not in names


def test_search_posts_expected_shape(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _fake_exa_fetch(
        monkeypatch,
        seen,
        {
            "results": [{"title": "t", "url": "https://example.com"}],
            "searchType": "auto",
            "costDollars": {"total": 0.007},
        },
    )
    data = web_exa.exa_search("blog post about AI", num_results=5)
    assert seen["url"] == "https://api.exa.ai/search"
    assert seen["method"] == "POST"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["payload"]["query"] == "blog post about AI"
    assert seen["payload"]["numResults"] == 5
    assert len(data.results) == 1
    assert web_exa.format_web_results(data).startswith("Title: t")


def test_offset_page_ignores_extra_provider_rows(monkeypatch):
    """Offset paging must return exactly the requested page, not the tail.

    The provider occasionally returns more rows than asked for; the slice
    must stay ``[start:start+n]`` over the junk-filtered window so extra
    rows and non-dict entries cannot lengthen a page.
    """
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    results = ["junk"] + [{"title": f"t{i}"} for i in range(5)]

    seen: dict = {}
    _fake_exa_fetch(
        monkeypatch,
        seen,
        {"results": results, "searchType": "auto", "costDollars": {"total": 0.007}},
    )
    data = web_exa.exa_search("ai", num_results=2, offset=1)
    assert seen["payload"]["numResults"] == 3
    assert [r["title"] for r in data.results] == ["t1", "t2"]


def test_format_empty_results():
    assert "No EXA results" in web_exa.format_web_results(web_exa.WebSearchData())


def test_route_dormant_without_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "hello", "provider": "exa"})
    assert resp.status_code == 503, resp.text
    assert "EXA_API_KEY" in resp.text


def test_route_forwards_domains(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}

    def fake_exa_search(query, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return web_exa.WebSearchData(results=[])

    monkeypatch.setattr(web_exa, "exa_search", fake_exa_search)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/web_search",
        json={
            "query": "hello",
            "provider": "exa",
            "include_domains": ["example.com"],
            "exclude_domains": ["bad.example"],
        },
    )
    assert resp.status_code == 200, resp.text
    assert seen["query"] == "hello"
    assert seen["kwargs"]["include_domains"] == ["example.com"]
    assert seen["kwargs"]["exclude_domains"] == ["bad.example"]


# --- Paging (#4234): offset over one enlarged window, bounded by the EXA cap ----


def _page_results(n: int) -> list[dict]:
    return [{"title": f"t{i}", "url": f"https://example.com/{i}"} for i in range(1, n + 1)]


def _patch_exa_post(monkeypatch, results: list[dict], seen: dict) -> None:
    """Fake the EXA POST (over the digifetch seam) honoring ``numResults``."""

    def body(record: dict) -> dict:
        return {"results": results[: record["payload"]["numResults"]], "searchType": "auto"}

    _fake_exa_fetch(monkeypatch, seen, body)


def test_exa_max_results_is_the_pinned_cap():
    """The cap is the 1-100 EXA bound pinned by monitors models (#4065 / R6)."""
    assert web_exa.EXA_MAX_RESULTS == 100
    from digisearch.monitors.models import Watch

    bounds = Watch.model_fields["num_results"].metadata
    assert web_exa.EXA_MAX_RESULTS in [getattr(m, "le", None) for m in bounds]


def test_search_default_call_is_unchanged(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    data = web_exa.exa_search("blog post about AI")
    assert seen["payload"] == {
        "query": "blog post about AI",
        "type": "auto",
        "numResults": 8,
        "contents": {"highlights": {"query": "blog post about AI", "maxCharacters": 4000}},
    }
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(1, 9)]


def test_search_pages_offset_over_one_enlarged_window(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(20), seen)
    data = web_exa.exa_search("q", num_results=8, offset=8)
    # EXA POST /search has no offset: the window is enlarged on the wire...
    assert seen["payload"]["numResults"] == 16
    assert "offset" not in seen["payload"]
    # ...and the page is sliced client-side.
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(9, 17)]


def test_search_page1_and_page2_are_deterministic_and_non_overlapping(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    page1 = web_exa.exa_search("q", num_results=8, offset=0)
    page2 = web_exa.exa_search("q", num_results=8, offset=8)
    urls1 = [r["url"] for r in page1.results]
    urls2 = [r["url"] for r in page2.results]
    assert urls1 == [f"https://example.com/{i}" for i in range(1, 9)]
    assert urls2 == [f"https://example.com/{i}" for i in range(9, 17)]
    assert not set(urls1) & set(urls2)
    assert [p["numResults"] for p in seen["payloads"]] == [8, 16]


def test_search_window_clipped_by_cap_is_out_of_range(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    with pytest.raises(web_exa.ExaPageOutOfRangeError, match="cap"):
        web_exa.exa_search("q", num_results=8, offset=95)
    # Never a silent truncated page, and never an unbounded scan.
    assert "payloads" not in seen


def test_search_offset_beyond_cap_is_out_of_range(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    with pytest.raises(web_exa.ExaPageOutOfRangeError) as excinfo:
        web_exa.exa_search("q", num_results=8, offset=100)
    assert isinstance(excinfo.value, ValueError)  # existing callers catch ValueError
    assert "100" in str(excinfo.value)
    assert "payloads" not in seen


def test_search_last_page_at_the_cap_is_reachable(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    data = web_exa.exa_search("q", num_results=8, offset=92)
    assert seen["payload"]["numResults"] == 100
    assert [r["url"] for r in data.results] == [f"https://example.com/{i}" for i in range(93, 101)]


def test_search_negative_offset_rejected(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(8), seen)
    with pytest.raises(ValueError, match="offset"):
        web_exa.exa_search("q", offset=-1)
    assert "payloads" not in seen


# --- HTTP route (#4241): offset on POST /v1/web_search with provider="exa" -------


def test_route_default_offset_is_byte_identical(monkeypatch):
    """The default call and an explicit ``offset=0`` are the same request/response."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    default = client.post(
        "/v1/web_search", json={"query": "q", "max_results": 8, "provider": "exa"}
    )
    explicit = client.post(
        "/v1/web_search",
        json={"query": "q", "max_results": 8, "provider": "exa", "offset": 0},
    )
    assert default.status_code == 200, default.text
    assert default.content == explicit.content
    assert seen["payloads"][0] == seen["payloads"][1]
    assert seen["payload"]["numResults"] == 8
    assert "offset" not in seen["payload"]


def test_route_page2_is_deterministic_and_non_overlapping(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(16), seen)
    client = TestClient(app, headers=auth_headers())
    page1 = client.post("/v1/web_search", json={"query": "q", "max_results": 8, "provider": "exa"})
    page2 = client.post(
        "/v1/web_search",
        json={"query": "q", "max_results": 8, "provider": "exa", "offset": 8},
    )
    assert page1.status_code == 200, page1.text
    assert page2.status_code == 200, page2.text
    urls1 = [r["url"] for r in page1.json()["results"]]
    urls2 = [r["url"] for r in page2.json()["results"]]
    assert urls1 == [f"https://example.com/{i}" for i in range(1, 9)]
    assert urls2 == [f"https://example.com/{i}" for i in range(9, 17)]
    # One enlarged window on the wire; the page is sliced client-side.
    assert [p["numResults"] for p in seen["payloads"]] == [8, 16]


def test_route_window_past_the_cap_is_400_explicit(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/web_search",
        json={"query": "q", "max_results": 8, "provider": "exa", "offset": 95},
    )
    assert resp.status_code == 400, resp.text
    assert "cap" in resp.text
    assert "100" in resp.text
    # Refused before any EXA POST — never a silently truncated page.
    assert "payloads" not in seen


def test_route_offset_beyond_the_cap_is_400_explicit(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "exa", "offset": 100})
    assert resp.status_code == 400, resp.text
    assert "100" in resp.text
    assert "payloads" not in seen


def test_route_negative_offset_is_422(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "exa", "offset": -1})
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    # The envelope flattens the field path; the ge=0 bound is still explicit.
    assert "greater than or equal to 0" in error["message"]


def test_route_last_page_at_the_cap_is_reachable(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _patch_exa_post(monkeypatch, _page_results(100), seen)
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/web_search",
        json={"query": "q", "max_results": 8, "provider": "exa", "offset": 92},
    )
    assert resp.status_code == 200, resp.text
    assert seen["payload"]["numResults"] == 100
    urls = [r["url"] for r in resp.json()["results"]]
    assert urls == [f"https://example.com/{i}" for i in range(93, 101)]


# --- Orchestrator manifest (#4241): offset advertised in the invoke schema ------


def test_manifest_web_search_exposes_offset():
    tool = build_first_party_web_search_tool()
    props = tool["function"]["parameters"]["properties"]
    assert props["offset"]["type"] == "integer"
    # Paging is a per-provider capability: the description says so, and the
    # provider that lacks it errors instead of silently returning page one.
    assert "exa" in props["offset"]["description"]
    # required stays query-only: offset is optional and defaults to the unpaged call.
    assert tool["function"]["parameters"]["required"] == ["query"]


def test_manifest_web_search_exposes_provider_and_effort():
    props = build_first_party_web_search_tool()["function"]["parameters"]["properties"]
    # 'auto' leads the enum (the description sells it); 'internal' always follows.
    assert props["provider"]["enum"][:2] == ["auto", "internal"]
    assert props["effort"]["enum"] == ["fast", "thorough"]


# --- digifetch seam (DIG-912 §5.3 / DIG-1072 L5): the EXA POST rides the fetch seam ---


def test_exa_fetch_goes_through_digifetch(monkeypatch):
    """The EXA request is issued by ``digifetch.HttpFetcher``, not by hand.

    Asserts the *call*: a private ``httpx.post`` left in place would never touch
    this fake and the test would fail, while a future refactor that keeps
    ``httpx`` imported for some other reason still passes.
    """
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    seen: dict = {}
    _fake_exa_fetch(monkeypatch, seen, {"results": [], "searchType": "auto"})

    web_exa.exa_search("q")

    assert isinstance(seen["fetcher"], digifetch.HttpFetcher)
    assert seen["url"] == "https://api.exa.ai/search"
    assert seen["method"] == "POST"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["payload"]["query"] == "q"


def test_exa_import_does_not_require_digifetch_at_module_level():
    """Import-time side-effect freedom: ``digifetch`` is a lazy import in ``_post``.

    Mirrors ``pipeline/url_ingest.py`` — the ``[web-search]`` extra must stay
    optional, so ``import digisearch.web_exa`` may not pull it in eagerly.
    """
    source = (Path(web_exa.__file__ or "")).read_text()
    top_level = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "digifetch" in line
    ]
    assert top_level == []


def test_exa_fetch_that_digifetch_refuses_is_refused_here(monkeypatch):
    """A blocked target never reaches the wire: the seam's SSRF guard refuses it.

    ``EXA_API_BASE`` is attacker-influenceable in the webhook flows this leaf is
    hardening. ``digifetch.ssrf`` refuses a loopback / link-local / metadata
    address, and that refusal must surface as ``ExaError`` *before* any socket
    is opened — not as a silent success and not as a raw ``SsrfBlockedError``
    escaping the ``except ExaError`` handlers in server.py / mcp_server.py.
    """
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    dialled: list[str] = []

    def spy_request(self, method, url, **kwargs):
        dialled.append(str(url))
        raise AssertionError(f"refused URL was dialled anyway: {url}")

    monkeypatch.setattr(httpx.Client, "request", spy_request)
    for base in (
        "http://169.254.169.254",  # cloud metadata (IMDS)
        "http://127.0.0.1:8002",  # loopback (the digisearch service itself)
        "http://10.1.2.3",  # RFC1918
        "http://[::1]",  # IPv6 loopback
        "file:///etc/passwd",  # non-http scheme
    ):
        monkeypatch.setattr(web_exa, "EXA_API_BASE", base)
        with pytest.raises(web_exa.ExaError, match="digifetch SSRF guard"):
            web_exa.exa_search("q")
    assert dialled == [], "the guard must refuse before the request, not after"


def test_exa_ssrf_refusal_keeps_the_exa_error_contract(monkeypatch):
    """The refusal is an ``ExaError`` carrying no HTTP status, so callers keep one type."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr(web_exa, "EXA_API_BASE", "http://169.254.169.254")
    with pytest.raises(web_exa.ExaError) as excinfo:
        web_exa.exa_search("q")
    assert excinfo.value.status_code is None
    # The underlying guard error stays reachable for diagnosis.
    assert isinstance(excinfo.value.__cause__, digifetch.SsrfBlockedError)


def test_exa_transport_error_is_mapped_to_exa_error(monkeypatch):
    """A seam-level transport failure still lands as ``ExaError``, never httpx."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def boom(self, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(digifetch.HttpFetcher, "fetch", boom)
    with pytest.raises(web_exa.ExaError, match="EXA request failed"):
        web_exa.exa_search("q")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_exa_http_status_taxonomy_survives_the_seam(monkeypatch, status):
    """The seam raises on 4xx/5xx; the 401/403 / 429 / 5xx retry taxonomy must survive."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def fake_fetch(self, url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(status, text="boom", request=request)
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    monkeypatch.setattr(digifetch.HttpFetcher, "fetch", fake_fetch)
    with pytest.raises(web_exa.ExaError) as excinfo:
        web_exa.exa_search("q")
    assert excinfo.value.status_code == status
    # Each status keeps its own message: 401/403 and 429 are actionable, the rest
    # quote the upstream body. The taxonomy callers retry on must not flatten.
    if status in (401, 403):
        assert "EXA_API_KEY" in str(excinfo.value)
    elif status == 429:
        assert "rate limited" in str(excinfo.value)
    else:
        assert "boom" in str(excinfo.value)


def test_exa_non_json_body_is_mapped_to_exa_error(monkeypatch):
    """The seam returns text, so the shim parses JSON itself and keeps the old errors."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def fake_fetch(self, url, **kwargs):
        return FetchResult(status_code=200, url=url, text="<html>nope</html>")

    monkeypatch.setattr(digifetch.HttpFetcher, "fetch", fake_fetch)
    with pytest.raises(web_exa.ExaError, match="non-JSON"):
        web_exa.exa_search("q")


def test_exa_non_dict_body_is_mapped_to_exa_error(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def fake_fetch(self, url, **kwargs):
        return FetchResult(status_code=200, url=url, text=_json.dumps([1, 2, 3]))

    monkeypatch.setattr(digifetch.HttpFetcher, "fetch", fake_fetch)
    with pytest.raises(web_exa.ExaError, match="unexpected shape"):
        web_exa.exa_search("q")
