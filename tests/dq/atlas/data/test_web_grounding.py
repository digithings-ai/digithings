from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

# web_grounding imports digigraph.llm, which requires `openai` (a digigraph dep absent
# in the digiquant-only CI job). Skip cleanly there; runs in atlas-graph-ci / locally.
pytest.importorskip("openai")

from digiquant.olympus.atlas.data import web_grounding  # noqa: E402


def _domains_for(monkeypatch_segment: str) -> list[str]:
    captured = {}

    def _ws(model, query, *, allowed_domains=None, max_results=8):
        captured["allowed_domains"] = allowed_domains
        return ("- x[[1]](u)", ["https://u"])

    with patch.object(web_grounding, "web_search", side_effect=_ws):
        web_grounding.fetch_web_grounding(
            model="openrouter/openrouter/auto",
            segment=monkeypatch_segment,
            run_date=date(2026, 6, 9),
        )
    return captured["allowed_domains"]


@pytest.mark.unit
def test_fetch_web_grounding_returns_summary_and_sources():
    with patch.object(
        web_grounding, "web_search", return_value=("- CPI rose 0.6%[[1]](u)", ["https://u"])
    ):
        out = web_grounding.fetch_web_grounding(
            model="openrouter/openrouter/auto", segment="macro", run_date=date(2026, 6, 9)
        )
    assert out is not None
    assert out["summary"].startswith("- CPI")
    assert out["sources"] == ["https://u"]
    assert out["as_of"] == "2026-06-09"


@pytest.mark.unit
def test_per_segment_domains_are_used_and_capped():
    # Each phase searches its own highest-signal sources, capped at the xAI 5-domain limit.
    politician = _domains_for("alt-politician-signals")
    assert "capitoltrades.com" in politician
    assert len(politician) <= 5

    macro = _domains_for("macro")
    assert "federalreserve.gov" in macro and "bls.gov" in macro
    assert len(macro) <= 5


@pytest.mark.unit
def test_unmapped_segment_falls_back_to_default_allowlist():
    domains = _domains_for("some-unmapped-segment")
    assert "reuters.com" in domains  # the default web_allowed_websites
    assert len(domains) <= 5


@pytest.mark.unit
def test_fetch_web_grounding_none_when_search_unavailable():
    with patch.object(web_grounding, "web_search", return_value=None):
        assert (
            web_grounding.fetch_web_grounding(
                model="ollama/local", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_web_grounding_none_on_empty_text():
    with patch.object(web_grounding, "web_search", return_value=("   ", [])):
        assert (
            web_grounding.fetch_web_grounding(
                model="openrouter/openrouter/auto", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )
