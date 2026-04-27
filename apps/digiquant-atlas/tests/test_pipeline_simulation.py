"""End-to-end Atlas pipeline simulation tests.

These tests exercise the full LangGraph pipeline (preflight → all 9
phases → publish) using ``digiquant_atlas.testing.simulator`` to mock
both the LLM provider and Supabase. Zero network calls, zero token
spend, zero DB writes.

The point isn't to validate any single phase's prompt quality — that's
what the focused per-phase tests are for. The point is to catch graph
wiring bugs: phase ordering, state-reducer collisions, deps threading,
publish-path routing, delta carry-forward, custom-research routing.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant_atlas.graph import AtlasInput
from digiquant_atlas.testing import (
    DEFAULT_RESPONSES,
    parse_schema_name,
    simulated_pipeline,
)


@pytest.mark.unit
class TestSimulatorContract:
    def test_default_responses_cover_all_known_schemas(self) -> None:
        """Spot-check that the default response table covers the
        load-bearing models. Per-call dynamic schemas are exempt."""
        required = {
            "SentimentNewsReport",
            "MacroRegimeReport",
            "DigestSnapshot",
            "RebalanceDecision",
            "RiskDebateSummary",
            "Phase9Artifacts",
        }
        assert required.issubset(set(DEFAULT_RESPONSES.keys()))

    def test_parse_schema_name_extracts_class_name(self) -> None:
        msgs = [
            {
                "content": [
                    {"text": "PHASE_INPUTS (today): {}"},
                    {"text": "OUTPUT_SCHEMA (name: DigestSnapshot):\n{...}"},
                ]
            }
        ]
        assert parse_schema_name(msgs) == "DigestSnapshot"

    def test_parse_schema_name_returns_none_when_missing(self) -> None:
        assert parse_schema_name([{"content": [{"text": "no schema"}]}]) is None


@pytest.mark.unit
class TestBaselineEndToEnd:
    def test_full_baseline_run_produces_publish_artifacts(self) -> None:
        """Smoke test: invoke a baseline graph, assert every phase wrote
        its piece of state and the publish phase routed the digest."""
        with simulated_pipeline(watchlist=("AAPL", "MSFT")) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="baseline",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL", "MSFT"),
                )
            )

        # Phase 1-5 segment outputs landed.
        assert final.phase1_outputs, "Phase 1 outputs missing"
        assert final.phase2_outputs, "Phase 2 outputs missing"
        assert final.phase3_output is not None, "Phase 3 macro missing"
        assert final.phase4_outputs, "Phase 4 outputs missing"
        assert final.phase5_outputs, "Phase 5 equity missing"

        # Phase 6 bias row aggregated.
        assert final.phase6_bias_row is not None
        # Phase 7 digest synthesised.
        assert final.phase7_digest is not None

        # Phase 7C 4-axis specialists ran for every ticker (#430).
        for ticker in ("AAPL", "MSFT"):
            assert ticker in final.phase7c_specialists
            assert set(final.phase7c_specialists[ticker].keys()) == {
                "technical",
                "sentiment",
                "news",
                "fundamental",
            }
            # Join produced an AnalystPayload for every ticker.
            assert ticker in final.phase7c_analysts

        # Phase 7C-D bull/bear debate produced summaries (#429).
        for ticker in ("AAPL", "MSFT"):
            debate = final.phase7cd_debates[ticker]
            assert "net_stance" in debate

        # Phase 7D risk debate (#431) + PM rebalance.
        assert final.phase7d_risk_debate is not None
        assert final.phase7d_rebalance is not None

        # Phase 9 evolution emitted.
        assert final.phase9_evolution is not None

        # Publish phase wrote both daily_snapshots + per-segment documents.
        assert "daily_snapshots" in run.client.store
        assert len(run.client.store["daily_snapshots"]) == 1
        assert run.client.store["daily_snapshots"][0]["run_type"] == "baseline"
        assert "documents" in run.client.store
        digest_rows = [r for r in run.client.store["documents"] if r["doc_type"] == "Daily Digest"]
        assert len(digest_rows) == 1

    def test_publish_skipped_when_dep_omitted(self) -> None:
        """``publish=False`` keeps the run hermetic for orchestration tests
        that don't care about the persistence path."""
        with simulated_pipeline(watchlist=("AAPL",), publish=False) as run:
            run.invoke(
                AtlasInput(
                    run_type="baseline",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )
        assert "daily_snapshots" not in run.client.store


@pytest.mark.unit
class TestDeltaCarryForward:
    def test_delta_run_invokes_triage_and_publishes_digest_delta(self) -> None:
        with simulated_pipeline(watchlist=("AAPL",)) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="delta",
                    run_date=date(2026, 4, 26),
                    baseline_date=date(2026, 4, 19),
                    watchlist=("AAPL",),
                )
            )

        # Triage decisions were generated for the run.
        assert final.triage is not None
        # Publish routed under the delta key + doc_type.
        digest_rows = [r for r in run.client.store["documents"] if r["doc_type"] == "Daily Delta"]
        assert len(digest_rows) == 1
        assert digest_rows[0]["document_key"] == "digest-delta"


