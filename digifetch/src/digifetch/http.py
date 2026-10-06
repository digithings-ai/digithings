"""HTTP fetch / download helpers (the non-browser fetch path).

Covers the lightweight HTTP seam twelve-x uses *alongside* the browser:
- ``nodes/scrape.py`` captures Playwright session cookies, then issues a plain
  ``requests.post(AJAX_URL, data=..., cookies=..., timeout=30)`` to resolve a
  pre-signed S3 URL, with ``raise_for_status()``.
- The downstream step then downloads PDF *bytes* from that URL (the byte fetch
  is generic; PDF text extraction with pdfplumber stays site-specific).

This module provides a small ``HttpFetcher`` over ``httpx`` (not ``requests`` —
the monorepo HTTP convention, async-capable, and it dodges the venv's
``requests``/urllib3 version warning) with a bounded timeout envelope mirroring
``digibase.http_client.DEFAULT_TIMEOUT``. Retry/backoff is *composed* via
:func:`digifetch.retry.with_retry`, not baked in.

The cookie hand-off (``cookies_from_playwright``) is the real twelve-x seam:
turn ``context.cookies()`` into a plain ``{name: value}`` dict an HTTP client
can send.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import (
    Any,  # score:allow untyped any — Playwright cookie dicts are untyped (browser optional)
)
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, ConfigDict

from digifetch.ssrf import validate_fetch_url

logger = logging.getLogger(__name__)

# Bounded timeout envelope, mirroring digibase.http_client.DEFAULT_TIMEOUT so the
# scraping engine shares the fleet-wide HTTP timeout convention. A bare
# httpx.Client() waits forever on a slow upstream — unacceptable on a scrape path.
DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

# Conservative default cap on a single download (32 MiB). Research PDFs are well
# under this; the cap prevents a misbehaving/poisoned URL from exhausting memory.
DEFAULT_MAX_BYTES = 32 * 1024 * 1024

# Redirects are never auto-followed: each hop is re-validated by the SSRF guard
# before it is requested. This caps how many hops one fetch may take.
MAX_REDIRECTS = 5

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Redirect statuses that rewrite a body-bearing method to GET. 303 always becomes
# GET; 301/302 downgrade POST to GET (browser semantics, and httpx's own rule).
# 307/308 are deliberately absent: RFC 9110 §15.4 requires them to preserve both
# method and body, so a POST retry must stay a POST with its body intact.
_METHOD_DOWNGRADE_STATUSES = frozenset({301, 302, 303})

# Headers that may follow a redirect to another origin. This is an ALLOW-list, so
# a credential header the seam has never heard of (Authorization, x-api-key, a
# vendor's x-auth-token, …) is dropped by default rather than leaked — httpx only
# strips Authorization, which is too narrow a net for a shared seam. Anything not
# named here does not cross an origin boundary.
#
# `referer` is included deliberately: browsers send it cross-origin by default,
# and the one consumer that sets it (digiquant's gloomberb) needs it past an
# anti-hotlink hop. It can disclose the original path, which is a smaller risk
# than breaking a live scraper — narrow it via a Referrer-Policy if that changes.
_CROSS_ORIGIN_SAFE_HEADERS = frozenset(
    {
        "accept",
        "accept-charset",
        "accept-encoding",
        "accept-language",
        "cache-control",
        "content-type",
        "if-match",
        "if-modified-since",
        "if-none-match",
        "if-unmodified-since",
        "range",
        "referer",
        "user-agent",
    }
)

# Body-only headers. A hop rewritten to GET carries no body, so these must not
# survive the rewrite (httpx strips the same pair on a downgrade).
_BODY_ONLY_HEADERS = frozenset({"content-length", "transfer-encoding"})


def _url_origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) identity used for same-origin redirect decisions."""
    parsed = urlparse(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port)


