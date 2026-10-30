"""Pinned-tenant site fence: url matching, fenced page fetch, fenced enrichment.

No network: the real ``HttpFetcher`` runs against ``httpx.MockTransport`` with
DNS stubbed to a public address, so the SSRF guard and the per-hop fence both
run exactly as in production.
"""

from __future__ import annotations

import ipaddress

import httpx
import pytest
from digifetch.http import HttpFetcher

from digisearch.web_search import page_corpus as pc
from digisearch.web_search import service as svc
from digisearch.web_search.fence import FenceRefusedError, fence_guard, url_in_fence
from digisearch.web_search.fenced_fetch import fenced_links, invoke_web_fetch
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

pytestmark = pytest.mark.unit

# The Nomadis allowlist (12 pins over 11 sites), as the corpus map holds it.
PINS = [
    "nomadis.co",
    "linkedin.com/company/nomadis",
    "linkedin.com/posts/nomadis_*",
    "facebook.com/nomadisinc",
    "x.com/nomadisinc",
    "apps.apple.com/us/app/my-nomadis/id6737207494",
    "play.google.com/store/apps/details?id=co.nomadis.mynomadis",
    "cloud.google.com/customers/nomadis",
    "partners.sabre.com/partners/Nomadis%20Inc.",
    "imarcglobal.com/exhibitors/nomadis",
    "australianminingreview.com.au/techtalk/the-human-touch",
    "jobillico.com/see-company/nomadis",
]

PAGE = (
    "<html><head><title>Nomadis Academy</title></head><body><article><h1>Academy</h1><p>"
    + "Course text about camp operations. " * 80
    + "</p>"
    '<a href="/courses/intro">Intro</a>'
    '<a href="https://fr.academy.nomadis.co/">FR</a>'
    '<a href="https://www.nomadis.co/modules/rooms/">Rooms</a>'
    '<a href="https://www.linkedin.com/posts/nomadis_launch-123">Post</a>'
    '<a href="https://www.linkedin.com/in/someone">Person</a>'
    '<a href="https://nomadis.co.evil.com/x">Evil</a>'
    '<a href="https://en.wikipedia.org/wiki/Camp">Wiki</a>'
    '<a href="mailto:hi@nomadis.co">Mail</a>'
    "</article></body></html>"
)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    # The resolver the fetcher actually calls (robust to a package re-import).
    monkeypatch.setitem(
        HttpFetcher.fetch.__globals__["validate_fetch_url"].__globals__,
        "_resolve",
        lambda host, port: [ipaddress.ip_address("8.8.8.8")],
    )


def _fetcher(handler) -> HttpFetcher:
    return HttpFetcher(client=httpx.Client(transport=httpx.MockTransport(handler)))


# ── url_in_fence ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://nomadis.co/",
        "https://www.nomadis.co/modules/rooms/",
        "https://academy.nomadis.co/courses",
        "https://fr.academy.nomadis.co/",
        "https://support.nomadis.co/support/home",
        "https://lwmail.nomadis.co/",
        "https://www.linkedin.com/company/nomadis/about/",
        "https://ca.linkedin.com/company/nomadis",
        "https://www.linkedin.com/posts/nomadis_launch-activity-123",
        "https://m.facebook.com/nomadisinc/",
        "https://x.com/nomadisinc/status/1",
        "https://play.google.com/store/apps/details?id=co.nomadis.mynomadis&hl=en",
        "https://www.imarcglobal.com/exhibitors/nomadis",
        "https://www.jobillico.com/see-company/nomadis/jobs",
        "https://partners.sabre.com/partners/Nomadis%20Inc.",
    ],
)
def test_fence_admits_pinned_hosts_subdomains_and_paths(url: str) -> None:
    assert url_in_fence(url, PINS)


@pytest.mark.parametrize(
    "url",
    [
        "https://nomadis.co.evil.com/",
        "https://evilnomadis.co/",
        "https://nomadis.com/",
        "https://en.wikipedia.org/wiki/Nomadis",
        "https://www.linkedin.com/",
        "https://www.linkedin.com/in/someone",
        "https://www.linkedin.com/posts/othercorp_nomadis-123",
        "https://www.linkedin.com/company/nomadisfake",
        "https://facebook.com/",
        "https://twitter.com/nomadisinc",
        "https://play.google.com/store/apps/details?id=com.evil",
        "https://cloud.google.com/customers/",
        "ftp://nomadis.co/",
        "not a url",
    ],
)
def test_fence_refuses_lookalikes_other_paths_and_other_sites(url: str) -> None:
    assert not url_in_fence(url, PINS)


