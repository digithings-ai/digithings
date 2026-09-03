"""Contract tests for provider telemetry records and fail-soft observation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from openai import APITimeoutError
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessage as OpenAIMessage
from openai.types.chat.chat_completion import Choice
from pydantic import ValidationError

import digillm
from digillm import client as client_mod
from digillm.telemetry import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
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


class AttemptCollector(list[ProviderAttemptRecord]):
    def observe(self, record: TelemetryRecord) -> None:
        if isinstance(record, ProviderAttemptRecord):
            self.append(record)


class TelemetryCollector(list[TelemetryRecord]):
    def observe(self, record: TelemetryRecord) -> None:
        self.append(record)


@pytest.fixture(autouse=True)
def _clean_client_state(monkeypatch: pytest.MonkeyPatch) -> None:
    previous_observer = client_mod._telemetry_observer
    digillm.clear_caches()
    digillm.set_telemetry_observer(None)
    for name in ("OPENAI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield
    digillm.set_telemetry_observer(previous_observer)
    digillm.clear_caches()


def _completion(
    content: str,
    *,
    model: str = "served-model",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> ChatCompletion:
    response = ChatCompletion(
        id="cmpl-telemetry",
        created=0,
        model=model,
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=OpenAIMessage(role="assistant", content=content),
            )
        ],
    )
    if prompt_tokens is not None or completion_tokens is not None:
        response.usage = SimpleNamespace(  # type: ignore[assignment]
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_extra={},
        )
    return response


def test_contracts_are_exported_from_package() -> None:
    assert digillm.NodeRunRecord is NodeRunRecord
    assert digillm.ProviderCallRecord is ProviderCallRecord
    assert digillm.ProviderAttemptRecord is ProviderAttemptRecord
    assert digillm.TelemetryObserver is TelemetryObserver
    assert digillm.emit_telemetry is emit_telemetry
    assert digillm.set_telemetry_observer is client_mod.set_telemetry_observer


def _node_run(**overrides: object) -> NodeRunRecord:
    values: dict[str, object] = {
        "node_run_id": uuid4(),
        "run_id": "dashboard-2026-08-06-attempt-1",
        "node_name": "research.phase_1",
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
        "no_artifact_reason": NoArtifactReason.CONSUMED_INLINE,
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


def test_fanout_key_is_absent_by_default() -> None:
    assert _node_run().fanout_key is None


@pytest.mark.parametrize("value", ("", "f" * 201))
def test_fanout_key_rejects_empty_and_overlong_labels(value: str) -> None:
    with pytest.raises(ValidationError):
        _node_run(fanout_key=value)


def test_fanout_key_accepts_the_bound() -> None:
    assert _node_run(fanout_key="f" * 200).fanout_key == "f" * 200


# "ticker" is listed deliberately: `fanout_key` is an opaque producer-supplied label, and
# DigiLLM must never grow dashboard vocabulary of its own. extra="forbid" turns that anti-goal
# into a test rather than prose.
@pytest.mark.parametrize("field", ("prompt", "response", "api_key", "raw_exception", "ticker"))
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


def test_successful_call_requires_exactly_one_artifact_disposition() -> None:
    node = _node_run()
    with pytest.raises(ValidationError, match="either artifacts or one no-artifact reason"):
        _call(node.node_run_id, no_artifact_reason=None)
    with pytest.raises(ValidationError, match="either artifacts or one no-artifact reason"):
        _call(
            node.node_run_id,
            artifacts=(
                ArtifactRef(
                    artifact_type="research_bundle",
                    artifact_id="bundle-1",
                    version="v1",
                ),
            ),
            no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
        )


def test_failed_call_requires_sanitized_type_and_failure_disposition() -> None:
    node = _node_run()
    failed = _call(
        node.node_run_id,
        cache_status=CacheStatus.BYPASSED,
        outcome=ProviderCallOutcome.FAILED,
        error_type="RuntimeError",
        no_artifact_reason=NoArtifactReason.CALL_FAILED,
    )
    assert failed.error_type == "RuntimeError"
    with pytest.raises(ValidationError, match="sanitized error type"):
        _call(
            node.node_run_id,
            cache_status=CacheStatus.BYPASSED,
            outcome=ProviderCallOutcome.FAILED,
            no_artifact_reason=NoArtifactReason.CALL_FAILED,
        )


def test_cost_usd_rejects_nan_and_infinity() -> None:
    """Postgres CHECK (cost_usd >= 0) admits NaN; Pydantic must not (#1989)."""
    node = _node_run()
    call = _call(node.node_run_id)
    with pytest.raises(ValidationError):
        _attempt(call.call_id, cost_usd=Decimal("NaN"))
    with pytest.raises(ValidationError):
        _attempt(call.call_id, cost_usd=Decimal("Infinity"))


def test_provider_identifiers_have_defensive_length_bounds() -> None:
    node = _node_run()
    with pytest.raises(ValidationError):
        _call(node.node_run_id, requested_model="m" * 257)
    with pytest.raises(ValidationError):
        _call(
            node.node_run_id,
            cache_status=CacheStatus.BYPASSED,
            outcome=ProviderCallOutcome.FAILED,
            error_type="E" * 201,
            no_artifact_reason=NoArtifactReason.CALL_FAILED,
        )
    call = _call(node.node_run_id)
    with pytest.raises(ValidationError):
        _attempt(call.call_id, requested_model="m" * 257)
    with pytest.raises(ValidationError):
        _attempt(call.call_id, error_type="E" * 201)


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


def test_completion_emits_one_record_per_repository_retry() -> None:
    timeout = APITimeoutError(request=MagicMock())
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [timeout, _completion("recovered")]
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod, "_sleep_transient_retry", return_value=5.0),
    ):
        result = digillm.completion(
            "openrouter/requested-model",
            [{"role": "user", "content": "hello"}],
        )

    assert result.choices[0].message.content == "recovered"
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert len({attempt.call_id for attempt in attempts}) == 1
    assert [attempt.outcome for attempt in attempts] == [
        ProviderAttemptOutcome.FAILED,
        ProviderAttemptOutcome.SUCCEEDED,
    ]
    assert [attempt.retry_reason for attempt in attempts] == [
        RetryReason.NOT_APPLICABLE,
        RetryReason.TIMEOUT,
    ]
    assert attempts[0].error_type == "APITimeoutError"
    assert attempts[1].requested_model == "openrouter/requested-model"
    assert attempts[1].served_model == "served-model"
    assert attempts[1].prompt_tokens is None
    assert attempts[1].completion_tokens is None
    assert attempts[1].cost_usd is None


