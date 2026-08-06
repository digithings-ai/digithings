"""Provider-agnostic telemetry contracts for logical calls and physical attempts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Protocol, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CallPurpose(StrEnum):
    """Why a logical provider call exists."""

    INITIAL_GENERATION = "initial_generation"
    CHAT_COMPLETION = "chat_completion"
    STRUCTURED_COMPLETION = "structured_completion"
    STRUCTURED_REPAIR = "structured_repair"
    TOOL_SELECTION = "tool_selection"
    TOOL_FOLLOW_UP = "tool_follow_up"
    WEB_GROUNDING = "web_grounding"
    X_GROUNDING = "x_grounding"
    TOOL_LOOP = "tool_loop"
    WEB_SEARCH = "web_search"
    X_SEARCH = "x_search"
    EMBEDDING = "embedding"


class CacheStatus(StrEnum):
    """Logical-call interaction with a response cache."""

    BYPASSED = "bypassed"
    HIT = "hit"
    MISS = "miss"
    UNAVAILABLE = "unavailable"


class NoArtifactReason(StrEnum):
    """Why a logical call has no immutable artifact reference."""

    CONSUMED_INLINE = "consumed_inline"
    TOOL_DISPATCH = "tool_dispatch"
    VALIDATION_REJECTED = "validation_rejected"
    NO_OUTPUT = "no_output"
    CALL_FAILED = "call_failed"
    CALL_CANCELLED = "call_cancelled"
    UNKNOWN = "unknown"


class NodeRunOutcome(StrEnum):
    """Terminal or in-progress state of a graph node execution."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderCallOutcome(StrEnum):
    """Terminal or in-progress state of one logical provider call."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderAttemptOutcome(StrEnum):
    """Terminal or in-progress state of one physical provider attempt."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetryReason(StrEnum):
    """Closed reasons for issuing a physical attempt after the first."""

    NOT_APPLICABLE = "not_applicable"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    EMPTY_RESPONSE = "empty_response"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class TelemetryModel(BaseModel):
    """Strict immutable base for deterministic event serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactRef(TelemetryModel):
    """Generic immutable reference to an artifact, never its payload."""

    artifact_type: Annotated[str, Field(min_length=1)]
    artifact_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]


class TimedTelemetryModel(TelemetryModel):
    """Shared UTC and lifecycle validation for timed telemetry records."""

    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> TimedTelemetryModel:
        for value in (self.started_at, self.finished_at):
            if value is not None and value.utcoffset() != timedelta(0):
                raise ValueError("telemetry timestamps must be UTC")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class NodeRunRecord(TimedTelemetryModel):
    """One execution of a stable graph node within a workflow run."""

    node_run_id: UUID
    run_id: Annotated[str, Field(min_length=1)]
    node_name: Annotated[str, Field(min_length=1)]
    outcome: NodeRunOutcome
    artifacts: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def validate_lifecycle(self) -> NodeRunRecord:
        _validate_finished_state(self.outcome.value, self.finished_at)
        return self


class ProviderCallRecord(TimedTelemetryModel):
    """One logical invocation, which may contain zero or more physical attempts."""

    call_id: UUID
    node_run_id: UUID
    parent_call_id: UUID | None = None
    purpose: CallPurpose
    requested_model: Annotated[str, Field(min_length=1, max_length=256)]
    cache_status: CacheStatus
    outcome: ProviderCallOutcome
    attempt_count: Annotated[int, Field(ge=0)]
    artifacts: tuple[ArtifactRef, ...] = ()
    no_artifact_reason: NoArtifactReason | None = None
    error_type: Annotated[str, Field(min_length=1, max_length=200)] | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ProviderCallRecord:
        _validate_finished_state(self.outcome.value, self.finished_at)
        if bool(self.artifacts) == (self.no_artifact_reason is not None):
            raise ValueError("a logical call requires either artifacts or one no-artifact reason")
        if self.outcome is ProviderCallOutcome.FAILED:
            if self.error_type is None:
                raise ValueError("a failed logical call requires a sanitized error type")
            if self.no_artifact_reason is not NoArtifactReason.CALL_FAILED:
                raise ValueError("a failed logical call requires the call_failed disposition")
        elif self.error_type is not None:
            raise ValueError("only a failed logical call can carry an error type")
        if (
            self.outcome is ProviderCallOutcome.CANCELLED
            and self.no_artifact_reason is not NoArtifactReason.CALL_CANCELLED
        ):
            raise ValueError("a cancelled logical call requires the call_cancelled disposition")
        if (
            self.outcome is ProviderCallOutcome.SUCCEEDED
            and self.cache_status is not CacheStatus.HIT
            and self.attempt_count == 0
        ):
            raise ValueError("a successful non-cache call requires a physical attempt")
        if self.cache_status is CacheStatus.HIT and self.attempt_count != 0:
            raise ValueError("a cache-hit call cannot contain physical attempts")
        return self


class ProviderAttemptRecord(TimedTelemetryModel):
    """One physical request at the observable provider transport boundary."""

    attempt_id: UUID
    call_id: UUID
    attempt_number: Annotated[int, Field(ge=1)]
    provider: Annotated[str, Field(min_length=1)]
    requested_model: Annotated[str, Field(min_length=1, max_length=256)]
    served_model: Annotated[str, Field(min_length=1)] | None = None
    outcome: ProviderAttemptOutcome
    retry_reason: RetryReason
    prompt_tokens: Annotated[int, Field(ge=0)] | None = None
    completion_tokens: Annotated[int, Field(ge=0)] | None = None
    cost_usd: Annotated[Decimal, Field(ge=0)] | None = None
    error_type: Annotated[str, Field(min_length=1, max_length=200)] | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ProviderAttemptRecord:
        _validate_finished_state(self.outcome.value, self.finished_at)
        if self.attempt_number == 1 and self.retry_reason is not RetryReason.NOT_APPLICABLE:
            raise ValueError("the first physical attempt cannot have a retry reason")
        if self.attempt_number > 1 and self.retry_reason is RetryReason.NOT_APPLICABLE:
            raise ValueError("a retry attempt requires a retry reason")
        return self


TelemetryRecord: TypeAlias = NodeRunRecord | ProviderCallRecord | ProviderAttemptRecord
TelemetryFailureReporter: TypeAlias = Callable[[UUID, str], None]


class TelemetryObserver(Protocol):
    """Synchronous sink boundary; implementations own buffering and persistence."""

    def observe(self, record: TelemetryRecord) -> None: ...


def emit_telemetry(
    observer: TelemetryObserver,
    record: TelemetryRecord,
    *,
    on_failure: TelemetryFailureReporter | None = None,
) -> bool:
    """Deliver one event without allowing telemetry failure to abort caller work."""
    try:
        observer.observe(record)
    except Exception as error:
        if on_failure is not None:
            try:
                on_failure(_record_id(record), type(error).__name__)
            except Exception:
                pass
        return False
    return True


def _record_id(record: TelemetryRecord) -> UUID:
    if isinstance(record, NodeRunRecord):
        return record.node_run_id
    if isinstance(record, ProviderCallRecord):
        return record.call_id
    return record.attempt_id


def _validate_finished_state(outcome: str, finished_at: datetime | None) -> None:
    if outcome == "started" and finished_at is not None:
        raise ValueError("a started record cannot have finished_at")
    if outcome != "started" and finished_at is None:
        raise ValueError("a terminal record requires finished_at")


__all__ = [
    "ArtifactRef",
    "CacheStatus",
    "CallPurpose",
    "NoArtifactReason",
    "NodeRunOutcome",
    "NodeRunRecord",
    "ProviderAttemptOutcome",
    "ProviderAttemptRecord",
    "ProviderCallOutcome",
    "ProviderCallRecord",
    "RetryReason",
    "TelemetryFailureReporter",
    "TelemetryObserver",
    "TelemetryRecord",
    "emit_telemetry",
]
