"""Contract tests for provider telemetry records and fail-soft observation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import digillm
from digillm.telemetry import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NodeRunOutcome,
    NodeRunRecord,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallOutcome,
    ProviderCallRecord,
    RetryReason,
    TelemetryObserver,
    TelemetryRecord,
    emit_telemetry,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


def test_contracts_are_exported_from_package() -> None:
    assert digillm.NodeRunRecord is NodeRunRecord
    assert digillm.ProviderCallRecord is ProviderCallRecord
    assert digillm.ProviderAttemptRecord is ProviderAttemptRecord
    assert digillm.TelemetryObserver is TelemetryObserver
    assert digillm.emit_telemetry is emit_telemetry


def _node_run(**overrides: object) -> NodeRunRecord:
    values: dict[str, object] = {
        "node_run_id": uuid4(),
        "run_id": "olympus-2026-08-06-attempt-1",
        "node_name": "atlas.phase_1",
        "started_at": NOW,
        "finished_at": NOW,
        "outcome": NodeRunOutcome.SUCCEEDED,
    }
    values.update(overrides)
    return NodeRunRecord.model_validate(values)


def _call(node_run_id: UUID, **overrides: object) -> ProviderCallRecord:
    values: dict[str, object] = {
        "call_id": uuid4(),
        "node_run_id": node_run_id,
        "purpose": CallPurpose.CHAT_COMPLETION,
        "requested_model": "openrouter/test-model",
        "cache_status": CacheStatus.MISS,
        "started_at": NOW,
        "finished_at": NOW,
        "outcome": ProviderCallOutcome.SUCCEEDED,
        "attempt_count": 1,
    }
    values.update(overrides)
    return ProviderCallRecord.model_validate(values)


def _attempt(call_id: UUID, **overrides: object) -> ProviderAttemptRecord:
    values: dict[str, object] = {
        "attempt_id": uuid4(),
        "call_id": call_id,
        "attempt_number": 1,
        "provider": "openrouter",
        "requested_model": "openrouter/test-model",
        "served_model": "test-model",
        "started_at": NOW,
        "finished_at": NOW,
        "outcome": ProviderAttemptOutcome.SUCCEEDED,
        "retry_reason": RetryReason.NOT_APPLICABLE,
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "cost_usd": Decimal("0.0012"),
    }
    values.update(overrides)
    return ProviderAttemptRecord.model_validate(values)


@pytest.mark.parametrize("field", ("prompt", "response", "api_key", "raw_exception"))
def test_records_reject_payload_and_secret_fields(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _node_run(**{field: "must-not-persist"})


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        _node_run(started_at=NOW.replace(tzinfo=None))


def test_timestamps_must_use_utc_offset() -> None:
    non_utc = timezone(timedelta(hours=5))
    with pytest.raises(ValidationError, match="telemetry timestamps must be UTC"):
        _node_run(started_at=datetime(2026, 8, 6, 12, tzinfo=non_utc))


def test_call_requires_node_parent() -> None:
    with pytest.raises(ValidationError):
        ProviderCallRecord.model_validate(
            {
                "call_id": uuid4(),
                "purpose": CallPurpose.CHAT_COMPLETION,
                "requested_model": "test-model",
                "cache_status": CacheStatus.MISS,
                "started_at": NOW,
                "outcome": ProviderCallOutcome.STARTED,
                "attempt_count": 0,
            }
        )


def test_attempt_requires_logical_call_parent() -> None:
    with pytest.raises(ValidationError):
        ProviderAttemptRecord.model_validate(
            {
                "attempt_id": uuid4(),
                "attempt_number": 1,
                "provider": "openrouter",
                "requested_model": "test-model",
                "started_at": NOW,
                "outcome": ProviderAttemptOutcome.STARTED,
                "retry_reason": RetryReason.NOT_APPLICABLE,
            }
        )


def test_cache_hit_logical_call_has_zero_attempts() -> None:
    node = _node_run()
    call = _call(
        node.node_run_id,
        cache_status=CacheStatus.HIT,
        attempt_count=0,
        requested_model="test-model",
    )
    assert call.attempt_count == 0


def test_non_cache_hit_cannot_succeed_without_an_attempt() -> None:
    node = _node_run()
    with pytest.raises(ValidationError):
        _call(node.node_run_id, cache_status=CacheStatus.MISS, attempt_count=0)


def test_attempt_number_is_positive() -> None:
    node = _node_run()
    call = _call(node.node_run_id)
    with pytest.raises(ValidationError):
        _attempt(call.call_id, attempt_number=0)


def test_missing_usage_and_cost_remain_unavailable() -> None:
    node = _node_run()
    call = _call(node.node_run_id)
    attempt = _attempt(
        call.call_id,
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
    )
    assert attempt.prompt_tokens is None
    assert attempt.completion_tokens is None
    assert attempt.cost_usd is None


def test_artifact_reference_is_generic_and_immutable() -> None:
    artifact = ArtifactRef(
        artifact_type="research_bundle",
        artifact_id="bundle-AAPL-2026-08-06",
        version="sha256:abc123",
    )
    with pytest.raises(ValidationError):
        artifact.version = "changed"


def test_serialization_is_deterministic_and_json_safe() -> None:
    node_run_id = UUID("13a7cc1a-57d5-4c58-b147-47db96c87861")
    record = _node_run(node_run_id=node_run_id)
    first = record.model_dump_json()
    second = record.model_dump_json()
    assert first == second
    assert '"node_run_id":"13a7cc1a-57d5-4c58-b147-47db96c87861"' in first
    assert '"started_at":"2026-08-06T12:00:00Z"' in first


def test_enums_reject_unknown_states() -> None:
    with pytest.raises(ValidationError):
        _node_run(outcome="mostly_succeeded")


def test_emit_telemetry_reports_failure_without_raising() -> None:
    observed: list[NodeRunRecord] = []
    failures: list[tuple[UUID, str]] = []

    class BrokenObserver:
        def observe(self, record: TelemetryRecord) -> None:
            assert isinstance(record, NodeRunRecord)
            observed.append(record)
            raise RuntimeError("database unavailable: secret detail")

    observer: TelemetryObserver = BrokenObserver()
    node = _node_run()

    delivered = emit_telemetry(
        observer,
        node,
        on_failure=lambda record_id, error_type: failures.append((record_id, error_type)),
    )

    assert delivered is False
    assert observed == [node]
    assert failures == [(node.node_run_id, "RuntimeError")]
