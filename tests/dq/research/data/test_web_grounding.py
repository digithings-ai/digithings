from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

# web_grounding imports digigraph.llm, which requires `openai` (a digigraph dep absent
# in the digiquant-only CI job). Skip cleanly there; runs in atlas-graph-ci / locally.
pytest.importorskip("openai")

from digiquant.olympus.atlas.data import web_grounding


def _query_for(segment: str) -> str:
    captured: dict[str, str] = {}

    def _ws(model: str, query: str):
        captured["query"] = query
        return ("- x[[1]](u)", ["https://u"])

    with patch.object(web_grounding, "_openrouter_web_search", side_effect=_ws):
        web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar",
            segment=segment,
            run_date=date(2026, 6, 9),
        )
    return captured["query"]


@pytest.mark.unit
def test_fetch_web_grounding_returns_summary_and_sources():
    with patch.object(
        web_grounding,
        "_openrouter_web_search",
        return_value=("- CPI rose 0.6%[[1]](u)", ["https://u"]),
    ):
        out = web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar", segment="macro", run_date=date(2026, 6, 9)
        )
    assert out is not None
    assert out["summary"].startswith("- CPI")
    assert out["sources"] == ["https://u"]
    assert out["as_of"] == "2026-06-09"


@pytest.mark.unit
def test_per_segment_domains_folded_into_query_and_capped():
    # Native search has no Exa allowlist — domains are a soft preference in the query (#2567).
    politician = _query_for("alt-politician-signals")
    assert "capitoltrades.com" in politician

    macro = _query_for("macro")
    assert "federalreserve.gov" in macro and "bls.gov" in macro


@pytest.mark.unit
def test_unmapped_segment_falls_back_to_default_allowlist_in_query():
    query = _query_for("some-unmapped-segment")
    assert "reuters.com" in query  # the default web_allowed_websites


@pytest.mark.unit
def test_olympus_grounding_does_not_pass_exa_params():
    """Olympus must not assemble engine=/max_results= for the digillm Exa toolkit (#2567)."""
    captured: dict = {}

    def _or_ws(model, query, **kwargs):
        captured["kwargs"] = kwargs
        return ("- ok[[1]](https://u)", ["https://u"])

    with patch("digigraph.llm_client.openrouter_web_search", side_effect=_or_ws):
        web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar",
            segment="macro",
            run_date=date(2026, 6, 9),
        )
    assert captured["kwargs"] == {}


@pytest.mark.unit
def test_fetch_web_grounding_none_when_search_unavailable():
    with patch.object(web_grounding, "_openrouter_web_search", return_value=None):
        assert (
            web_grounding.fetch_web_grounding(
                model="ollama/local", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_web_grounding_none_on_empty_text():
    with patch.object(web_grounding, "_openrouter_web_search", return_value=("   ", [])):
        assert (
            web_grounding.fetch_web_grounding(
                model="openrouter/openrouter/auto", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_web_grounding_raises_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_WEB_SEARCH", "required")
    with patch.object(web_grounding, "_openrouter_web_search", return_value=None):
        with pytest.raises(web_grounding.OlympusWebSearchError):
            web_grounding.fetch_web_grounding(
                model="openrouter/perplexity/sonar", segment="macro", run_date=date(2026, 6, 9)
            )


@pytest.mark.unit
def test_build_grounding_live_search_without_data_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Web grounding must not be gated on ATLAS_DATA_TOOLS (#946)."""
    from digiquant.olympus.atlas.phases import _node_factory as nf

    monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")
    grounding = {"summary": "ok", "sources": [], "as_of": "2026-06-09"}
    with patch(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        return_value=grounding,
    ):
        tools, execute_tool, web_grounding = nf.build_grounding(
            use_data_tools=True,
            live_search=True,
            run_date=date(2026, 6, 9),
            segment="alt-sentiment-news",
        )
    assert tools is None
    assert execute_tool is None
    assert web_grounding == grounding
