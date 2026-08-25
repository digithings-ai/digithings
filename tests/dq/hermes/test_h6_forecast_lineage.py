"""H6 forecast amendment + quiet-carry lineage (#2655 / WP4.4)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.atlas.supabase_io import load_prior_deliberation_summaries
from digiquant.olympus.hermes.focus_roster import with_fanout_ticker
from digiquant.olympus.hermes.models.deliberation import DeliberationPmTurn, DeliberationSummary
from digiquant.olympus.hermes.models.forecast import (
    EffectiveForecastSource,
    ForecastAssessment,
    ForecastLineageDegradation,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    forecast_assessment_id,
    forecast_terms_content_hash,
    resolve_effective_forecast,
)
from digiquant.olympus.hermes.phases import h6_deliberation
from digiquant.olympus.hermes.phases.h6_deliberation import (
    attach_h6_forecast_lineage,
    build_h6_deliberation,
    build_h6_from_state,
)
from digiquant.olympus.hermes.ticker_fingerprint import news_hash_for_ticker

pytestmark = pytest.mark.unit

_TS = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


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
        evidence_ids=("ev-1",),
        counter_evidence_ids=(),
        assumptions=("rates stable",),
        invalidation_rules=("break thesis stop",),
    )
    fields.update(overrides)
    return ForecastTerms(**fields)


def _assessment(**overrides: object) -> ForecastAssessment:
    terms = overrides.pop("terms", None) or _terms()
    content_hash = forecast_terms_content_hash(terms)
    fields: dict[str, object] = dict(
        ticker="AAPL",
        terms=terms,
        source_run_id="run-h5",
        provider_invocation_id="inv-h5",
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
            ticker="AAPL", source_run_id="run-h5", content_hash=content_hash
        ),
    )
    fields.update(overrides)
    return ForecastAssessment(**fields)


def _analyst_with_assessment(assessment: ForecastAssessment) -> dict:
    return {
        "ticker": "AAPL",
        "conviction_score": 1,
        "stance": "hold",
        "thesis": "unchanged",
        "risks": "",
        "sources": [],
        "forecast": assessment.terms.model_dump(mode="json"),
        "forecast_assessment": assessment.model_dump(mode="json"),
    }


class TestAttachH6ForecastLineage:
    def test_no_amendment_keeps_base_effective(self) -> None:
        base = _assessment()
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            knowledge_cutoff_at=_TS,
        )
        summary = DeliberationSummary(ticker="AAPL", conclusion="ok", net_stance="neutral")
        out = attach_h6_forecast_lineage(
            state=state,
            ticker="AAPL",
            analyst=_analyst_with_assessment(base),
            summary=summary,
            pm_turn=DeliberationPmTurn(converged=True, challenge="probe", conclusion="ok"),
        )
        assert out.effective_forecast is not None
        assert out.effective_forecast.source is EffectiveForecastSource.BASE
        assert out.effective_forecast.base_forecast_id == base.forecast_id

    def test_accepted_amendment_replaces_terms(self) -> None:
        base = _assessment()
        new_terms = _terms(base_return=Decimal("0.08"), bull_return=Decimal("0.22"))
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            knowledge_cutoff_at=_TS,
        )
        summary = DeliberationSummary(ticker="AAPL", conclusion="amended", net_stance="bullish")
        pm = DeliberationPmTurn(
            converged=True,
            challenge="sizing",
            conclusion="amended",
            forecast_amendment=new_terms,
            amendment_reason="new confirming evidence",
            amendment_evidence_ids=["ev-new"],
        )
        out = attach_h6_forecast_lineage(
            state=state,
            ticker="AAPL",
            analyst=_analyst_with_assessment(base),
            summary=summary,
            pm_turn=pm,
        )
        assert out.effective_forecast is not None
        assert out.effective_forecast.source is EffectiveForecastSource.AMENDMENT
        assert out.effective_forecast.terms.base_return == Decimal("0.08")

    def test_invalid_amendment_preserves_base(self) -> None:
        base = _assessment()
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            knowledge_cutoff_at=_TS,
        )
        summary = DeliberationSummary(ticker="AAPL", conclusion="reject", net_stance="neutral")
        pm = DeliberationPmTurn(
            converged=True,
            challenge="probe",
            conclusion="reject",
            forecast_amendment=_terms(base_return=Decimal("0.09")),
            amendment_reason="",  # missing reason → rejected
        )
        out = attach_h6_forecast_lineage(
            state=state,
            ticker="AAPL",
            analyst=_analyst_with_assessment(base),
            summary=summary,
            pm_turn=pm,
        )
        assert out.effective_forecast is not None
        assert out.effective_forecast.source is EffectiveForecastSource.BASE
        assert out.effective_forecast.degradation is ForecastLineageDegradation.AMENDMENT_REJECTED


class TestQuietCarryForecastLineage:
    def test_fingerprint_skip_carries_prior_effective_identity(self) -> None:
        base = _assessment()
        prior_ef = resolve_effective_forecast(base)
        news_hash = news_hash_for_ticker(
            AtlasResearchState(
                run_type="delta",
                run_date=date(2026, 6, 20),
                config=AtlasConfigBundle(watchlist=["AAPL"]),
            ),
            "AAPL",
        )
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            knowledge_cutoff_at=_TS + timedelta(hours=1),
            prior_context=PriorContext(
                prior_analyst_by_ticker={
                    "AAPL": {
                        "date": "2026-06-19",
                        "stance": "hold",
                        "conviction_score": 1,
                        "fingerprint_news_hash": news_hash,
                    }
                },
                prior_deliberation_by_ticker={
                    "AAPL": {
                        "date": "2026-06-19",
                        "net_stance": "neutral",
                        "conviction_delta": 0,
                        "converged": True,
                        "conclusion_excerpt": "prior agreement",
                        "effective_forecast": prior_ef.model_dump(mode="json"),
                        "known_at": prior_ef.known_at.isoformat(),
                    }
                },
            ),
            price_deltas={"AAPL": 0.001},
        )
        state.phase_hermes = PhaseHermesState(
            focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
            asset_analysts={"AAPL": _analyst_with_assessment(base)},
        )
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("skip path must not call LLM"),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["carried"] is True
        assert summary["carry_reason"] == "fingerprint_skip"
        ef = summary["effective_forecast"]
        assert ef is not None
        assert ef["effective_forecast_id"] == str(prior_ef.effective_forecast_id)
        assert ef["content_hash"] == prior_ef.content_hash
        assert str(ef["known_at"]).startswith("2026-06-20")

    def test_llm_failure_preserves_base_with_degradation(self) -> None:
        base = _assessment()
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            knowledge_cutoff_at=_TS,
        )
        state.phase_hermes = PhaseHermesState(
            focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
            asset_analysts={"AAPL": _analyst_with_assessment(base)},
        )
        with patch.object(
            h6_deliberation,
            "run_deliberation_loop",
            side_effect=ValueError("boom"),
        ):
            out = build_h6_from_state().worker.run(with_fanout_ticker(state, "AAPL"))
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carry_reason"] == "llm_failure"
        ef = summary["effective_forecast"]
        assert ef is not None
        assert ef["degradation"] == "llm_failure"
        assert ef["base_forecast_id"] == str(base.forecast_id)
        assert ef["amendment_id"] is None


class FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lt(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        class _R:
            data: list[dict] | None = None

        r = _R()
        r.data = list(self._rows)
        return r


class FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def table(self, _name: str) -> FakeQuery:
        return FakeQuery(self._rows)


class TestPriorDeliberationCutoff:
    def test_cutoff_excludes_future_known_prior(self) -> None:
        base = _assessment()
        prior_ef = resolve_effective_forecast(base)
        future = (_TS + timedelta(hours=5)).isoformat()
        past = (_TS - timedelta(hours=1)).isoformat()
        docs = [
            {
                "date": "2026-06-19",
                "document_key": "deliberation/AAPL",
                "payload": {
                    "net_stance": "bullish",
                    "conviction_delta": 1,
                    "converged": True,
                    "conclusion": "too new",
                    "effective_forecast": {
                        **prior_ef.model_dump(mode="json"),
                        "known_at": future,
                    },
                },
            },
            {
                "date": "2026-06-18",
                "document_key": "deliberation/AAPL",
                "payload": {
                    "net_stance": "neutral",
                    "conviction_delta": 0,
                    "converged": True,
                    "conclusion": "eligible prior",
                    "effective_forecast": {
                        **prior_ef.model_dump(mode="json"),
                        "known_at": past,
                    },
                },
            },
        ]
        client = FakeClient(docs)
        out = load_prior_deliberation_summaries(
            client,  # type: ignore[arg-type]
            date(2026, 6, 20),
            ["AAPL"],
            knowledge_cutoff_at=_TS,
        )
        assert out["AAPL"]["conclusion_excerpt"].startswith("eligible")
        assert out["AAPL"]["effective_forecast"]["known_at"] == past
