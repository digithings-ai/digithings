"""Grounding models + landed web_search adaptation seam (#4064 Phase B)."""

from __future__ import annotations

import pytest
from digisearch.web.grounding_models import (
    EFFORT_PRESETS,
    EffortMode,
    FieldGrounding,
    GroundingCitation,
    StructuredSynthesis,
    WebResearchConfig,
)


@pytest.mark.unit
def test_effort_presets_order():
    fast: WebResearchConfig = EFFORT_PRESETS[EffortMode.FAST]
    thorough: WebResearchConfig = EFFORT_PRESETS[EffortMode.THOROUGH]
    assert fast.live_top_n <= thorough.live_top_n
    assert fast.fetch_top_n <= thorough.fetch_top_n
    assert fast.cited_top_n <= thorough.cited_top_n


@pytest.mark.unit
def test_field_grounding_requires_citation():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FieldGrounding(field="rounds[0].company", citations=[])


@pytest.mark.unit
def test_grounding_citation_is_landed_atom():
    from digisearch.web_search.citation import Citation

    assert GroundingCitation is Citation  # re-export, never a fork


@pytest.mark.unit
def test_structured_synthesis_exa_shape():
    s = StructuredSynthesis(
        content={"rounds": [{"company": "Wafer"}]},
        text="Three recent Series A rounds.",
        grounding=[
            {
                "field": "rounds[0].company",
                "citations": [{"url": "https://a.com/1", "title": "A"}],
                "confidence": "high",
            }
        ],
    )
    assert s.grounding[0].citations[0].url == "https://a.com/1"


@pytest.mark.unit
def test_retrieve_seam_maps_landed_rows(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult

    fake = WebSearchResponse(
        query="q",
        provider="searxng",
        results=[
            WebSearchResult(
                url="https://a.com/1", title="A", snippet="s", score=0.9, engine="searxng"
            )
        ],
    )
    monkeypatch.setattr(ret, "_live", lambda q, top_n: fake)
    hits = ret.live_search("q", top_n=4)
    assert hits[0].url == "https://a.com/1"
    assert hits[0].snippet == "s"  # landed rows carry snippet, never highlights


@pytest.mark.unit
def test_fetch_seam_returns_fetched_pages(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search.models import WebSearchResult

    page = ret.FetchedPage(url="https://a.com/1", title="A", markdown="# body")
    monkeypatch.setattr(ret, "_fetch", lambda hits, top_n: [page])
    hits = [WebSearchResult(url="https://a.com/1", title="A", snippet="s")]
    assert ret.fetch_pages(hits, top_n=4)[0].markdown == "# body"


@pytest.mark.unit
def test_retrieve_module_never_indexes():
    import inspect

    from digisearch.web import retrieve as ret

    assert "ingest_url" not in inspect.getsource(ret)  # it indexes (R3)


@pytest.mark.unit
def test_fetch_seam_tolerates_partial_failure(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search import fetch as fetch_mod
    from digisearch.web_search.models import WebSearchResult

    def fake_fetch_markdown(url: str) -> str:
        if url.endswith("/bad"):
            raise RuntimeError("boom")
        return "# good"

    monkeypatch.setattr(fetch_mod, "fetch_markdown", fake_fetch_markdown)
    hits = [
        WebSearchResult(url="https://a.com/bad", title="Bad", snippet="s"),
        WebSearchResult(url="https://a.com/good", title="Good", snippet="s"),
    ]
    pages = ret.fetch_pages(hits, top_n=4)
    assert [p.url for p in pages] == ["https://a.com/good"]
    assert pages[0].markdown == "# good"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["raise", "empty"])
def test_fetch_seam_raises_when_no_pages_survive(monkeypatch, mode):
    from digisearch.web import retrieve as ret
    from digisearch.web_search import fetch as fetch_mod
    from digisearch.web_search.models import WebSearchResult

    def fake_fetch_markdown(url: str) -> str:
        if mode == "raise":
            raise RuntimeError("boom")
        return ""

    monkeypatch.setattr(fetch_mod, "fetch_markdown", fake_fetch_markdown)
    hits = [
        WebSearchResult(url="https://a.com/1", title="A", snippet="s"),
        WebSearchResult(url="https://a.com/2", title="B", snippet="s"),
    ]
    with pytest.raises(ret.WebResearchError) as excinfo:
        ret.fetch_pages(hits, top_n=4)
    if mode == "raise":
        assert isinstance(excinfo.value.__cause__, RuntimeError)


@pytest.mark.unit
def test_live_clamps_top_n_to_landed_search_cap(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search import service as service_mod
    from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

    seen: list[WebSearchRequest] = []

    def fake_search_web(req: WebSearchRequest, config=None) -> WebSearchResponse:
        seen.append(req)
        return WebSearchResponse(query=req.query, provider="fake")

    monkeypatch.setattr(service_mod, "search_web", fake_search_web)
    ret._live("q", 20)
    ret._live("q", 4)
    assert seen[0].max_results <= 10
    assert seen[1].max_results == 4
