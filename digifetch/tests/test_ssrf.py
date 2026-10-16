"""SSRF guard tests for the digifetch fetch path (#3934).

A benign-looking URL (or a redirect target) must never be dialled when it is
loopback, link-local, RFC1918 / CGNAT, unspecified, or a cloud metadata
address. The network is mocked — the assertion is that the handler is *never
called* for a refused URL, i.e. no socket is opened.
"""

from __future__ import annotations

import httpx
import pytest

from digifetch.http import HttpFetcher
from digifetch.ssrf import SsrfBlockedError, validate_fetch_url

pytestmark = pytest.mark.unit

# Public, globally-routable literals so the guard needs no live DNS.
_PUBLIC = "93.184.216.34"
_PUBLIC_2 = "1.1.1.1"


def _fetcher(handler, **kwargs) -> HttpFetcher:
    """Build a fetcher on the production (client-owning) path, mocked transport."""
    return HttpFetcher(transport=httpx.MockTransport(handler), **kwargs)


# ── validate_fetch_url ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://127.0.0.1/admin",
        "http://127.1/admin",
        "http://localhost/admin",
        "http://[::1]/admin",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
    ],
)
def test_validate_refuses_internal_targets(url: str) -> None:
    with pytest.raises(SsrfBlockedError):
        validate_fetch_url(url)


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/", "javascript:alert(1)"],
)
def test_validate_refuses_non_http_schemes(url: str) -> None:
    with pytest.raises(SsrfBlockedError):
        validate_fetch_url(url)


def test_validate_allows_public_https_literal() -> None:
    url = f"https://{_PUBLIC}/report"
    assert validate_fetch_url(url) == url


def test_allowlist_host_bypasses_private_refusal() -> None:
    url = "http://10.0.0.5/internal"
    assert validate_fetch_url(url, allowed_hosts=["10.0.0.5"]) == url


# ── fetch: initial URL ────────────────────────────────────────────────────────


def test_fetch_refuses_internal_url_without_dialling() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="secret")

    with _fetcher(handler) as f, pytest.raises(SsrfBlockedError):
        f.fetch("http://169.254.169.254/latest/meta-data/")
    assert calls == []


# ── fetch: redirect hops ──────────────────────────────────────────────────────


def test_fetch_refuses_redirect_to_internal_address() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == f"https://{_PUBLIC}/start":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})
        return httpx.Response(200, text="secret")

    with _fetcher(handler) as f, pytest.raises(SsrfBlockedError):
        f.fetch(f"https://{_PUBLIC}/start")
    # The internal hop must never be requested.
    assert calls == [f"https://{_PUBLIC}/start"]


def test_fetch_refuses_redirect_to_metadata_address() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(301, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with _fetcher(handler) as f, pytest.raises(SsrfBlockedError):
        f.fetch(f"https://{_PUBLIC}/start")
    assert calls == [f"https://{_PUBLIC}/start"]


def test_fetch_follows_legitimate_public_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"https://{_PUBLIC}/start":
            return httpx.Response(302, headers={"location": f"https://{_PUBLIC_2}/final"})
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    with _fetcher(handler) as f:
        result = f.fetch(f"https://{_PUBLIC}/start")

    assert result.text == "ok"
    assert result.url == f"https://{_PUBLIC_2}/final"


def test_fetch_caps_redirect_hops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Self-redirect forever: the hop cap must break the loop.
        return httpx.Response(302, headers={"location": str(request.url)})

    with _fetcher(handler) as f, pytest.raises(httpx.TooManyRedirects):
        f.fetch(f"https://{_PUBLIC}/loop")


def test_download_refuses_redirect_to_internal_address() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == f"https://{_PUBLIC}/doc":
            return httpx.Response(302, headers={"location": "http://10.1.2.3/secret"})
        return httpx.Response(200, content=b"secret")

    with _fetcher(handler) as f, pytest.raises(SsrfBlockedError):
        f.download(f"https://{_PUBLIC}/doc")
    assert calls == [f"https://{_PUBLIC}/doc"]


def test_fetch_allowlist_permits_operator_trusted_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="internal ok", headers={"content-type": "text/plain"})

    with _fetcher(handler, allowed_hosts=["10.9.9.9"]) as f:
        result = f.fetch("http://10.9.9.9/service")
    assert result.text == "internal ok"
