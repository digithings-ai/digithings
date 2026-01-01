"""#4585 — the five-family evidence sum and its net-preserving legacy repair.

``EvidenceAssessment.independent_confirming_signals`` and ``contradicting_signals``
are two halves of one five-family universe (technicals, fundamentals,
flows/positioning, macro regime, sentiment/news). Each family is itemized once, on
one side or the other, so ``confirming + contradicting <= 5`` holds by construction.
The measured violation was ``analyst/IBIT`` 2026-09-22 (``4 + 4`` — eight families
over five), invisible because the derived conviction is ``max(0, 4 - 4) = 0``.
"""

from __future__ import annotations

import re

import pytest
from digiquant.portfolio.models.analyst import (
    AnalystPayload,
    EvidenceAssessment,
    derive_conviction,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_FAMILY_ERROR = "confirming + contradicting signals must be <= 5"
_FAMILIES = ("technicals", "fundamentals", "flows/positioning", "macro regime", "sentiment/news")


def _evidence(confirming: int, contradicting: int) -> dict[str, object]:
    return {
        "independent_confirming_signals": confirming,
        "contradicting_signals": contradicting,
        "catalyst_within_horizon": True,
        "trend_alignment": "with",
        "evidence_quality": "high",
    }


class TestEvidenceSumIsEnforced:
    def test_impossible_4_4_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=re.escape(_FAMILY_ERROR)):
            EvidenceAssessment(**_evidence(4, 4))

    def test_error_message_names_the_five_families(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            EvidenceAssessment(**_evidence(5, 1))
        message = str(excinfo.value)
        assert _FAMILY_ERROR in message
        for family in _FAMILIES:
            assert family in message

    @pytest.mark.parametrize(
        "confirming,contradicting",
        [(3, 2), (5, 0), (0, 5), (0, 0)],
    )
    def test_valid_pairs_are_accepted(self, confirming: int, contradicting: int) -> None:
        evidence = EvidenceAssessment(**_evidence(confirming, contradicting))
        assert evidence.independent_confirming_signals == confirming
        assert evidence.contradicting_signals == contradicting

    def test_analyst_payload_with_impossible_evidence_is_rejected(self) -> None:
        """The invariant fires through the parent payload, not just the model."""
        with pytest.raises(ValidationError):
            AnalystPayload.model_validate(
                {
                    "ticker": "IBIT",
                    "conviction_score": 0,
                    "stance": "buy",
                    "evidence": _evidence(4, 4),
                }
            )


class TestRepairEvidenceCountsIsNetPreserving:
    @pytest.mark.parametrize(
        ("pair", "expected"),
        [
            ((4, 4), (2, 2)),
            ((3, 3), (2, 2)),
            ((5, 2), (4, 1)),
            ((5, 1), (4, 0)),
            ((2, 5), (1, 4)),
            ((4, 3), (3, 2)),
            ((3, 2), (3, 2)),
            ((0, 0), (0, 0)),
        ],
    )
    def test_worked_examples(self, pair: tuple[int, int], expected: tuple[int, int]) -> None:
        from digiquant.portfolio.models.analyst import repair_evidence_counts

        confirming, contradicting = pair
        repaired = repair_evidence_counts(confirming, contradicting)
        assert repaired == expected
        assert repaired[0] + repaired[1] <= 5
        assert repaired[0] - repaired[1] == confirming - contradicting


class TestRepairLegacyEvidenceCountsBody:
    def test_overcounted_body_is_repaired_without_mutating_the_input(self) -> None:
        from digiquant.portfolio.models.analyst import repair_legacy_evidence_counts

        body = {"ticker": "IBIT", "stance": "buy", "evidence": _evidence(4, 4)}
        repaired = repair_legacy_evidence_counts(body)
        assert repaired["evidence"]["independent_confirming_signals"] == 2
        assert repaired["evidence"]["contradicting_signals"] == 2
        # Shallow copy: the legacy source body is left untouched.
        assert body["evidence"]["independent_confirming_signals"] == 4
        assert body["evidence"]["contradicting_signals"] == 4

    def test_valid_body_is_returned_unchanged(self) -> None:
        from digiquant.portfolio.models.analyst import repair_legacy_evidence_counts

        body = {"ticker": "AAPL", "evidence": _evidence(3, 1)}
        assert repair_legacy_evidence_counts(body)["evidence"] == _evidence(3, 1)

    @pytest.mark.parametrize(
        "body",
        [
            {"ticker": "AAPL"},  # no evidence block (legacy doc)
            {"ticker": "AAPL", "evidence": None},
            {"evidence": {"independent_confirming_signals": 4}},  # missing partner
            {"evidence": {"independent_confirming_signals": "4", "contradicting_signals": "4"}},
        ],
    )
    def test_bodies_without_repairable_counts_are_returned_unchanged(self, body: dict) -> None:
        from digiquant.portfolio.models.analyst import repair_legacy_evidence_counts

        assert repair_legacy_evidence_counts(body) == body


class TestCarriedLegacyBodyRepairsBeforeValidate:
    def test_carry_repairs_and_preserves_derived_conviction(self) -> None:
        from digiquant.portfolio.models.analyst import repair_legacy_evidence_counts

        legacy_body = {
            "ticker": "IBIT",
            "conviction_score": 0,
            "stance": "buy",
            "evidence": _evidence(4, 4),
        }
        # What the skip/carry path does: repair the persisted body, then validate.
        payload = AnalystPayload.model_validate(
            {**repair_legacy_evidence_counts(legacy_body), "ticker": "IBIT"}
        )
        assert payload.evidence is not None
        assert payload.evidence.independent_confirming_signals == 2
        assert payload.evidence.contradicting_signals == 2
        # Net 0 is preserved, so the derived conviction is what the repaired pair implies.
        assert payload.conviction_score == derive_conviction(payload.evidence, "buy") == 0

    def test_carry_without_repair_would_reject_the_row(self) -> None:
        with pytest.raises(ValidationError):
            AnalystPayload.model_validate(
                {
                    "ticker": "IBIT",
                    "conviction_score": 0,
                    "stance": "buy",
                    "evidence": _evidence(4, 4),
                }
            )
