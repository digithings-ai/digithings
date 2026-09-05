"""Unit tests for digiquant product compile + prompt walk inventory (#3415/#3424)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.dashboard.prompt_walk_inventory import prompt_walk_inventory
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest


@pytest.mark.unit
def test_compile_research_portfolio_dry_run() -> None:
    # digiquant-only CI omits digigraph/openai; research-graph lane covers compile.
    pytest.importorskip("openai")
    from digiquant.portfolio.product_compile import compile_research_portfolio, idempotency_key_for

    result = compile_research_portfolio(
        run_date=date(2026, 9, 3),
        watchlist=("AAPL",),
    )
    assert result.dry_run is True
    assert {g.name: g.compiled for g in result.graphs} == {
        "research": True,
        "portfolio": True,
    }
    assert result.idempotency_key == idempotency_key_for(
        graph_name="research-portfolio-chain",
        run_date=date(2026, 9, 3),
    )


@pytest.mark.unit
def test_idempotency_key_for_is_stable() -> None:
    from digiquant.portfolio.product_compile import idempotency_key_for

    assert idempotency_key_for(
        graph_name="research-portfolio-chain",
        run_date=date(2026, 9, 3),
    ) == "research-portfolio-chain:2026-09-03:daily:none"


@pytest.mark.unit
def test_orchestrator_manifest_includes_compile_tool() -> None:
    names = {
        t["function"]["name"]
        for t in build_orchestrator_tool_manifest()
        if isinstance(t, dict) and isinstance(t.get("function"), dict)
    }
    assert "digiquant_compile_research_portfolio" in names


@pytest.mark.unit
def test_prompt_walk_inventory_covers_h6_and_h7() -> None:
    inv = prompt_walk_inventory()
    by_id = {n.node_id: n for n in inv.nodes}
    assert by_id["portfolio/h6-deliberation"].structured_output == "prose_preferred"
    assert by_id["portfolio/h7-pm-direction"].structured_output == "keep"
    assert inv.issue == "3424"
