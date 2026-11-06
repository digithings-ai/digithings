"""Fail-soft execution wrapper for research nodes (Pillar 1A).

A single research node that gets an empty/invalid LLM body (or a transient
provider error) must not abort the whole run. Before this, an empty OpenRouter
response made ``run_research_agent`` raise ``JSONDecodeError`` after its retries,
the exception propagated through LangGraph, and the entire research→portfolio chain
died **before publish + materialize** — so 19 healthy phases' work and the paper
book were lost to one bad sector call.

``run_segment_fail_soft`` runs the node's research call and, on any recoverable
failure, degrades the segment to an explicit ``Carried`` slot (read the prior
baseline payload for this segment) plus a ``PhaseError`` the caller merges into
``state.errors`` for the diagnostics audit row — instead of raising. A data gap
thus yields a *more conservative* book (one stale segment), never a crashed run.

LLM output that fails Pydantic validation (or does not parse as JSON) takes a
narrower path. :func:`invoke_llm_output` retries that call **once** with a repair
prompt built from the validator errors, then raises :class:`LlmValidationSkipped`.
``run_segment_fail_soft`` turns that into a carry whose reason is
:data:`VALIDATION_SKIP_REASON` — a skip marker, not ``node_failed_no_data`` —
so one bad ``SectorReport`` / ``DocumentPatch`` / ``SentimentNewsReport`` does
not abort the graph. Provider errors stay on the failure-carry path.

This is a **deliberate, observable** degrade boundary, not a silent swallow: every
failure is logged at WARNING with the exception type and recorded as a structured
``PhaseError`` that surfaces in ``run_diagnostics``. ``KeyboardInterrupt`` /
``SystemExit`` (``BaseException``) still propagate.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date
from typing import Any, TypeVar  # score:allow untyped any — phase_inputs JSON dict

from pydantic import BaseModel, ValidationError

from digiquant.research.state import (
    Carried,
    PhaseError,
    SegmentPayload,
    SegmentSlot,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

NODE_FAILED_REASON = "node_failed_no_data"
"""``Carried.reason`` marker distinguishing a node FAILURE carry from a triage carry."""

VALIDATION_SKIP_REASON = "llm_validation_skipped"
"""``Carried.reason`` / digest ``continuity`` marker for a validation skip.

