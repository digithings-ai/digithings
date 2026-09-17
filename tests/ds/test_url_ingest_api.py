"""Service surface tests for POST /ingest/url + ingest-url CLI (#4055). Offline only."""

from __future__ import annotations

import digisearch.pipeline.url_ingest as url_ingest_mod
import httpx
import pytest
from digisearch.cli import app as cli_app
from digisearch.pipeline.ingest import IngestError
from digisearch.search._stub import get_stub_index
from digisearch.server import app
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from digifetch import HttpFetcher
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

_PUBLIC = "93.184.216.34"

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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=_HTML.encode("utf-8"), headers={"content-type": "text/html"})


def _mock_default_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ingest_url's owned fetcher through an offline MockTransport."""

    def _fake_default_fetcher(allowed: tuple[str, ...]) -> HttpFetcher:
        return HttpFetcher(transport=httpx.MockTransport(_ok_handler))

    monkeypatch.setattr(url_ingest_mod, "_default_fetcher", _fake_default_fetcher)


def test_ingest_url_route_ok(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _mock_default_fetcher(monkeypatch)
    resp = client.post("/ingest/url", json={"source_url": f"https://{_PUBLIC}/article"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["doc_id"]
    assert body["chunks_created"] >= 1
    assert body["index_name"] == "default"
    assert body["source_url"] == f"https://{_PUBLIC}/article"


def test_ingest_url_route_ssrf_blocked(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    calls: list[str] = []

    def _recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"secret")

    def _fake_default_fetcher(allowed: tuple[str, ...]) -> HttpFetcher:
        return HttpFetcher(transport=httpx.MockTransport(_recording_handler))

    monkeypatch.setattr(url_ingest_mod, "_default_fetcher", _fake_default_fetcher)
    resp = client.post(
        "/ingest/url", json={"source_url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400, resp.text
    assert calls == []


def test_ingest_url_route_empty_url(client: TestClient) -> None:
    resp = client.post("/ingest/url", json={"source_url": ""})
    assert resp.status_code in (400, 422), resp.text
    assert resp.status_code != 500


def test_ingest_url_route_ingest_error_maps_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    _mock_default_fetcher(monkeypatch)

    def _raise(*args: object, **kwargs: object) -> None:
        raise IngestError("index write failed", code="ingest_failed", http_status=503)

    monkeypatch.setattr(url_ingest_mod, "ingest_source", _raise)
    resp = client.post("/ingest/url", json={"source_url": f"https://{_PUBLIC}/article"})
    assert resp.status_code == 503, resp.text


def test_ingest_url_route_missing_extra_maps_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    def _raise(allowed: tuple[str, ...]) -> None:
        raise ImportError("No module named 'digifetch'")

    monkeypatch.setattr(url_ingest_mod, "_default_fetcher", _raise)
    resp = client.post("/ingest/url", json={"source_url": f"https://{_PUBLIC}/article"})
    assert resp.status_code == 503, resp.text
    assert "digisearch[web-search]" in resp.json()["error"]["message"]


def test_ingest_url_route_malformed_port(client: TestClient) -> None:
    resp = client.post("/ingest/url", json={"source_url": f"http://{_PUBLIC}:99999999/"})
    assert resp.status_code == 400, resp.text


def test_ingest_url_cli_ssrf_exits_nonzero() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["ingest-url", "http://169.254.169.254/latest/meta-data/"])
    assert result.exit_code == 1, result.output


def test_ingest_url_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_default_fetcher(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_app, ["ingest-url", f"https://{_PUBLIC}/article", "--index", "url-cli-ok"]
    )
    assert result.exit_code == 0, result.output
    assert "chunks" in result.output
