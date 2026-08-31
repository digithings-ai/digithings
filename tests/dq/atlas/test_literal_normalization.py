"""Generic ``Literal[...]`` synonym normalization on segment reports (#1741).

#1641 gave ``InstitutionalFlowsReport.flow_direction`` a synonym validator and, in the
same commit, replaced the ``edit merge failed`` ``PhaseError`` with a silent fallback to
full-mode regeneration. The other Literal axes never got a validator — their
``literal_error`` failures did not stop, they stopped being *recorded*, each one paying
for a patch call and then a full regeneration.

These tests are written against the concrete phase models rather than the normalizer's
internals on purpose: the contract is "a plausible LLM synonym must not fail
``model_validate``", not "a particular table has a particular key".
"""

from __future__ import annotations

import inspect
from datetime import date
from types import ModuleType, UnionType
from typing import (
    Any,  # score:allow untyped any — raw pre-validation body shape
    Literal,
    Union,
    get_args,
    get_origin,
)

import pytest
from digiquant.olympus.atlas.phases import (
    phase1_altdata,
    phase2_institutional,
    phase3_macro,
    phase4_assetclass,
    phase5_equities,
    phase7_synthesis,
)
from digiquant.olympus.atlas.phases.phase1_altdata import (
    CtaPositioningReport,
    OptionsDerivativesReport,
    SentimentNewsReport,
)
from digiquant.olympus.atlas.phases.phase2_institutional import InstitutionalFlowsReport
from digiquant.olympus.atlas.phases.phase3_macro import MacroRegimeReport
from digiquant.olympus.atlas.phases.phase4_assetclass import (
    BondsReport,
    CryptoReport,
    ForexReport,
    InternationalReport,
)
from digiquant.olympus.atlas.phases.phase5_equities import EquityOverviewReport, SectorReport
from digiquant.olympus.atlas.segments import SegmentReport
from pydantic import BaseModel, ValidationError

pytestmark = pytest.mark.unit

_PHASE_MODULES: tuple[ModuleType, ...] = (
    phase1_altdata,
    phase2_institutional,
    phase3_macro,
    phase4_assetclass,
    phase5_equities,
    phase7_synthesis,
)

_NOT_A_MEMBER = "definitely-not-a-literal-member"


def _core(**extra: Any) -> dict[str, Any]:
    return {
        "segment": "test-segment",
        "date": "2026-07-31",
        "bias": "neutral",
        "headline": "h",
        **extra,
    }


def _literal_members(annotation: object) -> tuple[frozenset[str], bool] | None:
    """``(members, optional)`` for a string ``Literal`` / ``Literal | None`` annotation."""

    def members_of(ann: object) -> frozenset[str] | None:
        if get_origin(ann) is not Literal:
            return None
        args = get_args(ann)
        if not args or not all(isinstance(a, str) for a in args):
            return None
        return frozenset(args)

    direct = members_of(annotation)
    if direct is not None:
        return direct, False
    if get_origin(annotation) not in (Union, UnionType):
        return None
    found: set[str] = set()
    optional = False
    for arg in get_args(annotation):
        if arg is type(None):
            optional = True
            continue
        inner = members_of(arg)
        if inner is None:
            return None
        found.update(inner)
    return (frozenset(found), optional) if found else None


def _minimal_body(model: type[BaseModel]) -> dict[str, Any]:
    """Smallest body that validates for *model*, with required Literals set to a member."""
    body = _core()
    for name, field in model.model_fields.items():
        if not field.is_required() or name in body:
            continue
        spec = _literal_members(field.annotation)
        if spec is not None:
            body[name] = sorted(spec[0])[0]
        elif field.annotation is str:
            body[name] = "x"
        elif field.annotation is date:
            body[name] = "2026-07-31"
        else:  # pragma: no cover — a new required non-str field would need a case here
            raise AssertionError(f"no fixture value for required {model.__name__}.{name}")
    return body