@pytest.mark.unit
class TestCustomResearchRouting:
    def test_custom_prompt_routes_under_custom_research_doc_type(self) -> None:
        with simulated_pipeline(watchlist=("AAPL",)) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="baseline",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                    custom_prompt="Drill into NVDA earnings risk.",
                )
            )

        assert final.custom_prompt == "Drill into NVDA earnings risk."
        # Custom research lands in documents but NOT in daily_snapshots
        # (cadence stays clean).
        custom_rows = [
            r for r in run.client.store["documents"] if r["doc_type"] == "Custom Research"
        ]
        assert len(custom_rows) == 1
        assert custom_rows[0]["document_key"].startswith("custom-research/")
        assert "daily_snapshots" not in run.client.store


@pytest.mark.unit
class TestOverrides:
    def test_override_callable_can_inspect_inputs(self) -> None:
        """Per-call override receives the raw messages so it can specialize
        on ticker/axis/role, etc."""
        seen_tickers: list[str] = []

        def custom_specialist(messages: list[dict], _kwargs: dict) -> dict:
            from digiquant_atlas.testing.simulator import parse_phase_inputs

            inputs = parse_phase_inputs(messages)
            ticker = inputs.get("ticker", "?")
            axis = inputs.get("axis", "?")
            seen_tickers.append(ticker)
            return {
                "axis": axis,
                "ticker": ticker,
                "conviction_axis": 0.9,
                "stance_axis": "buy",
                "rationale": f"override for {ticker}",
                "sources": [],
            }

        with simulated_pipeline(
            watchlist=("AAPL", "MSFT"),
            overrides={"SpecialistPayload": custom_specialist},
        ) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="baseline",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL", "MSFT"),
                )
            )

        # 4 axes × 2 tickers = 8 specialist calls.
        assert len(seen_tickers) == 8
        # Every override response set conviction_axis=0.9, so the join's
        # weighted average maps to a strong-buy conviction_score.
        for ticker in ("AAPL", "MSFT"):
            payload = final.phase7c_analysts[ticker]
            assert payload["conviction_score"] >= 1


@pytest.mark.unit
class TestNoNetworkOrTokens:
    def test_simulator_does_not_import_supabase_client(self) -> None:
        """Hard rule: the simulator must not pull in the real client."""
        import sys

        from digiquant_atlas.testing import simulator  # noqa: F401

        assert "supabase" not in sys.modules or all(
            not name.startswith("supabase.")
            or name == "supabase"
            and not hasattr(sys.modules.get("supabase"), "create_client")
            for name in sys.modules
        )

    def test_chat_completion_is_patched_inside_context(self) -> None:
        """Outside the context manager, real chat_completion is restored."""
        from digigraph.graph import research_agent

        original = research_agent.chat_completion
        with simulated_pipeline(watchlist=("AAPL",), publish=False) as _run:
            assert research_agent.chat_completion is not original
        assert research_agent.chat_completion is original
