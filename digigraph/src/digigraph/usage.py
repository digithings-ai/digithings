"""Thread-safe per-run LLM/search usage accumulator (#663).

A process-global, opt-in sink: ``start()`` activates capture for a run, the LLM
helpers (``chat_completion`` / ``web_search`` / ``x_search``) call ``record(...)``,
and the pipeline reads ``snapshot()`` at run end to write a diagnostics row.
No-op until ``start()`` so library callers pay nothing. Phases may fan out across
threads, so all mutation is under a lock.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous call records
    Iterator,
    Literal,
)
from uuid import UUID

from digillm import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallContextHandle,
    ProviderCallOutcome,
    ProviderCallRecord,
    TelemetryRecord,
)
from pydantic import BaseModel, ConfigDict, Field

_LOCK = threading.Lock()
_ACTIVE = False
_CALLS: list[dict[str, Any]] = []
_EVENTS: list["RunCallEvent"] = []
_PROVIDER_CALLS: list[ProviderCallRecord] = []
_PROVIDER_ATTEMPTS: list[ProviderAttemptRecord] = []

_SEARCH_KINDS = {"web_search", "x_search"}
_PHASE_MAX = 120
_OPERATION_MAX = 200
_DOCUMENT_KEY_MAX = 500
_NAME_MAX = 255
_SUMMARY_MAX = 500
_SENSITIVE_FIELD_PARTS = frozenset(
    {
        "access_key",
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "cipher",
        "credential",
        "hmac",
        "jwt",
        "passphrase",
        "password",
        "private_key",
        "secret",
        "signing_key",
        "token",
    }
)


class CallContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_run_id: UUID | None = None
    phase: str | None = Field(default=None, max_length=_PHASE_MAX)
    operation: str | None = Field(default=None, max_length=_OPERATION_MAX)
    document_key: str | None = Field(default=None, max_length=_DOCUMENT_KEY_MAX)


class RunCallEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    kind: Literal["model_call", "search_call", "tool_call"]
    phase: str | None = Field(default=None, max_length=_PHASE_MAX)
    operation: str | None = Field(default=None, max_length=_OPERATION_MAX)
    document_key: str | None = Field(default=None, max_length=_DOCUMENT_KEY_MAX)
    name: str = Field(max_length=_NAME_MAX)
    status: Literal["ok", "error"]
    duration_ms: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    sources: int = Field(default=0, ge=0)
    input_summary: str = Field(max_length=_SUMMARY_MAX)
    output_summary: str = Field(max_length=_SUMMARY_MAX)


_CALL_CONTEXT: ContextVar[CallContext] = ContextVar(
    "digigraph_usage_call_context",
    default=CallContext(),
)


class LogicalCallContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    purpose: CallPurpose
    parent_call_id: UUID | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    no_artifact_reason: NoArtifactReason | None = None
    follow_up_purpose: CallPurpose | None = None
    follow_up_artifacts: tuple[ArtifactRef, ...] = ()
    follow_up_no_artifact_reason: NoArtifactReason | None = None
    defer_finalization: bool = False
    handle: ProviderCallContextHandle


_LOGICAL_CALL_CONTEXT: ContextVar[LogicalCallContext | None] = ContextVar(
    "digigraph_usage_logical_call_context",
    default=None,
)


def _bounded(value: str | None, limit: int) -> str | None:
    return value[:limit] if value is not None else None


@contextmanager
def call_context(
    *,
    node_run_id: UUID | None = None,
    phase: str | None = None,
    operation: str | None = None,
    document_key: str | None = None,
) -> Iterator[None]:
    """Label calls in the current phase without retaining prompts or outputs."""
    current = _CALL_CONTEXT.get()
    token = _CALL_CONTEXT.set(
        CallContext(
            node_run_id=node_run_id if node_run_id is not None else current.node_run_id,
            phase=_bounded(phase, _PHASE_MAX) if phase is not None else current.phase,
            operation=(
                _bounded(operation, _OPERATION_MAX) if operation is not None else current.operation
            ),
            document_key=(
                _bounded(document_key, _DOCUMENT_KEY_MAX)
                if document_key is not None
                else current.document_key
            ),
        )
    )
    try:
        yield
    finally:
        _CALL_CONTEXT.reset(token)


@contextmanager
def logical_call_context(
    *,
    purpose: CallPurpose,
    parent_call_id: UUID | None = None,
    artifacts: tuple[ArtifactRef, ...] = (),
    no_artifact_reason: NoArtifactReason | None = None,
    follow_up_purpose: CallPurpose | None = None,
    follow_up_artifacts: tuple[ArtifactRef, ...] = (),
    follow_up_no_artifact_reason: NoArtifactReason | None = None,
    defer_finalization: bool = False,
) -> Iterator[ProviderCallContextHandle]:
    """Describe one generic provider invocation without requiring Olympus semantics."""
    handle = ProviderCallContextHandle()
    token = _LOGICAL_CALL_CONTEXT.set(
        LogicalCallContext(
            purpose=purpose,
            parent_call_id=parent_call_id,
            artifacts=artifacts,
            no_artifact_reason=no_artifact_reason,
            follow_up_purpose=follow_up_purpose,
            follow_up_artifacts=follow_up_artifacts,
            follow_up_no_artifact_reason=follow_up_no_artifact_reason,
            defer_finalization=defer_finalization,
            handle=handle,
        )
    )
    try:
        yield handle
    finally:
        _LOGICAL_CALL_CONTEXT.reset(token)


def provider_call_metadata() -> tuple[UUID | None, LogicalCallContext | None]:
    """Return the current real node identity and optional logical-call description."""
    return _CALL_CONTEXT.get().node_run_id, _LOGICAL_CALL_CONTEXT.get()


def start() -> None:
    """Activate capture and clear any prior calls."""
    global _ACTIVE
    with _LOCK:
        _ACTIVE = True
        _CALLS.clear()
        _EVENTS.clear()
        _PROVIDER_CALLS.clear()
        _PROVIDER_ATTEMPTS.clear()


def reset() -> None:
    """Deactivate capture and clear."""
    global _ACTIVE
    with _LOCK:
        _ACTIVE = False
        _CALLS.clear()
        _EVENTS.clear()
        _PROVIDER_CALLS.clear()
        _PROVIDER_ATTEMPTS.clear()


def is_active() -> bool:
    return _ACTIVE


def record(
    *,
    kind: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    cost: float = 0.0,
    sources: int = 0,
    ok: bool = True,
    duration_ms: int | None = None,
    retry_count: int = 0,
    **_ignored: Any,
) -> None:
    """Record one LLM/search call. No-op unless capture is active.

    ``cached_tokens`` is the prompt-cache-hit portion of ``prompt_tokens`` (OpenRouter
    ``prompt_tokens_details.cached_tokens``) — surfaced so a run can show how much of the
    repeated shared-context prefix was billed at the cheaper cached rate. ``cost`` is the actual
    USD charged for the call (OpenRouter ``usage.cost``, always present on its responses; 0.0 for
    providers that don't report it) — summed into run-level spend for accurate cost telemetry.
    ``**_ignored`` keeps the observer forward-compatible with future digillm fields."""
    if not _ACTIVE:
        return
    context = _CALL_CONTEXT.get()
    event_kind: Literal["model_call", "search_call"] = (
        "search_call" if kind in _SEARCH_KINDS else "model_call"
    )
    output_summary = (
        f"{int(sources or 0)} sources returned"
        if event_kind == "search_call"
        else "Model response returned"
        if ok
        else "Model call failed"
    )
    with _LOCK:
        _CALLS.append(
            {
                "kind": kind,
                "model": model,
                "prompt_tokens": int(prompt_tokens or 0),
                "completion_tokens": int(completion_tokens or 0),
                "cached_tokens": int(cached_tokens or 0),
                "cost": float(cost or 0.0),
                "sources": int(sources or 0),
                "ok": bool(ok),
            }
        )
        _EVENTS.append(
            RunCallEvent(
                sequence=len(_EVENTS) + 1,
                kind=event_kind,
                phase=context.phase,
                operation=context.operation,
                document_key=context.document_key,
                name=_bounded(model, _NAME_MAX) or "unknown",
                status="ok" if ok else "error",
                duration_ms=duration_ms,
                retry_count=retry_count,
                prompt_tokens=int(prompt_tokens or 0),
                completion_tokens=int(completion_tokens or 0),
                cached_tokens=int(cached_tokens or 0),
                cost_usd=float(cost or 0.0),
                sources=int(sources or 0),
                input_summary=(
                    "Grounding search request"
                    if event_kind == "search_call"
                    else "Structured model request"
                ),
                output_summary=output_summary,
            )
        )


def observe_telemetry(record: TelemetryRecord) -> None:
    """Collect strict logical/attempt records for the active run without persistence."""
    if not _ACTIVE:
        return
    with _LOCK:
        if isinstance(record, ProviderCallRecord):
            _PROVIDER_CALLS.append(record)
        elif isinstance(record, ProviderAttemptRecord):
            _PROVIDER_ATTEMPTS.append(record)


class DetailedUsageObserver:
    """Adapt the in-process collector to DigiLLM's strict observer protocol."""

    def observe(self, record: TelemetryRecord) -> None:
        observe_telemetry(record)


DETAILED_USAGE_OBSERVER = DetailedUsageObserver()


def _nullable_sum(values: list[int | float | None]) -> int | float | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def detailed_usage_projection() -> dict[str, int | float | None]:
    """Project aggregate-compatible successes without fabricating provider evidence."""
    with _LOCK:
        calls = list(_PROVIDER_CALLS)
        attempts = list(_PROVIDER_ATTEMPTS)
    successful_calls = [call for call in calls if call.outcome is ProviderCallOutcome.SUCCEEDED]
    aggregate_calls = [
        call for call in successful_calls if call.cache_status is not CacheStatus.HIT
    ]
    attempts_by_call: dict[UUID, ProviderAttemptRecord] = {}
    for attempt in attempts:
        if attempt.outcome is ProviderAttemptOutcome.SUCCEEDED:
            attempts_by_call[attempt.call_id] = attempt
    successful_attempts = [
        attempts_by_call[call.call_id]
        for call in aggregate_calls
        if call.call_id in attempts_by_call
    ]
    search_purposes = {CallPurpose.WEB_GROUNDING, CallPurpose.X_GROUNDING}
    llm_call_ids = {call.call_id for call in aggregate_calls if call.purpose not in search_purposes}
    llm_attempts = [attempt for attempt in successful_attempts if attempt.call_id in llm_call_ids]
    prompt_tokens = (
        _nullable_sum([attempt.prompt_tokens for attempt in llm_attempts]) if llm_call_ids else 0
    )
    completion_tokens = (
        _nullable_sum([attempt.completion_tokens for attempt in llm_attempts])
        if llm_call_ids
        else 0
    )
    cost_usd = _nullable_sum(
        [
            float(attempt.cost_usd) if attempt.cost_usd is not None else None
            for attempt in successful_attempts
        ]
    )
    return {
        "llm_calls": sum(call.purpose not in search_purposes for call in aggregate_calls),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(float(cost_usd), 6) if cost_usd is not None else None,
        "search_calls": sum(call.purpose in search_purposes for call in aggregate_calls),
    }


def _is_sensitive_field(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_FIELD_PARTS)


def _count_sensitive_fields(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            1 if _is_sensitive_field(str(key)) else _count_sensitive_fields(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(_count_sensitive_fields(item) for item in value)
    return 0


def _tool_input_summary(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return "Arguments recorded as a non-object value"
    visible = sorted(str(key) for key in arguments if not _is_sensitive_field(str(key)))
    sensitive_count = _count_sensitive_fields(arguments)
    fields = ", ".join(visible) if visible else "none"
    redaction = (
        f"; {sensitive_count} sensitive field{'s' if sensitive_count != 1 else ''} redacted"
        if sensitive_count
        else ""
    )
    return f"Arguments: {fields}{redaction}"


def _tool_output_summary(result: Any, ok: bool) -> str:
    if not ok:
        return "Tool call failed"
    if isinstance(result, dict):
        return f"Returned {len(result)} fields"
    if isinstance(result, list):
        return f"Returned {len(result)} items"
    if result is None:
        return "Returned no value"
    return f"Returned {type(result).__name__}"


def record_tool_call(
    *,
    name: str,
    arguments: Any,
    result: Any = None,
    duration_ms: int | None = None,
    ok: bool = True,
    retry_count: int = 0,
    phase: str | None = None,
    operation: str | None = None,
    document_key: str | None = None,
) -> None:
    """Record one tool execution using shape summaries only, never argument/result values."""
    if not _ACTIVE:
        return
    context = _CALL_CONTEXT.get()
    with _LOCK:
        _EVENTS.append(
            RunCallEvent(
                sequence=len(_EVENTS) + 1,
                kind="tool_call",
                phase=_bounded(phase, _PHASE_MAX) if phase is not None else context.phase,
                operation=(
                    _bounded(operation, _OPERATION_MAX)
                    if operation is not None
                    else context.operation
                ),
                document_key=(
                    _bounded(document_key, _DOCUMENT_KEY_MAX)
                    if document_key is not None
                    else context.document_key
                ),
                name=_bounded(name, _NAME_MAX) or "unknown",
                status="ok" if ok else "error",
                duration_ms=duration_ms,
                retry_count=retry_count,
                input_summary=_bounded(_tool_input_summary(arguments), _SUMMARY_MAX) or "",
                output_summary=_bounded(_tool_output_summary(result, ok), _SUMMARY_MAX) or "",
            )
        )


def events_snapshot() -> list[dict[str, Any]]:
    """Return an ordered, body-free copy of the current run's call events."""
    with _LOCK:
        return [event.model_dump(mode="json") for event in _EVENTS]


def snapshot() -> dict[str, Any]:
    """Aggregate the recorded calls into run-level totals + a per-kind breakdown."""
    with _LOCK:
        calls = list(_CALLS)
    chat = [c for c in calls if c["kind"] == "chat"]
    search = [c for c in calls if c["kind"] in _SEARCH_KINDS]
    prompt = sum(c["prompt_tokens"] for c in chat)
    completion = sum(c["completion_tokens"] for c in chat)
    cached = sum(c.get("cached_tokens", 0) for c in chat)
    cost = sum(c.get("cost", 0.0) for c in calls)
    by_kind: dict[str, dict[str, float]] = {}
    for c in calls:
        b = by_kind.setdefault(
            c["kind"],
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "cost": 0.0,
                "sources": 0,
            },
        )
        b["calls"] += 1
        b["prompt_tokens"] += c["prompt_tokens"]
        b["completion_tokens"] += c["completion_tokens"]
        b["cached_tokens"] += c.get("cached_tokens", 0)
        b["cost"] += c.get("cost", 0.0)
        b["sources"] += c["sources"]
    return {
        "llm_calls": len(chat),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "total_tokens": prompt + completion,
        # Actual USD charged across all calls (OpenRouter usage.cost); 0.0 when no provider
        # reported a cost. Rounded to 6 dp — sub-cent per-call costs must not lose precision.
        "cost_usd": round(cost, 6),
        "search_calls": len(search),
        "sources_used": sum(c["sources"] for c in search),
        "grounding_ok": sum(1 for c in search if c["ok"]),
        "grounding_failed": sum(1 for c in search if not c["ok"]),
        "models": sorted({c["model"] for c in calls}),
        "by_kind": by_kind,
        "events": events_snapshot(),
    }
