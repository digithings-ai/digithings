"""H5 edit-mode tests (dashboard #930 PR 4b)."""

from __future__ import annotations

import json
from datetime import date
from typing import (
    Any,  # score:allow untyped any — scored-lint: heterogeneous fake-row / fixture dicts
)
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.dashboard.edit_mode import DocumentPatch, PatchOp
from digiquant.portfolio.models.analyst import AnalystPayload
from digiquant.portfolio.phases.h5_asset_analyst import build_h5_asset_analyst
from digiquant.research.state import (
    FocusRosterEntry,
    PhasePortfolioState,
    PriorContext,
    ResearchConfigBundle,
    ResearchState,
)


def _state(*, prior: dict[str, Any] | None = None) -> ResearchState:
    prior_ctx = PriorContext(
        prior_analyst_by_ticker={"AAPL": prior} if prior else {},
        latest_segments={
            "analyst/AAPL": {
                "date": "2026-06-19",
                "payload": {
                    "body": {
                        "ticker": "AAPL",
                        "conviction_score": 2,
                        "stance": "hold",
                        "thesis": "prior thesis",
                        "risks": "prior risk",
                        "sources": [],
                    }
                },
            }
        }
        if prior
        else {},
    )
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 6, 20),
        config=ResearchConfigBundle(watchlist=["AAPL"]),
        prior_context=prior_ctx,
        price_deltas={"AAPL": 0.02},
    )
    state.phase_portfolio = PhasePortfolioState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")]
    )
    return state


@pytest.mark.unit
class TestAnalystEdit:
    def test_stale_fingerprint_uses_document_patch(self) -> None:
        from datetime import UTC, datetime

        from digiquant.portfolio.models.forecast import (
            ForecastTerms,
            PriceAnchor,
            PriceAnchorStatus,
        )
        from digiquant.portfolio.phases.portfolio_common import (
            materialize_forecast_assessment,
        )

        terms = ForecastTerms.model_validate(_sample_terms())
        cutoff = datetime(2026, 6, 19, 15, 0, tzinfo=UTC)
        assessment = materialize_forecast_assessment(
            ticker="AAPL",
            terms=terms,
            source_run_id="run-prior",
            provider_invocation_id="inv-prior",
            prompt_version="asset-analyst-full@prior",
            artifact_version="h5-full@1",
            price_anchor=PriceAnchor(
                status=PriceAnchorStatus.UNAVAILABLE,
                unavailable_reason="mark_price_not_available_in_h5_state",
            ),
            effective_at=cutoff,
            known_at=cutoff,
        )
        prior_body = {
            "ticker": "AAPL",
            "conviction_score": 2,
            "stance": "hold",
            "thesis": "prior thesis",
            "risks": "prior risk",
            "sources": [],
            "fingerprint_news_hash": "abc",
            "forecast": terms.model_dump(mode="json"),
            "forecast_assessment": assessment.model_dump(mode="json"),
        }
        state = _state(
            prior={
                "date": "2026-06-19",
                "stance": "hold",
                "conviction_score": 2,
                "fingerprint_news_hash": "abc",
            }
        )
        state = state.model_copy(
            update={
                "knowledge_cutoff_at": datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
                "prior_context": state.prior_context.model_copy(
                    update={
                        "latest_segments": {
                            "analyst/AAPL": {
                                "date": "2026-06-19",
                                "payload": {"body": prior_body},
                            }
                        }
                    }
                ),
            }
        )
        compiled = build_pipeline(ResearchState, [build_h5_asset_analyst(["AAPL"], held={"AAPL"})])

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert "DocumentPatch" in schema
            patch = DocumentPatch(
                date=date(2026, 6, 20),
                prior_date=date(2026, 6, 19),
                target_document_key="analyst/AAPL",
                status="updated",
                ops=[PatchOp(op="set", path="/body/stance", value="buy")],
            )
            return json.dumps(patch.model_dump(mode="json"))

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result)
        payload = AnalystPayload.model_validate(final.phase_portfolio.asset_analysts["AAPL"])
        assert payload.stance == "buy"
        assert payload.thesis == "prior thesis"
        assert payload.forecast_assessment is not None
        assert payload.forecast_assessment.forecast_id == assessment.forecast_id


