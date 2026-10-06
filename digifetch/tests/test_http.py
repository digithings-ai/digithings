"""Tests for digifetch.http — fetch, download, size cap, cookie hand-off.

The network is mocked with ``httpx.MockTransport`` (no sockets). This exercises
the real ``httpx.Client`` request/stream machinery against an in-process handler
— closer to production than a fully fake client, while still hitting no network.
"""

from __future__ import annotations

import json

import httpx
import pytest

from digifetch.http import (
    DownloadResult,
    DownloadTooLargeError,
    FetchResult,
    HttpFetcher,
    cookies_from_playwright,
)
from digifetch.retry import RetryPolicy, with_retry

pytestmark = pytest.mark.unit


def _fetcher(handler, **kwargs) -> HttpFetcher:
    """Build an HttpFetcher backed by an httpx.MockTransport handler."""
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return HttpFetcher(client=client, **kwargs)


# ── cookie hand-off ───────────────────────────────────────────────────────────


def test_cookies_from_playwright_flattens_name_value() -> None:
    pw_cookies = [
        {"name": "session", "value": "abc123", "domain": "x.com", "path": "/"},
        {"name": "csrf", "value": "tok", "domain": "x.com"},
        {"domain": "x.com"},  # malformed (no name/value) — skipped
        {"name": "n", "value": 5},  # non-str value — skipped
    ]
    assert cookies_from_playwright(pw_cookies) == {"session": "abc123", "csrf": "tok"}


# ── fetch ─────────────────────────────────────────────────────────────────────


def test_fetch_post_returns_typed_result_and_echoes_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content"] = request.content
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(
            200,
            text="https://s3.example.com/report.pdf?sig=abc",
            headers={"content-type": "text/plain"},
        )

    with _fetcher(handler) as f:
        result = f.fetch(
            "https://x.com/ajax",
            method="POST",
            data={"file_id": "111"},
            cookies={"session": "abc123"},
        )

    assert isinstance(result, FetchResult)
    assert result.status_code == 200
    assert result.text.startswith("https://s3.example.com/")
    assert result.content_type == "text/plain"
    assert seen["method"] == "POST"
    assert b"file_id=111" in seen["content"]  # form-encoded body sent
    assert "session=abc123" in (seen["cookie"] or "")


def test_fetch_raises_for_status_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    with _fetcher(handler) as f, pytest.raises(httpx.HTTPStatusError):
        f.fetch("https://x.com/missing")


def test_default_headers_applied_when_fetcher_builds_client() -> None:
    """Default headers passed to HttpFetcher (the production path) reach the wire."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, text="ok")

    # Construct via the real (client-owning) path, injecting only the transport
    # so no socket opens — this exercises the production default-header wiring.
    with HttpFetcher(
        headers={"User-Agent": "DigiFetchBot/1.0"},
        transport=httpx.MockTransport(handler),
    ) as f:
        f.fetch("https://x.com/")
    assert seen["ua"] == "DigiFetchBot/1.0"


def test_per_call_cookies_override_and_merge() -> None:
    """Per-call cookies are sent even when the fetcher has none by default."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    with _fetcher(handler) as f:
        f.fetch("https://x.com/ajax", cookies={"session": "xyz"})
    assert "session=xyz" in (seen["cookie"] or "")


# ── download ────────────────────────────────────────────────────────────────


def test_download_returns_bytes_and_size() -> None:
    body = b"%PDF-1.7 fake pdf bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    with _fetcher(handler) as f:
        result = f.download("https://s3.example.com/report.pdf")

    assert isinstance(result, DownloadResult)
    assert result.content == body
    assert result.size == len(body)
    assert result.content_type == "application/pdf"


def test_download_enforces_max_bytes() -> None:
    big = b"x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    with _fetcher(handler, max_bytes=1024) as f, pytest.raises(DownloadTooLargeError):
        f.download("https://s3.example.com/huge.bin")


