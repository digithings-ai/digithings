"""H6 amendment envelope coerce (house GHA 33426508863 GLD/SLV/IAU)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from digiquant.research.state import AtlasResearchState, PhaseHermesState
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    fill_forecast_tenor_from_base,
    unwrap_forecast_terms_payload,
)
from digiquant.portfolio.phases.h6_deliberation import _resolve_from_debate
from digiquant.portfolio.phases.portfolio_common import materialize_forecast_assessment
from pydantic import ValidationError

from tests.dq.hermes.phase1_e2e_fixtures import sample_forecast_terms_dict

pytestmark = pytest.mark.unit

_CUTOFF = datetime(2026, 8, 31, 18, 43, tzinfo=UTC)


def _analyst() -> tuple[dict[str, object], AtlasResearchState]:
    terms = ForecastTerms.model_validate(sample_forecast_terms_dict())
    assessment = materialize_forecast_assessment(
        ticker="GLD",
        terms=terms,
        source_run_id="run-h6-coerce",
        provider_invocation_id="inv-h6",
        prompt_version="pv-test",
        artifact_version="av-test",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.UNAVAILABLE,
            unavailable_reason="test",
        ),
        effective_at=_CUTOFF,
        known_at=_CUTOFF,
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 31),
        knowledge_cutoff_at=_CUTOFF,
        phase_hermes=PhaseHermesState(),
    )
    analyst = {
        "ticker": "GLD",
        "forecast_assessment": assessment.model_dump(mode="json"),
        "forecast": terms.model_dump(mode="json"),
    }
    return analyst, state


def test_gld_missing_tenor_fills_from_base_and_accepts_string_probabilities() -> None:
    analyst, state = _analyst()
    raw = sample_forecast_terms_dict()
    del raw["horizon_sessions"]
    del raw["half_life_sessions"]
    raw["base_probability"] = "0.50"
    raw["bear_probability"] = "0.25"
    raw["bull_probability"] = "0.25"
    raw["evidence_ids"] = ["flows:gold_ETF_inflows"]
    effective, amendment = _resolve_from_debate(
        state=state,
        ticker="GLD",
        analyst=analyst,
        amendment_terms_raw=raw,
        amendment_reason="h6_challenge_revision",
    )
    assert amendment is not None
    assert effective is not None
    assert effective.amendment_outcome is AmendmentOutcome.ACCEPTED
    assert amendment.terms.horizon_sessions == 21
    assert amendment.terms.half_life_sessions == 10
    assert amendment.terms.base_probability == Decimal("0.50")


def test_iau_nested_terms_wrapper_materializes() -> None:
    analyst, state = _analyst()
    effective, amendment = _resolve_from_debate(
        state=state,
        ticker="IAU",
        analyst=analyst,
        amendment_terms_raw={"terms": sample_forecast_terms_dict()},
        amendment_reason="h6_challenge_revision",
    )
    assert amendment is not None
    assert effective is not None
    assert effective.amendment_outcome is AmendmentOutcome.ACCEPTED
    assert amendment.terms.raw_uncertainty.value == "medium"


def test_slv_wrapper_with_top_level_and_nested_terms_materializes() -> None:
    analyst, state = _analyst()
    nested = sample_forecast_terms_dict()
    raw = {
        "counter_evidence_ids": ["sep-fomc"],
        "thesis_valid_probability": "0.40",
        "terms": nested,
    }
    effective, amendment = _resolve_from_debate(
        state=state,
        ticker="SLV",
        analyst=analyst,
        amendment_terms_raw=raw,
        amendment_reason="h6_challenge_revision",
    )
    assert amendment is not None
    assert amendment.terms.thesis_valid_probability == Decimal("0.40")
    assert amendment.terms.counter_evidence_ids == ("sep-fomc",)


def test_missing_economics_are_not_copied_from_base() -> None:
    body = sample_forecast_terms_dict()
    del body["bear_return"]
    base = ForecastTerms.model_validate(sample_forecast_terms_dict())
    filled = fill_forecast_tenor_from_base(body, base)
    assert "bear_return" not in filled
    with pytest.raises(ValidationError):
        ForecastTerms.model_validate(filled)


def test_invalid_probability_sum_still_rejects_after_unwrap() -> None:
    analyst, state = _analyst()
    nested = sample_forecast_terms_dict()
    nested["bull_probability"] = "0.30"
    effective, amendment = _resolve_from_debate(
        state=state,
        ticker="GLD",
        analyst=analyst,
        amendment_terms_raw={"terms": nested},
        amendment_reason="invalid probabilities",
    )
    assert amendment is None
    assert effective is not None
    assert effective.amendment_outcome is AmendmentOutcome.REJECTED


def test_unwrap_skips_when_required_fields_already_present() -> None:
    body = sample_forecast_terms_dict()
    body["terms"] = {"bear_return": "-0.99"}
    out = unwrap_forecast_terms_payload(body)
    assert isinstance(out, dict)
    assert out["bear_return"] == body["bear_return"]
    assert out["terms"]["bear_return"] == "-0.99"
