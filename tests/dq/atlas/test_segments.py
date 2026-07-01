"""SegmentReport data-quality contract (Pillar 1E).

``data_quality`` + ``confidence`` are optional (backward-compatible: old bodies without
them validate and default to None). ``confidence`` is clamped to [0,1]; a non-numeric
value degrades to None rather than hard-failing a run.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.segments import SegmentReport

pytestmark = pytest.mark.unit


def _report(**over: object) -> SegmentReport:
    base: dict[str, object] = {
        "segment": "macro",
        "date": date(2026, 6, 12),
        "bias": "neutral",
        "headline": "h",
    }
    base.update(over)
    return SegmentReport(**base)  # type: ignore[arg-type]


def test_data_quality_defaults_to_none() -> None:
    r = _report()
    assert r.data_quality is None
    assert r.confidence is None


def test_data_quality_accepts_grades() -> None:
    for grade in ("high", "medium", "low", "absent"):
        assert _report(data_quality=grade).data_quality == grade


def test_confidence_clamped_to_unit_interval() -> None:
    assert _report(confidence=1.5).confidence == 1.0
    assert _report(confidence=-0.2).confidence == 0.0
    assert _report(confidence="0.7").confidence == pytest.approx(0.7)


def test_confidence_non_numeric_degrades_to_none() -> None:
    assert _report(confidence="high").confidence is None
    assert _report(confidence=None).confidence is None


def test_data_quality_normalizes_case_and_whitespace() -> None:
    # LLM case/whitespace variants normalize rather than hard-fail the run.
    assert _report(data_quality="ABSENT").data_quality == "absent"
    assert _report(data_quality=" High ").data_quality == "high"
    assert _report(data_quality="Medium").data_quality == "medium"


def test_data_quality_unrecognized_degrades_to_none() -> None:
    # An out-of-vocab grade degrades to None (publishes ungraded) instead of ValidationError.
    assert _report(data_quality="unknown").data_quality is None
    assert _report(data_quality="n/a").data_quality is None


def test_bias_synonym_still_normalizes() -> None:
    # The new fields don't disturb the existing bias-synonym normalization.
    assert _report(bias="positive").bias == "bullish"
