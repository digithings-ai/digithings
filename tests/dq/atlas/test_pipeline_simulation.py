"""End-to-end Atlas pipeline simulation tests.

These tests exercise the full LangGraph pipeline (preflight → all 9
phases → publish) using ``digiquant.olympus.atlas.testing.simulator`` to mock
both the LLM provider and Supabase. Zero network calls, zero token
spend, zero DB writes.

The point isn't to validate any single phase's prompt quality — that's
what the focused per-phase tests are for. The point is to catch graph
wiring bugs: phase ordering, state-reducer collisions, deps threading,
publish-path routing, delta carry-forward, custom-research routing.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.olympus.atlas.graph import AtlasInput
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.atlas.testing import (
    DEFAULT_RESPONSES,
    parse_phase_inputs,
    parse_schema_name,
    simulated_pipeline,
)
from digiquant.olympus.hermes.graph import HermesGraphDeps, ThesisGraphDeps
from digiquant.olympus.hermes.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    MissingFactProposal,
)
from digiquant.olympus.research_retrieval.h6_amendment import H6AmendmentOutcome
from digiquant.olympus.research_retrieval.store import EvidenceBundleStore

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


@pytest.mark.unit
class TestSimulatorContract:
    def test_default_responses_cover_all_known_schemas(self) -> None:
        """Spot-check that the default response table covers the
        load-bearing models. Per-call dynamic schemas are exempt."""
        required = {
            "SentimentNewsReport",
            "MacroRegimeReport",
            "DigestSnapshot",
            "DigestSubsection",
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
                    refresh_scope="all",
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
            assert ticker in final.phase_hermes.asset_analysts

        for ticker in ("AAPL", "MSFT"):
            debate = final.phase_hermes.deliberation_summaries[ticker]
            assert "net_stance" in debate

        # H7 direction + H8 sized book.
        assert final.phase_hermes.pm_direction_memo is not None
        assert final.phase_hermes.sized_book is not None

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
                    refresh_scope="all",
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
                    refresh_scope="all",
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

        def custom_analyst(messages: list[dict], _kwargs: dict) -> dict:
            from digiquant.olympus.atlas.testing.simulator import parse_phase_inputs

            inputs = parse_phase_inputs(messages)
            ticker = str(inputs.get("ticker", "?"))
            seen_tickers.append(ticker)
            return {
                "ticker": ticker,
                "conviction_score": 5,
                "stance": "buy",
                "thesis": f"override for {ticker}",
                "risks": "",
                "sources": [],
            }

        with simulated_pipeline(
            watchlist=("AAPL", "MSFT"),
            overrides={"AnalystPayload": custom_analyst},
        ) as run:
            final = run.invoke(
                AtlasInput(
                    refresh_scope="all",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL", "MSFT"),
                )
            )

        # H5 unified analyst: one call per ticker.
        assert len(seen_tickers) == 2
        for ticker in ("AAPL", "MSFT"):
            payload = final.phase_hermes.asset_analysts[ticker]
            assert payload["conviction_score"] == 5


@pytest.mark.unit
class TestNoNetworkOrTokens:
    def test_simulator_module_does_not_reference_create_client(self) -> None:
        """Hard rule: the simulator must not reach for the real client.

        Static check rather than ``sys.modules`` introspection — the prior
        runtime check was order-dependent (any earlier test that imported
        ``supabase`` would taint ``sys.modules``). Reading the simulator's
        source directly is deterministic.
        """
        from pathlib import Path

        import digiquant.olympus.atlas.testing.simulator as simulator_module

        source = Path(simulator_module.__file__).read_text(encoding="utf-8")
        assert "from supabase import" not in source
        assert "import supabase\n" not in source
        assert "create_client" not in source

    def test_chat_completion_is_patched_inside_context(self) -> None:
        """Outside the context manager, real chat_completion is restored."""
        from digigraph.graph import research_agent

        original = research_agent.completion_text
        with simulated_pipeline(watchlist=("AAPL",), publish=False) as _run:
            assert research_agent.completion_text is not original
        assert research_agent.completion_text is original


@pytest.mark.unit
class TestDurableH5H6LineageRoundTrip:
    """WP11.5 — H5 base + H6 amendment lineage survives store/checkpoint reload."""

    def test_store_checkpoint_reload_preserves_byte_equivalent_lineage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_EVIDENCE_BUNDLE_WRITER", "on")
        monkeypatch.setenv("OLYMPUS_H6_SELECTION_MODE", "enforce")
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "2")

        store = EvidenceBundleStore()
        grounding_calls: list[bool] = []
        pm_round: dict[str, int] = {}

        def _analyst_override(
            messages: list[dict[str, Any]], _kwargs: dict[str, Any]
        ) -> dict[str, Any]:
            inputs = parse_phase_inputs(messages)
            ticker = str(inputs.get("ticker", "AAPL")).upper()
            body = dict(DEFAULT_RESPONSES["AnalystPayload"])
            body["ticker"] = ticker
            if ticker == "AAPL":
                body["conviction_score"] = 4
            return body

        def fake_research_agent(*, output_model, phase_inputs=None, **_kwargs: Any) -> Any:
            ticker = str((phase_inputs or {}).get("ticker", "AAPL")).upper()
            round_number = int((phase_inputs or {}).get("round_number") or 1)
            if output_model is DeliberationPmTurn:
                pm_round[ticker] = round_number
                base = (phase_inputs or {}).get("base_evidence_bundle") or {}
                evidence_ids = base.get("evidence_ids") or []
                claim_id = str(evidence_ids[0]) if evidence_ids else ""
                if ticker == "AAPL" and round_number == 1 and claim_id:
                    return DeliberationPmTurn(
                        converged=False,
                        challenge="need earnings date",
                        conclusion="pending catalyst",
                        net_stance="neutral",
                        missing_fact=MissingFactProposal(
                            claim_id=claim_id,
                            question="When is the next earnings date?",
                            source_kind="analyst",
                            reason="catalyst timing challenge",
                        ),
                    )
                if ticker == "MSFT" and round_number == 1:
                    return DeliberationPmTurn(
                        converged=False,
                        challenge="need secret metric",
                        conclusion="still open",
                        net_stance="neutral",
                        missing_fact=MissingFactProposal(
                            claim_id="not-in-base-bundle",
                            question="What is the secret metric?",
                            source_kind="analyst",
                            reason="invalid claim test",
                        ),
                    )
                return DeliberationPmTurn(
                    converged=True,
                    challenge="",
                    accepts_analyst_position=True,
                    conclusion=f"settled {ticker}",
                    net_stance="neutral",
                )
            if output_model is DeliberationAnalystTurn:
                return DeliberationAnalystTurn(
                    converged=round_number >= 2,
                    response=f"analyst response for {ticker}",
                    conclusion="settled",
                    net_stance="bullish" if ticker == "AAPL" else "neutral",
                )
            raise AssertionError(output_model)

        def execute_tool(name: str, _args: dict[str, object]) -> str:
            assert name == "query_research"
            return json.dumps({"payload": {"body": "Next earnings on 2026-10-28."}})

        def _grounding_with_search_flag(*_args: Any, **kwargs: Any) -> tuple[list[Any], Any, Any]:
            grounding_calls.append(bool(kwargs.get("live_search")))
            return ([{"type": "function"}], execute_tool, None)

        atlas_input = AtlasInput(
            refresh_scope="all",
            run_date=date(2026, 4, 26),
            watchlist=("AAPL", "MSFT"),
        )

        with simulated_pipeline(
            watchlist=("AAPL", "MSFT"),
            overrides={"AnalystPayload": _analyst_override},
            evidence_bundle_store=store,
            publish=False,
            commit_run=False,
        ) as run:
            with (
                patch(
                    "digiquant.olympus.hermes.phases.h6_deliberation.run_research_agent",
                    side_effect=fake_research_agent,
                ),
                patch(
                    "digiquant.olympus.hermes.phases.h6_deliberation.build_grounding",
                    side_effect=_grounding_with_search_flag,
                ),
            ):
                after_h5 = run.invoke_through_h5(atlas_input)

            h5_snapshot = store.dump_snapshot()
            checkpoint_json = after_h5.model_dump_json()
            reloaded_store = EvidenceBundleStore.from_snapshot(h5_snapshot)
            checkpoint_state = AtlasResearchState.model_validate_json(checkpoint_json)

            assert len(reloaded_store._bases) >= 1
            for ticker in ("AAPL", "MSFT"):
                bundle_dump = checkpoint_state.phase_hermes.ticker_evidence_bundles.get(ticker)
                assert bundle_dump is not None, f"missing H5 bundle for {ticker}"
                bundle_id = UUID(str(bundle_dump["bundle_id"]))
                loaded = reloaded_store.load_base_bundle(bundle_id)
                assert loaded.content_hash == bundle_dump["content_hash"]
                assert (
                    reloaded_store.base_bundle_count_for(
                        run_id=str(checkpoint_state.run_id),
                        ticker=ticker,
                        content_hash=loaded.content_hash,
                    )
                    == 1
                )

            prior_lineage = reloaded_store.lineage_bytes()
            run.hermes_deps = HermesGraphDeps(
                thesis=run.hermes_deps.thesis,
                risk_sizing=run.hermes_deps.risk_sizing,
                commit_run=run.hermes_deps.commit_run,
                phase9=run.hermes_deps.phase9,
                evidence_bundle_store=reloaded_store,
            )

            with (
                patch(
                    "digiquant.olympus.hermes.phases.h6_deliberation.run_research_agent",
                    side_effect=fake_research_agent,
                ),
                patch(
                    "digiquant.olympus.hermes.phases.h6_deliberation.build_grounding",
                    side_effect=_grounding_with_search_flag,
                ),
            ):
                final = run.invoke_hermes_from_h6(checkpoint_state)

        assert grounding_calls and all(live is False for live in grounding_calls)
        assert pm_round.get("AAPL", 0) >= 2

        aapl = final.phase_hermes.deliberation_summaries["AAPL"]
        msft = final.phase_hermes.deliberation_summaries["MSFT"]
        assert aapl.get("evidence_amendment_outcome") == H6AmendmentOutcome.ACCEPTED.value
        assert aapl.get("evidence_amendment_id")
        assert aapl.get("missing_fact_request_id")
        assert msft.get("evidence_amendment_outcome") == H6AmendmentOutcome.INVALID_REQUEST.value
        assert msft.get("evidence_amendment_failure_reason") == "claim_id_not_in_base_bundle"

        aapl_bundle_id = UUID(str(aapl["base_bundle_id"]))
        base_hash = reloaded_store.load_base_bundle(aapl_bundle_id).content_hash
        assert base_hash == final.phase_hermes.ticker_evidence_bundles["AAPL"]["content_hash"]
        assert reloaded_store.amendment_count_for_base(aapl_bundle_id) == 1

        post_h6_snapshot = reloaded_store.dump_snapshot()
        roundtrip_store = EvidenceBundleStore.from_snapshot(post_h6_snapshot)
        assert roundtrip_store.lineage_bytes() == post_h6_snapshot
        assert roundtrip_store.lineage_bytes() != prior_lineage
        assert len(roundtrip_store._amendments) >= 1
        assert roundtrip_store.unlinked_amendment_count() == 0


@pytest.mark.unit
class TestPhase3ResearchComposition:
    """Integration 3.1 — one-graph Phase 3 lock surface (#3019)."""

    def test_simulator_graphs_exclude_planner_nodes(self) -> None:
        from digiquant.olympus.atlas.graph import AtlasGraphDeps, build_atlas_graph
        from digiquant.olympus.atlas.phases.preflight import PreflightDeps
        from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
        from digiquant.olympus.hermes.graph import build_hermes_graph
        from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps
        from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps

        from tests.dq.hermes.phase3_e2e_fixtures import FORBIDDEN_PHASE3_NODES

        client = FakeSupabaseClient()
        atlas = build_atlas_graph(
            deps=AtlasGraphDeps(
                preflight=PreflightDeps(
                    client=client,
                    config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
                ),
                triage=TriageDeps(client=client),
            ),
            watchlist=("AAPL", "MSFT"),
        )
        hermes = build_hermes_graph(
            watchlist=["AAPL", "MSFT"],
            deps=HermesGraphDeps(
                thesis=ThesisGraphDeps(client=client),
                risk_sizing=RiskSizingDeps(client=client),
                commit_run=CommitRunDeps(client=client),
            ),
        )
        atlas_nodes = set(atlas.get_graph().nodes.keys())
        hermes_nodes = set(hermes.get_graph().nodes.keys())
        assert FORBIDDEN_PHASE3_NODES.isdisjoint(atlas_nodes)
        assert FORBIDDEN_PHASE3_NODES.isdisjoint(hermes_nodes)

    def test_simulated_run_threads_evidence_bundle_store(self) -> None:
        store = EvidenceBundleStore()
        with simulated_pipeline(
            watchlist=("AAPL",),
            evidence_bundle_store=store,
            publish=False,
            commit_run=False,
        ) as run:
            final = run.invoke(
                AtlasInput(
                    refresh_scope="all",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )
        assert final.phase_hermes.asset_analysts.get("AAPL")
        assert store._bases, "H5 must persist at least one base bundle when writer enabled"
        snapshot = store.dump_snapshot()
        reloaded = EvidenceBundleStore.from_snapshot(snapshot)
        assert reloaded.lineage_bytes() == snapshot