def _segment_report_models() -> list[type[SegmentReport]]:
    seen: dict[str, type[SegmentReport]] = {}
    for module in _PHASE_MODULES:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, SegmentReport) and obj is not SegmentReport:
                seen[f"{obj.__module__}.{obj.__name__}"] = obj
    return [seen[key] for key in sorted(seen)]


def _literal_field_cases() -> list[tuple[type[SegmentReport], str, bool]]:
    cases: list[tuple[type[SegmentReport], str, bool]] = []
    for model in _segment_report_models():
        for name, field in model.model_fields.items():
            spec = _literal_members(field.annotation)
            if spec is not None:
                cases.append((model, name, spec[1]))
    return cases


_LITERAL_FIELD_CASES = _literal_field_cases()


class TestObservedProductionOffenders:
    """Every ``literal_error`` seen in the DB history or the 07-30/07-31 run logs."""

    @pytest.mark.parametrize(
        ("model", "field", "raw", "expected"),
        [
            # run 30636503352 (07-31) and 30548840632 (07-30), all silently regenerated.
            (SentimentNewsReport, "retail_sentiment_stance", "neutral", "mixed"),
            (CryptoReport, "funding_rate_bias", "neutral", "balanced"),
            (CtaPositioningReport, "cta_flow_bias", "buying", "adding"),
            (SectorReport, "conviction", "moderate", "medium"),
            # atlas_run_diagnostics 07-20 (sector-energy + sector-materials).
            (SectorReport, "relative_strength_vs_spy", "neutral", "inline"),
            # atlas_run_diagnostics 06-30 / 07-03 / 07-04 — a REQUIRED axis.
            (MacroRegimeReport, "risk_appetite", "neutral", "mixed"),
            # atlas_run_diagnostics 07-07 (run 28873813620).
            (InternationalReport, "europe_stance", "cautious", "neutral"),
            # Same 'neutral' synonym landing on four more axes that exclude it.
            (BondsReport, "yield_curve_shape", "neutral", "normal"),
            (ForexReport, "dxy_trend", "neutral", "range"),
            (OptionsDerivativesReport, "vix_term_structure", "neutral", "flat"),
            (EquityOverviewReport, "factor_leader", "neutral", "mixed"),
            (SentimentNewsReport, "retail_sentiment_stance", "fear", "risk_off"),
            (SentimentNewsReport, "retail_sentiment_stance", "bearish", "risk_off"),
            (SentimentNewsReport, "retail_sentiment_stance", "downbeat", "risk_off"),
        ],
    )
    def test_synonym_resolves_onto_the_fields_own_literal(
        self,
        model: type[SegmentReport],
        field: str,
        raw: str,
        expected: str,
    ) -> None:
        report = model.model_validate({**_minimal_body(model), field: raw})
        assert getattr(report, field) == expected

    @pytest.mark.parametrize("raw", ["Neutral", " neutral ", "RISK-ON", "risk on"])
    def test_case_space_and_hyphen_variants_resolve(self, raw: str) -> None:
        body = {**_minimal_body(SentimentNewsReport), "retail_sentiment_stance": raw}
        stance = SentimentNewsReport.model_validate(body).retail_sentiment_stance
        assert stance == ("mixed" if raw.strip().lower() == "neutral" else "risk_on")