def _redirect_method(status_code: int, method: str) -> str:
    """The method to re-send on the next hop after *status_code*.

    303 always becomes GET and 301/302 downgrade a body-bearing method to GET
    (browser semantics, matching httpx's own rule). 307/308 keep *method*: RFC 9110
    §15.4 requires them to preserve both method and body, so a POST re-sent after
    a 307 must stay a POST with its body.
    """
    if status_code in _METHOD_DOWNGRADE_STATUSES and method not in ("GET", "HEAD"):
        return "GET"
    return method


def _hop_headers(
    headers: Mapping[str, str] | None,
    *,
    same_origin: bool,
    method: str,
) -> dict[str, str] | None:
    """Per-call headers for one hop, with credentials dropped when off-origin.

    Per-call headers are host-agnostic — the same reasoning that origin-scopes
    per-call cookies applies to a bearer token or API key handed to the seam. On
    a hop that leaves the original origin only :data:`_CROSS_ORIGIN_SAFE_HEADERS`
    survive, so an unknown credential header cannot leak by default.
    """
    if not headers:
        return None
    hop = (
        dict(headers)
        if same_origin
        else {k: v for k, v in headers.items() if k.lower() in _CROSS_ORIGIN_SAFE_HEADERS}
    )
    if method == "GET":
        hop = {k: v for k, v in hop.items() if k.lower() not in _BODY_ONLY_HEADERS}
    return hop or None


class FetchResult(BaseModel):
    """Outcome of an HTTP fetch — text body plus useful response metadata.

    A typed model (never a bare dict) so consumers get a stable, validated
    contract. ``url`` is the final URL after redirects.
    """

    model_config = ConfigDict(frozen=True)

    status_code: int
    url: str
    text: str
    content_type: str = ""


class DownloadResult(BaseModel):
    """Outcome of a binary download — raw bytes plus metadata.

    ``content`` carries the downloaded bytes (e.g. a PDF) for hand-off to a
    site-specific parser. ``content_type`` echoes the server's declared type.
    """

    model_config = ConfigDict(frozen=True)

    status_code: int
    url: str
    content: bytes
    content_type: str = ""

    @property
    def size(self) -> int:
        """Number of downloaded bytes."""
        return len(self.content)


class DownloadTooLargeError(RuntimeError):
    """Raised when a download exceeds the configured byte cap."""


