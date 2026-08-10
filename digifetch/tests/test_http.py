"""Tests for digifetch.http — fetch, download, size cap, cookie hand-off.

The network is mocked with ``httpx.MockTransport`` (no sockets). This exercises
the real ``httpx.Client`` request/stream machinery against an in-process handler
— closer to production than a fully fake client, while still hitting no network.
"""

from __future__ import annotations

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
            data={"GetReserchFile": "111"},
            cookies={"session": "abc123"},
        )

    assert isinstance(result, FetchResult)
    assert result.status_code == 200
    assert result.text.startswith("https://s3.example.com/")
    assert result.content_type == "text/plain"
    assert seen["method"] == "POST"
    assert b"GetReserchFile=111" in seen["content"]  # form-encoded body sent
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
