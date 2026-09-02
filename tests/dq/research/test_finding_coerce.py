"""Finding/Source LLM-shape coercion (house GHA 33426508863 sector-real-estate).

Attempt 1 failed ``material_findings.*.summary`` Field required on dicts that
had ``as_of`` plus a long prose field that was not named ``summary``. Attempt 2
failed ``model_type`` because Gemini emitted each Finding/Source as a JSON
string wrapping ``completionState`` / ``type: Object``. Carrying the sector
baseline is the expensive outcome; these tests pin that a usable body validates.
"""

from __future__ import annotations

import json

import pytest
from digiquant.olympus.atlas.segments import SegmentReport
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _sector(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "segment": "sector-real-estate",
        "date": "2026-08-31",
        "bias": "neutral",
        "headline": "XLRE mixed",
    }
    body.update(over)
    return body


class TestSummaryAliases:
    def test_text_field_fills_summary(self) -> None:
        report = SegmentReport.model_validate(
            _sector(
                material_findings=[
                    {
                        "label": "XLRE range",
                        "text": "XLRE traded between $38 and $45.36 all week.",
                        "as_of": "2026-08-28",
                    }
                ]
            )
        )
        assert report.material_findings[0].summary.startswith("XLRE traded")

    def test_as_of_plus_unlabeled_prose_fills_summary_and_label(self) -> None:
        """Production attempt 1: pydantic showed as_of plus a long string, no summary."""
        prose = "XLRE traded between $38 and $45.36 all week."
        report = SegmentReport.model_validate(
            _sector(material_findings=[{"as_of": "2026-08-28", "detail": prose}])
        )
        finding = report.material_findings[0]
        assert finding.summary == prose
        assert finding.label == "XLRE traded between $38 and $45.36 all week"
        assert finding.as_of == "2026-08-28"

    def test_as_of_only_still_rejected(self) -> None:
        with pytest.raises(ValidationError, match="summary"):
            SegmentReport.model_validate(_sector(material_findings=[{"as_of": "2026-08-28"}]))

    def test_url_and_completion_state_are_not_promoted_to_summary(self) -> None:
        """Residual long strings that are not prose aliases must not become research."""
        with pytest.raises(ValidationError, match="summary"):
            SegmentReport.model_validate(
                _sector(
                    material_findings=[
                        {
                            "as_of": "2026-08-28",
                            "url": "https://example.com/xlre-range-notes",
                            "completionState": "complete",
                            "source_id": "price_technicals:XLRE",
                        }
                    ]
                )
            )

    def test_question_mark_cuts_derived_label(self) -> None:
        report = SegmentReport.model_validate(
            _sector(
                material_findings=[
                    {
                        "text": "Did XLRE break out? It remains uncertain on the weekly.",
                        "as_of": "2026-08-28",
                    }
                ]
            )
        )
        assert report.material_findings[0].label == "Did XLRE break out"


class TestJsonStringItems:
    def test_finding_json_string_validates(self) -> None:
        payload = {
            "label": "MACD",
            "summary": "Histograms flipped negative.",
            "as_of": "2026-08-28",
        }
        report = SegmentReport.model_validate(_sector(material_findings=[json.dumps(payload)]))
        assert report.material_findings[0].label == "MACD"

    def test_gemini_object_envelope_json_string_validates(self) -> None:
        envelope = {
            "completionState": "complete",
            "type": "Object",
            "properties": {
                "label": {"stringValue": "XLRE range"},
                "summary": {"stringValue": "XLRE traded between $38 and $45.36 all week."},
                "as_of": {"stringValue": "2026-08-28"},
            },
        }
        report = SegmentReport.model_validate(
            _sector(
                material_findings=[json.dumps(envelope)],
                sources=[
                    json.dumps(
                        {
                            "completionState": "complete",
                            "type": "Object",
                            "fields": {
                                "id": {"stringValue": "price_technicals:XLRE"},
                                "title": {"stringValue": "XLRE technicals"},
                            },
                        }
                    )
                ],
            )
        )
        assert report.material_findings[0].label == "XLRE range"
        assert report.sources[0].id == "price_technicals:XLRE"

    def test_gemini_pair_list_envelope_json_string_validates(self) -> None:
        """Production 33426508863 shape: properties/fields as ``[[key, {stringValue}]]``."""
        finding_envelope = {
            "completionState": "complete",
            "type": "Object",
            "properties": [
                ["label", {"stringValue": "XLRE range"}],
                ["summary", {"stringValue": "XLRE traded between $38 and $45.36 all week."}],
                ["as_of", {"stringValue": "2026-08-28"}],
            ],
        }
        source_envelope = {
            "completionState": "complete",
            "type": "Object",
            "fields": [
                ["id", {"stringValue": "price_technicals:XLRE"}],
                ["title", {"stringValue": "XLRE technicals"}],
            ],
        }
        report = SegmentReport.model_validate(
            _sector(
                material_findings=[json.dumps(finding_envelope)],
                sources=[json.dumps(source_envelope)],
            )
        )
        assert report.material_findings[0].label == "XLRE range"
        assert report.material_findings[0].summary.startswith("XLRE traded")
        assert report.sources[0].id == "price_technicals:XLRE"

    def test_mixed_properties_list_is_not_treated_as_a_map(self) -> None:
        with pytest.raises(ValidationError, match="summary"):
            SegmentReport.model_validate(
                _sector(
                    material_findings=[
                        {
                            "completionState": "complete",
                            "type": "Object",
                            "properties": [
                                ["label", {"stringValue": "XLRE range"}],
                                "not-a-pair",
                            ],
                        }
                    ]
                )
            )
