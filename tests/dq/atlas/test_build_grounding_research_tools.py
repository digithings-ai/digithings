"""build_grounding wiring for RESEARCH_TOOLS (Olympus #930)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.research_retrieval import RESEARCH_TOOLS


@pytest.mark.unit
def test_build_grounding_includes_research_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", lambda: object())

    tools, execute_tool, _grounding = _node_factory.build_grounding(
        use_data_tools=False,
        live_search=False,
        run_date=date(2026, 6, 20),
        use_research_tools=True,
        research_phase="h1_thesis",
    )
    assert tools is not None
    names = {t["function"]["name"] for t in tools}
    research_names = {t["function"]["name"] for t in RESEARCH_TOOLS}
    assert research_names.issubset(names)
    assert execute_tool is not None


@pytest.mark.unit
def test_build_grounding_h5_blinds_portfolio_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", lambda: object())

    tools, _execute, _ = _node_factory.build_grounding(
        use_data_tools=False,
        live_search=False,
        run_date=date(2026, 6, 20),
        use_research_tools=True,
        research_phase="h5_analyst",
    )
    assert tools is not None
    names = {t["function"]["name"] for t in tools}
    assert "query_research" in names
    assert "fetch_prior_document" in names
    assert "query_portfolio" not in names
