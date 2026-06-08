from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.data.live_search import build_search_parameters


@pytest.mark.unit
def test_build_search_parameters_shape():
    sp = build_search_parameters(run_date=date(2026, 6, 8))
    assert sp["mode"] == "on"
    assert sp["return_citations"] is True
    assert sp["from_date"] == "2026-06-01"  # run_date - recency_days
    types = {s["type"] for s in sp["sources"]}
    assert {"web", "news", "x"} <= types
    web = next(s for s in sp["sources"] if s["type"] == "web")
    assert "reuters.com" in web["allowed_websites"]
    # xAI caps allowed_websites at 5 per source.
    assert len(web["allowed_websites"]) == 5
    assert sp["max_search_results"] == 8
