from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

# web_grounding imports digigraph.llm, which requires `openai` (a digigraph dep absent
# in the digiquant-only CI job). Skip cleanly there; runs in atlas-graph-ci / locally.
pytest.importorskip("openai")

from digiquant.olympus.atlas.data import web_grounding  # noqa: E402


@pytest.mark.unit
def test_fetch_web_grounding_returns_summary_and_sources():
    with patch.object(
        web_grounding, "web_search", return_value=("- CPI rose 0.6%[[1]](u)", ["https://u"])
    ) as ws:
        out = web_grounding.fetch_web_grounding(
            model="xai/grok-4.3", segment="alt-options-derivatives", run_date=date(2026, 6, 9)
        )
    assert out is not None
    assert out["summary"].startswith("- CPI")
    assert out["sources"] == ["https://u"]
    assert out["as_of"] == "2026-06-09"
    # allowlist forwarded from search_domains.yaml, capped at the xAI 5-domain limit
    kwargs = ws.call_args[1]
    assert "reuters.com" in kwargs["allowed_domains"]
    assert len(kwargs["allowed_domains"]) <= 5


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
                model="xai/grok-4.3", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )
