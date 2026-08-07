"""Thread-safe per-run usage accumulator (#663)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessage as OpenAIMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails

from digigraph import llm_client, usage
from digillm import CallPurpose, NoArtifactReason, set_telemetry_observer
from digillm import client as digillm_client


@pytest.fixture(autouse=True)
def _clean():
    usage.reset()
    yield
    usage.reset()


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
