"""Point-in-time page fetch from a public web archive.

``fetch_markdown_at`` resolves a capture at or before ``as_of`` and downloads
only that archive URL. The caller's original URL is never opened: a miss
raises :class:`SnapshotUnavailable` instead of falling through to live HTML.

The resolver asks the archive's CDX index first (bounded by ``to=as_of``),
then the availability API, then a Memento TimeGate. A capture whose timestamp
is later than ``as_of`` is discarded even if an endpoint offers it as the
closest hit. Replay uses the ``id_`` raw modifier so the archived bytes are
not the archive's rewritten page, and a redirect onto a later capture is
refused.

Callers owe the archive a polite rate. The default client waits at least
``DIGISEARCH_SNAPSHOT_MIN_INTERVAL_S`` (1s) between requests.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from ipaddress import ip_address
from typing import Literal, Protocol
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
from digifetch.ratelimit import RateLimiter
from digifetch.ssrf import is_blocked_ip, validate_fetch_url
from pydantic import BaseModel, ConfigDict, Field

from digisearch.web_search.extractor import extract_markdown

_ARCHIVE_HOSTS = frozenset({"web.archive.org", "archive.org", "wayback.archive.org"})
_UA = (
    "digisearch-snapshot/1.0 (point-in-time research; +https://github.com/digithings-ai/digithings)"
)
_TOOLBAR_BLOCK = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT\s*-->.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_WM_IPP = re.compile(
    r"<div\b[^>]*\bid=[\"']wm-ipp(?:-base)?[\"'][^>]*>.*?</div>",
    re.IGNORECASE | re.DOTALL,
)
_TS_IN_PATH = re.compile(r"/web/(\d{14})")
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_LOCAL_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal", "metadata.goog"})
_LOCAL_SUFFIXES = (".local", ".internal", ".localhost")
_MAX_REDIRECTS = 3


class SnapshotError(RuntimeError):
    """Bad ``as_of``, a non-http URL, or a URL outside the archive allow-list."""


class SnapshotUnavailable(SnapshotError):
    """No capture at or before ``as_of``, or the archive redirect left that window."""


class Capture(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: str
    captured_at: datetime
    original_url: str
    status: str = "200"


class SnapshotRef(BaseModel):
    """Provenance for one accepted capture. ``source`` is ``wayback`` or ``memento``."""

    model_config = ConfigDict(frozen=True)

    original_url: str
    archive_url: str
    captured_at: datetime
    source: Literal["wayback", "memento"]
    timestamp: str


class SnapshotPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown: str
    ref: SnapshotRef


class ArchiveResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_code: int
    url: str
    content: bytes = b""
    headers: dict[str, str] = Field(default_factory=dict)


class ArchiveClient(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> ArchiveResponse:
        """GET one archive URL and return the raw response, without following redirects."""


def require_aware(as_of: datetime) -> datetime:
    """Return ``as_of`` as UTC. Naive datetimes are ambiguous for a cutoff and refused."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise SnapshotError("as_of must be timezone-aware")
    return as_of.astimezone(timezone.utc)


def assert_archive_url(url: str) -> str:
    """Refuse any URL whose host is not an archive host."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in _ARCHIVE_HOSTS:
        raise SnapshotError(f"refusing non-archive URL: {host or url}")
    return url


def parse_wayback_timestamp(raw: str) -> datetime | None:
    """Parse a 14-digit archive timestamp as UTC, or None when it is not one."""
    stamp = raw.strip()
    if len(stamp) < 14 or not stamp[:14].isdigit():
        return None
    try:
        parsed = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed


def select_capture(captures: Sequence[Capture], as_of: datetime) -> Capture | None:
    """Closest HTTP 200 capture at or before ``as_of``. Later rows are ignored."""
    as_of_utc = require_aware(as_of)
    eligible = [
        capture
        for capture in captures
        if capture.status in {"", "200"} and capture.captured_at <= as_of_utc
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda capture: capture.captured_at)


def strip_wayback_toolbar(html: str) -> str:
    """Drop the archive toolbar the replay shell inserts around the original page."""
    without_block = _TOOLBAR_BLOCK.sub("", html)
    return _WM_IPP.sub("", without_block)


def parse_cdx(payload: object) -> list[Capture]:
    """Turn a CDX JSON listing into captures. A header row and bad stamps are skipped."""
    if not isinstance(payload, list):
        return []
    start = 0
    header = ["timestamp", "original", "statuscode"]
    if payload and isinstance(payload[0], list) and payload[0] and payload[0][0] == "timestamp":
        header = [str(column) for column in payload[0]]
        start = 1
    index = {name: pos for pos, name in enumerate(header)}

    def _col(row: list[object], name: str) -> str:
        pos = index.get(name)
        if pos is None or pos >= len(row):
            return ""
        return str(row[pos])

    captures: list[Capture] = []
    for row in payload[start:]:
        if not isinstance(row, list):
            continue
        stamp = _col(row, "timestamp")
        captured = parse_wayback_timestamp(stamp)
        if captured is None:
            continue
        captures.append(
            Capture(
                timestamp=stamp[:14],
                captured_at=captured,
                original_url=_col(row, "original"),
                status=_col(row, "statuscode") or "200",
            )
        )
    return captures


class HttpxArchiveClient:
    """httpx client that only dials archive hosts and spaces requests."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        http: httpx.Client | None = None,
        min_interval_s: float = 1.0,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._owns = http is None
        self._http = http or httpx.Client(timeout=timeout, follow_redirects=False)
        self._limiter = limiter if limiter is not None else RateLimiter(min_interval=min_interval_s)

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> ArchiveResponse:
        assert_archive_url(url)
        validate_fetch_url(url, allowed_hosts=_ARCHIVE_HOSTS)
        self._limiter.acquire()
        merged = {"User-Agent": _UA, **dict(headers or {})}
        response = self._http.get(url, headers=merged, follow_redirects=False)
        return ArchiveResponse(
            status_code=response.status_code,
            url=str(response.url),
            content=response.content,
            headers=dict(response.headers.items()),
        )

    def close(self) -> None:
        if self._owns:
            self._http.close()


