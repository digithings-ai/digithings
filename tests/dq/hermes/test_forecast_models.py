"""Typed forecast contract models (#2637 / WP4.2).

Red coverage from phase-1 Task 4.2: probability sums, ordered scenarios,
finite numbers, horizon/half-life sessions, evidence IDs, immutability,
extra-field forbid, deterministic UUID5 identity, and same-ID/different-hash
conflict. Legacy ``conviction_score`` / ``price_targets`` never synthesize terms.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.hermes.models.analyst import AnalystPayload, EvidenceAssessment
from digiquant.olympus.hermes.models.forecast import (
    EffectiveForecastSource,
    ForecastAmendment,
    ForecastAssessment,
    ForecastLineageDegradation,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    effective_forecast_id,
    forecast_amendment_id,
    forecast_assessment_id,
    forecast_terms_content_hash,
    materialize_forecast_amendment,
    resolve_effective_forecast,
    try_resolve_effective_forecast,
)
from pydantic import ValidationError

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
        evidence_ids=("ev-1", "ev-2"),
        counter_evidence_ids=("cev-1",),
        assumptions=("rates stay within 50bp",),
        invalidation_rules=("close below thesis stop",),
    )
    fields.update(overrides)
    return ForecastTerms(**fields)


def _assessment(**overrides: object) -> ForecastAssessment:
    terms = overrides.pop("terms", None)
    if terms is None:
        terms = _terms()
    content_hash = forecast_terms_content_hash(terms)
    fields: dict[str, object] = dict(
        ticker="AAPL",
        terms=terms,
        source_run_id="run-abc",
        provider_invocation_id="inv-001",
        prompt_version="asset-analyst@v3",
        artifact_version="h5-full@1",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.OBSERVED,
            price=Decimal("190.50"),
            observed_at=_TS - timedelta(hours=1),
        ),
        effective_at=_TS,
        known_at=_TS,
        content_hash=content_hash,
        forecast_id=forecast_assessment_id(
            ticker="AAPL",
            source_run_id="run-abc",
            content_hash=content_hash,
        ),
    )
    fields.update(overrides)
    return ForecastAssessment(**fields)


class TestForecastTermsValidation:
    def test_valid_terms_accept_ordered_scenarios_and_unit_probabilities(self) -> None:
        terms = _terms()
        assert terms.bear_return < terms.base_return < terms.bull_return
        assert terms.bear_probability + terms.base_probability + terms.bull_probability == Decimal(
            "1"
        )

    def test_probability_must_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match="probabilities"):
            _terms(bull_probability=Decimal("0.30"))

    def test_probabilities_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _terms(
                bear_probability=Decimal("-0.10"),
                base_probability=Decimal("0.60"),
                bull_probability=Decimal("0.50"),
            )

    def test_returns_must_be_ordered_bear_base_bull(self) -> None:
        with pytest.raises(ValidationError, match="ordered"):
            _terms(
                bear_return=Decimal("0.10"),
                base_return=Decimal("0.04"),
                bull_return=Decimal("0.18"),
            )

    def test_rejects_non_finite_returns(self) -> None:
        with pytest.raises(ValidationError):
            _terms(base_return=Decimal("Infinity"))

    def test_horizon_and_half_life_must_be_positive_sessions(self) -> None:
        with pytest.raises(ValidationError):
            _terms(horizon_sessions=0)
        with pytest.raises(ValidationError):
            _terms(half_life_sessions=-1)

    def test_evidence_ids_must_be_non_empty_strings(self) -> None:
        with pytest.raises(ValidationError):
            _terms(evidence_ids=("ev-1", ""))
        with pytest.raises(ValidationError):
            _terms(counter_evidence_ids=("  ",))

    def test_terms_are_immutable_and_forbid_extra_fields(self) -> None:
        terms = _terms()
        with pytest.raises(ValidationError):
            terms.model_validate({**terms.model_dump(), "conviction_score": 3})
        with pytest.raises((TypeError, ValidationError)):
            terms.bear_return = Decimal("-0.01")  # type: ignore[misc]


class TestForecastAssessmentIdentity:
    def test_uuid5_identity_is_deterministic(self) -> None:
        a = _assessment()
        b = _assessment()
        assert a.forecast_id == b.forecast_id
        assert isinstance(a.forecast_id, UUID)
        assert a.forecast_id.version == 5

    def test_same_id_different_hash_is_rejected(self) -> None:
        a = _assessment()
        other_terms = _terms(base_return=Decimal("0.05"))
        other_hash = forecast_terms_content_hash(other_terms)
        with pytest.raises(ValidationError, match="content_hash|forecast_id"):
            ForecastAssessment(
                forecast_id=a.forecast_id,
                ticker="AAPL",
                terms=other_terms,
                source_run_id="run-abc",
                provider_invocation_id="inv-001",
                prompt_version="asset-analyst@v3",
                artifact_version="h5-full@1",
                price_anchor=PriceAnchor(
                    status=PriceAnchorStatus.OBSERVED,
                    price=Decimal("190.50"),
                    observed_at=_TS - timedelta(hours=1),
                ),
                effective_at=_TS,
                known_at=_TS,
                content_hash=other_hash,
            )

    def test_content_hash_must_match_terms(self) -> None:
        terms = _terms()
        with pytest.raises(ValidationError, match="content_hash"):
            ForecastAssessment(
                forecast_id=uuid4(),
                ticker="AAPL",
                terms=terms,
                source_run_id="run-abc",
                provider_invocation_id="inv-001",
                prompt_version="asset-analyst@v3",
                artifact_version="h5-full@1",
                price_anchor=PriceAnchor(
                    status=PriceAnchorStatus.UNAVAILABLE,
                    unavailable_reason="price_feed_missing",
                ),
                effective_at=_TS,
                known_at=_TS,
                content_hash="deadbeef",
            )

    def test_naive_timestamps_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _assessment(effective_at=datetime(2026, 8, 25, 14, 30))  # noqa: DTZ001

    def test_price_anchor_xor_unavailable(self) -> None:
        with pytest.raises(ValidationError, match="price_anchor"):
            PriceAnchor(
                status=PriceAnchorStatus.OBSERVED,
                price=None,
                observed_at=None,
            )
        unavailable = PriceAnchor(
            status=PriceAnchorStatus.UNAVAILABLE,
            unavailable_reason="session_close_not_observed",
        )
        assert unavailable.price is None
        assert unavailable.observed_at is None

    def test_assessment_forbids_extra_fields_and_is_frozen(self) -> None:
        assessment = _assessment()
        with pytest.raises(ValidationError):
            ForecastAssessment.model_validate(
                {**assessment.model_dump(mode="json"), "legacy_conviction": 2}
            )
        with pytest.raises((TypeError, ValidationError)):
            assessment.ticker = "MSFT"  # type: ignore[misc]


class TestLegacyAnalystDoesNotDeriveForecast:
    def test_conviction_and_price_targets_do_not_create_forecast_terms(self) -> None:
        payload = AnalystPayload(
            ticker="AAPL",
            conviction_score=4,
            stance="buy",
            evidence=EvidenceAssessment(
                independent_confirming_signals=4,
                contradicting_signals=0,
                catalyst_within_horizon=True,
                trend_alignment="with",
                evidence_quality="high",
            ),
            price_targets={"base": 200, "bull": 240},
        )
        assert payload.forecast is None
        assert not hasattr(payload, "forecast_terms")
        # Legacy fields remain, but WP4.2 never maps them into ForecastTerms.
        assert payload.conviction_score == 4
        assert payload.price_targets == {"base": 200, "bull": 240}

    def test_optional_typed_forecast_coexists_without_deriving_from_legacy(self) -> None:
        terms = _terms()
        payload = AnalystPayload(
            ticker="AAPL",
            conviction_score=1,
            stance="hold",
            price_targets={"base": 999},
            forecast=terms,
        )
        assert payload.forecast is terms
        assert payload.forecast.base_return == Decimal("0.04")
        assert payload.price_targets == {"base": 999}


class TestForecastAmendmentAndEffective:
    def test_accepted_complete_amendment_selects_new_terms(self) -> None:
        base = _assessment()
        new_terms = _terms(base_return=Decimal("0.06"), bull_return=Decimal("0.20"))
        amendment = materialize_forecast_amendment(
            base=base,
            terms=new_terms,
            reason="new catalyst within horizon",
            source_run_id="run-h6",
            provider_invocation_id="inv-h6",
            effective_at=_TS,
            known_at=_TS,
            evidence_ids=("ev-new",),
        )
        effective = resolve_effective_forecast(base, amendment)
        assert effective.source is EffectiveForecastSource.AMENDMENT
        assert effective.amendment_id == amendment.amendment_id
        assert effective.base_forecast_id == base.forecast_id
        assert effective.terms.base_return == Decimal("0.06")
        assert effective.degradation is ForecastLineageDegradation.NONE

    def test_unchanged_base_when_no_amendment(self) -> None:
        base = _assessment()
        effective = resolve_effective_forecast(base)
        assert effective.source is EffectiveForecastSource.BASE
        assert effective.amendment_id is None
        assert effective.content_hash == base.content_hash
        assert effective.effective_forecast_id == effective_forecast_id(
            base_forecast_id=base.forecast_id,
            amendment_id=None,
            content_hash=base.content_hash,
        )

    def test_invalid_amendment_preserves_base_via_try_resolve(self) -> None:
        base = _assessment()
        other_terms = _terms(base_return=Decimal("0.07"))
        other_hash = forecast_terms_content_hash(other_terms)
        other = _assessment(
            ticker="MSFT",
            source_run_id="run-other",
            terms=other_terms,
            content_hash=other_hash,
            forecast_id=forecast_assessment_id(
                ticker="MSFT",
                source_run_id="run-other",
                content_hash=other_hash,
            ),
        )
        bad_terms = _terms(base_return=Decimal("0.07"))
        content_hash = forecast_terms_content_hash(bad_terms)
        mismatched = ForecastAmendment(
            amendment_id=forecast_amendment_id(
                base_forecast_id=other.forecast_id,
                source_run_id="run-h6",
                content_hash=content_hash,
            ),
            base_forecast_id=other.forecast_id,
            ticker="MSFT",
            terms=bad_terms,
            reason="wrong base",
            source_run_id="run-h6",
            provider_invocation_id="inv",
            effective_at=_TS,
            known_at=_TS,
            content_hash=content_hash,
        )
        effective = try_resolve_effective_forecast(base, mismatched)
        assert effective is not None
        assert effective.source is EffectiveForecastSource.BASE
        assert effective.degradation is ForecastLineageDegradation.AMENDMENT_REJECTED
        assert effective.content_hash == base.content_hash

    def test_amendment_identity_is_deterministic(self) -> None:
        base = _assessment()
        terms = _terms(base_return=Decimal("0.055"))
        a = materialize_forecast_amendment(
            base=base,
            terms=terms,
            reason="evidence update",
            source_run_id="run-h6",
            provider_invocation_id="inv",
            effective_at=_TS,
            known_at=_TS,
        )
        b = materialize_forecast_amendment(
            base=base,
            terms=terms,
            reason="evidence update",
            source_run_id="run-h6",
            provider_invocation_id="inv",
            effective_at=_TS,
            known_at=_TS,
        )
        assert a.amendment_id == b.amendment_id
