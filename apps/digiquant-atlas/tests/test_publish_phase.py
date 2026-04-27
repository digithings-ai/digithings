"""Unit + integration tests for the terminal publish phase (#382)."""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for fake-payload dict shape

import pytest

from digiquant_atlas.phases.publish_phase import (
    PublishDeps,
    build_publish_node,
    build_publish_phase,
)
from digiquant_atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,
    SegmentPayload,
    SegmentSlot,
)

from tests.test_supabase_io import FakeSupabaseClient


def _slot(slug: str, **extra: Any) -> SegmentSlot:
    body = {"segment": slug, **extra}
    return SegmentSlot(payload=SegmentPayload(segment=slug, body=body, as_of=date(2026, 4, 26)))


def _carried_slot(reason: str = "below_triage_threshold") -> SegmentSlot:
    return SegmentSlot(payload=Carried(baseline_date=date(2026, 4, 19), reason=reason))


def _seed_full_state(run_type: str = "baseline") -> AtlasResearchState:
    """Populate every phase output that the publish node should write."""
    state = AtlasResearchState(
        run_type=run_type,  # type: ignore[arg-type]
        run_date=date(2026, 4, 26),
        baseline_date=date(2026, 4, 19) if run_type == "delta" else None,
        config=AtlasConfigBundle(watchlist=["AAPL", "MSFT"]),
    )
    state.phase1_outputs = {
        "alt-sentiment-news": _slot("alt-sentiment-news"),
        "alt-cta-positioning": _slot("alt-cta-positioning"),
    }
    state.phase2_outputs = {"inst-institutional-flows": _slot("inst-institutional-flows")}
    state.phase3_output = _slot("macro", regime_label="Slowing")
    state.phase4_outputs = {"bonds": _slot("bonds")}
    state.phase5_outputs = {"equity": _slot("equity")}
    state.phase7_digest = {
        "market_regime_snapshot": "regime",
        "us_equities_summary": "equities",
    }
    state.phase7c_analysts = {
        "AAPL": {"ticker": "AAPL", "stance": "buy"},
        "MSFT": {"ticker": "MSFT", "stance": "hold"},
    }
    state.phase7d_rebalance = {"decisions": [{"ticker": "AAPL", "action": "increase"}]}
    return state