def _default_client(timeout: float) -> HttpxArchiveClient:
    raw = os.environ.get("DIGISEARCH_SNAPSHOT_MIN_INTERVAL_S", "1")
    try:
        interval = float(raw)
    except ValueError as exc:
        raise SnapshotError(f"invalid DIGISEARCH_SNAPSHOT_MIN_INTERVAL_S={raw!r}") from exc
    if interval < 0:
        raise SnapshotError("DIGISEARCH_SNAPSHOT_MIN_INTERVAL_S must be >= 0")
    return HttpxArchiveClient(timeout=timeout, min_interval_s=interval)


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _json_body(response: ArchiveResponse) -> object | None:
    if response.status_code != 200 or not response.content:
        return None
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return None


def _require_public_http_url(url: str) -> str:
    """Accept an http(s) URL and refuse literal internal hosts. Does not resolve DNS.

    The original URL is never fetched. Name resolution is the archive's job;
    doing it here would turn every unit test into a network call. Literal
    internal addresses and local names are still refused so they are not
    forwarded as an archive lookup.
    """
    raw = (url or "").strip()
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise SnapshotError(f"refusing non-http URL: {url!r}")
    if host in _LOCAL_HOSTS or host.endswith(_LOCAL_SUFFIXES):
        raise SnapshotError(f"refusing internal host: {host}")
    try:
        address = ip_address(host)
    except ValueError:
        return raw
    if is_blocked_ip(address):
        raise SnapshotError(f"refusing blocked address: {host}")
    return raw


def _from_cdx(client: ArchiveClient, url: str, as_of: datetime) -> Capture | None:
    query = urlencode(
        {
            "url": url,
            "output": "json",
            "fl": "timestamp,original,statuscode",
            "filter": "statuscode:200",
            "to": as_of.strftime("%Y%m%d%H%M%S"),
            "limit": "-1",
        }
    )
    response = client.get(f"https://web.archive.org/cdx/search/cdx?{query}")
    return select_capture(parse_cdx(_json_body(response)), as_of)


def _from_availability(client: ArchiveClient, url: str, as_of: datetime) -> Capture | None:
    query = urlencode({"url": url, "timestamp": as_of.strftime("%Y%m%d%H%M%S")})
    payload = _json_body(client.get(f"https://archive.org/wayback/available?{query}"))
    if not isinstance(payload, dict):
        return None
    snapshots = payload.get("archived_snapshots")
    closest = snapshots.get("closest") if isinstance(snapshots, dict) else None
    if not isinstance(closest, dict) or not closest.get("available"):
        return None
    stamp = str(closest.get("timestamp") or "")
    captured = parse_wayback_timestamp(stamp)
    status = str(closest.get("status") or "")
    if captured is None or captured > as_of or (status and status != "200"):
        return None
    return Capture(
        timestamp=stamp[:14],
        captured_at=captured,
        original_url=url,
        status="200",
    )


def _timestamp_in_url(url: str) -> str | None:
    match = _TS_IN_PATH.search(urlsplit(url).path)
    return match.group(1) if match else None


