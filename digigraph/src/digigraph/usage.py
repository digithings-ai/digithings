"""Thread-safe per-run LLM/search usage accumulator (#663).

By default a process-global, opt-in sink: ``start()`` activates capture for a run, the
LLM helpers (``chat_completion`` / ``web_search`` / ``x_search``) call ``record(...)``,
and the pipeline reads ``snapshot()`` at run end to write a diagnostics row.
No-op until ``start()`` so library callers pay nothing. Phases may fan out across
threads, so all mutation is under a lock.

That global is deliberately one-run-per-process -- the portfolio chain and the research
diagnostics writer pair ``start()`` with ``reset()`` once each. Concurrent HTTP streams
cannot share it: two overlapping responses would record into one buffer and whichever
finishes first would clear the other's totals (#3982). Those callers bind a
:class:`UsageRun` with :func:`bind_run` before the worker thread's
``contextvars.copy_context()`` snapshot instead; every ``record(...)`` reached from that
context lands in the request's own buffers, and the module-global state is untouched.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous call records
    Iterator,
    Literal,
)
from uuid import UUID, uuid4

from digillm import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
    NodeRunOutcome,
    NodeRunRecord,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallContextHandle,
    ProviderCallOutcome,
    ProviderCallRecord,
    TelemetryRecord,
    emit_telemetry,
)
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_ACTIVE = False
# The durable identifier every record in this run is keyed by. A module global rather than a
# ContextVar: `start()` and `reset()` are plain functions, so a token minted in one and reset in
# the other only survives if both run in the same Context — a mismatch would raise out of
# `reset()`, i.e. telemetry inventing a new exception on the run's exit path. Matches `_ACTIVE`.
_RUN_ID: str | None = None
_CALLS: list[dict[str, Any]] = []
_EVENTS: list["RunCallEvent"] = []
_PROVIDER_CALLS: list[ProviderCallRecord] = []
_PROVIDER_ATTEMPTS: list[ProviderAttemptRecord] = []
_NODE_RUNS: list[NodeRunRecord] = []
# Empty-completion self-heal retries (#1639) — keyed by served model slug.
_EMPTY_RETRIES: dict[str, int] = {}

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
    # Missing usage stays None — never fabricate 0 (#2763 / WP1 invariant 4).
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    sources: int = Field(default=0, ge=0)
    input_summary: str = Field(max_length=_SUMMARY_MAX)
    output_summary: str = Field(max_length=_SUMMARY_MAX)
    # Soft stamps to WP1 ledger (067); economics authority remains provider attempts.
    call_id: UUID | None = None
    attempt_id: UUID | None = None
    node_run_id: UUID | None = None


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

# Request-scoped accumulator selected by ``bind_run`` (#3982). ``None`` routes every
# recorder to the process-global buffers above, preserving the start()/reset() contract
# the portfolio chain and research diagnostics rely on.
_SCOPED_RUN: ContextVar["UsageRun | None"] = ContextVar(
    "digigraph_usage_scoped_run",
    default=None,
)


def _bounded(value: str | None, limit: int) -> str | None:
    return value[:limit] if value is not None else None


def _optional_nonnegative_int(value: int | None) -> int | None:
    """Preserve None; coerce present values without inventing zero for missing usage."""
    if value is None:
        return None
    return int(value)


def _optional_nonnegative_float(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_uuid(value: UUID | str | None) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


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
    """Describe one generic provider invocation without requiring dashboard semantics."""
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


def detach_logical_call_context() -> None:
    """Drop the inherited logical-call description in a fan-out worker.

    :func:`logical_call_context` hands its :class:`ProviderCallContextHandle` to the
    context var, and that handle is *mutable* — it carries ``last_call_id`` and a list of
    deferred records. A parallel worker started from a ``contextvars.copy_context()``
    snapshot (which is how digillm carries the request's BYOK credentials into its tool
    pool) inherits the value by reference, so several workers would write ``last_call_id``
    onto one shared handle and append into one shared deferred list — interleaving each
    other's telemetry. digillm clears its own equivalent var in
    ``detach_provider_call_context``; this is the same move one layer up, and
    ``llm_client`` registers it as digillm's fan-out detach hook.

    Token-free by necessity: a copied context carries values but no reset tokens, so there
    is nothing to ``reset`` and nothing to restore — the worker's context dies with the
    worker. Never call this on a caller's own context; it would silently unbind a live
    :func:`logical_call_context` block.

    ``_CALL_CONTEXT`` is deliberately left alone: its :class:`CallContext` is frozen and
    holds no mutable state, so inheriting the node identity is safe and improves
    attribution.
    """
    _LOGICAL_CALL_CONTEXT.set(None)


def provider_call_metadata() -> tuple[UUID | None, LogicalCallContext | None]:
    """Return the current real node identity and optional logical-call description."""
    return _CALL_CONTEXT.get().node_run_id, _LOGICAL_CALL_CONTEXT.get()


def start(*, run_id: str | None = None) -> None:
    """Activate capture and clear any prior calls.

    ``run_id`` is the durable identifier every record in this run is keyed by — the
    ``GITHUB_RUN_ID`` that ``run_diagnostics`` already uses, so detailed telemetry and
    the diagnostics row join on one value. It is stored verbatim and never truncated, because
    it is a join key. A blank or absent value leaves the run without node identity rather than
    inventing one: nodes then keep the existing no-identity behaviour of emitting physical
    attempts and no logical records. Keyword-only with a default, so every existing zero-arg
    caller is untouched.
    """
    global _ACTIVE, _RUN_ID
    raw = str(run_id) if run_id is not None else ""
    with _LOCK:
        _ACTIVE = True
        _RUN_ID = raw if raw.strip() else None
        _CALLS.clear()
        _EVENTS.clear()
        _PROVIDER_CALLS.clear()
        _PROVIDER_ATTEMPTS.clear()
        _NODE_RUNS.clear()
        _EMPTY_RETRIES.clear()


def reset() -> None:
    """Deactivate capture and clear."""
    global _ACTIVE, _RUN_ID
    with _LOCK:
        _ACTIVE = False
        _RUN_ID = None
        _CALLS.clear()
        _EVENTS.clear()
        _PROVIDER_CALLS.clear()
        _PROVIDER_ATTEMPTS.clear()
        _NODE_RUNS.clear()
        _EMPTY_RETRIES.clear()


def active_run_id() -> str | None:
    """Run identifier of the live capture, or ``None`` when there is no identity to attribute to."""
    with _LOCK:
        return _RUN_ID if _ACTIVE else None


def is_active() -> bool:
    return _ACTIVE


def _record_call_into(
    *,
    calls: list[dict[str, Any]],
    events: list[RunCallEvent],
    empty_retries: dict[str, int],
    lock: threading.Lock,
    kind: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    cost: float | None,
    sources: int,
    ok: bool,
    duration_ms: int | None,
    retry_count: int,
    call_id: UUID | str | None,
    attempt_id: UUID | str | None,
    node_run_id: UUID | str | None,
) -> None:
    """Append one call to the given buffers; shared by the global and scoped runs."""
    if kind == "empty_retry":
        with lock:
            empty_retries[model] = empty_retries.get(model, 0) + 1
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
    prompt = _optional_nonnegative_int(prompt_tokens)
    completion = _optional_nonnegative_int(completion_tokens)
    cached = _optional_nonnegative_int(cached_tokens)
    cost_usd = _optional_nonnegative_float(cost)
    stamped_call = _optional_uuid(call_id)
    stamped_attempt = _optional_uuid(attempt_id)
    stamped_node = _optional_uuid(node_run_id if node_run_id is not None else context.node_run_id)
    with lock:
        # Aggregate counters: missing usage contributes 0 to run totals (diagnostics only).
        calls.append(
            {
                "kind": kind,
                "model": model,
                "prompt_tokens": int(prompt or 0),
                "completion_tokens": int(completion or 0),
                "cached_tokens": int(cached or 0),
                "cost": float(cost_usd or 0.0),
                "sources": int(sources or 0),
                "ok": bool(ok),
            }
        )
        events.append(
            RunCallEvent(
                sequence=len(events) + 1,
                kind=event_kind,
                phase=context.phase,
                operation=context.operation,
                document_key=context.document_key,
                name=_bounded(model, _NAME_MAX) or "unknown",
                status="ok" if ok else "error",
                duration_ms=duration_ms,
                retry_count=retry_count,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cached_tokens=cached,
                cost_usd=cost_usd,
                sources=int(sources or 0),
                input_summary=(
                    "Grounding search request"
                    if event_kind == "search_call"
                    else "Structured model request"
                ),
                output_summary=output_summary,
                call_id=stamped_call,
                attempt_id=stamped_attempt,
                node_run_id=stamped_node,
            )
        )


def record(
    *,
    kind: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cached_tokens: int | None = None,
    cost: float | None = None,
    sources: int = 0,
    ok: bool = True,
    duration_ms: int | None = None,
    retry_count: int = 0,
    call_id: UUID | str | None = None,
    attempt_id: UUID | str | None = None,
    node_run_id: UUID | str | None = None,
    **_ignored: Any,
) -> None:
    """Record one LLM/search call. No-op unless capture is active.

    ``cached_tokens`` is the prompt-cache-hit portion of ``prompt_tokens`` (OpenRouter
    ``prompt_tokens_details.cached_tokens``) — surfaced so a run can show how much of the
    repeated shared-context prefix was billed at the cheaper cached rate. ``cost`` is the actual
    USD charged when the provider reports it; ``None`` when unknown (never fabricate 0 on the
    glass-box event path — WP1 / #2763). Aggregate run totals still treat missing as 0 for
    diagnostics counters only. ``call_id`` / ``attempt_id`` soft-stamp the WP1 ledger (067).
    ``**_ignored`` keeps the observer forward-compatible with future digillm fields.

    A request-scoped run bound by :func:`bind_run` takes precedence over the global
    accumulator, so concurrent streams never share buffers (#3982)."""
    scoped = _SCOPED_RUN.get()
    if scoped is not None:
        scoped.record(
            kind=kind,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost=cost,
            sources=sources,
            ok=ok,
            duration_ms=duration_ms,
            retry_count=retry_count,
            call_id=call_id,
            attempt_id=attempt_id,
            node_run_id=node_run_id,
        )
        return
    if not _ACTIVE:
        return
    _record_call_into(
        calls=_CALLS,
        events=_EVENTS,
        empty_retries=_EMPTY_RETRIES,
        lock=_LOCK,
        kind=kind,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        cost=cost,
        sources=sources,
        ok=ok,
        duration_ms=duration_ms,
        retry_count=retry_count,
        call_id=call_id,
        attempt_id=attempt_id,
        node_run_id=node_run_id,
    )


def _observe_telemetry_into(
    *,
    provider_calls: list[ProviderCallRecord],
    provider_attempts: list[ProviderAttemptRecord],
    node_runs: list[NodeRunRecord],
    lock: threading.Lock,
    record: TelemetryRecord,
) -> None:
    with lock:
        if isinstance(record, ProviderCallRecord):
            provider_calls.append(record)
        elif isinstance(record, ProviderAttemptRecord):
            provider_attempts.append(record)
        elif isinstance(record, NodeRunRecord):
            node_runs.append(record)


def observe_telemetry(record: TelemetryRecord) -> None:
    """Collect strict logical/attempt records for the active run without persistence."""
    scoped = _SCOPED_RUN.get()
    if scoped is not None:
        scoped.observe(record)
        return
    if not _ACTIVE:
        return
    _observe_telemetry_into(
        provider_calls=_PROVIDER_CALLS,
        provider_attempts=_PROVIDER_ATTEMPTS,
        node_runs=_NODE_RUNS,
        lock=_LOCK,
        record=record,
    )


class DetailedUsageObserver:
    """Adapt the in-process collector to DigiLLM's strict observer protocol."""

    def observe(self, record: TelemetryRecord) -> None:
        observe_telemetry(record)


DETAILED_USAGE_OBSERVER = DetailedUsageObserver()

_FANOUT_KEY_MAX = 200  # keep in step with NodeRunRecord.fanout_key and migration 067's CHECK


@contextmanager
def node_run_scope(node_name: str, *, fanout_key: str | None = None) -> Iterator[UUID | None]:
    """Scope one graph-node execution.

    Mints the node's identity, labels every provider call it makes, and emits exactly one
    terminal ``NodeRunRecord``. Yields the ``node_run_id``, or ``None`` when the run has no
    identifier — a node executed outside an identified run keeps today's no-identity behaviour
    rather than fabricating a parent that could never be persisted against 067's foreign keys.

    The ``ContextVar`` work is delegated to :func:`call_context`, whose set and reset are
    lexically paired in one frame, so a token can never be reset from a different Context.
    ``phase`` is deliberately not set: populating it would change the ``events`` JSON the
    diagnostics writer already stores.
    """
    run_id = active_run_id()
    name = _bounded(node_name, _NAME_MAX) or ""
    if run_id is None or not name:
        yield None
        return
    node_run_id = uuid4()
    bounded_key = _bounded(fanout_key, _FANOUT_KEY_MAX) if fanout_key is not None else None
    key = (bounded_key.strip() or None) if bounded_key is not None else None
    started_at = datetime.now(tz=timezone.utc)
    outcome = NodeRunOutcome.SUCCEEDED
    try:
        with call_context(node_run_id=node_run_id):
            yield node_run_id
    except BaseException:
        # Deliberately broader than digillm's `except Exception`: losing the record on the exact
        # path where a run dies is the worst place to lose it, and an incomplete run must be a
        # counted signal. A LangGraph control-flow exception would be recorded FAILED; no
        # build_pipeline node uses interrupt() today, so that path is dead rather than wrong.
        outcome = NodeRunOutcome.FAILED
        raise
    finally:
        _emit_node_run(
            node_run_id=node_run_id,
            run_id=run_id,
            node_name=name,
            fanout_key=key,
            outcome=outcome,
            started_at=started_at,
        )


def _emit_node_run(
    *,
    node_run_id: UUID,
    run_id: str,
    node_name: str,
    fanout_key: str | None,
    outcome: NodeRunOutcome,
    started_at: datetime,
) -> None:
    """Deliver one terminal node record; telemetry failure never reaches the caller."""
    try:
        finished_at = datetime.now(tz=timezone.utc)
        record = NodeRunRecord(
            node_run_id=node_run_id,
            run_id=run_id,
            node_name=node_name,
            fanout_key=fanout_key,
            outcome=outcome,
            started_at=started_at,
            # A backwards clock step would fail the `finished_at < started_at` validator and
            # drop the record. Clamping preserves the identity reconciliation needs; duration
            # is not an identity claim.
            finished_at=max(finished_at, started_at),
        )
        emit_telemetry(DETAILED_USAGE_OBSERVER, record)
    except Exception as telemetry_error:
        # Construction and delivery share one guard: a ValidationError raised from the caller's
        # `finally` would otherwise replace the node's real exception.
        logger.debug("node-run telemetry failed: %s", type(telemetry_error).__name__)


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
    search_purposes = {CallPurpose.WEB_SEARCH, CallPurpose.X_SEARCH}
    # Tool search counts toward llm tokens (#3859): the first-party web_search
    # tool is the only grounding, so token totals fold search attempts in —
    # matching snapshot(), which sums chat + search kinds together.
    prompt_tokens = (
        _nullable_sum([attempt.prompt_tokens for attempt in successful_attempts])
        if aggregate_calls
        else 0
    )
    completion_tokens = (
        _nullable_sum([attempt.completion_tokens for attempt in successful_attempts])
        if aggregate_calls
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


def node_runs_snapshot() -> list[NodeRunRecord]:
    """Return this run's node execution records in completion order."""
    with _LOCK:
        return list(_NODE_RUNS)


def provider_calls_snapshot() -> list[ProviderCallRecord]:
    """Return this run's logical provider-call records.

    Typed records rather than dicts: reconciliation joins on ``UUID`` identity, and the Task 1.5
    writer wants rows it can persist without re-parsing.
    """
    with _LOCK:
        return list(_PROVIDER_CALLS)


def provider_attempts_snapshot() -> list[ProviderAttemptRecord]:
    """Return this run's physical provider-attempt records."""
    with _LOCK:
        return list(_PROVIDER_ATTEMPTS)


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


def _record_tool_call_into(
    *,
    events: list[RunCallEvent],
    lock: threading.Lock,
    name: str,
    arguments: Any,
    result: Any,
    duration_ms: int | None,
    ok: bool,
    retry_count: int,
    phase: str | None,
    operation: str | None,
    document_key: str | None,
) -> None:
    context = _CALL_CONTEXT.get()
    with lock:
        events.append(
            RunCallEvent(
                sequence=len(events) + 1,
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
                node_run_id=context.node_run_id,
            )
        )


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
    scoped = _SCOPED_RUN.get()
    if scoped is not None:
        scoped.record_tool_call(
            name=name,
            arguments=arguments,
            result=result,
            duration_ms=duration_ms,
            ok=ok,
            retry_count=retry_count,
            phase=phase,
            operation=operation,
            document_key=document_key,
        )
        return
    if not _ACTIVE:
        return
    _record_tool_call_into(
        events=_EVENTS,
        lock=_LOCK,
        name=name,
        arguments=arguments,
        result=result,
        duration_ms=duration_ms,
        ok=ok,
        retry_count=retry_count,
        phase=phase,
        operation=operation,
        document_key=document_key,
    )


def events_snapshot() -> list[dict[str, Any]]:
    """Return an ordered, body-free copy of the current run's call events."""
    with _LOCK:
        return [event.model_dump(mode="json") for event in _EVENTS]


def _aggregate_snapshot(
    *,
    calls: list[dict[str, Any]],
    event_dumps: list[dict[str, Any]],
    empty_retries: dict[str, int],
) -> dict[str, Any]:
    """Pure aggregation shared by the global and request-scoped runs."""
    chat = [c for c in calls if c["kind"] == "chat"]
    search = [c for c in calls if c["kind"] in _SEARCH_KINDS]
    prompt = sum(c["prompt_tokens"] for c in chat + search)
    completion = sum(c["completion_tokens"] for c in chat + search)
    cached = sum(c.get("cached_tokens", 0) for c in chat + search)
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
    # Per-model split (#4596): the token counts a token-derived cost estimate needs. Additive
    # to by_kind, which answers "which kind of call"; this answers "which model". ``cost`` stays
    # the ACTUAL figure — a caller that wants an estimate prices the tokens itself.
    by_model: dict[str, dict[str, float]] = {}
    for c in calls:
        m = by_model.setdefault(
            c["model"],
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "cost": 0.0,
            },
        )
        m["calls"] += 1
        m["prompt_tokens"] += c["prompt_tokens"]
        m["completion_tokens"] += c["completion_tokens"]
        m["cached_tokens"] += c.get("cached_tokens", 0)
        m["cost"] += c.get("cost", 0.0)
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
        "by_model": by_model,
        "empty_retries": {"total": sum(empty_retries.values()), "by_model": empty_retries},
        "events": event_dumps,
    }


def snapshot() -> dict[str, Any]:
    """Aggregate the recorded calls into run-level totals + a per-kind breakdown."""
    with _LOCK:
        calls = list(_CALLS)
        event_dumps = [event.model_dump(mode="json") for event in _EVENTS]
        empty_retries = dict(sorted(_EMPTY_RETRIES.items()))
    return _aggregate_snapshot(calls=calls, event_dumps=event_dumps, empty_retries=empty_retries)


class UsageRun:
    """Request-scoped accumulator that never touches the process-global buffers.

    Bind one with :func:`bind_run` before a worker thread's
    ``contextvars.copy_context()`` snapshot; every ``record`` / ``record_tool_call`` /
    telemetry observation reached from that context lands here. Overlapping HTTP
    streams therefore keep independent totals, and one response can neither read nor
    clear another's (#3982). Mutation stays under a per-run lock because a bound run is
    shared by every thread the worker's copied context reaches.
    """

    def __init__(self, *, run_id: str | None = None) -> None:
        raw = str(run_id) if run_id is not None else ""
        self._lock = threading.Lock()
        self._run_id = raw if raw.strip() else None
        self._calls: list[dict[str, Any]] = []
        self._events: list[RunCallEvent] = []
        self._provider_calls: list[ProviderCallRecord] = []
        self._provider_attempts: list[ProviderAttemptRecord] = []
        self._node_runs: list[NodeRunRecord] = []
        self._empty_retries: dict[str, int] = {}

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def record(
        self,
        *,
        kind: str,
        model: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cached_tokens: int | None = None,
        cost: float | None = None,
        sources: int = 0,
        ok: bool = True,
        duration_ms: int | None = None,
        retry_count: int = 0,
        call_id: UUID | str | None = None,
        attempt_id: UUID | str | None = None,
        node_run_id: UUID | str | None = None,
        **_ignored: Any,
    ) -> None:
        """Record one call into this run's buffers; always active."""
        _record_call_into(
            calls=self._calls,
            events=self._events,
            empty_retries=self._empty_retries,
            lock=self._lock,
            kind=kind,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost=cost,
            sources=sources,
            ok=ok,
            duration_ms=duration_ms,
            retry_count=retry_count,
            call_id=call_id,
            attempt_id=attempt_id,
            node_run_id=node_run_id,
        )

    def record_tool_call(
        self,
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
        _record_tool_call_into(
            events=self._events,
            lock=self._lock,
            name=name,
            arguments=arguments,
            result=result,
            duration_ms=duration_ms,
            ok=ok,
            retry_count=retry_count,
            phase=phase,
            operation=operation,
            document_key=document_key,
        )

    def observe(self, record: TelemetryRecord) -> None:
        """Strict-observer entry point for this run's logical/attempt telemetry."""
        _observe_telemetry_into(
            provider_calls=self._provider_calls,
            provider_attempts=self._provider_attempts,
            node_runs=self._node_runs,
            lock=self._lock,
            record=record,
        )

    def events_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.model_dump(mode="json") for event in self._events]

    def node_runs_snapshot(self) -> list[NodeRunRecord]:
        with self._lock:
            return list(self._node_runs)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            calls = list(self._calls)
            event_dumps = [event.model_dump(mode="json") for event in self._events]
            empty_retries = dict(sorted(self._empty_retries.items()))
        return _aggregate_snapshot(
            calls=calls, event_dumps=event_dumps, empty_retries=empty_retries
        )


def bind_run(run: UsageRun | None) -> Token:
    """Install ``run`` as the current context's accumulator, returning its reset token.

    The streaming caller binds, takes ``contextvars.copy_context()``, then resets the
    token in the same frame: the copy the worker thread starts with keeps ``run``,
    while the caller's own context is restored (a plain ``list(stream)`` consumer in
    tests shares that context and would otherwise leak the binding into later work).
    Set and reset must stay in one frame -- a token cannot be reset from a different
    Context.
    """
    return _SCOPED_RUN.set(run)


def unbind_run(token: Token) -> None:
    """Undo :func:`bind_run` in the context that minted ``token``."""
    _SCOPED_RUN.reset(token)