def test_exhausted_transient_retries_emit_every_attempt_and_preserve_error() -> None:
    failures = [APITimeoutError(request=MagicMock()) for _ in range(12)]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = failures
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod, "_sleep_transient_retry", return_value=5.0),
        pytest.raises(APITimeoutError) as caught,
    ):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hello"}])

    assert caught.value is failures[-1]
    assert [attempt.attempt_number for attempt in attempts] == list(range(1, 13))
    assert len({attempt.call_id for attempt in attempts}) == 1
    assert attempts[0].retry_reason is RetryReason.NOT_APPLICABLE
    assert all(attempt.retry_reason is RetryReason.TIMEOUT for attempt in attempts[1:])


def test_empty_response_retry_keeps_one_call_and_monotonic_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_MAX", 1)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _delay: None)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _completion(""),
        _completion("healed"),
    ]
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.completion(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
        )

    assert result.choices[0].message.content == "healed"
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert len({attempt.call_id for attempt in attempts}) == 1
    assert attempts[1].retry_reason is RetryReason.EMPTY_RESPONSE


def test_terminal_error_is_preserved_and_only_its_type_is_recorded() -> None:
    failure = ValueError("secret response body")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = failure
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(ValueError) as caught,
    ):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hello"}])

    assert caught.value is failure
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.FAILED
    assert attempts[0].error_type == "ValueError"
    assert "secret response body" not in attempts[0].model_dump_json()


def test_chat_request_cancellation_closes_attempt_and_logical_call() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = asyncio.CancelledError()
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.INITIAL_GENERATION,
            no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hello"}])

    call = next(record for record in records if isinstance(record, ProviderCallRecord))
    attempt = next(record for record in records if isinstance(record, ProviderAttemptRecord))
    assert call.outcome is ProviderCallOutcome.CANCELLED
    assert call.attempt_count == 1
    assert attempt.call_id == call.call_id
    assert attempt.outcome is ProviderAttemptOutcome.CANCELLED
    assert attempt.error_type is None


def test_broken_attempt_observer_does_not_change_completion() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("unchanged")

    class BrokenObserver:
        def observe(self, _record: TelemetryRecord) -> None:
            raise RuntimeError("telemetry unavailable")

    digillm.set_telemetry_observer(BrokenObserver())
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.completion(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
        )
    assert result.choices[0].message.content == "unchanged"


