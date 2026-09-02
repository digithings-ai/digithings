"""Dated quantitative findings (#1750).

The `sector-healthcare` document published for 2026-07-31 stated "XLV is at $162.16, up 5.46%
from its 50-day SMA" — the same block on seven publication dates, with the 200DMA figure frozen
across eleven since the 07-19 baseline. A reader had no cue that the number was old, because
`Finding.summary` asked only for "Quantified where possible" and nothing required a data date.

`Finding.as_of` plus `QUANTITATIVE_FINDING_RULES` make the claim auditable. What they do NOT do
is make it true: the verification established that $162.16 was never an XLV close or intraday
print on 2026-07-23 when it first appeared, and the payload attributed it to
`price_technicals:XLV`. Dating a fabricated number does not ground it — that needs a
numeric-fidelity validator, which is deliberately out of scope.

**These tests are honest about their own limits.** They assert the field exists, coerces safely,
never costs a merge, and that the instruction reaches the model. Nothing here can assert the
model actually fills it in truthfully — that is LLM behaviour, and a green suite must not be read
as "numbers are grounded now".
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.segments import Finding, SegmentReport
from digiquant.research.skills import (
    QUANTITATIVE_FINDING_RULES,
    load_skill,
    load_skill_edit,
)

pytestmark = pytest.mark.unit


class TestItStaysOptional:
    """The single most expensive way to get this wrong.

    `merge_document_patch` re-validates the *materialized* body — derived from the PRIOR
    published row — through `spec.output_model.model_validate`. All ~660 existing `documents`
    rows carry findings with no `as_of`, so a required field would raise ValidationError on every
    edit-mode merge, and #1641 converts that into a full regeneration. Mandatory would have
    quietly multiplied the run's LLM bill.
    """

    def test_a_finding_without_as_of_validates(self) -> None:
        f = Finding(label="Breakout", summary="XLV broke its 200-DMA.")
        assert f.as_of is None

    def test_a_pre_existing_published_body_still_validates(self) -> None:
        """Shape taken from a real 2026-07-29 `documents.payload` — no `as_of` anywhere."""
        prior_body = {
            "segment": "sector-healthcare",
            "date": "2026-07-29",
            "bias": "bullish",
            "headline": "Healthcare holds its bid",
            "material_findings": [
                {
                    "label": "XLV vs SMAs",
                    "summary": "XLV is at $162.16, up 5.46% from its 50-day SMA.",
                    "source_ids": ["price_technicals:XLV"],
                },
                {"label": "Biotech leads", "summary": "Sub-sector leadership rotated."},
            ],
            "sources": [{"id": "price_technicals:XLV", "title": "XLV Technicals"}],
            "notes": "",
        }
        report = SegmentReport.model_validate(prior_body)
        assert [f.as_of for f in report.material_findings] == [None, None]


class TestItNeverCostsAMerge:
    """#1740's lesson verbatim: a hard schema constraint on an informational field discarded the
    ENTIRE DocumentPatch over a long `reason`, costing 1-4 segments per run and once the master
    digest. A model writing "Jul 24" must not cost a segment."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-07-24", "2026-07-24"),
            ("Jul 24 2026", "2026-07-24"),
            ("Jul 24, 2026", "2026-07-24"),
            ("24 Jul 2026", "2026-07-24"),
            ("2026/07/24", "2026-07-24"),
            ("07/24/2026", "2026-07-24"),
        ],
    )
    def test_loose_dates_normalize_to_iso(self, raw: str, expected: str) -> None:
        assert Finding(label="l", summary="s", as_of=raw).as_of == expected

    def test_a_date_object_normalizes(self) -> None:
        assert Finding(label="l", summary="s", as_of=date(2026, 7, 24)).as_of == "2026-07-24"

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_becomes_none(self, raw: object) -> None:
        assert Finding(label="l", summary="s", as_of=raw).as_of is None

    def test_an_unparseable_value_is_kept_not_rejected(self) -> None:
        """Disclosure beats silence: "late July" tells a reader more than nothing, and raising
        here would discard a whole patch. Consumers comparing dates should check the ISO shape."""
        assert Finding(label="l", summary="s", as_of="late July").as_of == "late July"

    def test_an_absurd_value_is_capped_not_rejected(self) -> None:
        f = Finding(label="l", summary="s", as_of="x" * 500)
        assert f.as_of is not None
        assert len(f.as_of) == 32

    @pytest.mark.parametrize("raw", [12345, 3.5, [], {}, True])
    def test_a_non_string_non_date_degrades_to_none(self, raw: object) -> None:
        assert Finding(label="l", summary="s", as_of=raw).as_of is None


class TestTheInstructionReachesTheModel:
    """Appended at the single load chokepoint, not copied into 20 SKILL.md files — the same
    anti-drift reasoning as EDIT_SCHEMA_CONSTRAINTS (#1740)."""

    def test_a_full_skill_carries_the_rules(self) -> None:
        """The FULL path matters most here: the frozen XLV block came from a baseline run, which
        forces `resolve_edit_mode → full` and never calls `merge_document_patch`."""
        assert QUANTITATIVE_FINDING_RULES in load_skill("sector-research")

    def test_an_edit_skill_carries_the_rules(self) -> None:
        assert QUANTITATIVE_FINDING_RULES in load_skill_edit("sector-research")

    def test_the_edit_skill_still_carries_the_schema_constraints(self) -> None:
        """Appending one shared block must not displace the other."""
        from digiquant.research.skills import EDIT_SCHEMA_CONSTRAINTS

        body = load_skill_edit("sector-research")
        assert EDIT_SCHEMA_CONSTRAINTS in body
        assert QUANTITATIVE_FINDING_RULES in body

    @pytest.mark.parametrize("slug", ["macro", "equity", "sector-research", "bonds", "crypto"])
    def test_every_sampled_skill_gets_it(self, slug: str) -> None:
        assert QUANTITATIVE_FINDING_RULES in load_skill(slug)

    def test_the_rules_tell_the_model_to_date_numbers_inline(self) -> None:
        """Memo body is markdown; dates live in the prose, not a Finding.as_of slot."""
        lowered = QUANTITATIVE_FINDING_RULES.lower()
        assert "markdown body" in lowered
        assert "not the date of this run" in lowered or "do not write" in lowered
        assert "carry a number forward" in lowered


class TestWhatThisDoesNotClaim:
    def test_the_schema_cannot_detect_a_fabricated_number(self) -> None:
        """Recorded as an executable note, not a wish. $162.16 dated 2026-07-23 validates
        perfectly — and that figure was outside XLV's actual 07-23 range of 159.32–161.61.
        Grounding needs a numeric-fidelity validator cross-checking prose against
        `price_technicals`; nothing in this change does that.
        """
        fabricated = Finding(
            label="XLV vs SMAs",
            summary="XLV is at $162.16, up 5.46% from its 50-day SMA.",
            source_ids=["price_technicals:XLV"],
            as_of="2026-07-23",
        )
        assert fabricated.as_of == "2026-07-23"  # well-formed, and wrong