@pytest.mark.unit
class TestEvidenceDerivedConviction:
    """#1672 — conviction is computed from itemized evidence, not model vibes.

    Production decision_log 2026-07-01..22: 77% of entries at exactly +2. The
    evidence block takes the number away from the LLM; these tests pin the
    mapping's shape: high conviction structurally rare, spread otherwise.
    """

    @staticmethod
    def _payload(stance: str, **ev: object) -> "AnalystPayload":
        from digiquant.portfolio.models.analyst import AnalystPayload

        base = {
            "independent_confirming_signals": 3,
            "contradicting_signals": 1,
            "catalyst_within_horizon": False,
            "trend_alignment": "with",
            "evidence_quality": "medium",
        }
        base.update(ev)
        return AnalystPayload.model_validate(
            {
                "ticker": "SPY",
                "conviction_score": 2,  # the model's parked default — must be ignored
                "stance": stance,
                "evidence": base,
            }
        )

    def test_model_provided_score_is_overridden(self) -> None:
        p = self._payload("buy")
        # 3 confirming − 1 contradicting = 2; caps don't bind → 2 (computed, not parked)
        assert p.conviction_score == 2
        p2 = self._payload("buy", contradicting_signals=3)
        assert p2.conviction_score == 0, "net evidence drives the score, not the default"

    def test_high_conviction_requires_the_full_bar(self) -> None:
        full_bar = dict(
            independent_confirming_signals=5,
            contradicting_signals=0,
            catalyst_within_horizon=True,
            trend_alignment="with",
            evidence_quality="high",
        )
        assert self._payload("buy", **full_bar).conviction_score == 5
        # Remove any single requirement → high (>=4) is unreachable
        assert (
            self._payload("buy", **{**full_bar, "catalyst_within_horizon": False}).conviction_score
            <= 3
        )
        assert (
            self._payload("buy", **{**full_bar, "evidence_quality": "medium"}).conviction_score <= 3
        )
        assert self._payload("buy", **{**full_bar, "evidence_quality": "low"}).conviction_score <= 2
        assert (
            self._payload("buy", **{**full_bar, "contradicting_signals": 2}).conviction_score <= 3
        )

    def test_sell_mirrors_negative_and_hold_clamps(self) -> None:
        strong = dict(
            independent_confirming_signals=5,
            contradicting_signals=0,
            catalyst_within_horizon=True,
            trend_alignment="with",
            evidence_quality="high",
        )
        assert self._payload("sell", **strong).conviction_score == -5
        assert abs(self._payload("hold", **strong).conviction_score) <= 1
        assert self._payload("watch", trend_alignment="mixed").conviction_score == 0

    def test_distribution_over_realistic_grid_is_spread_and_high_is_rare(self) -> None:
        from collections import Counter

        scores = []
        for confirming in range(6):
            for contradicting in range(4):
                for catalyst in (True, False):
                    for quality in ("high", "medium", "low"):
                        scores.append(
                            self._payload(
                                "buy",
                                independent_confirming_signals=confirming,
                                contradicting_signals=contradicting,
                                catalyst_within_horizon=catalyst,
                                evidence_quality=quality,
                            ).conviction_score
                        )
        counts = Counter(scores)
        n = len(scores)
        assert max(counts.values()) / n < 0.5, f"single-mode collapse: {counts}"
        high = sum(v for k, v in counts.items() if k >= 4)
        low = sum(v for k, v in counts.items() if k in (0, 1))
        assert high < low, f"high must be scarcer than low: {counts}"
        assert high > 0, "high must remain reachable"

    def test_legacy_payload_without_evidence_keeps_stored_score(self) -> None:
        from digiquant.portfolio.models.analyst import AnalystPayload

        p = AnalystPayload.model_validate({"ticker": "SPY", "conviction_score": 4, "stance": "buy"})
        assert p.conviction_score == 4, "legacy docs keep their stored score"


def _sample_terms() -> dict[str, object]:
    return {
        "horizon_sessions": 21,
        "half_life_sessions": 10,
        "bear_return": "-0.10",
        "base_return": "0.03",
        "bull_return": "0.15",
        "bear_probability": "0.25",
        "base_probability": "0.50",
        "bull_probability": "0.25",
        "thesis_valid_probability": "0.55",
        "raw_uncertainty": "medium",
        "evidence_ids": ["ev-1"],
        "counter_evidence_ids": [],
        "assumptions": ["rates stable"],
        "invalidation_rules": ["break below support"],
    }


