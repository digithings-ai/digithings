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
