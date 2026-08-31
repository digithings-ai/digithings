"""H6 forecast unwrap, registry reason, and conviction_delta clamp (#3299)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.edit_mode.models import DocumentPatch
from digiquant.olympus.hermes.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
)
from digiquant.olympus.hermes.models.forecast import (
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    forecast_assessment_id,
    forecast_terms_content_hash,
    unwrap_nested_forecast_terms,
)
from digiquant.olympus.hermes.phases.h6_deliberation import _resolve_from_debate
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 29, 20, 0, tzinfo=UTC)
_REGISTRY_REASON_MAX = 2000


def _terms_dict(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "horizon_sessions": 21,
        "half_life_sessions": 10,
        "bear_return": "-0.12",
        "base_return": "0.04",
        "bull_return": "0.18",
        "bear_probability": "0.25",
        "base_probability": "0.50",
        "bull_probability": "0.25",
        "thesis_valid_probability": "0.60",
        "raw_uncertainty": "medium",
        "evidence_ids": ["ev-1"],
        "counter_evidence_ids": [],
        "assumptions": ["rates stay put"],
        "invalidation_rules": ["close below stop"],
    }
    body.update(over)
    return body


def _base_terms() -> ForecastTerms:
    return ForecastTerms.model_validate(_terms_dict())


def _assessment() -> ForecastAssessment:
    terms = _base_terms()
    content_hash = forecast_terms_content_hash(terms)
    return ForecastAssessment(
        ticker="XLB",
        terms=terms,
        source_run_id="run-h6",
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
            ticker="XLB", source_run_id="run-h6", content_hash=content_hash
        ),
    )


class TestUnwrapNestedForecastTerms:
    @pytest.mark.parametrize("wrapper", ["terms", "amendment", "forecast_amendment"])
    def test_unwraps_one_wrapper_level(self, wrapper: str) -> None:
        inner = _terms_dict()
        out = unwrap_nested_forecast_terms({wrapper: inner})
        assert out == inner
        assert ForecastTerms.model_validate(out).horizon_sessions == 21

    def test_copies_horizons_from_h5_base_when_economics_present(self) -> None:
        inner = _terms_dict()
        del inner["horizon_sessions"]
        del inner["half_life_sessions"]
        out = unwrap_nested_forecast_terms({"terms": inner}, base=_base_terms())
        terms = ForecastTerms.model_validate(out)
        assert terms.horizon_sessions == 21
        assert terms.half_life_sessions == 10
        assert terms.base_return == Decimal("0.04")

    def test_rejects_blob_with_no_scenario_returns(self) -> None:
        blob = {"catalyst_within_horizon": "earnings next week", "note": "ASHR"}
        out = unwrap_nested_forecast_terms(blob, base=_base_terms())
        with pytest.raises(ValidationError):
            ForecastTerms.model_validate(out)


class TestH6RegistryReason:
    def test_persists_short_code_never_conclusion(self) -> None:
        base = _assessment()
        state = AtlasResearchState(
            run_type="delta",
            run_date=_TS.date(),
            knowledge_cutoff_at=_TS,
            config=AtlasConfigBundle(watchlist=["XLB"]),
        )
        long_conclusion = "PM note. " * 300
        assert len(long_conclusion) > _REGISTRY_REASON_MAX
        _effective, amendment = _resolve_from_debate(
            state=state,
            ticker="XLB",
            analyst={"forecast_assessment": base.model_dump(mode="json")},
            amendment_terms_raw={"terms": _terms_dict(base_return="0.05")},
            amendment_reason="h6_challenge_revision",
        )
        assert amendment is not None
        assert amendment.reason == "h6_challenge_revision"
        assert 1 <= len(amendment.reason) <= _REGISTRY_REASON_MAX
        assert amendment.reason != long_conclusion


class TestConvictionDeltaClamp:
    @pytest.mark.parametrize(
        "model",
        [DeliberationAnalystTurn, DeliberationPmTurn, DeliberationSummary],
    )
    def test_clamps_minus_three_to_minus_two(self, model: type[object]) -> None:
        kwargs: dict[str, object] = {"conviction_delta": -3}
        if model is DeliberationSummary:
            kwargs["ticker"] = "EWU"
        out = model.model_validate(kwargs)  # type: ignore[attr-defined]
        assert out.conviction_delta == -2

    def test_clamps_above_two(self) -> None:
        assert DeliberationAnalystTurn.model_validate({"conviction_delta": 5}).conviction_delta == 2


class TestDocumentPatchOpFilter:
    def _body(self, ops: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "doc_type": "document_delta",
            "date": "2026-08-29",
            "prior_date": "2026-08-28",
            "target_document_key": "macro",
            "status": "updated",
            "ops": ops,
        }

    def test_drops_decision_log_rows_keeps_real_ops(self) -> None:
        patch = DocumentPatch.model_validate(
            self._body(
                [
                    {"role": "pm", "message": "challenge the book", "round": 1},
                    {"op": "set", "path": "/headline", "value": "new", "reason": "ok"},
                    {"note": "not a patch"},
                ]
            )
        )
        assert len(patch.ops) == 1
        assert patch.ops[0].op == "set"
        assert patch.ops[0].path == "/headline"

    def test_all_junk_ops_leave_empty_patch(self) -> None:
        patch = DocumentPatch.model_validate(
            self._body([{"role": "analyst", "message": "transcript row"}])
        )
        assert patch.ops == []
