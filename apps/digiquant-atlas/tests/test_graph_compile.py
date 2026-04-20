"""End-to-end graph-compilation tests.

Verifies that ``build_atlas_graph`` returns a well-formed StateGraph for
each run_type and that the public contract (AtlasInput, initial_state)
behaves as advertised.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for fake-client shape

import pytest

from digiquant_atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    build_atlas_graph,
    initial_state,
)
from digiquant_atlas.phases.preflight import PreflightDeps
from digiquant_atlas.state import AtlasConfigBundle, AtlasResearchState

from tests.test_supabase_io import FakeSupabaseClient


def _deps(canned: dict[str, list[dict[str, Any]]] | None = None) -> AtlasGraphDeps:
    client = FakeSupabaseClient(
        canned_reads=canned
        or {
            "daily_snapshots": [],
            "documents": [],
            "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
            "macro_series_observations": [{"date": "2026-04-25"}],
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
        inp = AtlasInput(run_type="baseline", run_date=date(2026, 4, 26))
        assert inp.baseline_date is None
        assert inp.watchlist == ()
        assert inp.digi_bearer is None

    def test_initial_state_round_trip(self) -> None:
        inp = AtlasInput(
            run_type="delta",
            run_date=date(2026, 4, 27),
            baseline_date=date(2026, 4, 26),
            watchlist=("AAPL", "MSFT"),
        )
        state = initial_state(inp)
        assert state.run_type == "delta"
        assert state.baseline_date == date(2026, 4, 26)
        assert state.config.watchlist == ["AAPL", "MSFT"]


@pytest.mark.unit
class TestBuildGraph:
    def test_baseline_compiles(self) -> None:
        g = build_atlas_graph("baseline", deps=_deps(), watchlist=("AAPL",))
        names = set(g.get_graph().nodes.keys())
        # Every top-level phase node is present.
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
            "analyst-AAPL",
            "pm-rebalance",
            "evolution",
        ):
            assert expected in names, f"{expected!r} missing from compiled baseline graph"

    def test_delta_includes_triage_phase(self) -> None:
        g = build_atlas_graph("delta", deps=_deps(), watchlist=())
        names = set(g.get_graph().nodes.keys())
        assert "triage" in names
        # phase7c still present even with empty watchlist (no-op node).
        assert "analyst-noop" in names

    def test_monthly_graph_is_compact(self) -> None:
        g = build_atlas_graph("monthly", deps=_deps())
        names = set(g.get_graph().nodes.keys())
        # Monthly skips the segment layer.
        assert "preflight" in names
        assert "monthly-digest" in names
        # No per-segment nodes.
        assert "alt-sentiment-news" not in names
        assert "sector-technology" not in names


@pytest.mark.unit
class TestLegacyFreezeMarkers:
    def test_publish_document_is_marked_frozen(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "publish_document.py"
        text = path.read_text(encoding="utf-8")
        assert "FROZEN" in text
        assert "ADR-0009" in text

    def test_materialize_snapshot_is_marked_frozen(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "materialize_snapshot.py"
        text = path.read_text(encoding="utf-8")
        assert "FROZEN" in text
        assert "ADR-0009" in text


@pytest.mark.unit
class TestSectorSkillsDeleted:
    def test_legacy_sector_directories_removed(self) -> None:
        """Commit 9 drops the 11 per-sector SKILL dirs in favor of the
        templated sector-research skill + config/sectors.yaml."""
        from pathlib import Path

        skills_dir = Path(__file__).resolve().parents[1] / "skills"
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