def cookies_from_playwright(cookies: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Flatten Playwright ``context.cookies()`` into a ``{name: value}`` dict.

    Playwright returns a list of cookie dicts (``name``/``value``/``domain``/...);
    an HTTP client only needs name→value to replay the authenticated session.
    This is exactly the hand-off twelve-x's ``scrape_research`` does inline
    before its AJAX call.
    """
    out: dict[str, str] = {}
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and isinstance(value, str):
            out[name] = value
    return out


class HttpFetcher:
    """Thin, bounded-timeout HTTP client for the fetch/download seam.

    Wraps a single reusable ``httpx.Client`` (connection pooling) with a default
    timeout envelope and optional default headers/cookies. Use as a context
    manager to release the transport on exit — note :meth:`close` only closes a
    client this fetcher *created*; an injected ``client=`` is owned by the caller
    and is left open (the caller closes it). Retry/backoff is applied by
    *wrapping* a method call in :func:`digifetch.retry.with_retry`.

    **SSRF guard.** Neither :meth:`fetch` nor :meth:`download` auto-follows
    redirects. Every URL — the original and each redirect hop — is validated by
    :func:`digifetch.ssrf.validate_fetch_url` (http/https only; loopback,
    link-local, RFC1918, CGNAT, ``0.0.0.0`` and metadata addresses refused)
    before a request is sent, and hops are capped at :data:`MAX_REDIRECTS`. Pass
    ``allowed_hosts`` for operator-trusted internal hosts.

    **Redirect credentials.** Per-call ``cookies`` (the Playwright hand-off
    seam) and per-call ``headers`` are host-agnostic, so both are scoped to the
    original origin: a cross-origin redirect hop drops them instead of carrying a
    session cookie or an API key onto another host. Off-origin, only headers on
    the :data:`_CROSS_ORIGIN_SAFE_HEADERS` allow-list survive — a credential
    header the seam has never heard of is dropped by default, not leaked. Cookies
    given to the constructor are gated the same way. Headers an injected
    ``client=`` carries are the caller's own and are not touched.
    """

    def __init__(
        self,
        *,
        timeout: httpx.Timeout | float | None = DEFAULT_TIMEOUT,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        allowed_hosts: Iterable[str] | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """Build a fetcher.

        Args:
            timeout:   httpx timeout (float / ``httpx.Timeout`` / None to disable).
            headers:   Default headers sent on every request (e.g. a User-Agent).
                        Baked into the client this fetcher builds, so they are the
                        caller's to keep credential-free.
            cookies:   Default cookies (e.g. from :func:`cookies_from_playwright`),
                        applied per hop and origin-scoped like per-call cookies.
            max_bytes: Hard cap on a single download body; exceeding it raises
                       :class:`DownloadTooLargeError`.
            allowed_hosts: Operator-trusted hostnames (exact, case-insensitive)
                       exempted from the SSRF address refusal. Read no env here —
                       the caller passes this in (``digisearch`` sources it from
                       ``DIGISEARCH_FETCH_ALLOWED_HOSTS``).
            transport: Optional ``httpx`` transport for the client this fetcher
                       builds (tests inject ``httpx.MockTransport`` to exercise
                       the real header/cookie/timeout path without a socket).
                       Ignored when ``client`` is supplied.
            client:    Inject a fully pre-built ``httpx.Client``. When given, the
                       client owns its own ``headers`` / ``cookies`` / ``timeout``
                       — the corresponding constructor args are NOT re-applied.
                       Redirects are still driven manually with per-request
                       ``follow_redirects=False``, so an injected client cannot
                       bypass the SSRF guard.
        """
        self._max_bytes = max_bytes
        self._allowed_hosts = tuple(
            h.strip().lower() for h in (allowed_hosts or ()) if h and h.strip()
        )
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                timeout=timeout,
                transport=transport,
                follow_redirects=False,
            )
            self._owns_client = True
        # Fetcher-level headers/cookies are applied per hop rather than baked
        # into the client, so they pass through the same origin gate as per-call
        # values. Two reasons: a client-jar cookie set without a domain is
        # host-agnostic and httpx replays it to *every* host; and httpx rejects a
        # ``None`` header value, so a client-level header cannot be withdrawn on
        # a hop that has to drop it. An injected client keeps its own.
        self._default_headers = dict(headers) if headers else {}
        self._default_cookies = dict(cookies) if cookies else {}

    def _validate(self, url: str) -> None:
        """Refuse *url* unless it passes the SSRF guard (raises :class:`SsrfBlockedError`)."""
        validate_fetch_url(url, allowed_hosts=self._allowed_hosts)

    def _hop_cookies(
        self,
        per_call: Mapping[str, str] | None,
        *,
        same_origin: bool,
    ) -> dict[str, str] | None:
        """Merged fetcher + per-call cookies for one hop, or ``None`` when off-origin.

        Per-call cookies override the fetcher defaults. A hop that leaves the
        original origin gets nothing at all, so no session credential follows a
        redirect onto another host.
        """
        if not same_origin:
            return None
        merged = {**self._default_cookies, **dict(per_call or {})}
        return merged or None

    def _hop_headers(
        self,
        per_call: Mapping[str, str] | None,
        *,
        same_origin: bool,
        method: str,
    ) -> dict[str, str] | None:
        """Merged fetcher + per-call headers for one hop, origin-gated.

        Per-call headers override the fetcher defaults. Off-origin, only
        :data:`_CROSS_ORIGIN_SAFE_HEADERS` survive, so a credential header the
        seam has never heard of is dropped by default rather than leaked.
        """
        merged = {**self._default_headers, **dict(per_call or {})}
        return _hop_headers(merged, same_origin=same_origin, method=method)

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying client (only if this fetcher created it)."""
        if self._owns_client:
            self._client.close()

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json: Any = None,  # arbitrary JSON-serializable body
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> FetchResult:
        """Issue an HTTP request and return the decoded text body.

        Generalizes twelve-x's ``requests.post(AJAX_URL, data=..., cookies=...)``
        → it raises on a 4xx/5xx (``raise_for_status``) and returns a typed
        :class:`FetchResult`. Per-call ``headers``/``cookies`` merge over the
        fetcher defaults.

        Redirects are followed manually (bounded by :data:`MAX_REDIRECTS`) and
        each hop is re-validated by the SSRF guard before it is requested. Both
        ``cookies`` and ``headers`` are forwarded **only to same-origin hops**
        (see :data:`_CROSS_ORIGIN_SAFE_HEADERS` for the headers that may cross
        an origin boundary). A 307/308 re-sends the original method and body;
        301/302/303 rewrite a body-bearing method to GET and drop the body, per
        RFC 9110 §15.4.
        """
        origin = _url_origin(url)
        current_url = url
        current_method = method
        for _ in range(MAX_REDIRECTS + 1):
            self._validate(current_url)
            same_origin = _url_origin(current_url) == origin
            hop_cookies = self._hop_cookies(cookies, same_origin=same_origin)
            response = self._client.request(
                current_method,
                current_url,
                params=dict(params) if params else None,
                data=dict(data) if data else None,
                json=json,
                headers=self._hop_headers(
                    headers, same_origin=same_origin, method=current_method
                ),
                cookies=hop_cookies,
                follow_redirects=False,
            )
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if location:
                    current_url = urljoin(str(response.url), location)
                    next_method = _redirect_method(response.status_code, current_method)
                    if next_method != current_method:
                        # Only a rewritten hop discards the body; 307/308 keep
                        # re-encoding it from the same ``data``/``json`` mapping.
                        current_method, data, json = next_method, None, None
                    params = None
                    continue
            response.raise_for_status()
            return FetchResult(
                status_code=response.status_code,
                url=str(response.url),
                text=response.text,
                content_type=response.headers.get("content-type", ""),
            )
        raise httpx.TooManyRedirects(f"exceeded {MAX_REDIRECTS} redirects fetching {url}")

    def download(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> DownloadResult:
        """Download binary content (e.g. a PDF) with a size cap.

        Streams the body so an oversized response is aborted *before* the whole
        payload is buffered. Returns raw bytes in a typed :class:`DownloadResult`
        for hand-off to a site-specific parser (pdfplumber, etc.).

        Redirects are followed manually (bounded by :data:`MAX_REDIRECTS`) and
        each hop is re-validated by the SSRF guard before it is requested.
        Cookies, headers and the 307/308 method-preservation rule all behave
        exactly as in :meth:`fetch`.

        Raises:
            DownloadTooLargeError: if the body exceeds ``max_bytes``.
            httpx.HTTPStatusError: on a 4xx/5xx response.
            SsrfBlockedError: if a URL or redirect hop is refused by the guard.
        """
        origin = _url_origin(url)
        current_url = url
        current_method = method
        for _ in range(MAX_REDIRECTS + 1):
            self._validate(current_url)
            same_origin = _url_origin(current_url) == origin
            hop_cookies = self._hop_cookies(cookies, same_origin=same_origin)
            with self._client.stream(
                current_method,
                current_url,
                headers=self._hop_headers(
                    headers, same_origin=same_origin, method=current_method
                ),
                cookies=hop_cookies,
                follow_redirects=False,
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if location:
                        current_url = urljoin(str(response.url), location)
                        current_method = _redirect_method(response.status_code, current_method)
                        continue
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self._max_bytes:
                        raise DownloadTooLargeError(
                            f"download from {url} exceeded {self._max_bytes} bytes"
                        )
                    chunks.append(chunk)
                return DownloadResult(
                    status_code=response.status_code,
                    url=str(response.url),
                    content=b"".join(chunks),
                    content_type=response.headers.get("content-type", ""),
                )
        raise httpx.TooManyRedirects(f"exceeded {MAX_REDIRECTS} redirects downloading {url}")