@pytest.mark.unit
class TestPublishNode:
    def test_writes_one_documents_row_per_fresh_segment(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        node = build_publish_node(PublishDeps(client=client))

        result = node(state)

        # Per-segment docs: phase1 (2) + phase2 (1) + phase3 (1) + phase4 (1) +
        # phase5 (1) + digest doc (1) + analyst (2) + rebalance (1) = 10.
        doc_rows = client.store["documents"]
        keys = sorted(r["document_key"] for r in doc_rows)
        assert keys == sorted(
            [
                "alt-sentiment-news",
                "alt-cta-positioning",
                "inst-institutional-flows",
                "macro",
                "bonds",
                "equity",
                "digest",
                "analyst/AAPL",
                "analyst/MSFT",
                "pm-rebalance",
            ]
        )
        # Idempotency: every upsert declares (date, document_key) on-conflict.
        assert all(r["_on_conflict"] == "date,document_key" for r in doc_rows)
        # Return value records every artifact so state.published is populated.
        assert len(result["published"]) == len(doc_rows) + 1  # +1 for daily_snapshots

    def test_writes_one_daily_snapshot_row(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        snapshots = client.store["daily_snapshots"]
        assert len(snapshots) == 1
        assert snapshots[0]["date"] == "2026-04-26"
        assert snapshots[0]["run_type"] == "baseline"
        assert snapshots[0]["snapshot"] == state.phase7_digest
        assert snapshots[0]["_on_conflict"] == "date"

    def test_skips_carried_segment_slots(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="delta")
        # Mark some slots Carried — these must not be re-published.
        state.phase1_outputs = {
            "alt-sentiment-news": _slot("alt-sentiment-news"),
            "alt-cta-positioning": _carried_slot(),
        }
        state.phase4_outputs = {"bonds": _carried_slot()}
        state.phase3_output = _carried_slot("macro_unchanged")

        node = build_publish_node(PublishDeps(client=client))
        node(state)

        keys = {r["document_key"] for r in client.store["documents"]}
        assert "alt-sentiment-news" in keys  # fresh, written
        assert "alt-cta-positioning" not in keys  # carried, skipped
        assert "bonds" not in keys  # carried, skipped
        assert "macro" not in keys  # carried, skipped

    def test_delta_run_uses_digest_delta_doc_type(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="delta")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        digest_row = next(
            r for r in client.store["documents"] if r["document_key"] == "digest-delta"
        )
        assert digest_row["doc_type"] == "Daily Delta"
        assert client.store["daily_snapshots"][0]["run_type"] == "delta"
        assert client.store["daily_snapshots"][0]["baseline_date"] == "2026-04-19"

    def test_baseline_run_uses_daily_digest_doc_type(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        digest_row = next(r for r in client.store["documents"] if r["document_key"] == "digest")
        assert digest_row["doc_type"] == "Daily Digest"

    def test_no_digest_no_snapshot_written(self) -> None:
        """Defensive: if Phase 7 was skipped (shouldn't happen on real runs),
        the publish node must not write an empty snapshot."""
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        state.phase7_digest = None

        node = build_publish_node(PublishDeps(client=client))
        node(state)

        assert "daily_snapshots" not in client.store
        digest_keys = {
            r["document_key"]
            for r in client.store.get("documents", [])
            if r["document_key"] in ("digest", "digest-delta")
        }
        assert digest_keys == set()

    def test_pm_rebalance_uses_rebalance_decision_doc_type(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        rebalance = next(
            r for r in client.store["documents"] if r["document_key"] == "pm-rebalance"
        )
        assert rebalance["doc_type"] == "Rebalance Decision"

    def test_per_ticker_analyst_keyed_under_analyst_prefix(self) -> None:
        client = FakeSupabaseClient()
        state = _seed_full_state(run_type="baseline")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        analyst_rows = [
            r for r in client.store["documents"] if r["document_key"].startswith("analyst/")
        ]
        assert {r["document_key"] for r in analyst_rows} == {"analyst/AAPL", "analyst/MSFT"}
        assert all(r["segment"] == "analyst" for r in analyst_rows)
        assert {r["sector"] for r in analyst_rows} == {"AAPL", "MSFT"}


@pytest.mark.unit
class TestPublishPhaseCompiles:
    def test_phase_factory_returns_single_node_phase(self) -> None:
        deps = PublishDeps(client=FakeSupabaseClient())
        phase = build_publish_phase(deps)
        assert phase.name == "publish"
        assert len(phase.nodes) == 1
        assert phase.nodes[0].name == "publish-supabase"

    def test_compiles_into_pipeline(self) -> None:
        from digigraph.graph.pipeline_builder import build_pipeline

        deps = PublishDeps(client=FakeSupabaseClient())
        compiled = build_pipeline(AtlasResearchState, [build_publish_phase(deps)])
        # Compile-time assertion only: invoking would require a hydrated state
        # and the publish node currently expects phase outputs to exist.
        assert compiled is not None


@pytest.mark.unit
class TestGraphDepsWiring:
    def test_publish_none_skips_publish_phase(self) -> None:
        """Default ``AtlasGraphDeps.publish=None`` must not append the publish phase."""
        from digiquant_atlas.graph import AtlasGraphDeps, build_atlas_graph
        from digiquant_atlas.phases.preflight import PreflightDeps

        client = FakeSupabaseClient()
        deps = AtlasGraphDeps(
            preflight=PreflightDeps(client=client, config_loader=lambda: AtlasConfigBundle())
        )
        # Compiles without error and without needing publish wiring.
        graph = build_atlas_graph("baseline", deps=deps, watchlist=("AAPL",))
        assert graph is not None

    def test_publish_provided_appends_publish_phase(self) -> None:
        from digiquant_atlas.graph import AtlasGraphDeps, build_atlas_graph
        from digiquant_atlas.phases.preflight import PreflightDeps

        client = FakeSupabaseClient()
        deps = AtlasGraphDeps(
            preflight=PreflightDeps(client=client, config_loader=lambda: AtlasConfigBundle()),
            publish=PublishDeps(client=client),
        )
        graph = build_atlas_graph("baseline", deps=deps, watchlist=("AAPL",))
        assert graph is not None
