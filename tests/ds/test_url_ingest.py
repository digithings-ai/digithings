"""Minimal ingest_url() tests: URL to index over landed seams (#4055). Offline only."""

from __future__ import annotations

import os
import tempfile

import httpx
import pytest
from digisearch.pipeline.url_ingest import UrlFetchError, ingest_url
from digisearch.search._stub import get_stub_index

pytestmark = pytest.mark.unit

_PUBLIC = "93.184.216.34"
_PUBLIC_2 = "1.1.1.1"

_HTML = """<html><head><title>Test Article</title></head><body>
<article><h1>Revenue growth report</h1>
<p>First paragraph with enough content about revenue growth and market analysis for testing extraction.</p>
<p>Second paragraph with more detail on earnings, outlook, and analyst commentary for the quarter.</p>
<p>Third paragraph adds further context so trafilatura has enough signal to extract main content.</p>
</article></body></html>"""


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    monkeypatch.setenv("DIGISEARCH_EMBED", "0")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    get_stub_index().clear()


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=_HTML.encode("utf-8"), headers={"content-type": "text/html"})


def test_ingest_url_ok_path() -> None:
    from digifetch import HttpFetcher

    url = f"https://{_PUBLIC}/article"
    with HttpFetcher(transport=httpx.MockTransport(_ok_handler)) as fetcher:
        result = ingest_url(url, index_name="url-ingest-ok", fetcher=fetcher)
    assert result.chunks_created >= 1
    assert result.source_url == url
    assert result.final_url == url
    assert result.index_name == "url-ingest-ok"
    assert result.doc_id
    indexed = get_stub_index().get("url-ingest-ok") or []
    assert len(indexed) == result.chunks_created
    assert any(c.metadata.get("source_url") == result.final_url for c in indexed)
    assert all(c.metadata.get("evidence_tier") == "web" for c in indexed)


def test_ingest_url_ssrf_blocked_before_socket() -> None:
    from digifetch import HttpFetcher

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"secret")

    with HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(UrlFetchError):
            ingest_url("http://169.254.169.254/latest/meta-data/", fetcher=fetcher)
    assert calls == []


def test_ingest_url_redirect_to_private_raises() -> None:
    from digifetch import HttpFetcher

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == f"https://{_PUBLIC}/start":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})
        return httpx.Response(200, content=b"secret")

    with HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(UrlFetchError):
            ingest_url(f"https://{_PUBLIC}/start", fetcher=fetcher)
    assert calls == [f"https://{_PUBLIC}/start"]


def test_ingest_url_temp_dir_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:
    from digifetch import HttpFetcher

    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def _recording_mkdtemp(*args: object, **kwargs: object) -> str:
        path = real_mkdtemp(*args, **kwargs)  # type: ignore[arg-type]
        created.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", _recording_mkdtemp)
    url = f"https://{_PUBLIC}/article"
    with HttpFetcher(transport=httpx.MockTransport(_ok_handler)) as fetcher:
        ingest_url(url, index_name="url-ingest-tmp", fetcher=fetcher)
    assert created, "expected ingest_url to stage via tempfile.mkdtemp"
    for path in created:
        assert not os.path.exists(path) or os.listdir(path) == []


def test_ingest_url_rejects_non_text() -> None:
    from digifetch import HttpFetcher

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"%PDF-1.7 fake", headers={"content-type": "application/pdf"}
        )

    with HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(UrlFetchError):
            ingest_url(f"https://{_PUBLIC}/doc.pdf", fetcher=fetcher)


def test_ingest_url_rejects_oversize() -> None:
    from digifetch import HttpFetcher

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/html"})

    with HttpFetcher(transport=httpx.MockTransport(handler), max_bytes=1024) as fetcher:
        with pytest.raises(UrlFetchError):
            ingest_url(f"https://{_PUBLIC}/huge", fetcher=fetcher)


def test_ingest_url_redirect_updates_final_url() -> None:
    from digifetch import HttpFetcher

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"https://{_PUBLIC}/start":
            return httpx.Response(302, headers={"location": f"https://{_PUBLIC_2}/final"})
        return httpx.Response(
            200, content=_HTML.encode("utf-8"), headers={"content-type": "text/html"}
        )

    url = f"https://{_PUBLIC}/start"
    with HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        result = ingest_url(url, index_name="url-ingest-redirect", fetcher=fetcher)
    assert result.source_url == url
    assert result.final_url == f"https://{_PUBLIC_2}/final"
    assert result.chunks_created >= 1
