"""Validation failures retry once with a repair prompt, then skip the node."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # score:allow untyped any — captured agent kwargs

import pytest
from digiquant.research.phases.fail_soft import (
    VALIDATION_SKIP_REASON,
    LlmValidationSkipped,
    format_repair_prompt,
    invoke_llm_output,
    run_segment_fail_soft,
)
from digiquant.research.phases.phase7_synthesis import _degrade_digest, _synthesis_node
from digiquant.research.state import ResearchState
from pydantic import BaseModel, ValidationError

pytestmark = pytest.mark.unit

_SECRET = "SHOULD_NOT_ECHO_REJECTED_INPUT"


class _Report(BaseModel):
    segment: str
    n: int


def _validation_error() -> ValidationError:
    try:
        _Report.model_validate({"segment": _SECRET})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


def test_repair_prompt_names_errors_and_omits_rejected_input() -> None:
    prompt = format_repair_prompt("SectorReport", _validation_error())
    assert "SectorReport" in prompt
    assert "n" in prompt
    assert _SECRET not in prompt


def test_first_valid_output_does_not_retry() -> None:
    seen: list[str | None] = []

    def _call(repair: str | None) -> _Report:
        seen.append(repair)
        return _Report(segment="sector-technology", n=1)

    out = invoke_llm_output(_call, schema_name="SectorReport")
    assert out.n == 1
    assert seen == [None]


def test_validation_failure_retries_with_repair_then_returns() -> None:
    seen: list[str | None] = []

    def _call(repair: str | None) -> _Report:
        seen.append(repair)
        if repair is None:
            raise _validation_error()
        return _Report(segment="alt-sentiment-news", n=2)

    out = invoke_llm_output(_call, schema_name="SentimentNewsReport")
    assert out.segment == "alt-sentiment-news"
    assert seen[0] is None
    assert seen[1] is not None
    assert "SentimentNewsReport" in seen[1]
    assert _SECRET not in seen[1]


def test_second_validation_failure_skips_instead_of_raising_the_model_error() -> None:
    calls = 0

    def _call(repair: str | None) -> _Report:
        del repair
        nonlocal calls
        calls += 1
        raise _validation_error()

    with pytest.raises(LlmValidationSkipped) as caught:
        invoke_llm_output(_call, schema_name="DocumentPatch")
    assert calls == 2
    assert caught.value.schema_name == "DocumentPatch"
    assert not isinstance(caught.value, ValidationError)


def test_non_validation_error_is_not_retried() -> None:
    calls = 0

    def _call(repair: str | None) -> _Report:
        del repair
        nonlocal calls
        calls += 1
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        invoke_llm_output(_call, schema_name="DigestSnapshot")
    assert calls == 1


def test_json_decode_error_is_repaired_once() -> None:
    seen: list[str | None] = []

    def _call(repair: str | None) -> _Report:
        seen.append(repair)
        if repair is None:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return _Report(segment="macro", n=3)

    out = invoke_llm_output(_call, schema_name="DigestSnapshot")
    assert out.n == 3
    assert seen[1] is not None
    assert "JSONDecodeError" in seen[1]


def test_fail_soft_maps_validation_skip_to_marker() -> None:
    def _run() -> _Report:
        raise LlmValidationSkipped("SectorReport", "ValidationError: n")

    slot, errors = run_segment_fail_soft(
        run_fn=_run,
        segment_slug="sector-technology",
        phase="phase5_outputs",
        run_date=date(2026, 6, 20),
        baseline_date=None,
    )
    assert slot.payload.source == "carried"
    assert slot.payload.reason == VALIDATION_SKIP_REASON  # type: ignore[union-attr]
    assert errors[0].node == "sector-technology"
    assert errors[0].phase == "phase5_outputs"


def test_segment_node_skips_with_marker_after_repair_retry() -> None:
    from unittest.mock import patch

    from digiquant.research.phases._node_factory import SegmentNodeSpec, build_segment_node

    calls: list[dict[str, Any]] = []

    def _agent(**kwargs: Any) -> _Report:
        calls.append(kwargs)
        raise _validation_error()

    spec = SegmentNodeSpec(
        segment_slug="sector-technology",
        skill_slug="sector-research",
        output_model=_Report,
        phase_outputs_field="phase5_outputs",
        live_search=False,
    )
    node = build_segment_node(spec)
    state = ResearchState(run_type="baseline", run_date=date(2026, 6, 20))
    with patch(
        "digiquant.research.phases._node_factory.run_research_agent",
        side_effect=_agent,
    ):
        update = node(state)

    assert len(calls) == 2
    assert calls[0]["max_retries"] == 0
    assert "validation_repair" not in calls[0]["phase_inputs"]
    assert calls[1]["max_retries"] == 0
    repair = calls[1]["phase_inputs"]["validation_repair"]
    assert _Report.__name__ in repair
    assert "n:" in repair or "- n:" in repair
    assert _SECRET not in repair
    slot = update["phase5_outputs"]["sector-technology"]
    assert slot.payload.reason == VALIDATION_SKIP_REASON
    assert update["errors"][0].node == "sector-technology"


def test_digest_without_prior_skips_with_marker() -> None:
    state = ResearchState(run_type="baseline", run_date=date(2026, 6, 20))
    out = _degrade_digest(state, "digest", _validation_error())
    digest = out["phase7_digest"]
    assert digest["continuity"] == VALIDATION_SKIP_REASON
    assert digest["date"] == "2026-06-20"
    assert out["errors"][0].node == "master-digest"


def test_stitch_node_survives_digest_validation_failure() -> None:
    from unittest.mock import patch

    calls: list[dict[str, Any]] = []

    def _agent(**kwargs: Any) -> Any:
        calls.append(kwargs)
        raise _validation_error()

    state = ResearchState(run_type="baseline", run_date=date(2026, 6, 20))
    with patch(
        "digiquant.research.phases.phase7_synthesis.run_research_agent",
        side_effect=_agent,
    ):
        update = _synthesis_node(state)

    assert len(calls) == 2
    assert calls[1]["phase_inputs"]["validation_repair"]
    assert update["phase7_digest"]["continuity"] == VALIDATION_SKIP_REASON
    assert update["errors"]
