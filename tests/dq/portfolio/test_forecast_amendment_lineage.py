"""WP4.4 H6 quiet-carry + amendment lineage attachment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from unittest.mock import patch

import pytest
from digiquant.research.state import AtlasConfigBundle, FocusRosterEntry, PriorContext
from digiquant.portfolio.focus_roster import with_fanout_ticker
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    EffectiveSource,
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    forecast_assessment_id,
    forecast_terms_content_hash,
    materialize_forecast_amendment,
    resolve_effective_forecast,
)
from digiquant.portfolio.phases import h6_deliberation
from digiquant.portfolio.phases.h6_deliberation import build_h6_from_state

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 25, 14, 30, tzinfo=UTC)


def _terms(**overrides: object) -> ForecastTerms:
    fields: dict[str, object] = dict(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return=Decimal("-0.12"),
        base_return=Decimal("0.04"),
        bull_return=Decimal("0.18"),
        bear_probability=Decimal("0.25"),
        base_probability=Decimal("0.50"),
        bull_probability=Decimal("0.25"),
        thesis_valid_probability=Decimal("0.60"),
        raw_uncertainty=RawUncertainty.MEDIUM,
    )
    fields.update(overrides)
    return ForecastTerms(**fields)


def _assessment() -> ForecastAssessment:
    terms = _terms()
    content_hash = forecast_terms_content_hash(terms)
    return ForecastAssessment(
        ticker="AAPL",
        terms=terms,
        source_run_id="run-abc",
        provider_invocation_id="inv-001",
        prompt_version="asset-analyst@v3",
        artifact_version="h5-full@1",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.UNAVAILABLE,
            unavailable_reason="test_fixture",
        ),
        effective_at=_TS,
        known_at=_TS,
        content_hash=content_hash,
        forecast_id=forecast_assessment_id(
            ticker="AAPL", source_run_id="run-abc", content_hash=content_hash
        ),
    )


def _state(*, assessment: ForecastAssessment | None = None) -> Any:
    from digiquant.research.state import AtlasResearchState, PhaseHermesState

    fa = assessment or _assessment()
    return AtlasResearchState(
        run_type="delta",
        run_date=_TS.date(),
        knowledge_cutoff_at=_TS,
        config=AtlasConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(),
        phase_hermes=PhaseHermesState(
            focus_roster=[
                FocusRosterEntry(
                    ticker="AAPL",
                    roster_reason="technical",
                    rationale="fixture",
                )
            ],
            asset_analysts={
                "AAPL": {
                    "ticker": "AAPL",
                    "stance": "buy",
                    "thesis": "fixture thesis",
                    "forecast_assessment": fa.model_dump(mode="json"),
                    "forecast": fa.terms.model_dump(mode="json"),
                }
            },
        ),
    )


class TestH6ForecastLineageCarry:
    def test_fingerprint_skip_carries_prior_effective_identity(self) -> None:
        base = _assessment()
        amendment = materialize_forecast_amendment(
            base=base,
            terms=_terms(base_return=Decimal("0.02")),
            reason="prior_challenge",
            source_run_id="run-prior",
            provider_invocation_id="inv-prior",
            effective_at=_TS - timedelta(days=1),
            known_at=_TS - timedelta(days=1),
        )
        prior_eff = resolve_effective_forecast(
            base=base,
            amendment=amendment,
            amendment_outcome=AmendmentOutcome.ACCEPTED,
        )
        state = _state(assessment=base)
        state.prior_context = PriorContext(
            prior_deliberation_by_ticker={
                "AAPL": {
                    "conclusion_excerpt": "prior agreement",
                    "net_stance": "bullish",
                    "conviction_delta": 1,
                    "effective_forecast": prior_eff.model_dump(mode="json"),
                    "base_forecast_id": str(prior_eff.base_forecast_id),
                    "amendment_id": str(prior_eff.amendment_id),
                    "effective_forecast_id": str(prior_eff.effective_id),
                    "amendment_outcome": AmendmentOutcome.ACCEPTED.value,
                    # Round-trip dump so H9 can re-persist after fail-soft (#2790).
                    "forecast_amendment": amendment.model_dump(mode="json"),
                }
            }
        )
        with patch.object(h6_deliberation, "deliberation_skip_signal", return_value=True):
            out = build_h6_from_state().worker.run(with_fanout_ticker(state, "AAPL"))
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carry_reason"] == "fingerprint_skip"
        assert summary["effective_forecast_id"] == str(prior_eff.effective_id)
        assert summary["amendment_id"] == str(prior_eff.amendment_id)
        carried = EffectiveForecast.model_validate(summary["effective_forecast"])
        assert carried.source is EffectiveSource.AMENDMENT
        assert carried.content_hash == prior_eff.content_hash
        assert carried.known_at == prior_eff.known_at
        assert summary.get("forecast_amendment") is not None
        assert summary["forecast_amendment"]["amendment_id"] == str(amendment.amendment_id)
        from digiquant.research.forecast_registry import collect_lineage_from_state
        from digiquant.research.state import AtlasResearchState, PhaseHermesState

        collected_state = AtlasResearchState(
            run_type="delta",
            run_date=_TS.date(),
            knowledge_cutoff_at=_TS,
            phase_hermes=out["phase_hermes"],
        )
        # H5 assessment still on the input state path for registry; attach for collect.
        collected_state.phase_hermes = PhaseHermesState(
            asset_analysts=state.phase_hermes.asset_analysts,
            deliberation_summaries=out["phase_hermes"].deliberation_summaries,
        )
        _assessments, amendments = collect_lineage_from_state(collected_state)
        assert len(amendments) == 1
        assert amendments[0].amendment_id == amendment.amendment_id

    def test_llm_failure_preserves_base_as_effective(self) -> None:
        base = _assessment()
        state = _state(assessment=base)
        with patch.object(
            h6_deliberation,
            "run_deliberation_loop",
            side_effect=ValueError("boom"),
        ):
            out = build_h6_from_state().worker.run(with_fanout_ticker(state, "AAPL"))
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carry_reason"] == "llm_failure"
        assert summary["base_forecast_id"] == str(base.forecast_id)
        assert summary["effective_forecast_id"] == str(base.forecast_id)
        assert summary["amendment_outcome"] == AmendmentOutcome.LLM_FAILURE.value
        assert summary["forecast_degradation"] == "llm_failure"


def test_deliberation_payloads_round_trip_forecast_amendment() -> None:
    """Published debate shape must retain the amendment dump for registry retry."""
    from digiquant.research.state import AtlasResearchState, PhaseHermesState
    from digiquant.portfolio.payloads import deliberation_summaries

    base = _assessment()
    amendment = materialize_forecast_amendment(
        base=base,
        terms=_terms(base_return=Decimal("0.02")),
        reason="challenge",
        source_run_id="run-abc",
        provider_invocation_id="inv-h6",
        effective_at=_TS,
        known_at=_TS,
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=_TS.date(),
        phase_hermes=PhaseHermesState(
            deliberation_summaries={
                "AAPL": {
                    "ticker": "AAPL",
                    "net_stance": "bullish",
                    "conviction_delta": 1,
                    "converged": True,
                    "conclusion": "revised",
                    "forecast_amendment": amendment.model_dump(mode="json"),
                    "amendment_id": str(amendment.amendment_id),
                }
            }
        ),
    )
    shaped = deliberation_summaries(state)["AAPL"]
    assert shaped["forecast_amendment"]["amendment_id"] == str(amendment.amendment_id)


def test_slim_deliberation_preserves_forecast_amendment() -> None:
    from digiquant.research.supabase_io import _slim_deliberation_summary

    slim = _slim_deliberation_summary(
        {
            "body": {
                "conclusion": "revised",
                "net_stance": "bullish",
                "conviction_delta": 1,
                "converged": True,
                "forecast_amendment": {"amendment_id": "keep-me", "reason": "r"},
                "effective_forecast": {"effective_id": "e"},
            }
        }
    )
    assert slim["forecast_amendment"]["amendment_id"] == "keep-me"
    assert slim["effective_forecast"]["effective_id"] == "e"