def test_cache_hit_does_not_emit_a_second_physical_attempt() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("cached")
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        first = digillm.completion("gpt-4o-mini", messages)
        second = digillm.completion("gpt-4o-mini", messages)

    assert first.choices[0].message.content == "cached"
    assert second.choices[0].message.content == "cached"
    assert fake_client.chat.completions.create.call_count == 1
    assert len(attempts) == 1


def test_cache_miss_and_hit_emit_reconciled_logical_calls() -> None:
    node_run_id = uuid4()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("cached")
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=node_run_id,
            purpose=CallPurpose.INITIAL_GENERATION,
            no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            first = digillm.completion("gpt-4o-mini", messages)
        with digillm.provider_call_context(
            node_run_id=node_run_id,
            purpose=CallPurpose.INITIAL_GENERATION,
            no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            second = digillm.completion("gpt-4o-mini", messages)

    assert first.choices[0].message.content == "cached"
    assert second.choices[0].message.content == "cached"
    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    assert len(calls) == 2
    assert [call.cache_status for call in calls] == [CacheStatus.MISS, CacheStatus.HIT]
    assert [call.attempt_count for call in calls] == [1, 0]
    assert calls[0].call_id == attempts[0].call_id
    assert calls[1].call_id != calls[0].call_id
    assert all(call.node_run_id == node_run_id for call in calls)
    assert all(call.purpose is CallPurpose.INITIAL_GENERATION for call in calls)
    assert fake_client.chat.completions.create.call_count == 1


def test_completion_emits_immutable_artifact_reference_without_payloads() -> None:
    artifact = ArtifactRef(
        artifact_type="research_bundle",
        artifact_id="bundle-1",
        version="sha256:abc123",
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("private response")
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.STRUCTURED_COMPLETION,
            artifacts=(artifact,),
        ):
            digillm.completion(
                "gpt-4o-mini",
                [{"role": "user", "content": "private prompt"}],
            )

    call = next(record for record in records if isinstance(record, ProviderCallRecord))
    serialized = call.model_dump_json()
    assert call.artifacts == (artifact,)
    assert call.no_artifact_reason is None
    assert "private prompt" not in serialized
    assert "private response" not in serialized


def test_unrelated_top_level_calls_do_not_share_parentage_or_attempt_counters() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _completion("first"),
        _completion("second"),
    ]
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        for content in ("first request", "second request"):
            with digillm.provider_call_context(
                node_run_id=uuid4(),
                purpose=CallPurpose.INITIAL_GENERATION,
                no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
            ):
                digillm.completion(
                    "gpt-4o-mini",
                    [{"role": "user", "content": content}],
                )

    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    assert len(calls) == 2
    assert len({call.call_id for call in calls}) == 2
    assert all(call.parent_call_id is None for call in calls)
    assert [call.attempt_count for call in calls] == [1, 1]
    assert [attempt.attempt_number for attempt in attempts] == [1, 1]
    assert [attempt.call_id for attempt in attempts] == [call.call_id for call in calls]


def test_tool_follow_up_links_to_selection_call_without_sharing_attempt_counter() -> None:
    function = SimpleNamespace(name="lookup", arguments='{"query":"rates"}')
    tool_call = SimpleNamespace(id="call-1", function=function)
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    selection = SimpleNamespace(choices=[SimpleNamespace(message=message)], model="served-model")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [selection, _completion("final")]
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.TOOL_SELECTION,
            no_artifact_reason=digillm.NoArtifactReason.TOOL_DISPATCH,
            follow_up_purpose=CallPurpose.TOOL_FOLLOW_UP,
            follow_up_no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            result = digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "research rates"}],
                [{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
                execute_tool=lambda _name, _arguments: "grounded",
            )

    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    assert result == "final"
    assert [call.purpose for call in calls] == [
        CallPurpose.TOOL_SELECTION,
        CallPurpose.TOOL_FOLLOW_UP,
    ]
    assert calls[0].parent_call_id is None
    assert calls[1].parent_call_id == calls[0].call_id
    assert [call.attempt_count for call in calls] == [1, 1]
    assert [attempt.attempt_number for attempt in attempts] == [1, 1]
    assert [call.no_artifact_reason for call in calls] == [
        digillm.NoArtifactReason.TOOL_DISPATCH,
        digillm.NoArtifactReason.CONSUMED_INLINE,
    ]


def test_process_observer_receives_attempt_from_worker_thread() -> None:
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("threaded")

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(
                digillm.completion,
                "gpt-4o-mini",
                [{"role": "user", "content": "hello"}],
            ).result()

    assert result.choices[0].message.content == "threaded"
    assert len(attempts) == 1


def _stream_chunk(
    content: str | None,
    *,
    model: str = "stream-served-model",
    usage: object | None = None,
) -> MagicMock:
    delta = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
    chunk = MagicMock()
    chunk.choices = [SimpleNamespace(delta=delta)] if content is not None else []
    chunk.model = model
    chunk.usage = usage
    return chunk


def test_stream_attempt_finalizes_usage_after_exhaustion() -> None:
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=3, model_extra={})
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = [
        _stream_chunk("streamed"),
        _stream_chunk(None, usage=usage),
        _stream_chunk(None),
    ]
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
            [],
            execute_tool=lambda *_args: "",
            stream_deltas=True,
        )

    assert result == "streamed"
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.SUCCEEDED
    assert attempts[0].served_model == "stream-served-model"
    assert attempts[0].prompt_tokens == 12
    assert attempts[0].completion_tokens == 3
    assert attempts[0].cost_usd is None