def test_download_raises_for_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"boom")

    with _fetcher(handler) as f, pytest.raises(httpx.HTTPStatusError):
        f.download("https://s3.example.com/err")


# ── composition with retry (the documented seam) ──────────────────────────────


def test_fetch_composed_with_retry_recovers_from_transient_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("transient")
        return httpx.Response(200, text="ok")

    policy = RetryPolicy(attempts=3, jitter=False, sleep=lambda _: None)
    with _fetcher(handler) as f:
        result = with_retry(lambda: f.fetch("https://x.com/"), policy, description="ajax")

    assert result.text == "ok"
    assert calls["n"] == 2  # failed once, retried, succeeded


# ── redirect cookie scoping ───────────────────────────────────────────────────


def test_redirect_drops_per_call_cookies_on_cross_origin_hop() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("cookie")))
        if request.url.host == "one.example":
            return httpx.Response(302, headers={"location": "https://two.example/final"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example", "two.example"]) as f:
        result = f.fetch("https://one.example/start", cookies={"session": "secret"})

    assert result.text == "ok"
    assert seen[0] == ("https://one.example/start", "session=secret")
    assert seen[1][0] == "https://two.example/final"
    assert seen[1][1] is None


def test_redirect_keeps_per_call_cookies_on_same_origin_hop() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("cookie")))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://one.example/final"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example"]) as f:
        result = f.fetch("https://one.example/start", cookies={"session": "secret"})

    assert result.text == "ok"
    assert seen[1] == ("https://one.example/final", "session=secret")


def test_download_redirect_drops_per_call_cookies_on_cross_origin_hop() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("cookie")))
        if request.url.host == "one.example":
            return httpx.Response(302, headers={"location": "https://two.example/final"})
        return httpx.Response(200, content=b"bytes")

    with _fetcher(handler, allowed_hosts=["one.example", "two.example"]) as f:
        result = f.download("https://one.example/doc", cookies={"session": "secret"})

    assert result.content == b"bytes"
    assert seen[0][1] == "session=secret"
    assert seen[1][1] is None


# ── redirect header scoping (credential leak) ─────────────────────────────────


def test_redirect_drops_per_call_credential_headers_on_cross_origin_hop() -> None:
    """A credential in a per-call header must not follow a redirect off-origin.

    Regression for DIG-1377: ``headers`` was forwarded to every hop, so an
    ``x-api-key`` handed to the original origin arrived at the redirect target.
    """
    seen: list[tuple[str, str | None, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                str(request.url),
                request.headers.get("x-api-key"),
                request.headers.get("authorization"),
                request.headers.get("user-agent"),
            )
        )
        if request.url.host == "one.example":
            return httpx.Response(302, headers={"location": "https://two.example/steal"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example", "two.example"]) as f:
        result = f.fetch(
            "https://one.example/search",
            method="POST",
            json={"query": "q"},
            headers={
                "x-api-key": "exa_live_SECRET",
                "Authorization": "Bearer tok",
                "User-Agent": "DigiFetchBot/1.0",
            },
        )

    assert result.text == "ok"
    # Hop 1 (the origin the caller named) gets everything it was handed.
    assert seen[0] == (
        "https://one.example/search",
        "exa_live_SECRET",
        "Bearer tok",
        "DigiFetchBot/1.0",
    )
    # Hop 2 (off-origin) gets neither credential...
    assert seen[1][0] == "https://two.example/steal"
    assert seen[1][1] is None, "x-api-key leaked to the cross-origin redirect target"
    assert seen[1][2] is None, "Authorization leaked to the cross-origin redirect target"
    # ...but a non-credential header still rides along, so ordinary same-work
    # cross-origin redirects keep working.
    assert seen[1][3] == "DigiFetchBot/1.0"


def test_redirect_keeps_per_call_headers_on_same_origin_hop() -> None:
    """Origin scoping must not cost same-origin hops their credentials."""
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("x-api-key")))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://one.example/final"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example"]) as f:
        result = f.fetch("https://one.example/start", headers={"x-api-key": "k_SECRET"})

    assert result.text == "ok"
    assert seen[1] == ("https://one.example/final", "k_SECRET")


