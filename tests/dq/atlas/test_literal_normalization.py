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
from digiquant.olympus.atlas.phases.phase1_altdata import SentimentNewsReport
from digiquant.olympus.atlas.phases.phase3_macro import MacroRegimeReport
from digiquant.olympus.atlas.phases.phase5_equities import SectorReport
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
        "body": "# test\n\nmemo",
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


def _segment_report_models() -> list[type[BaseModel]]:
    from digiquant.olympus.atlas.segments import ResearchMemo, SegmentReport

    seen: dict[str, type[BaseModel]] = {}
    for module in _PHASE_MODULES:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, (ResearchMemo, SegmentReport)):
                continue
            if obj in (ResearchMemo, SegmentReport):
                continue
            seen[f"{obj.__module__}.{obj.__name__}"] = obj
    return [seen[key] for key in sorted(seen)]


def _literal_field_cases() -> list[tuple[type[BaseModel], str, bool]]:
    cases: list[tuple[type[BaseModel], str, bool]] = []
    for model in _segment_report_models():
        for name, field in model.model_fields.items():
            spec = _literal_members(field.annotation)
            if spec is not None:
                cases.append((model, name, spec[1]))
    return cases


_LITERAL_FIELD_CASES = _literal_field_cases()


class TestObservedProductionOffenders:
    """Synonyms that used to hard-fail research envelopes now land on internal_bias / macro chips."""

    @pytest.mark.parametrize(
        ("model", "field", "raw", "expected"),
        [
            (MacroRegimeReport, "risk_appetite", "neutral", "mixed"),
            (MacroRegimeReport, "growth", "growing", "expanding"),
            (SentimentNewsReport, "internal_bias", "cautious", "neutral"),
            (SentimentNewsReport, "internal_bias", "positive", "bullish"),
            (SectorReport, "internal_bias", "very_positive", "strong_bullish"),
        ],
    )
    def test_synonym_resolves_onto_the_fields_own_literal(
        self,
        model: type[BaseModel],
        field: str,
        raw: str,
        expected: str,
    ) -> None:
        report = model.model_validate({**_minimal_body(model), field: raw})
        assert getattr(report, field) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Neutral", "neutral"),
            (" cautious ", "neutral"),
            ("RISK-ON", "bullish"),
            ("risk on", "bullish"),
        ],
    )
    def test_case_space_and_hyphen_variants_resolve(self, raw: str, expected: str) -> None:
        body = {**_minimal_body(SentimentNewsReport), "internal_bias": raw}
        assert SentimentNewsReport.model_validate(body).internal_bias == expected


class TestFailSoftTiers:
    def test_unmappable_optional_axis_degrades_to_none(self) -> None:
        """'stable' growth is not expanding|slowing|contracting — optional chip → None."""
        body = {**_minimal_body(MacroRegimeReport), "growth": "stable"}
        assert MacroRegimeReport.model_validate(body).growth is None

    def test_unmappable_required_axis_is_still_rejected(self) -> None:
        """SegmentReport.bias stays required; digest no longer has a required bias Literal."""
        body = {**_minimal_body(SegmentReport), "bias": "stable"}
        with pytest.raises(ValidationError, match="bias"):
            SegmentReport.model_validate(body)
        from digiquant.olympus.atlas.phases.phase7_synthesis import DigestSnapshot

        DigestSnapshot.model_validate(
            {**_minimal_body(DigestSnapshot), "bias": "stable", "body": "# Daily Digest\n"}
        )

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

    def test_internal_bias_synonyms_survive(self) -> None:
        body = {**_minimal_body(SectorReport), "internal_bias": "very_positive"}
        assert SectorReport.model_validate(body).internal_bias == "strong_bullish"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("cautious", "neutral"),
            (" Cautious ", "neutral"),
            ("risk_on", "bullish"),
            ("RISK-ON", "bullish"),
        ],
    )
    def test_internal_bias_consults_generic_synonym_table(self, raw: str, expected: str) -> None:
        body = {**_minimal_body(SentimentNewsReport), "internal_bias": raw}
        assert SentimentNewsReport.model_validate(body).internal_bias == expected

    def test_unknown_internal_bias_degrades_to_none(self) -> None:
        body = {**_minimal_body(SectorReport), "internal_bias": _NOT_A_MEMBER}
        assert SectorReport.model_validate(body).internal_bias is None


class TestNoIncidentalChanges:
    def test_already_canonical_values_are_untouched(self) -> None:
        body = {
            **_minimal_body(MacroRegimeReport),
            "growth": "expanding",
            "risk_appetite": "risk_on",
        }
        report = MacroRegimeReport.model_validate(body)
        assert report.growth == "expanding"
        assert report.risk_appetite == "risk_on"

    def test_non_mapping_input_passes_through(self) -> None:
        original = MacroRegimeReport.model_validate(_minimal_body(MacroRegimeReport))
        assert MacroRegimeReport.model_validate(original) == original

    def test_non_string_value_is_not_coerced(self) -> None:
        body = {**_minimal_body(MacroRegimeReport), "growth": 7}
        with pytest.raises(ValidationError, match="growth"):
            MacroRegimeReport.model_validate(body)