def test_fence_guard_raises_outside() -> None:
    guard = fence_guard(PINS)
    guard("https://academy.nomadis.co/")
    with pytest.raises(FenceRefusedError):
        guard("https://nomadis.freshworks.com/login")


def test_fenced_links_keep_only_in_fence_absolute_links() -> None:
    hrefs = ["/a", "#top", "mailto:x@y", "https://evilnomadis.co/", "https://academy.nomadis.co/b"]
    assert fenced_links("https://www.nomadis.co/", hrefs, PINS) == [
        "https://www.nomadis.co/a",
        "https://academy.nomadis.co/b",
    ]


# ── web_fetch ─────────────────────────────────────────────────────────────────


def test_web_fetch_reads_a_full_subdomain_page_and_returns_in_fence_links() -> None:
    env = invoke_web_fetch(
        {"url": "https://academy.nomadis.co/", "fence": PINS},
        fetcher=_fetcher(lambda r: httpx.Response(200, html=PAGE)),
    )
    assert env["ok"] is True
    data = env["data"]
    assert data["source"] == "live"
    assert data["title"] == "Nomadis Academy"
    assert "camp operations" in data["content"]
    assert len(data["content"]) > 2000  # the full page, not a 2000-char snippet
    assert data["links"] == [
        "https://academy.nomadis.co/courses/intro",
        "https://fr.academy.nomadis.co/",
        "https://www.nomadis.co/modules/rooms/",
        "https://www.linkedin.com/posts/nomadis_launch-123",
    ]


def test_web_fetch_refuses_an_off_fence_url_without_a_request() -> None:
    seen: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(str(r.url))
        return httpx.Response(200, html=PAGE)

    for url in (
        "https://nomadis.co.evil.com/",
        "https://evilnomadis.co/",
        "https://en.wikipedia.org/wiki/Nomadis",
        "https://www.linkedin.com/in/someone",
    ):
        env = invoke_web_fetch({"url": url, "fence": PINS}, fetcher=_fetcher(handler))
        assert env["ok"] is False and env["error"].startswith("fence_refused")
    assert seen == []


def test_web_fetch_refuses_a_redirect_hop_that_leaves_the_fence() -> None:
    seen: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(str(r.url))
        if r.url.host == "support.nomadis.co":
            return httpx.Response(302, headers={"location": "https://nomadis.freshworks.com/login"})
        return httpx.Response(200, html="<p>login page secret</p>")

    env = invoke_web_fetch(
        {"url": "https://support.nomadis.co/support/home", "fence": PINS},
        fetcher=_fetcher(handler),
    )
    assert env["ok"] is False and env["error"].startswith("fence_refused")
    assert seen == ["https://support.nomadis.co/support/home"]  # the far side is never asked


def test_web_fetch_follows_an_in_fence_redirect() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.host == "nomadis.co":
            return httpx.Response(301, headers={"location": "https://www.nomadis.co/"})
        return httpx.Response(200, html=PAGE)

    env = invoke_web_fetch({"url": "https://nomadis.co/", "fence": PINS}, fetcher=_fetcher(handler))
    assert env["ok"] is True
    assert env["data"]["final_url"] == "https://www.nomadis.co/"


def test_web_fetch_redirect_refusal_never_falls_back_to_corpus(tmp_path, monkeypatch) -> None:
    _corpus(tmp_path, monkeypatch, "https://support.nomadis.co/support/home")
    env = invoke_web_fetch(
        {"url": "https://support.nomadis.co/support/home", "fence": PINS, "page_corpus": "acme"},
        fetcher=_fetcher(
            lambda r: httpx.Response(302, headers={"location": "https://evil.example/"})
        ),
    )
    assert env["ok"] is False and env["error"].startswith("fence_refused")


def _corpus(tmp_path, monkeypatch, url: str) -> None:
    site = tmp_path / "acme"
    site.mkdir(exist_ok=True)
    (site / "page.md").write_text(
        f"---\nurl: {url}\n---\n\nSaved text. [Rooms](https://www.nomadis.co/modules/rooms/) "
        "[Off](https://evil.example/)\n"
    )
    monkeypatch.setenv(pc.PAGE_CORPUS_DIR_ENV, str(tmp_path))
    pc._load.cache_clear()