@pytest.mark.unit
class TestH5ForecastMaterialization:
    """WP4.3 — every new full H5 produces an immutable ForecastAssessment."""

    def test_serializer_includes_assessment_and_anchor_reason(self) -> None:
        from datetime import UTC, datetime
        from decimal import Decimal

        from digiquant.portfolio.models.analyst import AnalystPayload
        from digiquant.portfolio.models.forecast import (
            ForecastTerms,
            PriceAnchor,
            PriceAnchorStatus,
            forecast_assessment_id,
            forecast_terms_content_hash,
        )
        from digiquant.portfolio.phases.portfolio_common import (
            analyst_body_from_payload,
            materialize_forecast_assessment,
        )

        terms = ForecastTerms.model_validate(_sample_terms())
        cutoff = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
        assessment = materialize_forecast_assessment(
            ticker="AAPL",
            terms=terms,
            source_run_id="run-1",
            provider_invocation_id="inv-1",
            prompt_version="asset-analyst-full@abc",
            artifact_version="h5-full@1",
            price_anchor=PriceAnchor(
                status=PriceAnchorStatus.UNAVAILABLE,
                unavailable_reason="mark_price_not_available_in_h5_state",
            ),
            effective_at=cutoff,
            known_at=cutoff,
        )
        payload = AnalystPayload.model_validate(
            {
                "ticker": "AAPL",
                "conviction_score": 2,
                "stance": "buy",
                "thesis": "thesis",
                "risks": "risks",
                "forecast": terms.model_dump(mode="json"),
                "forecast_assessment": assessment.model_dump(mode="json"),
            }
        )
        body = analyst_body_from_payload(payload)
        assert "forecast" in body
        assert "forecast_assessment" in body
        fa = body["forecast_assessment"]
        assert fa["forecast_id"] == str(
            forecast_assessment_id(
                ticker="AAPL",
                source_run_id="run-1",
                content_hash=forecast_terms_content_hash(terms),
            )
        )
        assert fa["price_anchor"]["status"] == "unavailable"
        assert fa["price_anchor"]["unavailable_reason"]
        assert Decimal(str(body["forecast"]["base_return"])) == Decimal("0.03")

    def test_legacy_prior_forces_full(self) -> None:
        from digiquant.portfolio.phases.portfolio_common import resolve_analyst_edit_mode

        state = _state(
            prior={
                "date": "2026-06-19",
                "stance": "hold",
                "conviction_score": 2,
                "fingerprint_news_hash": "abc",
            }
        )
        # Quiet fingerprint would otherwise skip — legacy typed-forecast gap forces full.
        state = state.model_copy(update={"price_deltas": {"AAPL": 0.0}})
        assert resolve_analyst_edit_mode(state, "AAPL") == "full"

    def test_skip_preserves_forecast_identity(self) -> None:
        from datetime import UTC, datetime

        from digiquant.portfolio.models.forecast import (
            ForecastTerms,
            PriceAnchor,
            PriceAnchorStatus,
        )
        from digiquant.portfolio.phases.portfolio_common import (
            materialize_forecast_assessment,
            run_asset_analyst_llm,
        )

        terms = ForecastTerms.model_validate(_sample_terms())
        cutoff = datetime(2026, 6, 19, 15, 0, tzinfo=UTC)
        assessment = materialize_forecast_assessment(
            ticker="AAPL",
            terms=terms,
            source_run_id="run-prior",
            provider_invocation_id="inv-prior",
            prompt_version="asset-analyst-full@prior",
            artifact_version="h5-full@1",
            price_anchor=PriceAnchor(
                status=PriceAnchorStatus.UNAVAILABLE,
                unavailable_reason="mark_price_not_available_in_h5_state",
            ),
            effective_at=cutoff,
            known_at=cutoff,
        )
        prior_body = {
            "ticker": "AAPL",
            "conviction_score": 2,
            "stance": "hold",
            "thesis": "prior thesis",
            "risks": "prior risk",
            "sources": [],
            "fingerprint_news_hash": "abc",
            "forecast": terms.model_dump(mode="json"),
            "forecast_assessment": assessment.model_dump(mode="json"),
        }
        state = _state(
            prior={
                "date": "2026-06-19",
                "stance": "hold",
                "conviction_score": 2,
                "fingerprint_news_hash": "abc",
            }
        )
        # Quiet day → skip; typed prior may be carried.
        state = state.model_copy(
            update={
                "price_deltas": {"AAPL": 0.0},
                "knowledge_cutoff_at": datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
                "prior_context": state.prior_context.model_copy(
                    update={
                        "latest_segments": {
                            "analyst/AAPL": {
                                "date": "2026-06-19",
                                "payload": {"body": prior_body},
                            }
                        },
                        "prior_analyst_by_ticker": {
                            "AAPL": {
                                "date": "2026-06-19",
                                "stance": "hold",
                                "conviction_score": 2,
                                "fingerprint_news_hash": "abc",
                            }
                        },
                    }
                ),
            }
        )
        # Align news hash so triage stays quiet (triage reads ticker_fingerprint).
        with patch(
            "digiquant.portfolio.ticker_fingerprint.news_hash_for_ticker",
            return_value="abc",
        ):
            from digiquant.portfolio.phases.portfolio_common import (
                resolve_analyst_edit_mode,
            )

            assert resolve_analyst_edit_mode(state, "AAPL") == "skip"
            payload, doc, errors, _bundle = run_asset_analyst_llm(
                state=state,
                ticker="AAPL",
                roster_entry={"ticker": "AAPL", "roster_reason": "held"},
                phase_slug="portfolio/asset-analyst-AAPL",
            )
        assert not errors
        assert payload is not None
        assert payload.forecast_assessment is not None
        assert payload.forecast_assessment.forecast_id == assessment.forecast_id
        assert doc is not None
        assert doc["body"]["forecast_assessment"]["forecast_id"] == str(assessment.forecast_id)

    def test_partial_nested_forecast_edit_rejected(self) -> None:
        from datetime import UTC, datetime

        from digiquant.portfolio.models.forecast import (
            ForecastTerms,
            PriceAnchor,
            PriceAnchorStatus,
        )
        from digiquant.portfolio.phases.portfolio_common import (
            materialize_forecast_assessment,
            run_asset_analyst_llm,
        )

        terms = ForecastTerms.model_validate(_sample_terms())
        cutoff = datetime(2026, 6, 19, 15, 0, tzinfo=UTC)
        assessment = materialize_forecast_assessment(
            ticker="AAPL",
            terms=terms,
            source_run_id="run-prior",
            provider_invocation_id="inv-prior",
            prompt_version="asset-analyst-full@prior",
            artifact_version="h5-full@1",
            price_anchor=PriceAnchor(
                status=PriceAnchorStatus.UNAVAILABLE,
                unavailable_reason="mark_price_not_available_in_h5_state",
            ),
            effective_at=cutoff,
            known_at=cutoff,
        )
        prior_body = {
            "ticker": "AAPL",
            "conviction_score": 2,
            "stance": "hold",
            "thesis": "prior thesis",
            "risks": "prior risk",
            "sources": [],
            "fingerprint_news_hash": "stale",
            "forecast": terms.model_dump(mode="json"),
            "forecast_assessment": assessment.model_dump(mode="json"),
        }
        state = _state(
            prior={
                "date": "2026-06-19",
                "stance": "hold",
                "conviction_score": 2,
                "fingerprint_news_hash": "stale",
            }
        )
        state = state.model_copy(
            update={
                "knowledge_cutoff_at": datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
                "prior_context": state.prior_context.model_copy(
                    update={
                        "latest_segments": {
                            "analyst/AAPL": {
                                "date": "2026-06-19",
                                "payload": {"body": prior_body},
                            }
                        }
                    }
                ),
            }
        )
        compiled_patch = DocumentPatch(
            date=date(2026, 6, 20),
            prior_date=date(2026, 6, 19),
            target_document_key="analyst/AAPL",
            status="updated",
            ops=[PatchOp(op="set", path="/body/forecast/bear_return", value="-0.50")],
        )

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            return json.dumps(compiled_patch.model_dump(mode="json"))

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            payload, _doc, errors, _bundle = run_asset_analyst_llm(
                state=state,
                ticker="AAPL",
                roster_entry={"ticker": "AAPL", "roster_reason": "held"},
                phase_slug="portfolio/asset-analyst-AAPL",
            )
        assert payload is not None
        assert any("partial nested forecast" in e.message for e in errors)
        assert payload.forecast_assessment is not None
        assert payload.forecast_assessment.forecast_id == assessment.forecast_id

    def test_full_requires_terms(self) -> None:
        from datetime import UTC, datetime

        state = _state(prior=None)
        state = state.model_copy(
            update={"knowledge_cutoff_at": datetime(2026, 6, 20, 12, 0, tzinfo=UTC)}
        )
        compiled = build_pipeline(ResearchState, [build_h5_asset_analyst(["AAPL"], held={"AAPL"})])

        def fake_missing_forecast(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert "DocumentPatch" not in schema
            return json.dumps(
                {
                    "ticker": "AAPL",
                    "conviction_score": 2,
                    "stance": "buy",
                    "thesis": "no forecast terms",
                    "risks": "r",
                    "evidence": {
                        "independent_confirming_signals": 3,
                        "contradicting_signals": 1,
                        "catalyst_within_horizon": False,
                        "trend_alignment": "with",
                        "evidence_quality": "medium",
                    },
                }
            )

        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=fake_missing_forecast
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result)
        # Shadow rollout: retain analyst prose; do not fabricate assessment.
        raw = final.phase_portfolio.asset_analysts["AAPL"]
        payload = AnalystPayload.model_validate(raw)
        assert payload.forecast is None
        assert payload.forecast_assessment is None
        assert payload.stance == "buy"

    def test_full_materializes_assessment(self) -> None:
        from datetime import UTC, datetime

        state = _state(prior=None)
        state = state.model_copy(
            update={"knowledge_cutoff_at": datetime(2026, 6, 20, 12, 0, tzinfo=UTC)}
        )
        compiled = build_pipeline(ResearchState, [build_h5_asset_analyst(["AAPL"], held={"AAPL"})])

        def fake_with_forecast(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            return json.dumps(
                {
                    "ticker": "AAPL",
                    "conviction_score": 2,
                    "stance": "buy",
                    "thesis": "typed forecast thesis",
                    "risks": "r",
                    "evidence": {
                        "independent_confirming_signals": 3,
                        "contradicting_signals": 1,
                        "catalyst_within_horizon": False,
                        "trend_alignment": "with",
                        "evidence_quality": "medium",
                    },
                    "forecast": _sample_terms(),
                }
            )

        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=fake_with_forecast
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result)
        raw = final.phase_portfolio.asset_analysts["AAPL"]
        payload = AnalystPayload.model_validate(raw)
        assert payload.forecast is not None
        assert payload.forecast_assessment is not None
        assert payload.forecast_assessment.ticker == "AAPL"
        assert payload.forecast_assessment.content_hash
        assert payload.forecast_assessment.price_anchor.unavailable_reason or (
            payload.forecast_assessment.price_anchor.observed_at is not None
        )