class TestFailSoftTiers:
    def test_unmappable_optional_axis_degrades_to_none(self) -> None:
        """'improving' breadth is a trend, not a state — no member is honest, so None.

        Before #1741 this raised and triggered an invisible full-mode regeneration.
        """
        body = {**_minimal_body(EquityOverviewReport), "market_breadth": "improving"}
        assert EquityOverviewReport.model_validate(body).market_breadth is None

    def test_unmappable_required_axis_is_still_rejected(self) -> None:
        """``growth`` is expanding|slowing|contracting — no non-directional member.

        Mapping 'stable' onto any of them would invent a macro call that Phases 4–7 then
        consume as fact, so the honest outcome is a loud failure. This is the one place
        #1741 deliberately does not fail soft.
        """
        body = {**_minimal_body(MacroRegimeReport), "growth": "stable"}
        with pytest.raises(ValidationError, match="growth"):
            MacroRegimeReport.model_validate(body)

    @pytest.mark.parametrize(
        ("model", "field", "optional"),
        [(m, f, o) for m, f, o in _LITERAL_FIELD_CASES],
        ids=[f"{m.__name__}.{f}" for m, f, _ in _LITERAL_FIELD_CASES],
    )
    def test_every_literal_axis_is_guarded(
        self,
        model: type[SegmentReport],
        field: str,
        optional: bool,
    ) -> None:
        """Coverage gate over all Literal axes, so a new unguarded one cannot be added.

        Optional axis + unrecognized value ⇒ None, never a ``ValidationError``. Required
        axis ⇒ rejected, documented as intentional.
        """
        body = {**_minimal_body(model), field: _NOT_A_MEMBER}
        if optional:
            assert getattr(model.model_validate(body), field) is None
        else:
            with pytest.raises(ValidationError, match=field):
                model.model_validate(body)


class TestDedicatedValidatorsKeepOwnership:
    """A field with its own ``mode='before'`` validator must not be pre-empted."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("net inflows", "inflow"), ("net outflow", "outflow"), ("positive", "inflow")],
    )
    def test_flow_direction_multiword_synonyms_survive(self, raw: str, expected: str) -> None:
        body = {**_minimal_body(InstitutionalFlowsReport), "flow_direction": raw}
        assert InstitutionalFlowsReport.model_validate(body).flow_direction == expected

    def test_bias_synonyms_survive(self) -> None:
        body = {**_minimal_body(SectorReport), "bias": "very_positive"}
        assert SectorReport.model_validate(body).bias == "strong_bullish"

    def test_hawkish_bias_maps_to_bearish(self) -> None:
        body = {**_minimal_body(SectorReport), "bias": "hawkish"}
        assert SectorReport.model_validate(body).bias == "bearish"

    def test_dovish_bias_maps_to_bullish(self) -> None:
        body = {**_minimal_body(SectorReport), "bias": "dovish"}
        assert SectorReport.model_validate(body).bias == "bullish"

    def test_tightening_bias_maps_to_bearish(self) -> None:
        body = {**_minimal_body(SectorReport), "bias": "tightening"}
        assert SectorReport.model_validate(body).bias == "bearish"

    def test_hawkish_policy_still_maps_to_tightening(self) -> None:
        body = {**_minimal_body(MacroRegimeReport), "policy": "hawkish"}
        assert MacroRegimeReport.model_validate(body).policy == "tightening"

    def test_unknown_bias_is_still_rejected(self) -> None:
        body = {**_minimal_body(SectorReport), "bias": _NOT_A_MEMBER}
        with pytest.raises(ValidationError, match="bias"):
            SectorReport.model_validate(body)


class TestNoIncidentalChanges:
    def test_already_canonical_values_are_untouched(self) -> None:
        body = {
            **_minimal_body(SectorReport),
            "relative_strength_vs_spy": "outperforming",
            "conviction": "high",
        }
        report = SectorReport.model_validate(body)
        assert report.relative_strength_vs_spy == "outperforming"
        assert report.conviction == "high"

    def test_non_mapping_input_passes_through(self) -> None:
        original = MacroRegimeReport.model_validate(_minimal_body(MacroRegimeReport))
        assert MacroRegimeReport.model_validate(original) == original

    def test_non_string_value_is_not_coerced(self) -> None:
        body = {**_minimal_body(SectorReport), "conviction": 7}
        with pytest.raises(ValidationError, match="conviction"):
            SectorReport.model_validate(body)