def test_download_redirect_drops_per_call_headers_on_cross_origin_hop() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("x-api-key")))
        if request.url.host == "one.example":
            return httpx.Response(302, headers={"location": "https://two.example/final"})
        return httpx.Response(200, content=b"bytes")

    with _fetcher(handler, allowed_hosts=["one.example", "two.example"]) as f:
        result = f.download("https://one.example/doc", headers={"x-api-key": "k_SECRET"})

    assert result.content == b"bytes"
    assert seen[0][1] == "k_SECRET"
    assert seen[1][1] is None


def test_constructor_cookies_do_not_leak_on_cross_origin_hop() -> None:
    """Fetcher-level cookies are origin-scoped too.

    Regression for DIG-1377: constructor ``cookies=`` were baked into the client
    jar, and httpx sends a host-agnostic jar cookie to *every* host, so they
    rode along on every redirect hop regardless of origin.
    """
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("cookie")))
        if request.url.host == "one.example":
            return httpx.Response(302, headers={"location": "https://two.example/final"})
        return httpx.Response(200, text="ok")

    # The production wiring: transport= only, so the fetcher builds the client.
    with HttpFetcher(
        cookies={"session": "ctor_secret"},
        transport=httpx.MockTransport(handler),
        allowed_hosts=["one.example", "two.example"],
    ) as f:
        f.fetch("https://one.example/start")

    assert seen[0][1] == "session=ctor_secret"
    assert seen[1][1] is None, "constructor cookie leaked to the cross-origin hop"


# ── redirect method/body preservation (RFC 9110 §15.4) ───────────────────────


@pytest.mark.parametrize("status", [307, 308])
def test_307_and_308_preserve_post_method_and_body(status: int) -> None:
    """307/308 must re-send the original method and body (RFC 9110 §15.4).

    Regression for DIG-1377: the downgrade condition fired for *any* redirect
    status on a body-bearing method, silently turning the retry into a GET with
    no body.
    """
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.method, request.content))
        if request.url.path == "/submit":
            return httpx.Response(status, headers={"location": "https://one.example/final"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example"]) as f:
        result = f.fetch(
            "https://one.example/submit",
            method="POST",
            json={"query": "secret"},
            headers={"x-api-key": "k_SECRET"},
        )

    assert result.text == "ok"
    assert len(seen) == 2
    assert seen[1][1] == "POST", f"{status} downgraded the method"
    assert json.loads(seen[1][2]) == {"query": "secret"}, f"{status} dropped the body"


@pytest.mark.parametrize("status", [301, 302, 303])
def test_301_302_303_still_downgrade_post_to_get(status: int) -> None:
    """303 always becomes GET; 301/302 downgrade a body-bearing method to GET."""
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.method, request.content))
        if request.url.path == "/submit":
            return httpx.Response(status, headers={"location": "https://one.example/final"})
        return httpx.Response(200, text="ok")

    with _fetcher(handler, allowed_hosts=["one.example"]) as f:
        result = f.fetch("https://one.example/submit", method="POST", json={"query": "q"})

    assert result.text == "ok"
    assert seen[1][1] == "GET"
    assert seen[1][2] == b""


def test_download_307_preserves_post_method() -> None:
    """``download`` carries the same redirect rule as ``fetch``."""
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.method))
        if request.url.path == "/doc":
            return httpx.Response(307, headers={"location": "https://one.example/final"})
        return httpx.Response(200, content=b"bytes")

    with _fetcher(handler, allowed_hosts=["one.example"]) as f:
        result = f.download("https://one.example/doc", method="POST")

    assert result.content == b"bytes"
    assert seen[1] == ("https://one.example/final", "POST")
