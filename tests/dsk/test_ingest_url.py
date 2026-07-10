"""UrlCorpusBuilder tests. Skipped unless digifetch (the `[ingest]` extra) is installed.

No real network calls: an `httpx.MockTransport` is injected via a
`digifetch.HttpFetcher` built by the test — the same pattern digifetch's own
test suite uses (see digifetch/ARCHITECTURE.md).
"""

from __future__ import annotations

import pytest

pytest.importorskip("digifetch")

import httpx  # noqa: E402

from digifetch import HttpFetcher  # noqa: E402

from digiskills.ingest_url import UrlCorpusBuilder  # noqa: E402
from digiskills.models import SkillSource, SourceKind  # noqa: E402

pytestmark = pytest.mark.unit


def _fetcher(handler) -> HttpFetcher:
    return HttpFetcher(transport=httpx.MockTransport(handler))


def _source(urls: list[str]) -> SkillSource:
    return SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=urls)


def test_fetches_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello docs", headers={"content-type": "text/plain"})

    fetcher = _fetcher(handler)
    corpus = UrlCorpusBuilder(fetcher=fetcher).build(_source(["https://example.com/docs"]))

    assert len(corpus.documents) == 1
    assert corpus.documents[0].content == "hello docs"
    assert corpus.truncated is False


def test_strips_html_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        html = "<html><body><script>evil()</script><h1>Title</h1><p>Body text</p></body></html>"
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    fetcher = _fetcher(handler)
    corpus = UrlCorpusBuilder(fetcher=fetcher).build(_source(["https://example.com/page"]))

    content = corpus.documents[0].content
    assert "evil()" not in content
    assert "Title" in content
    assert "Body text" in content


def test_json_content_type_detected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text='{"openapi": "3.0.0"}', headers={"content-type": "application/json"}
        )

    fetcher = _fetcher(handler)
    corpus = UrlCorpusBuilder(fetcher=fetcher).build(_source(["https://example.com/openapi.json"]))

    assert corpus.documents[0].content_type == "application/json"


def test_failed_fetch_is_skipped_not_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    fetcher = _fetcher(handler)
    corpus = UrlCorpusBuilder(fetcher=fetcher).build(_source(["https://example.com/down"]))

    assert corpus.documents == []
    assert corpus.truncated is True


def test_max_urls_cap_truncates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="content", headers={"content-type": "text/plain"})

    fetcher = _fetcher(handler)
    urls = [f"https://example.com/{i}" for i in range(5)]
    corpus = UrlCorpusBuilder(max_urls=2, fetcher=fetcher).build(_source(urls))

    assert len(corpus.documents) == 2
    assert corpus.truncated is True


def test_wrong_kind_raises() -> None:
    from pathlib import Path

    source = SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=Path("."))
    with pytest.raises(ValueError, match="URLS"):
        UrlCorpusBuilder().build(source)