def test_stream_cancellation_closes_attempt_and_propagates() -> None:
    def cancelling_stream() -> object:
        yield _stream_chunk("partial")
        raise GeneratorExit

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = cancelling_stream()
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(GeneratorExit),
    ):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
            [],
            execute_tool=lambda *_args: "",
            stream_deltas=True,
        )

    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.CANCELLED
    assert attempts[0].error_type is None


def test_asyncio_cancellation_closes_stream_attempt_and_propagates() -> None:
    def cancelling_stream() -> object:
        yield _stream_chunk("partial")
        raise asyncio.CancelledError

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = cancelling_stream()
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(asyncio.CancelledError),
    ):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
            [],
            execute_tool=lambda *_args: "",
            stream_deltas=True,
        )

    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.CANCELLED
    assert attempts[0].error_type is None


def test_stream_iteration_failure_closes_attempt_and_preserves_error() -> None:
    failure = RuntimeError("private stream fragment")

    def failing_stream() -> object:
        yield _stream_chunk("partial")
        raise failure

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = failing_stream()
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(RuntimeError) as caught,
    ):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
            [],
            execute_tool=lambda *_args: "",
            stream_deltas=True,
        )

    assert caught.value is failure
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.FAILED
    assert attempts[0].error_type == "RuntimeError"
    assert "private stream fragment" not in attempts[0].model_dump_json()


def test_stream_callback_failure_is_not_misattributed_to_provider() -> None:
    failure = RuntimeError("consumer callback failed")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = [_stream_chunk("partial")]
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(RuntimeError) as caught,
    ):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.TOOL_SELECTION,
            no_artifact_reason=NoArtifactReason.TOOL_DISPATCH,
        ):
            digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "hello"}],
                [],
                execute_tool=lambda *_args: "",
                on_tool_step=lambda *_args: (_ for _ in ()).throw(failure),
                stream_deltas=True,
            )

    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    assert caught.value is failure
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.CANCELLED
    assert attempts[0].error_type is None
    assert len(calls) == 1
    assert calls[0].outcome is ProviderCallOutcome.CANCELLED
    assert calls[0].no_artifact_reason is NoArtifactReason.CALL_CANCELLED
    assert calls[0].error_type is None


