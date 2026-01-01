"""Page-corpus fallback for web_search enrichment: fakes only, no network."""

from __future__ import annotations

import pytest
from digifetch.http import FetchResult

from digisearch.web_search import page_corpus as pc
from digisearch.web_search import service as svc
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.web_search.service import WebSearchConfig, run_web_search

CHALLENGE = '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2F">'
LIVE_HTML = (
    "<html><body><article><h1>Live</h1><p>"
    + "Live page text. " * 80
    + "</p></article></body></html>"
)
URL = "https://example.org/modules/rooms/"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    site = tmp_path / "acme"
    site.mkdir()
    (site / "modules__rooms.md").write_text(
        "---\nurl: https://example.org/modules/rooms/\ntitle: Rooms\n---\n\nCorpus rooms text.\n"
    )
    (site / "no-front-matter.md").write_text("ignored\n")
    monkeypatch.setenv(pc.PAGE_CORPUS_DIR_ENV, str(tmp_path))
    pc._load.cache_clear()
    yield tmp_path
    pc._load.cache_clear()


def _run(monkeypatch, fetch, *, page_corpus="acme", url=URL):
    class _Fetcher:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch(self, u):
            return fetch(u)

    def _search(req, config):
        return WebSearchResponse(
            query=req.query,
            provider="ddgs",
            results=[WebSearchResult(url=url, title="Rooms", snippet="engine snippet")],
        )

    monkeypatch.setattr(svc, "HttpFetcher", _Fetcher)
    monkeypatch.setattr(svc, "_search_only", _search)
    monkeypatch.setattr(svc, "with_retry", lambda fn, policy, description="": fn())
    req = WebSearchRequest(query="rooms", page_corpus=page_corpus)
    return run_web_search(req, config=WebSearchConfig(fetch_max_pages=1, min_interval_s=0.0))


def test_challenge_page_uses_corpus(corpus, monkeypatch):
    resp = _run(monkeypatch, lambda u: FetchResult(status_code=202, url=u, text=CHALLENGE))
    assert resp.results[0].snippet == "Corpus rooms text."


def test_failed_fetch_uses_corpus(corpus, monkeypatch):
    def boom(u):
        raise RuntimeError("ssl eof")

    resp = _run(monkeypatch, boom)
    assert resp.results[0].snippet == "Corpus rooms text."


def test_redirect_to_challenge_uses_corpus(corpus, monkeypatch):
    resp = _run(
        monkeypatch,
        lambda u: FetchResult(
            status_code=200, url="https://example.org/.well-known/sgcaptcha/?r=x", text="x"
        ),
    )
    assert resp.results[0].snippet == "Corpus rooms text."


def test_live_page_wins_over_corpus(corpus, monkeypatch):
    resp = _run(monkeypatch, lambda u: FetchResult(status_code=200, url=u, text=LIVE_HTML))
    assert "Live page text" in resp.results[0].snippet
    assert "Corpus" not in resp.results[0].snippet


def test_without_page_corpus_enrichment_is_unchanged(corpus, monkeypatch):
    resp = _run(
        monkeypatch,
        lambda u: FetchResult(status_code=202, url=u, text=CHALLENGE),
        page_corpus=None,
    )
    assert "Corpus" not in resp.results[0].snippet


def test_page_missing_from_corpus_keeps_engine_snippet(corpus, monkeypatch):
    resp = _run(
        monkeypatch,
        lambda u: FetchResult(status_code=202, url=u, text=CHALLENGE),
        url="https://example.org/not-crawled/",
    )
    assert resp.results[0].snippet == "engine snippet"


def test_unknown_corpus_or_unset_dir_is_none(corpus, monkeypatch):
    assert pc.corpus_page_text("other", URL) is None
    assert pc.corpus_page_text("../acme", URL) is None
    monkeypatch.delenv(pc.PAGE_CORPUS_DIR_ENV)
    assert pc.corpus_page_text("acme", URL) is None


def test_url_normalisation_and_mirror_prefix(corpus):
    assert pc.corpus_page_text("acme", "http://www.EXAMPLE.org/modules/rooms?utm=1#x")
    assert pc.corpus_page_text("acme", "https://example.org/en-au/modules/rooms/")
    assert pc.corpus_page_text("acme", "https://example.org/fr/modules/rooms/") is None


@pytest.mark.parametrize(
    ("status", "url", "text", "expected"),
    [
        (202, URL, CHALLENGE, True),
        (202, URL, "", True),
        (200, "https://example.org/.well-known/sgcaptcha/", "", True),
        (200, URL, LIVE_HTML, False),
        (202, URL, LIVE_HTML, False),
    ],
)
def test_is_challenge_page(status, url, text, expected):
    assert pc.is_challenge_page(status, url, text) is expected


def test_request_rejects_bad_corpus_id():
    with pytest.raises(ValueError):
        WebSearchRequest(query="q", page_corpus="../etc")
