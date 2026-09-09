"""Unit tests for digigraph product graphs (#3415)."""

from __future__ import annotations

from datetime import date
from typing import Any  # score:allow untyped any — fake digiquant invoker payloads

import pytest
from digigraph.graph.product_graphs import (
    ProductGraphRunRequest,
    ProductGraphRunState,
    build_research_portfolio_product_graph,
    list_product_graphs,
    run_product_graph,
)


@pytest.mark.unit
def test_list_product_graphs_includes_research_portfolio_chain() -> None:
    specs = list_product_graphs()
    names = {s.name for s in specs}
    assert "research-portfolio-chain" in names


@pytest.mark.unit
def test_product_graph_dry_run_invokes_digiquant_compile() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_invoker(
        base_url: str,
        tool: str,
        arguments: dict[str, Any],
        *,
        bearer_token: str | None,
        request_id: str | None,
    ) -> dict[str, Any]:
        calls.append((base_url, tool, arguments))
        return {
            "ok": True,
            "data": {
                "dry_run": True,
                "idempotency_key": "research-portfolio-chain:2026-09-03:daily:none",
                "graphs": [
                    {"name": "research", "compiled": True, "error": None},
                    {"name": "portfolio", "compiled": True, "error": None},
                ],
            },
        }

    result = run_product_graph(
        "research-portfolio-chain",
        ProductGraphRunRequest(run_date=date(2026, 9, 3), dry_run=True),
        digiquant_base_url="http://digiquant.test:8001",
        invoker=fake_invoker,
    )
    assert result.status == "ok"
    assert result.idempotency_key == "research-portfolio-chain:2026-09-03:daily:none"
    assert calls and calls[0][1] == "digiquant_compile_research_portfolio"


@pytest.mark.unit
def test_product_graph_refuses_full_apply() -> None:
    result = run_product_graph(
        "research-portfolio-chain",
        ProductGraphRunRequest(run_date=date(2026, 9, 3), dry_run=False),
        digiquant_base_url="http://digiquant.test:8001",
        invoker=lambda *a, **k: {"ok": True, "data": {}},
    )
    assert result.status == "error"
    assert result.error is not None
    assert "full apply" in result.error


@pytest.mark.unit
def test_build_research_portfolio_product_graph_compiles() -> None:
    g = build_research_portfolio_product_graph(
        invoker=lambda *a, **k: {
            "ok": True,
            "data": {"dry_run": True, "idempotency_key": "k", "graphs": []},
        }
    )
    out = g.invoke(
        ProductGraphRunState(
            run_date=date(2026, 9, 3),
            digiquant_base_url="http://x",
            dry_run=True,
        )
    )
    state = (
        out if isinstance(out, ProductGraphRunState) else ProductGraphRunState.model_validate(out)
    )
    assert state.status == "ok"
