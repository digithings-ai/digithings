"""20-query web-search eval harness (#3853, task 9).

offline-first: search providers and the digifetch fetcher are mocked at the
``digisearch.web_search.service`` seam, so the full search -> fetch -> enrich
path runs with no network and no searxng sidecar. enrichment itself runs the
real ``digisearch.web_search.extractor.extract_markdown`` (trafilatura primary,
readability fallback), so table/list assertions exercise production code.
live sampling is opt-in behind ``DIGISEARCH_WEB_SEARCH_LIVE=1``.
"""

import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from web_search_eval_cases import CASES, fixture_html

_ROOT = Path(__file__).resolve().parents[2]
for _name in ("digifetch", "digibase", "digillm", "digisearch"):
    _src = _ROOT / _name / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

LIVE = os.environ.get("DIGISEARCH_WEB_SEARCH_LIVE") == "1"


def test_eval_harness_runs_offline():
    assert len(CASES) >= 20


def _keywords_by_query() -> dict[str, list[str]]:
    return {str(c["query"]): [str(w) for w in c["must_contain"]] for c in CASES}


class _OfflineWorld:
    """Shared state linking the fake provider to the fake fetcher."""

    def __init__(self) -> None:
        self.keywords_by_query = _keywords_by_query()
        self.last_query = ""


class _FakeSearchProvider:
    """Canned hits; records the query so the fake fetcher can echo it."""

    def __init__(self, world: _OfflineWorld, tag: str) -> None:
        self._world = world
        self._tag = tag

    def search(self, req):  # query-typed at runtime; kept loose for the seam
        from digisearch.web_search.models import WebSearchResponse, WebSearchResult

        self._world.last_query = req.query
        return WebSearchResponse(
            query=req.query,
            provider=self._tag,
            results=[
                WebSearchResult(
                    url=f"https://example.com/{self._tag}/{i}",
                    title=f"{req.query} — source {i}",
                    snippet=f"{req.query} snippet {i}",
                    engine=self._tag,
                )
                for i in (1, 2)
            ],
        )


class _FakeFetcher:
    """digifetch stand-in serving per-query fixture article html."""

    def __init__(self, world: _OfflineWorld) -> None:
        self._world = world

    def fetch(self, url: str):
        query = self._world.last_query or "markets"
        keywords = self._world.keywords_by_query.get(query, [])
        return SimpleNamespace(text=fixture_html(query, keywords))


class _NoWaitLimiter:
    def acquire(self) -> None:
        return None


def _patch_offline(monkeypatch, world: _OfflineWorld, *, searxng_down: bool = False) -> None:
    """Mock providers + fetcher only; the real extractor stays on the seam."""
    from digisearch.web_search import service as svc

    if searxng_down:

        def _boom(req):
            raise RuntimeError("searxng down")

        monkeypatch.setattr(
            svc,
            "SearXNGWebSearchProvider",
            lambda **k: type("S", (), {"search": staticmethod(_boom)})(),
        )
    else:
        monkeypatch.setattr(
            svc, "SearXNGWebSearchProvider", lambda **k: _FakeSearchProvider(world, "searxng")
        )
    monkeypatch.setattr(
        svc, "DdgsWebSearchProvider", lambda *a, **k: _FakeSearchProvider(world, "ddgs")
    )
    monkeypatch.setattr(svc, "HttpFetcher", lambda *a, **k: _FakeFetcher(world))
    monkeypatch.setattr(svc, "_limiter", _NoWaitLimiter())


def test_offline_enriched_markdown_quality(monkeypatch):
    # real-extractor leg: trafilatura is an optional extra, so skip (never
    # fail) when it is absent — same importorskip pattern as the single-case
    # test below. providers + fetcher stay mocked, so this is fully offline.
    trafilatura = pytest.importorskip("trafilatura", reason="needs [web-search] extra")
    assert trafilatura is not None
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchRequest

    world = _OfflineWorld()
    _patch_offline(monkeypatch, world)
    latencies: list[float] = []
    for case in CASES:
        query = str(case["query"])
        must = [str(w).lower() for w in case["must_contain"]]
        started = time.perf_counter()
        resp = svc.run_web_search(
            WebSearchRequest(query=query),
            config=svc.WebSearchConfig(backend="auto", fetch_max_pages=2),
        )
        latencies.append(time.perf_counter() - started)
        assert resp.results, f"no results for {query!r}"
        for hit in resp.results:
            assert hit.url.startswith("http"), f"non-url hit for {query!r}"
        enriched = " ".join(h.snippet for h in resp.results).lower()
        for word in must:
            assert word in enriched, f"{word!r} missing for {query!r}"
        tables_lists = " ".join(h.snippet for h in resp.results)
        assert "|" in tables_lists, f"table markdown lost for {query!r}"
        assert "- " in tables_lists, f"list markdown lost for {query!r}"
    assert statistics.median(latencies) < 5.0


def test_offline_ddgs_backend_and_failover(monkeypatch):
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchRequest

    world = _OfflineWorld()
    _patch_offline(monkeypatch, world)
    resp = svc.run_web_search(
        WebSearchRequest(query="bitcoin etf daily flows record"),
        config=svc.WebSearchConfig(backend="ddgs", fetch_max_pages=1),
    )
    assert resp.provider == "ddgs"
    assert resp.results and resp.results[0].url.startswith("http")

    _patch_offline(monkeypatch, world, searxng_down=True)
    resp = svc.run_web_search(
        WebSearchRequest(query="federal reserve rate decision dot plot"),
        config=svc.WebSearchConfig(backend="auto", fetch_max_pages=1),
    )
    assert resp.provider == "ddgs"
    assert resp.results


def test_offline_empty_results_fail_closed(monkeypatch):
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

    class _Empty:
        def search(self, req):
            return WebSearchResponse(query=req.query, provider="searxng", results=[])

    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: _Empty())
    resp = svc.run_web_search(
        WebSearchRequest(query="asml euv bookings lithography demand"),
        config=svc.WebSearchConfig(backend="searxng", fetch_max_pages=1),
    )
    assert resp.results == []


def test_real_extractor_preserves_tables_and_lists():
    trafilatura = pytest.importorskip("trafilatura")
    assert trafilatura is not None
    from digisearch.web_search.extractor import extract_markdown

    md = extract_markdown(
        fixture_html("bank of japan rate hike yen intervention", ["japan", "yen"]),
        url="https://example.com/1",
    )
    lowered = md.lower()
    assert "japan" in lowered and "yen" in lowered
    assert "|" in md
    assert "- " in md


def _live_sample() -> list[dict]:
    seen: set[str] = set()
    sample: list[dict] = []
    for case in CASES:
        category = str(case["category"])
        if category not in seen:
            seen.add(category)
            sample.append(case)
    return sample


@pytest.mark.skipif(not LIVE, reason="live sampling needs DIGISEARCH_WEB_SEARCH_LIVE=1")
def test_live_sampled_latency_and_quality():
    from digisearch.web_search import service as svc
    from digisearch.web_search.models import WebSearchRequest

    assert len(_live_sample()) >= 4
    latencies: list[float] = []
    for case in _live_sample():
        query = str(case["query"])
        started = time.perf_counter()
        resp = svc.run_web_search(
            WebSearchRequest(query=query), config=svc.WebSearchConfig.from_env()
        )
        latencies.append(time.perf_counter() - started)
        assert resp.results, f"live search returned no results for {query!r}"
        assert any(h.url.startswith("http") for h in resp.results)
    assert statistics.median(latencies) < 5.0