@pytest.mark.unit
def test_h5_persists_before_provider_and_failure_leaves_bundle() -> None:
    """WP11.2: publish base before provider; H5 failure retains typed bundle."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock
    from uuid import UUID, uuid4

    from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore
    from digiquant.portfolio.phases.portfolio_common import run_asset_analyst_llm

    store = EvidenceBundleStore()
    run_id = uuid4()
    state_version = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    cutoff = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
    state = ResearchState(
        run_id=run_id,
        run_type="delta",
        run_date=cutoff.date(),
        config=ResearchConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(),
        price_deltas={"AAPL": 0.01},
        knowledge_cutoff_at=cutoff,
        research_state_pin={"state_version_id": str(state_version)},
    )
    state.phase_portfolio = PhasePortfolioState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")]
    )

    def _boom(*_a: Any, **_k: Any) -> Any:
        assert len(store._bases) == 1  # persist-before-provider
        raise RuntimeError("provider down")

    with (
        patch.dict("os.environ", {"OLYMPUS_EVIDENCE_BUNDLE_WRITER": "on"}, clear=False),
        patch(
            "digiquant.portfolio.phases.portfolio_common.build_grounding",
            return_value=(
                [],
                MagicMock(),
                {"summary": "news", "sources": ["https://x"], "as_of": "2026-08-26"},
            ),
        ),
        patch(
            "digiquant.portfolio.phases.portfolio_common.apply_web_grounding_to_inputs",
            side_effect=lambda inputs, **_k: {
                **inputs,
                "web_grounding": {
                    "summary": "news",
                    "sources": ["https://x"],
                    "as_of": "2026-08-26",
                },
            },
        ),
        patch(
            "digiquant.portfolio.phases.portfolio_common.resolve_analyst_edit_mode",
            return_value="full",
        ),
        patch(
            "digiquant.portfolio.phases.portfolio_common.run_research_agent",
            side_effect=_boom,
        ),
        patch(
            "digiquant.portfolio.phases.portfolio_common.load_skill_full",
            return_value="skill",
        ),
    ):
        payload, doc, errors, bundle = run_asset_analyst_llm(
            state=state,
            ticker="AAPL",
            roster_entry={"ticker": "AAPL", "roster_reason": "held"},
            phase_slug="portfolio/asset-analyst-AAPL",
            evidence_bundle_store=store,
        )

    assert payload is None
    assert doc is None
    assert errors
    assert bundle is not None
    assert (
        store.base_bundle_count_for(
            run_id=str(run_id), ticker="AAPL", content_hash=bundle.content_hash
        )
        == 1
    )
    retained = PhasePortfolioState(
        ticker_evidence_bundles={"AAPL": bundle.model_dump(mode="json")},
    )
    assert retained.asset_analysts == {}
    assert retained.ticker_evidence_bundles["AAPL"]["bundle_id"] == str(bundle.bundle_id)
