"""WP11.4 — H6 deliberation uses bounded missing-fact amendments only (#2908)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.portfolio.focus_roster import with_fanout_ticker
from digiquant.portfolio.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    MissingFactProposal,
)
from digiquant.portfolio.phases import h6_deliberation
from digiquant.dashboard.research_retrieval.evidence_bundle import (
    H5EvidenceFact,
    build_h5_evidence_bundle,
)
from digiquant.dashboard.research_retrieval.h6_amendment import H6AmendmentOutcome
from digiquant.dashboard.research_retrieval.models import TickerEvidenceBundle, TypedProvenance
from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_STATE = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_PROV = TypedProvenance(
    source_run_id="run-h6-wire",
    attempt_id="attempt-1",
    artifact_id="artifact-h6",
)


def _bundle_dump(*, evidence_count: int = 1) -> tuple[dict[str, Any], tuple[Any, ...]]:
    facts = tuple(
        H5EvidenceFact(
            source=f"src-{index}",
            authority="analyst_doc",
            summary=f"fact {index}",
            event_time=_TS - timedelta(hours=1),
            effective_as_of=_TS - timedelta(minutes=30),
            known_at=_TS - timedelta(minutes=20),
        )
        for index in range(evidence_count)
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-h6-wire",
        attempt_id="attempt-1",
        state_version_id=_STATE,
        facts=facts,
        recorded_at=_TS,
        provenance=_PROV,
    )
    return built.bundle.model_dump(mode="json"), built.evidence


def _state() -> AtlasResearchState:
    bundle_dump, _evidence = _bundle_dump()
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 8, 26),
        knowledge_cutoff_at=_TS,
        config=AtlasConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(
            prior_book=[{"ticker": "AAPL", "weight": 0.05}],
            active_theses=[],
        ),
    )
    state.phase_hermes = PhaseHermesState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
        asset_analysts={
            "AAPL": {
                "ticker": "AAPL",
                "stance": "buy",
                "conviction_score": 3,
                "thesis": "growth intact",
                "forecast_assessment": {
                    "forecast_id": "11111111-1111-4111-8111-111111111111",
                    "ticker": "AAPL",
                    "terms": {
                        "base_return": "0.01",
                        "bull_return": "0.03",
                        "bear_return": "-0.02",
                        "bull_probability": "0.35",
                        "base_probability": "0.35",
                        "bear_probability": "0.30",
                        "evidence_ids": [],
                    },
                    "content_hash": "abc123def4567890123456789012345678901234567890123456789012345678",
                    "known_at": _TS.isoformat(),
                    "effective_at": _TS.isoformat(),
                    "source_run_id": str(state.run_id),
                    "provider_invocation_id": "inv-h5",
                    "prompt_version": "p",
                    "artifact_version": "a",
                },
            }
        },
        ticker_evidence_bundles={"AAPL": bundle_dump},
    )
    return state


@pytest.mark.unit
class TestH6AmendmentWiring:
    def test_h6_grounding_disables_generic_live_search(self) -> None:
        with patch("digiquant.portfolio.phases.h6_deliberation.build_grounding") as mocked:
            mocked.return_value = (None, None, None)
            h6_deliberation._h6_grounding(_state(), segment="test")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["live_search"] is False

    def test_missing_fact_supplement_links_request_to_amendment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_H6_SELECTION_MODE", "enforce")
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "1")
        store = EvidenceBundleStore()
        bundle_dump, evidence = _bundle_dump()
        store.append_base_bundle(TickerEvidenceBundle.model_validate(bundle_dump))
        claim_id = str(evidence[0].evidence_id)

        def fake_research_agent(*, output_model, **_kwargs):
            if output_model is DeliberationPmTurn:
                return DeliberationPmTurn(
                    converged=True,
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
            if output_model is DeliberationAnalystTurn:
                return DeliberationAnalystTurn(
                    converged=True,
                    response="earnings on 2026-10-28",
                    conclusion="dated catalyst",
                    net_stance="bullish",
                )
            raise AssertionError(output_model)

        def execute_tool(name: str, _args: dict[str, object]) -> str:
            assert name == "query_research"
            return json.dumps({"payload": {"body": "Next earnings on 2026-10-28."}})

        with patch(
            "digiquant.portfolio.phases.h6_deliberation.run_research_agent",
            side_effect=fake_research_agent,
        ):
            with patch(
                "digiquant.portfolio.phases.h6_deliberation.build_grounding",
                return_value=([{"type": "function"}], execute_tool, None),
            ):
                out = h6_deliberation.build_h6_from_state(store).worker.run(
                    with_fanout_ticker(_state(), "AAPL")
                )
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["evidence_amendment_outcome"] == H6AmendmentOutcome.ACCEPTED.value
        assert summary["missing_fact_request_id"]
        assert summary["evidence_amendment_id"]
        assert summary["base_bundle_id"] == bundle_dump["bundle_id"]
        assert store.amendment_count_for_base(UUID(bundle_dump["bundle_id"])) == 1

    def test_failed_amendment_records_reason_and_keeps_base_hash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_H6_SELECTION_MODE", "enforce")
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "1")
        bundle_dump, _evidence = _bundle_dump()
        state = _state()

        def fake_research_agent(*, output_model, **_kwargs):
            if output_model is DeliberationPmTurn:
                return DeliberationPmTurn(
                    converged=True,
                    challenge="need unknown fact",
                    conclusion="still open",
                    net_stance="neutral",
                    missing_fact=MissingFactProposal(
                        claim_id="not-in-base",
                        question="What is the secret metric?",
                        source_kind="analyst",
                        reason="invalid claim test",
                    ),
                )
            return DeliberationAnalystTurn(
                converged=True,
                response="cannot verify",
                conclusion="open",
                net_stance="neutral",
            )

        with patch(
            "digiquant.portfolio.phases.h6_deliberation.run_research_agent",
            side_effect=fake_research_agent,
        ):
            with patch(
                "digiquant.portfolio.phases.h6_deliberation.build_grounding",
                return_value=([{"type": "function"}], None, None),
            ):
                out = h6_deliberation.build_h6_from_state().worker.run(
                    with_fanout_ticker(state, "AAPL")
                )
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["evidence_amendment_outcome"] == H6AmendmentOutcome.INVALID_REQUEST.value
        assert summary["evidence_amendment_failure_reason"] == "claim_id_not_in_base_bundle"
        assert summary["base_bundle_id"] == bundle_dump["bundle_id"]
        assert summary.get("evidence_amendment_id") is None
