"""Thread-safe per-run usage accumulator (#663)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessage as OpenAIMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails

from digigraph import llm_client, usage
from digillm import (
    CallPurpose,
    NoArtifactReason,
    NodeRunOutcome,
    NodeRunRecord,
    set_telemetry_observer,
)
from digillm import client as digillm_client


@pytest.fixture(autouse=True)
def _clean():
    usage.reset()
    yield
    usage.reset()


def _node_record(**overrides: object) -> NodeRunRecord:
    now = datetime.now(tz=timezone.utc)
    fields: dict[str, object] = {
        "node_run_id": uuid4(),
        "run_id": "r",
        "node_name": "n",
        "outcome": NodeRunOutcome.SUCCEEDED,
        "started_at": now,
        "finished_at": now,
    }
    fields.update(overrides)
    return NodeRunRecord(**fields)  # type: ignore[arg-type]


@pytest.mark.unit
def test_detailed_observer_retains_node_records() -> None:
    usage.start()
    record = _node_record()
    # Delivered through the production observer, not observe_telemetry directly, so the test
    # fails if the sink is wired anywhere other than the real path.
    usage.DETAILED_USAGE_OBSERVER.observe(record)
    assert usage.node_runs_snapshot() == [record]


@pytest.mark.unit
def test_node_records_cleared_by_start_and_reset() -> None:
    usage.start()
    usage.DETAILED_USAGE_OBSERVER.observe(_node_record())
    usage.start()
    assert usage.node_runs_snapshot() == []
    usage.DETAILED_USAGE_OBSERVER.observe(_node_record())
    usage.reset()
    assert usage.node_runs_snapshot() == []


@pytest.mark.unit
def test_record_snapshots_return_copies() -> None:
    usage.start()
    usage.DETAILED_USAGE_OBSERVER.observe(_node_record())
    usage.node_runs_snapshot().clear()
    assert len(usage.node_runs_snapshot()) == 1
    assert usage.provider_calls_snapshot() == []
    assert usage.provider_attempts_snapshot() == []


@pytest.mark.unit
def test_start_stores_the_run_id_verbatim() -> None:
    usage.start(run_id="gha-1978")
    assert usage.active_run_id() == "gha-1978"


@pytest.mark.unit
@pytest.mark.parametrize("value", (None, "", "   "))
def test_blank_or_absent_run_id_leaves_the_run_unidentified(value: str | None) -> None:
    usage.start() if value is None else usage.start(run_id=value)
    assert usage.active_run_id() is None


@pytest.mark.unit
def test_reset_clears_the_run_id() -> None:
    usage.start(run_id="gha-1978")
    usage.reset()
    assert usage.active_run_id() is None


@pytest.mark.unit
def test_node_scope_without_a_run_id_yields_nothing_and_emits_nothing() -> None:
    usage.start()
    with usage.node_run_scope("n") as node_run_id:
        assert node_run_id is None
        assert usage.provider_call_metadata()[0] is None
    assert usage.node_runs_snapshot() == []


@pytest.mark.unit
def test_node_scope_labels_calls_and_emits_one_terminal_record() -> None:
    usage.start(run_id="r")
    with usage.node_run_scope("n", fanout_key="AAPL") as node_run_id:
        assert node_run_id is not None
        assert usage.provider_call_metadata()[0] == node_run_id
    assert usage.provider_call_metadata()[0] is None  # token reset in the finally
    (record,) = usage.node_runs_snapshot()
    assert (record.node_run_id, record.run_id, record.node_name, record.fanout_key) == (
        node_run_id,
        "r",
        "n",
        "AAPL",
    )
    assert record.outcome is NodeRunOutcome.SUCCEEDED
    assert record.finished_at is not None


@pytest.mark.unit
def test_node_scope_records_failure_and_reraises_the_original_error() -> None:
    usage.start(run_id="r")
    with pytest.raises(RuntimeError, match="boom"):
        with usage.node_run_scope("n"):
            raise RuntimeError("boom")
    (record,) = usage.node_runs_snapshot()
    assert record.outcome is NodeRunOutcome.FAILED
    assert record.finished_at is not None


@pytest.mark.unit
def test_node_scope_never_replaces_the_node_error_with_a_telemetry_error() -> None:
    # An over-length key would otherwise raise ValidationError out of the `finally` and mask
    # the node's real exception — telemetry inventing a new failure on the failure path.
    usage.start(run_id="r")
    with pytest.raises(RuntimeError, match="boom"):
        with usage.node_run_scope("n", fanout_key="x" * 5000):
            raise RuntimeError("boom")
    (record,) = usage.node_runs_snapshot()
    assert record.fanout_key is not None
    assert len(record.fanout_key) == 200


@pytest.mark.unit
@pytest.mark.parametrize("value", ("", "   "))
def test_blank_fanout_key_becomes_absent_not_empty_string(value: str) -> None:
    usage.start(run_id="r")
    with usage.node_run_scope("n", fanout_key=value):
        pass
    assert usage.node_runs_snapshot()[0].fanout_key is None


@pytest.mark.unit
def test_nested_call_context_inherits_the_node_run_id() -> None:
    usage.start(run_id="r")
    with usage.node_run_scope("n") as node_run_id:
        with usage.call_context(phase="p", operation="o"):
            inner = usage.provider_call_metadata()[0]
    assert inner is not None
    assert inner == node_run_id


@pytest.mark.unit
def test_start_still_accepts_no_arguments() -> None:
    # Pins the operator scripts (validate-providers.py, openrouter_diagnose.py) and chain.py
    # against a future required-argument regression.
    usage.start()
    assert usage.is_active() is True


@pytest.mark.unit
def test_records_only_when_active():
    # No-op until a run starts.
    usage.record(kind="chat", model="x", prompt_tokens=10, completion_tokens=5)
    assert usage.snapshot()["llm_calls"] == 0

    usage.start()
    usage.record(kind="chat", model="xai/grok-4.3", prompt_tokens=10, completion_tokens=5)
    snap = usage.snapshot()
    assert snap["llm_calls"] == 1
    assert snap["prompt_tokens"] == 10
    assert snap["completion_tokens"] == 5
    assert snap["total_tokens"] == 15


@pytest.mark.unit
def test_aggregates_chat_and_search():
    usage.start()
    usage.record(kind="chat", model="xai/grok-4.3", prompt_tokens=100, completion_tokens=40)
    usage.record(kind="chat", model="xai/grok-4.3", prompt_tokens=50, completion_tokens=20)
    usage.record(kind="web_search", model="xai/grok-4.3", sources=8, ok=True)
    usage.record(kind="x_search", model="xai/grok-4.3", sources=16, ok=True)
    usage.record(kind="web_search", model="xai/grok-4.3", sources=0, ok=False)
    snap = usage.snapshot()
    assert snap["llm_calls"] == 2
    assert snap["total_tokens"] == 210
    assert snap["search_calls"] == 3
    assert snap["sources_used"] == 24
    assert snap["grounding_ok"] == 2
    assert snap["grounding_failed"] == 1
    assert snap["by_kind"]["x_search"]["sources"] == 16


@pytest.mark.unit
def test_aggregates_cached_tokens_and_tolerates_unknown_fields():
    usage.start()
    # cached_tokens (prompt-cache hits) aggregates into totals + by_kind; an unknown future
    # field is tolerated (forward-compatible observer) rather than raising.
    usage.record(
        kind="chat",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=1000,
        completion_tokens=50,
        cached_tokens=700,
    )
    usage.record(
        kind="chat",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=200,
        completion_tokens=10,
        cached_tokens=100,
        some_future_field="ignored",
    )
    snap = usage.snapshot()
    assert snap["cached_tokens"] == 800
    assert snap["by_kind"]["chat"]["cached_tokens"] == 800
    # Calls that never report cached_tokens default to 0 (no KeyError).
    usage.record(kind="web_search", model="xai/grok-4-fast", sources=4, ok=True)
    assert usage.snapshot()["cached_tokens"] == 800


@pytest.mark.unit
def test_aggregates_cost_usd():
    usage.start()
    # Actual USD charged (OpenRouter usage.cost) sums into run-level cost_usd + by_kind.
    usage.record(kind="chat", model="m", prompt_tokens=100, completion_tokens=40, cost=0.0123)
    usage.record(kind="chat", model="m", prompt_tokens=50, completion_tokens=20, cost=0.0077)
    # A call with no cost reported defaults to 0.0 (no KeyError, no skew).
    usage.record(kind="web_search", model="m", sources=4, ok=True)
    snap = usage.snapshot()
    assert snap["cost_usd"] == pytest.approx(0.02)
    assert snap["by_kind"]["chat"]["cost"] == pytest.approx(0.02)
    assert snap["by_kind"]["web_search"]["cost"] == 0.0


@pytest.mark.unit
def test_detailed_successful_call_projection_matches_aggregate() -> None:
    response = ChatCompletion(
        id="cmpl-parity",
        created=0,
        model="served-model",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=OpenAIMessage(role="assistant", content="result"),
            )
        ],
    )
    response.usage = CompletionUsage(
        prompt_tokens=21,
        completion_tokens=8,
        total_tokens=29,
        prompt_tokens_details=PromptTokensDetails(cached_tokens=5),
        cost="0.0042",
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = response
    usage.start()
    set_telemetry_observer(usage.DETAILED_USAGE_OBSERVER)

    with (
        usage.call_context(node_run_id=uuid4()),
        usage.logical_call_context(
            purpose=CallPurpose.INITIAL_GENERATION,
            no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
        ),
        patch.object(digillm_client, "get_client_for_model", return_value=fake_client),
    ):
        llm_client.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])

    aggregate = usage.snapshot()
    detailed = usage.detailed_usage_projection()
    assert detailed == {
        "llm_calls": aggregate["llm_calls"],
        "prompt_tokens": aggregate["prompt_tokens"],
        "completion_tokens": aggregate["completion_tokens"],
        "cost_usd": aggregate["cost_usd"],
        "search_calls": aggregate["search_calls"],
    }


@pytest.mark.unit
def test_detailed_projection_keeps_unavailable_provider_evidence_null() -> None:
    response = ChatCompletion(
        id="cmpl-unavailable",
        created=0,
        model="served-model",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=OpenAIMessage(role="assistant", content="result"),
            )
        ],
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = response
    usage.start()
    set_telemetry_observer(usage.DETAILED_USAGE_OBSERVER)

    with (
        usage.call_context(node_run_id=uuid4()),
        patch.object(digillm_client, "get_client_for_model", return_value=fake_client),
    ):
        llm_client.completion(
            "gpt-4o-mini",
            [{"role": "user", "content": "unavailable usage"}],
        )

    assert usage.detailed_usage_projection() == {
        "llm_calls": 1,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost_usd": None,
        "search_calls": 0,
    }


@pytest.mark.unit
def test_detailed_grounding_projection_matches_aggregate_token_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    response = SimpleNamespace(
        model="grok-served",
        output_text="grounded",
        output=[],
        usage=SimpleNamespace(
            input_tokens=13,
            output_tokens=4,
            cost="0.0031",
            model_extra={},
        ),
    )
    fake_client = MagicMock()
    fake_client.responses.create.return_value = response
    usage.start()
    set_telemetry_observer(usage.DETAILED_USAGE_OBSERVER)

    with (
        usage.call_context(node_run_id=uuid4()),
        patch.object(digillm_client, "get_client_for_model", return_value=fake_client),
    ):
        llm_client.web_search("xai/grok-4", "ground this")

    aggregate = usage.snapshot()
    detailed = usage.detailed_usage_projection()
    assert detailed["llm_calls"] == aggregate["llm_calls"] == 0
    assert detailed["search_calls"] == aggregate["search_calls"] == 1
    assert detailed["prompt_tokens"] == aggregate["prompt_tokens"] == 0
    assert detailed["completion_tokens"] == aggregate["completion_tokens"] == 0
    assert detailed["cost_usd"] == aggregate["cost_usd"] == 0.0031


@pytest.mark.unit
def test_reset_clears_and_deactivates():
    usage.start()
    usage.record(kind="chat", model="x", prompt_tokens=1, completion_tokens=1)
    usage.reset()
    assert usage.is_active() is False
    assert usage.snapshot()["llm_calls"] == 0


@pytest.mark.unit
def test_records_ordered_phase_scoped_events_without_call_bodies():
    usage.start()
    with usage.call_context(
        phase="sector-technology",
        operation="SectorReport",
        document_key="sector-technology",
    ):
        usage.record(
            kind="chat",
            model="deepseek/deepseek-v4-flash",
            prompt_tokens=120,
            completion_tokens=30,
            cached_tokens=80,
            cost=0.0012,
            duration_ms=425,
            retry_count=1,
        )
        usage.record_tool_call(
            name="get_price_technicals",
            arguments={
                "ticker": "XLK",
                "api_key": "must-not-leak",
                "private_key": "also-must-not-leak",
                "jwt_claim": "nor-this",
            },
            duration_ms=18,
            ok=True,
            result={"ticker": "XLK", "close": 231.4},
        )

    events = usage.events_snapshot()
    assert [event["sequence"] for event in events] == [1, 2]
    assert events[0] == pytest.approx(
        {
            "sequence": 1,
            "kind": "model_call",
            "phase": "sector-technology",
            "operation": "SectorReport",
            "document_key": "sector-technology",
            "name": "deepseek/deepseek-v4-flash",
            "status": "ok",
            "duration_ms": 425,
            "retry_count": 1,
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "cached_tokens": 80,
            "cost_usd": 0.0012,
            "sources": 0,
            "input_summary": "Structured model request",
            "output_summary": "Model response returned",
            "call_id": None,
            "attempt_id": None,
            "node_run_id": None,
        }
    )
    assert events[1]["kind"] == "tool_call"
    assert events[1]["name"] == "get_price_technicals"
    assert events[1]["input_summary"] == "Arguments: ticker; 3 sensitive fields redacted"
    assert events[1]["output_summary"] == "Returned 2 fields"
    assert "api_key" not in str(events)
    assert "private_key" not in str(events)
    assert "jwt_claim" not in str(events)
    assert "231.4" not in str(events)


@pytest.mark.unit
def test_event_text_is_bounded_before_persistence():
    usage.start()
    with usage.call_context(
        phase="p" * 200,
        operation="o" * 300,
        document_key="d" * 700,
    ):
        usage.record_tool_call(
            name="n" * 400,
            arguments={f"field_{index:03d}": index for index in range(100)},
        )

    event = usage.events_snapshot()[0]
    assert len(event["phase"]) == 120
    assert len(event["operation"]) == 200
    assert len(event["document_key"]) == 500
    assert len(event["name"]) == 255
    assert len(event["input_summary"]) == 500


@pytest.mark.unit
def test_missing_usage_stays_null_on_glass_box_events() -> None:
    """WP1 invariant: unavailable tokens/cost must not become fabricated zeros (#2763)."""
    usage.start()
    call_id = uuid4()
    attempt_id = uuid4()
    node_run_id = uuid4()
    with usage.call_context(node_run_id=node_run_id, phase="macro", operation="MacroReport"):
        usage.record(
            kind="chat",
            model="openrouter/auto",
            prompt_tokens=None,
            completion_tokens=None,
            cached_tokens=None,
            cost=None,
            call_id=call_id,
            attempt_id=attempt_id,
        )

    event = usage.events_snapshot()[0]
    assert event["prompt_tokens"] is None
    assert event["completion_tokens"] is None
    assert event["cached_tokens"] is None
    assert event["cost_usd"] is None
    assert event["call_id"] == str(call_id)
    assert event["attempt_id"] == str(attempt_id)
    assert event["node_run_id"] == str(node_run_id)


@pytest.mark.unit
def test_explicit_zero_usage_is_preserved() -> None:
    usage.start()
    usage.record(
        kind="chat",
        model="m",
        prompt_tokens=0,
        completion_tokens=0,
        cached_tokens=0,
        cost=0.0,
    )
    event = usage.events_snapshot()[0]
    assert event["prompt_tokens"] == 0
    assert event["completion_tokens"] == 0
    assert event["cached_tokens"] == 0
    assert event["cost_usd"] == 0.0


def _mock_chat_response(content: str = "") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = "gpt-4o-mini"
    resp.usage = None
    return resp


@pytest.mark.unit
def test_empty_retry_records_per_model_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked empty-then-success completion increments usage.empty_retries (#1639)."""
    import digigraph.llm_client  # noqa: F401 — wires digillm observer to usage.record

    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setattr(digillm_client, "_EMPTY_RETRY_MAX", 2)
    monkeypatch.setattr(digillm_client.time, "sleep", lambda *_a, **_k: None)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_chat_response(""),
        _mock_chat_response("healed"),
    ]
    usage.start()
    with patch.object(digillm_client, "get_client_for_model", return_value=fake_client):
        digillm_client.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    snap = usage.snapshot()
    assert snap["empty_retries"] == {"total": 1, "by_model": {"gpt-4o-mini": 1}}
    assert snap["llm_calls"] == 1


@pytest.mark.unit
def test_empty_retry_keys_by_served_model_not_request_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter auto routes must attribute empty retries to ``r.model`` (#1639)."""
    import digigraph.llm_client  # noqa: F401 — wires digillm observer to usage.record

    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setattr(digillm_client, "_EMPTY_RETRY_MAX", 2)
    monkeypatch.setattr(digillm_client.time, "sleep", lambda *_a, **_k: None)

    empty = _mock_chat_response("")
    empty.model = "x-ai/grok-4"
    healed = _mock_chat_response("healed")
    healed.model = "x-ai/grok-4"

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [empty, healed]
    usage.start()
    with patch.object(digillm_client, "get_client_for_model", return_value=fake_client):
        digillm_client.completion("openrouter/auto", [{"role": "user", "content": "hi"}])
    snap = usage.snapshot()
    assert snap["empty_retries"] == {"total": 1, "by_model": {"x-ai/grok-4": 1}}
    assert "openrouter/auto" not in snap["empty_retries"]["by_model"]


@pytest.mark.unit
def test_empty_retries_default_zero_when_none_recorded() -> None:
    usage.start()
    assert usage.snapshot()["empty_retries"] == {"total": 0, "by_model": {}}
