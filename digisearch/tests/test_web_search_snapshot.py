"""Point-in-time archive fetch: closest capture at or before as_of, never live HTML."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import pytest

from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.web_search.snapshot import (
    ArchiveResponse,
    Capture,
    HttpxArchiveClient,
    SnapshotError,
    SnapshotPage,
    SnapshotRef,
    SnapshotUnavailable,
    fetch_markdown_at,
    resolve,
    select_capture,
)

pytestmark = pytest.mark.unit

AS_OF = datetime(2020, 6, 1, tzinfo=timezone.utc)
PAGE = "https://news.example/a"
EARLIER = datetime(2019, 6, 1, tzinfo=timezone.utc)
CLOSEST = datetime(2020, 3, 1, tzinfo=timezone.utc)
FUTURE = datetime(2021, 6, 1, tzinfo=timezone.utc)

_TOOLBAR_HTML = """<!DOCTYPE html>
<html><head><title>Earnings</title></head><body>
<!-- BEGIN WAYBACK TOOLBAR INSERT -->
<div id="wm-ipp-base">Wayback toolbar</div>
<!-- END WAYBACK TOOLBAR INSERT -->
<article><h1>Earnings</h1><p>Revenue grew in the quarter.</p></article>
</body></html>
"""


def _capture(when: datetime, *, status: str = "200", url: str = PAGE) -> Capture:
    return Capture(
        timestamp=when.strftime("%Y%m%d%H%M%S"),
        captured_at=when,
        original_url=url,
        status=status,
    )


def _cdx(*rows: Capture) -> bytes:
    payload: list[list[str]] = [["timestamp", "original", "statuscode"]]
    payload.extend([row.timestamp, row.original_url, row.status] for row in rows)
    return json.dumps(payload).encode()


class _Routes:
    """Offline archive stand-in. Records every URL and never opens a socket."""

    def __init__(
        self,
        *,
        cdx: bytes = b"[]",
        availability: bytes = b"{}",
        memento: ArchiveResponse | None = None,
        replay: bytes = b"",
        replay_status: int = 200,
    ) -> None:
        self.urls: list[str] = []
        self.cdx = cdx
        self.availability = availability
        self.memento = memento or ArchiveResponse(status_code=404, url="", content=b"")
        self.replay = replay
        self.replay_status = replay_status

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> ArchiveResponse:
        self.urls.append(url)
        host = (urlsplit(url).hostname or "").lower()
        if host not in {"web.archive.org", "archive.org", "wayback.archive.org"}:
            raise AssertionError(f"non-archive host requested: {url}")
        if "cdx/search/cdx" in url:
            return ArchiveResponse(status_code=200, url=url, content=self.cdx)
        if "wayback/available" in url:
            return ArchiveResponse(status_code=200, url=url, content=self.availability)
        if "/web/" in url and "id_" not in url:
            return self.memento.model_copy(update={"url": url})
        return ArchiveResponse(
            status_code=self.replay_status, url=url, content=self.replay, headers={}
        )


def test_select_capture_picks_closest_at_or_before_as_of() -> None:
    exact = _capture(AS_OF)
    chosen = select_capture([_capture(EARLIER), _capture(CLOSEST), exact, _capture(FUTURE)], AS_OF)
    assert chosen == exact


def test_select_capture_rejects_future_and_non_200() -> None:
    assert select_capture([_capture(FUTURE)], AS_OF) is None
    assert select_capture([_capture(CLOSEST, status="404")], AS_OF) is None
    assert select_capture([], AS_OF) is None


def test_resolve_uses_latest_cdx_row_at_or_before_as_of() -> None:
    client = _Routes(cdx=_cdx(_capture(EARLIER), _capture(CLOSEST), _capture(FUTURE)))
    ref = resolve(PAGE, AS_OF, client=client)
    assert ref is not None
    assert ref.source == "wayback"
    assert ref.captured_at == CLOSEST
    assert ref.original_url == PAGE
    assert (
        ref.archive_url
        == f"https://web.archive.org/web/{CLOSEST.strftime('%Y%m%d%H%M%S')}id_/{PAGE}"
    )
    assert "to=20200601000000" in client.urls[0]
    assert all((urlsplit(url).hostname or "") != "news.example" for url in client.urls)


def test_resolve_rejects_availability_snapshot_after_as_of() -> None:
    future = {
        "archived_snapshots": {
            "closest": {
                "available": True,
                "timestamp": FUTURE.strftime("%Y%m%d%H%M%S"),
                "status": "200",
            }
        }
    }
    client = _Routes(cdx=b"[]", availability=json.dumps(future).encode())
    assert resolve(PAGE, AS_OF, client=client) is None


def test_resolve_memento_when_cdx_and_availability_miss() -> None:
    past_stamp = CLOSEST.strftime("%Y%m%d%H%M%S")
    client = _Routes(
        cdx=b"[]",
        availability=json.dumps({"archived_snapshots": {}}).encode(),
        memento=ArchiveResponse(
            status_code=302,
            url="",
            content=b"",
            headers={
                "Memento-Datetime": "Sun, 01 Mar 2020 00:00:00 GMT",
                "Location": f"https://web.archive.org/web/{past_stamp}/{PAGE}",
            },
        ),
    )
    ref = resolve(PAGE, AS_OF, client=client)
    assert ref is not None
    assert ref.source == "memento"
    assert ref.captured_at == CLOSEST
    assert ref.archive_url.endswith(f"id_/{PAGE}")


def test_fetch_markdown_at_missing_archive_is_loud() -> None:
    client = _Routes()
    with pytest.raises(SnapshotUnavailable, match="no archive capture"):
        fetch_markdown_at(PAGE, AS_OF, client=client)
    assert client.urls
    assert all("id_" not in url for url in client.urls)


def test_fetch_markdown_at_strips_toolbar_before_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def _extract(html: str, url: str = "") -> str:
        seen["html"] = html
        seen["url"] = url
        return "Revenue grew in the quarter."

    monkeypatch.setattr("digisearch.web_search.snapshot.extract_markdown", _extract)
    client = _Routes(cdx=_cdx(_capture(CLOSEST)), replay=_TOOLBAR_HTML.encode())
    page = fetch_markdown_at(PAGE, AS_OF, client=client)
    assert isinstance(page, SnapshotPage)
    assert page.markdown == "Revenue grew in the quarter."
    assert page.ref.captured_at == CLOSEST
    assert "WAYBACK TOOLBAR" not in seen["html"]
    assert "wm-ipp-base" not in seen["html"]
    assert "Revenue grew" in seen["html"]
    assert seen["url"] == PAGE
    assert all((urlsplit(url).hostname or "") != "news.example" for url in client.urls)


def test_fetch_markdown_at_extracts_wayback_html_without_toolbar() -> None:
    client = _Routes(cdx=_cdx(_capture(CLOSEST)), replay=_TOOLBAR_HTML.encode())
    page = fetch_markdown_at(PAGE, AS_OF, client=client)
    assert "Revenue grew" in page.markdown
    assert "toolbar" not in page.markdown.lower()
    assert "wayback" not in page.markdown.lower()


def test_fetch_markdown_at_refuses_redirect_past_as_of() -> None:
    future = FUTURE.strftime("%Y%m%d%H%M%S")

    class _Redirect(_Routes):
        def get(self, url: str, *, headers: dict[str, str] | None = None) -> ArchiveResponse:
            self.urls.append(url)
            if "id_" in url:
                return ArchiveResponse(
                    status_code=302,
                    url=url,
                    content=b"<p>future page</p>",
                    headers={"Location": f"https://web.archive.org/web/{future}id_/{PAGE}"},
                )
            return super().get(url, headers=headers)

    with pytest.raises(SnapshotUnavailable, match="past as_of"):
        fetch_markdown_at(PAGE, AS_OF, client=_Redirect(cdx=_cdx(_capture(CLOSEST))))


def test_naive_as_of_and_internal_url_never_hit_the_client() -> None:
    client = _Routes()
    with pytest.raises(SnapshotError):
        fetch_markdown_at(PAGE, datetime(2020, 6, 1), client=client)  # noqa: DTZ001
    with pytest.raises(SnapshotError):
        resolve("http://169.254.169.254/latest", AS_OF, client=client)
    with pytest.raises(SnapshotError):
        resolve("file:///etc/passwd", AS_OF, client=client)
    assert client.urls == []


def test_http_client_refuses_non_archive_before_transport() -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"transport called for {request.url}")

    client = HttpxArchiveClient(
        http=httpx.Client(transport=httpx.MockTransport(_boom)),
        min_interval_s=0,
    )
    with pytest.raises(SnapshotError, match="non-archive"):
        client.get("https://news.example/a")
    client.close()


def test_run_web_search_as_of_refuses_live_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.web_search import service as svc

    class _LiveFetcher:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("live fetch")

    monkeypatch.setattr(svc, "HttpFetcher", _LiveFetcher)
    monkeypatch.setattr(
        svc,
        "_search_only",
        lambda req, config: WebSearchResponse(
            query=req.query,
            results=[
                WebSearchResult(url=PAGE, title="A", snippet="live serp blurb"),
                WebSearchResult(url="https://news.example/b", title="B", snippet="second live"),
            ],
            provider="searxng",
        ),
    )
    seen: list[str] = []

    def _fake_fetch(url: str, as_of: datetime, **kwargs: object) -> SnapshotPage:
        seen.append(url)
        assert as_of == AS_OF
        return SnapshotPage(
            markdown="# historical body " + url,
            ref=SnapshotRef(
                original_url=url,
                archive_url=f"https://web.archive.org/web/20200301000000id_/{url}",
                captured_at=CLOSEST,
                source="wayback",
                timestamp="20200301000000",
            ),
        )

    monkeypatch.setattr(svc, "fetch_markdown_at", _fake_fetch)
    resp = svc.run_web_search(
        WebSearchRequest(query="acme earnings"),
        svc.WebSearchConfig(fetch_max_pages=1),
        as_of=AS_OF,
    )
    assert seen == [PAGE]
    assert resp.results[0].snippet.startswith("# historical body")
    assert "live serp" not in resp.results[0].snippet
    assert resp.results[1].snippet == "second live"
    assert resp.output is not None
    assert resp.output["ranking"] == "live_serp_not_historical"
    assert resp.output["captures"][0]["source"] == "wayback"
    assert resp.output["captures"][0]["captured_at"] == CLOSEST.isoformat()
    assert resp.output["captures"][1]["fetched"] is False


def test_run_web_search_as_of_does_not_snapshot_outside_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digisearch.web_search import service as svc

    monkeypatch.setattr(
        svc,
        "_search_only",
        lambda req, config: WebSearchResponse(
            query=req.query,
            results=[WebSearchResult(url=PAGE, title="A", snippet="live serp blurb")],
            provider="searxng",
        ),
    )

    def _unexpected(url: str, as_of: datetime, **kwargs: object) -> SnapshotPage:
        raise AssertionError(f"snapshot fetch of fenced-out {url}")

    monkeypatch.setattr(svc, "fetch_markdown_at", _unexpected)
    resp = svc.run_web_search(
        WebSearchRequest(query="acme", fence=["other.example"]),
        as_of=AS_OF,
    )
    assert resp.results[0].snippet.startswith("[snapshot unavailable:")
    assert "live serp" not in resp.results[0].snippet


def test_run_web_search_snapshot_miss_does_not_keep_live_snippet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digisearch.web_search import service as svc

    class _LiveFetcher:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("live fetch")

    monkeypatch.setattr(svc, "HttpFetcher", _LiveFetcher)
    monkeypatch.setattr(
        svc,
        "_search_only",
        lambda req, config: WebSearchResponse(
            query=req.query,
            results=[WebSearchResult(url=PAGE, title="A", snippet="live serp blurb")],
            provider="ddgs",
        ),
    )

    def _miss(url: str, as_of: datetime, **kwargs: object) -> SnapshotPage:
        raise SnapshotUnavailable(f"no archive capture of {url} at or before {as_of.isoformat()}")

    monkeypatch.setattr(svc, "fetch_markdown_at", _miss)
    resp = svc.run_web_search(WebSearchRequest(query="acme"), as_of=AS_OF)
    assert resp.results[0].snippet.startswith("[snapshot unavailable:")
    assert "live serp" not in resp.results[0].snippet
    assert resp.output is not None
    assert resp.output["captures"][0]["error"]