@pytest.mark.parametrize(
    ("search", "tool_type"),
    ((digillm.web_search, "web_search"), (digillm.x_search, "x_search")),
)
def test_xai_search_transports_emit_attempts(
    monkeypatch: pytest.MonkeyPatch,
    search: object,
    tool_type: str,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    response = SimpleNamespace(
        model="grok-served",
        output_text="result",
        output=[],
        usage=SimpleNamespace(input_tokens=8, output_tokens=2, model_extra={}),
    )
    fake_client = MagicMock()
    fake_client.responses.create.return_value = response
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = search("xai/grok-4", "query")  # type: ignore[operator]

    assert result == ("result", [])
    assert fake_client.responses.create.call_args.kwargs["tools"][0]["type"] == tool_type
    assert len(attempts) == 1
    assert attempts[0].provider == "xai"
    assert attempts[0].requested_model == "xai/grok-4"
    assert attempts[0].served_model == "grok-served"
    assert attempts[0].prompt_tokens == 8
    assert attempts[0].completion_tokens == 2


@pytest.mark.parametrize(
    ("search", "purpose"),
    (
        (digillm.web_search, CallPurpose.WEB_GROUNDING),
        (digillm.x_search, CallPurpose.X_GROUNDING),
    ),
)
def test_xai_grounding_emits_one_logical_call(
    monkeypatch: pytest.MonkeyPatch,
    search: object,
    purpose: CallPurpose,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    response = SimpleNamespace(
        model="grok-served",
        output_text="result",
        output=[],
        usage=SimpleNamespace(input_tokens=8, output_tokens=2, model_extra={}),
    )
    fake_client = MagicMock()
    fake_client.responses.create.return_value = response
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=purpose,
            no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            result = search("xai/grok-4", "query")  # type: ignore[operator]

    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    assert result == ("result", [])
    assert len(calls) == 1
    assert calls[0].purpose is purpose
    assert calls[0].cache_status is CacheStatus.BYPASSED
    assert calls[0].attempt_count == 1
    assert attempts[0].call_id == calls[0].call_id


def test_openrouter_grounding_nested_completion_is_one_logical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion(
        "fact [source](https://example.com)"
    )
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.WEB_GROUNDING,
            no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            result = digillm.openrouter_web_search(
                "openrouter/perplexity/sonar",
                "query",
            )

    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    attempts = [record for record in records if isinstance(record, ProviderAttemptRecord)]
    assert result == ("fact [source](https://example.com)", ["https://example.com"])
    assert len(calls) == 1
    assert calls[0].purpose is CallPurpose.WEB_GROUNDING
    assert calls[0].attempt_count == 1
    assert attempts[0].call_id == calls[0].call_id


def test_xai_search_failure_emits_attempt_and_preserves_fail_soft_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = RuntimeError("private provider response")
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.web_search("xai/grok-4", "query")

    assert result is None
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.FAILED
    assert attempts[0].error_type == "RuntimeError"
    assert "private provider response" not in attempts[0].model_dump_json()


def test_responses_request_cancellation_closes_attempt_and_logical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = asyncio.CancelledError()
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.WEB_GROUNDING,
            no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        digillm.web_search("xai/grok-4", "query")

    call = next(record for record in records if isinstance(record, ProviderCallRecord))
    attempt = next(record for record in records if isinstance(record, ProviderAttemptRecord))
    assert call.outcome is ProviderCallOutcome.CANCELLED
    assert call.attempt_count == 1
    assert attempt.call_id == call.call_id
    assert attempt.outcome is ProviderAttemptOutcome.CANCELLED
    assert attempt.error_type is None


def test_xai_grounding_failure_emits_sanitized_logical_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = RuntimeError("private provider response")
    records = TelemetryCollector()
    digillm.set_telemetry_observer(records)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.provider_call_context(
            node_run_id=uuid4(),
            purpose=CallPurpose.WEB_GROUNDING,
            no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
        ):
            result = digillm.web_search("xai/grok-4", "query")

    calls = [record for record in records if isinstance(record, ProviderCallRecord)]
    assert result is None
    assert len(calls) == 1
    assert calls[0].outcome is ProviderCallOutcome.FAILED
    assert calls[0].no_artifact_reason is digillm.NoArtifactReason.CALL_FAILED
    assert calls[0].error_type == "RuntimeError"
    assert "private provider response" not in calls[0].model_dump_json()


def test_malformed_usage_evidence_cannot_change_search_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MalformedResponse:
        model = "grok-served"
        output_text = "result"
        output: list[object] = []

        @property
        def usage(self) -> object:
            raise RuntimeError("malformed optional evidence")

    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    fake_client = MagicMock()
    fake_client.responses.create.return_value = MalformedResponse()
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.web_search("xai/grok-4", "query")

    assert result == ("result", [])
    assert len(attempts) == 1
    assert attempts[0].prompt_tokens is None
    assert attempts[0].completion_tokens is None
    assert attempts[0].cost_usd is None


def test_openrouter_search_is_not_double_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion(
        "fact [source](https://example.com)"
    )
    attempts = AttemptCollector()
    digillm.set_telemetry_observer(attempts)

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        result = digillm.openrouter_web_search("openrouter/perplexity/sonar", "query")

    assert result == ("fact [source](https://example.com)", ["https://example.com"])
    assert fake_client.chat.completions.create.call_count == 1
    assert len(attempts) == 1