Distinct from :data:`NODE_FAILED_REASON`: diagnostics counts only the failure
reason as ``segments_failed``. A schema miss after the repair retry is a
per-node skip, not a crashed run.
"""

_REPAIR_ERROR_LIMIT = 12
_REPAIR_PROMPT_MAX = 2000
_PARSE_FAILURES = (ValidationError, json.JSONDecodeError, ValueError)


class LlmValidationSkipped(Exception):
    """The LLM output failed validation after one repair retry.

    Callers degrade the node (skip marker + ``PhaseError``) instead of letting
    this escape LangGraph and kill the run.
    """

    def __init__(self, schema_name: str, detail: str) -> None:
        self.schema_name = schema_name
        self.detail = detail
        super().__init__(f"{schema_name}: {detail}"[:500])


def format_repair_prompt(schema_name: str, exc: BaseException) -> str:
    """Repair prompt for one failed validation. Locations and messages only.

    Pydantic ``errors()`` also carries the rejected ``input``. That value is
    omitted: a SectorReport failure can be dozens of nested errors, and the
    input can echo the whole body back into the next prompt.
    """
    lines = [f"Your previous response did not validate against {schema_name}."]
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        lines.append(f"{len(errors)} validation error(s):")
        for err in errors[:_REPAIR_ERROR_LIMIT]:
            loc = ".".join(str(part) for part in err.get("loc", ()))
            lines.append(f"- {loc or '<root>'}: {err.get('msg', 'invalid')}")
        extra = len(errors) - _REPAIR_ERROR_LIMIT
        if extra > 0:
            lines.append(f"- … {extra} more")
    else:
        lines.append(f"Error: {type(exc).__name__}: {exc}"[:400])
    lines.append(
        "Re-emit a single JSON object that validates against the schema. "
        "No prose, no code fences. Include every required field."
    )
    return "\n".join(lines)[:_REPAIR_PROMPT_MAX]


def with_validation_repair(phase_inputs: dict[str, Any], repair: str | None) -> dict[str, Any]:
    """Return phase inputs, attaching ``validation_repair`` only on the retry."""
    if repair is None:
        return phase_inputs
    return {**phase_inputs, "validation_repair": repair}


def invoke_llm_output(call: Callable[[str | None], T], *, schema_name: str) -> T:
    """Run ``call(None)``, then once ``call(repair_prompt)`` on a parse/validation miss.

    ``call`` receives the repair prompt (or ``None`` on the first attempt) and
    must perform exactly one LLM call — pass ``max_retries=0`` into
    ``run_research_agent`` so this function owns the single repair retry.
    Anything other than a parse/validation error propagates immediately.
    """
    try:
        return call(None)
    except _PARSE_FAILURES as exc:
        prompt = format_repair_prompt(schema_name, exc)
        logger.info(
            "LLM output for %s failed validation (%s); retrying with repair prompt",
            schema_name,
            type(exc).__name__,
        )
        try:
            return call(prompt)
        except _PARSE_FAILURES as retry_exc:
            detail = f"{type(retry_exc).__name__}: {retry_exc}"
            raise LlmValidationSkipped(schema_name, detail[:400]) from retry_exc


def run_segment_fail_soft(
    *,
    run_fn: Callable[[], BaseModel],
    segment_slug: str,
    phase: str,
    run_date: date,
    baseline_date: date | None,
) -> tuple[SegmentSlot, list[PhaseError]]:
    """Run one research node's LLM call, degrading any failure to a Carried slot.

    Args:
        run_fn: Thunk that performs ONLY the ``run_research_agent(...)`` call and
            returns its validated model. Input preparation (skill load, grounding,
            inputs_builder) must happen *outside* the thunk so genuine wiring bugs
            still fail loud — only the LLM call + validation is made fail-soft.
        segment_slug: The segment this node owns (becomes ``PhaseError.node`` and
            the fresh payload's ``segment``).
        phase: The owning phase label (e.g. ``"phase5_outputs"``) for ``PhaseError.phase``.
        run_date: Run date for the fresh payload's ``as_of`` and the carry fallback.
        baseline_date: Baseline the carry points at (falls back to ``run_date``).

    Returns:
        ``(slot, errors)`` — on success a fresh ``SegmentPayload`` slot and ``[]``;
        on a recoverable failure a ``Carried`` slot and a single-element error list
        the caller merges into ``state.errors``.
    """
    try:
        result = run_fn()
        slot = SegmentSlot(
            payload=SegmentPayload(
                segment=segment_slug,
                body=result.model_dump(mode="json"),
                as_of=run_date,
            )
        )
        return slot, []
    except LlmValidationSkipped as exc:
        logger.warning(
            "research node %r (phase %s) skipped after LLM validation failed (%s)",
            segment_slug,
            phase,
            exc.detail,
        )
        slot = SegmentSlot(
            payload=Carried(
                baseline_date=baseline_date or run_date,
                reason=VALIDATION_SKIP_REASON,
            )
        )
        error = PhaseError(
            phase=phase,
            node=segment_slug,
            message=str(exc)[:500],
            retryable=True,
        )
        return slot, [error]
    except Exception as exc:  # deliberate fail-soft boundary; see module docstring
        logger.warning(
            "research node %r (phase %s) failed (%s: %s); carrying baseline forward",
            segment_slug,
            phase,
            type(exc).__name__,
            exc,
            exc_info=True,  # keep the stack trace — this is an observable degrade, not a swallow
        )
        slot = SegmentSlot(
            payload=Carried(baseline_date=baseline_date or run_date, reason=NODE_FAILED_REASON)
        )
        error = PhaseError(
            phase=phase,
            node=segment_slug,
            message=f"{type(exc).__name__}: {exc}"[:500],
            retryable=True,
        )
        return slot, [error]


__all__ = [
    "NODE_FAILED_REASON",
    "VALIDATION_SKIP_REASON",
    "LlmValidationSkipped",
    "format_repair_prompt",
    "invoke_llm_output",
    "run_segment_fail_soft",
    "with_validation_repair",
]
