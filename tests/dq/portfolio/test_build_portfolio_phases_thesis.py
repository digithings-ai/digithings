"""Smoke tests for thesis-first portfolio graph wiring (PR 4a–4c / #930)."""

from __future__ import annotations

import pytest
from digiquant.portfolio.graph import build_portfolio_graph, build_portfolio_phases_thesis
from digiquant.research.state import PhasePortfolioState, ResearchState


@pytest.mark.unit
class TestBuildPortfolioPhasesThesis:
    def test_phases_include_thesis_through_h9(self) -> None:
        phases = build_portfolio_phases_thesis(watchlist=["SPY", "QQQ"], held={"SPY"})
        names = [p.name for p in phases]
        assert "portfolio_thesis" in names
        assert "portfolio_market" in names
        assert "portfolio_vehicle_map" in names
        assert "portfolio_screener" in names
        assert "portfolio_analyst" in names
        assert "portfolio_deliberation" in names
        assert "portfolio_direction" in names
        assert "portfolio_sizing_risk_sizing" in names
        assert "portfolio_commit" in names
        assert not any(n.startswith("phase7c") for n in names)
        assert not any(n.startswith("phase7cd") for n in names)
        assert not any(n.startswith("phase7d") for n in names)
        assert not any(n.startswith("phase9") for n in names)

    def test_direction_precedes_h8(self) -> None:
        phases = build_portfolio_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        direction_idx = names.index("portfolio_direction")
        sizing_idx = names.index("portfolio_sizing_risk_sizing")
        assert direction_idx < sizing_idx

    def test_sizing_precedes_h9(self) -> None:
        phases = build_portfolio_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        sizing_idx = names.index("portfolio_sizing_risk_sizing")
        commit_idx = names.index("portfolio_commit")
        assert sizing_idx < commit_idx

    def test_screener_precedes_h5(self) -> None:
        phases = build_portfolio_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        screener_idx = names.index("portfolio_screener")
        analyst_idx = names.index("portfolio_analyst")
        assert screener_idx < analyst_idx

    def test_build_portfolio_graph_compiles_thesis_path(self) -> None:
        graph = build_portfolio_graph(watchlist=["AAPL", "MSFT"], held={"AAPL"})
        assert graph is not None

    def test_held_survives_analyst_fan_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "3")
        watchlist = ["AAA", "BBB", "SPY", "CCC", "IJR", "XLP"]
        held = {"SPY", "IJR", "XLP"}
        phases = build_portfolio_phases_thesis(watchlist=watchlist, held=held)
        all_nodes = {n.name for p in phases for n in p.nodes}
        assert "portfolio/asset-analyst-worker" in all_nodes
        assert "portfolio/deliberation-worker" in all_nodes

    def test_runtime_analyst_covers_thesis_mapped_off_watchlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        from digigraph.graph.pipeline_builder import build_pipeline
        from digiquant.portfolio.phases.analyst import build_analyst_from_state
        from digiquant.portfolio.phases.screener import (
            build_screener,
        )
        from digiquant.research.state import ResearchConfigBundle

        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "2")
        state = ResearchState(
            run_type="delta",
            run_date=__import__("datetime").date(2026, 6, 20),
            config=ResearchConfigBundle(watchlist=["SPY"]),
        )
        state.phase_portfolio = PhasePortfolioState(
            thesis_vehicle_map={
                "body": {"mappings": [{"thesis_id": "geo-gold", "candidate_tickers": ["GLD"]}]}
            },
        )
        compiled = build_pipeline(
            ResearchState,
            [build_screener(), build_analyst_from_state()],
        )

        def fake_analyst(**kwargs: object) -> tuple:
            from digiquant.portfolio.models.analyst import AnalystPayload

            ticker = kwargs.get("ticker", "GLD")
            payload = AnalystPayload(
                ticker=str(ticker),
                stance="buy",
                conviction_score=3,
                thesis="gold hedge",
                risks="usd strength",
                sources=[],
            )
            return payload, {}, [], None

        with patch(
            "digiquant.portfolio.phases.analyst.run_asset_analyst_llm",
            side_effect=fake_analyst,
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result)
        assert "GLD" in final.phase_portfolio.asset_analysts
