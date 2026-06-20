"""Smoke tests for thesis-first Hermes graph wiring (PR 4a–4c / #930)."""

from __future__ import annotations

import pytest

from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.graph import build_hermes_graph, build_hermes_phases_thesis


@pytest.mark.unit
class TestBuildHermesPhasesThesis:
    def test_phases_include_h1_through_h9(self) -> None:
        phases = build_hermes_phases_thesis(watchlist=["SPY", "QQQ"], held={"SPY"})
        names = [p.name for p in phases]
        assert "hermes_h1_thesis_review" in names
        assert "hermes_h2_market_exploration" in names
        assert "hermes_h3_vehicle_map" in names
        assert "hermes_h4_opportunity_screener" in names
        assert "hermes_h5_asset_analyst" in names
        assert "hermes_h6_deliberation" in names
        assert "hermes_h7_pm_direction" in names
        assert "hermes_h8_risk_sizing" in names
        assert "hermes_h9_commit_run" in names
        assert not any(n.startswith("phase7c") for n in names)
        assert not any(n.startswith("phase7cd") for n in names)
        assert not any(n.startswith("phase7d") for n in names)
        assert not any(n.startswith("phase9") for n in names)

    def test_h7_precedes_h8(self) -> None:
        phases = build_hermes_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        h7_idx = names.index("hermes_h7_pm_direction")
        h8_idx = names.index("hermes_h8_risk_sizing")
        assert h7_idx < h8_idx

    def test_h8_precedes_h9(self) -> None:
        phases = build_hermes_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        h8_idx = names.index("hermes_h8_risk_sizing")
        h9_idx = names.index("hermes_h9_commit_run")
        assert h8_idx < h9_idx

    def test_h4_precedes_h5(self) -> None:
        phases = build_hermes_phases_thesis(watchlist=["SPY"], held=set())
        names = [p.name for p in phases]
        h4_idx = names.index("hermes_h4_opportunity_screener")
        h5_idx = names.index("hermes_h5_asset_analyst")
        assert h4_idx < h5_idx

    def test_build_hermes_graph_compiles_thesis_path(self) -> None:
        graph = build_hermes_graph(watchlist=["AAPL", "MSFT"], held={"AAPL"})
        assert graph is not None

    def test_held_survives_h5_fan_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        watchlist = ["AAA", "BBB", "SPY", "CCC", "IJR", "XLP"]
        held = {"SPY", "IJR", "XLP"}
        phases = build_hermes_phases_thesis(watchlist=watchlist, held=held)
        all_nodes = {n.name for p in phases for n in p.nodes}
        assert "hermes/portfolio/asset-analyst-runtime" in all_nodes
        assert "hermes/portfolio/deliberation-runtime" in all_nodes

    def test_runtime_h5_covers_thesis_mapped_off_watchlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        from digigraph.graph.pipeline_builder import build_pipeline

        from digiquant.olympus.atlas.state import AtlasConfigBundle, FocusRosterEntry
        from digiquant.olympus.hermes.phases.h4_opportunity_screener import (
            build_h4_opportunity_screener,
        )
        from digiquant.olympus.hermes.phases.h5_asset_analyst import build_h5_from_state

        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        state = AtlasResearchState(
            run_type="delta",
            run_date=__import__("datetime").date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["SPY"]),
        )
        state.phase_hermes = PhaseHermesState(
            thesis_vehicle_map={
                "body": {"mappings": [{"thesis_id": "geo-gold", "candidate_tickers": ["GLD"]}]}
            },
        )
        compiled = build_pipeline(
            AtlasResearchState,
            [build_h4_opportunity_screener(), build_h5_from_state()],
        )

        def fake_analyst(**kwargs: object) -> tuple:
            from digiquant.olympus.hermes.models.analyst import AnalystPayload

            ticker = kwargs.get("ticker", "GLD")
            payload = AnalystPayload(
                ticker=str(ticker),
                stance="buy",
                conviction_score=3,
                thesis="gold hedge",
                risks="usd strength",
                sources=[],
            )
            return payload, {}, []

        with patch(
            "digiquant.olympus.hermes.phases.h5_asset_analyst.run_asset_analyst_llm",
            side_effect=fake_analyst,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result)
        assert "GLD" in final.phase_hermes.asset_analysts