def test_web_fetch_challenge_page_uses_the_saved_copy(tmp_path, monkeypatch) -> None:
    _corpus(tmp_path, monkeypatch, "https://www.nomadis.co/")
    challenge = '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2F">'
    env = invoke_web_fetch(
        {"url": "https://www.nomadis.co/", "fence": PINS, "page_corpus": "acme"},
        fetcher=_fetcher(lambda r: httpx.Response(202, html=challenge)),
    )
    pc._load.cache_clear()
    assert env["ok"] is True
    assert env["data"]["source"] == "page_corpus"
    assert "Saved text." in env["data"]["content"]
    assert env["data"]["links"] == ["https://www.nomadis.co/modules/rooms/"]


def test_web_fetch_challenge_without_corpus_is_an_error() -> None:
    challenge = '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2F">'
    env = invoke_web_fetch(
        {"url": "https://www.nomadis.co/", "fence": PINS},
        fetcher=_fetcher(lambda r: httpx.Response(202, html=challenge)),
    )
    assert env["ok"] is False and env["error"].startswith("web_fetch failed")


def test_web_fetch_needs_a_fence() -> None:
    env = invoke_web_fetch({"url": "https://www.nomadis.co/", "fence": []})
    assert env["ok"] is False and env["error"].startswith("invalid web_fetch input")


def test_web_fetch_truncates_to_max_chars() -> None:
    env = invoke_web_fetch(
        {"url": "https://academy.nomadis.co/", "fence": PINS, "max_chars": 500},
        fetcher=_fetcher(lambda r: httpx.Response(200, html=PAGE)),
    )
    assert env["ok"] is True
    assert len(env["data"]["content"]) == 500 and env["data"]["truncated"] is True


# ── web_search enrichment under a fence ───────────────────────────────────────


def test_enrichment_refuses_an_off_fence_redirect_and_keeps_the_snippet(monkeypatch) -> None:
    seen: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(str(r.url))
        if r.url.host == "support.nomadis.co":
            return httpx.Response(302, headers={"location": "https://evil.example/page"})
        return httpx.Response(200, html="<article>" + "off fence text " * 100 + "</article>")

    def _search(req, config):
        return WebSearchResponse(
            query=req.query,
            provider="ddgs",
            results=[
                WebSearchResult(
                    url="https://support.nomadis.co/a", title="Help", snippet="engine snippet"
                )
            ],
        )

    monkeypatch.setattr(svc, "HttpFetcher", lambda **k: _fetcher(handler))
    monkeypatch.setattr(svc, "_search_only", _search)
    monkeypatch.setattr(svc, "with_retry", lambda fn, policy, description="": fn())
    resp = svc.run_web_search(WebSearchRequest(query="help", fence=PINS))
    assert seen == ["https://support.nomadis.co/a"]
    assert resp.results[0].snippet == "engine snippet"
    assert "off fence" not in (resp.results[0].snippet or "")


def test_enrichment_without_a_fence_is_unchanged(monkeypatch) -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.host == "a.example":
            return httpx.Response(302, headers={"location": "https://b.example/page"})
        return httpx.Response(
            200,
            html="<html><body><article><p>" + "b page text " * 100 + "</p></article></body></html>",
        )

    def _search(req, config):
        return WebSearchResponse(
            query=req.query,
            provider="ddgs",
            results=[WebSearchResult(url="https://a.example/", title="A", snippet="s")],
        )

    monkeypatch.setattr(svc, "HttpFetcher", lambda **k: _fetcher(handler))
    monkeypatch.setattr(svc, "_search_only", _search)
    monkeypatch.setattr(svc, "with_retry", lambda fn, policy, description="": fn())
    resp = svc.run_web_search(WebSearchRequest(query="a"))
    assert "b page text" in (resp.results[0].snippet or "")


def test_web_fetch_keeps_visible_text_when_the_extractor_under_reads() -> None:
    # Builder pages: lots of text in divs, no article; nav/script must not leak.
    blocks = "".join(
        f"<div><span>Course module {i} covers camp check-in.</span></div>" for i in range(60)
    )
    html = (
        "<html><head><title>Academy</title><script>var secret=1</script></head>"
        f"<body><div class='wrap'>{blocks}</div></body></html>"
    )
    env = invoke_web_fetch(
        {"url": "https://academy.nomadis.co/", "fence": PINS},
        fetcher=_fetcher(lambda r: httpx.Response(200, html=html)),
    )
    assert env["ok"] is True
    assert "Course module 59 covers camp check-in." in env["data"]["content"]
    assert "secret" not in env["data"]["content"]