def _from_memento(client: ArchiveClient, url: str, as_of: datetime) -> Capture | None:
    stamp = as_of.strftime("%Y%m%d%H%M%S")
    gate = f"https://web.archive.org/web/{stamp}/{url}"
    response = client.get(gate, headers={"Accept": "application/link-format"})
    if response.status_code not in {200, *_REDIRECTS}:
        return None
    captured = _memento_datetime(response.headers)
    location = _header(response.headers, "location")
    located = _timestamp_in_url(urljoin(gate, location)) if location else None
    located_at = parse_wayback_timestamp(located) if located else None
    if located_at is not None and located_at > as_of:
        return None
    if captured is not None and captured > as_of:
        return None
    if located_at is not None:
        return Capture(
            timestamp=located_at.strftime("%Y%m%d%H%M%S"),
            captured_at=located_at,
            original_url=url,
            status="200",
        )
    if captured is None:
        return None
    return Capture(
        timestamp=captured.strftime("%Y%m%d%H%M%S"),
        captured_at=captured,
        original_url=url,
        status="200",
    )


def _memento_datetime(headers: Mapping[str, str]) -> datetime | None:
    raw = _header(headers, "memento-datetime")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve(url: str, as_of: datetime, *, client: ArchiveClient) -> SnapshotRef | None:
    """Return the closest capture at or before ``as_of``, or None when there is none."""
    original = _require_public_http_url(url)
    as_of_utc = require_aware(as_of)
    found: tuple[Literal["wayback", "memento"], Capture] | None = None
    cdx_hit = _from_cdx(client, original, as_of_utc)
    if cdx_hit is not None:
        found = ("wayback", cdx_hit)
    else:
        available = _from_availability(client, original, as_of_utc)
        if available is not None:
            found = ("wayback", available)
        else:
            memento = _from_memento(client, original, as_of_utc)
            if memento is not None:
                found = ("memento", memento)
    if found is None:
        return None
    source, chosen = found
    original_url = _require_public_http_url(chosen.original_url or original)
    archive_url = assert_archive_url(
        f"https://web.archive.org/web/{chosen.timestamp}id_/{original_url}"
    )
    return SnapshotRef(
        original_url=original_url,
        archive_url=archive_url,
        captured_at=chosen.captured_at,
        source=source,
        timestamp=chosen.timestamp,
    )


def _decode(content: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        name, _, value = part.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip("\"'") or "utf-8"
            break
    try:
        return content.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return content.decode("utf-8", errors="replace")


def _download_capture(client: ArchiveClient, archive_url: str, as_of: datetime) -> ArchiveResponse:
    current = assert_archive_url(archive_url)
    for _ in range(_MAX_REDIRECTS):
        response = client.get(current)
        if response.status_code not in _REDIRECTS:
            return response
        location = _header(response.headers, "location")
        if not location:
            raise SnapshotUnavailable(f"archive redirect from {current} had no location")
        nxt = urljoin(current, location)
        assert_archive_url(nxt)
        stamp = _timestamp_in_url(nxt)
        captured = parse_wayback_timestamp(stamp) if stamp else None
        if captured is None or captured > as_of:
            raise SnapshotUnavailable(
                f"archive redirect moved past as_of: {stamp or nxt} > {as_of.isoformat()}"
            )
        current = nxt
    raise SnapshotUnavailable(f"too many archive redirects for {archive_url}")


def fetch_markdown_at(
    url: str,
    as_of: datetime,
    *,
    client: ArchiveClient | None = None,
    timeout: float = 15.0,
) -> SnapshotPage:
    """Markdown of the capture at or before ``as_of``.

    Raises :class:`SnapshotUnavailable` when the archive has no such capture.
    The original URL is not fetched.
    """
    as_of_utc = require_aware(as_of)
    _require_public_http_url(url)
    owned: HttpxArchiveClient | None = None
    active: ArchiveClient
    if client is None:
        owned = _default_client(timeout)
        active = owned
    else:
        active = client
    try:
        ref = resolve(url, as_of_utc, client=active)
        if ref is None:
            raise SnapshotUnavailable(
                f"no archive capture of {url} at or before {as_of_utc.isoformat()}"
            )
        downloaded = _download_capture(active, ref.archive_url, as_of_utc)
        if downloaded.status_code != 200:
            raise SnapshotUnavailable(
                f"archive capture {ref.archive_url} returned HTTP {downloaded.status_code}"
            )
        html = strip_wayback_toolbar(
            _decode(downloaded.content, _header(downloaded.headers, "content-type"))
        )
        return SnapshotPage(markdown=extract_markdown(html, url=ref.original_url), ref=ref)
    finally:
        if owned is not None:
            owned.close()
