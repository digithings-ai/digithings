"""End-to-end graph-compilation tests.

Verifies that ``build_atlas_graph`` returns a well-formed StateGraph for
each run_type and that the public contract (AtlasInput, initial_state)
behaves as advertised.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for fake-client shape

import pytest

from digiquant.olympus.atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    build_atlas_graph,
    initial_state,
)
from digiquant.olympus.atlas.phases.preflight import PreflightDeps
from digiquant.olympus.atlas.state import AtlasConfigBundle

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


def _deps(canned: dict[str, list[dict[str, Any]]] | None = None) -> AtlasGraphDeps:
    client = FakeSupabaseClient(
        canned_reads=canned
        or {
            "daily_snapshots": [],
            "documents": [],
            "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
            "macro_series_observations": [{"obs_date": "2026-04-25"}],
        }
    )
    return AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
        )
    )


@pytest.mark.unit
class TestAtlasInput:
    def test_defaults(self) -> None:
        inp = AtlasInput(run_date=date(2026, 4, 26))
        assert inp.cadence == "daily"
        assert inp.refresh_scope == "none"
        assert inp.baseline_date is None
        assert inp.watchlist == ()
        assert inp.digi_bearer is None

    def test_initial_state_round_trip(self) -> None:
        inp = AtlasInput(
            run_date=date(2026, 4, 27),
            refresh_scope="all",
            baseline_date=date(2026, 4, 26),
            watchlist=("AAPL", "MSFT"),
        )
        state = initial_state(inp)
        assert state.cadence == "daily"
        assert state.refresh_scope == "all"
        assert state.run_type == "baseline"
        assert state.baseline_date == date(2026, 4, 26)
        assert state.config.watchlist == ["AAPL", "MSFT"]


@pytest.mark.unit
class TestBuildGraph:
    def test_baseline_compiles(self) -> None:
        g = build_atlas_graph(deps=_deps(), watchlist=("AAPL",))
        names = set(g.get_graph().nodes.keys())
        # Atlas is research-only after #473 — H-phase nodes (analyst,
        # debate, PM, evolution) live in digiquant.olympus.hermes.graph and are
        # asserted by the chain test below.
        for expected in (
            "preflight",
            "alt-sentiment-news",
            "alt-cta-positioning",
            "inst-institutional-flows",
            "macro",
            "bonds",
            "crypto",
            "equity",
            "sector-technology",
            "sector-scorecard",
            "consolidate",
            "master-digest",
        ):
            assert expected in names, f"{expected!r} missing from compiled baseline graph"
        # Sanity: no analyst / PM / evolution nodes leaked into Atlas.
        for forbidden in (
            "technical-analyst-AAPL",
            "fundamental-analyst-AAPL",
            "pm-rebalance",
            "evolution",
        ):
            assert forbidden not in names, f"{forbidden!r} should be in Hermes, not Atlas"

    def test_delta_includes_triage_phase(self) -> None:
        g = build_atlas_graph(deps=_deps(), watchlist=())
        names = set(g.get_graph().nodes.keys())
        assert "triage" in names
        # H-phase noop nodes live in the Hermes graph now (#473).
        assert "specialist-noop" not in names

    def test_baseline_includes_triage_phase(self) -> None:
        g = build_atlas_graph(deps=_deps(), watchlist=())
        names = set(g.get_graph().nodes.keys())
        assert "triage" in names

    def test_hermes_graph_compiles(self) -> None:
        from digiquant.olympus.hermes.graph import build_hermes_graph

        g = build_hermes_graph(watchlist=["AAPL"])
        names = set(g.get_graph().nodes.keys())
        # Thesis-first H1–H9 topology (Jun-20 greenfield).
        for expected in (
            "hermes/thesis/market-review",
            "hermes/thesis/market-exploration",
            "hermes/thesis/vehicle-map",
            "hermes/thesis/opportunity-screener",
            "hermes/portfolio/asset-analyst-AAPL",
            "hermes/portfolio/deliberation-AAPL",
            "hermes/portfolio/pm-direction",
            "hermes/portfolio/risk-sizing-noop",
            "hermes/portfolio/commit-run",
        ):
            assert expected in names, f"{expected!r} missing from compiled hermes graph"
        assert not any(n.startswith("technical-analyst-") for n in names)
        assert not any(n.startswith("phase7cd") for n in names)

    def test_daily_always_includes_triage(self) -> None:
        g = build_atlas_graph(deps=_deps(), watchlist=())
        names = set(g.get_graph().nodes.keys())
        assert "triage" in names
        assert "monthly-digest" not in names
        assert "alt-sentiment-news" in names


@pytest.mark.unit
class TestLegacyFreezeMarkers:
    def test_publish_document_is_marked_frozen(self) -> None:
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[3]
            / "digiquant"
            / "scripts"
            / "atlas"
            / "publish_document.py"
        )
        text = path.read_text(encoding="utf-8")
        assert "FROZEN" in text
        assert "ADR-0009" in text

    def test_materialize_snapshot_is_marked_frozen(self) -> None:
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[3]
            / "digiquant"
            / "scripts"
            / "atlas"
            / "materialize_snapshot.py"
        )
        text = path.read_text(encoding="utf-8")
        assert "FROZEN" in text
        assert "ADR-0009" in text


@pytest.mark.unit
class TestSectorSkillsDeleted:
    def test_legacy_sector_directories_removed(self) -> None:
        """Commit 9 drops the 11 per-sector SKILL dirs in favor of the
        templated sector-research skill + config/sectors.yaml."""
        from pathlib import Path

        skills_dir = (
            Path(__file__).resolve().parents[3]
            / "digiquant"
            / "src"
            / "digiquant"
            / "olympus"
            / "atlas"
            / "skills"
        )
        for slug in (
            "sector-technology",
            "sector-healthcare",
            "sector-energy",
            "sector-financials",
            "sector-consumer-disc",
            "sector-consumer-staples",
            "sector-industrials",
            "sector-utilities",
            "sector-materials",
            "sector-real-estate",
            "sector-comms",
        ):
            assert not (skills_dir / slug).exists(), f"{slug} should have been deleted in commit 9"
        # The replacement skill IS present.
        assert (skills_dir / "sector-research" / "SKILL.md").exists()
