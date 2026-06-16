"""Thread-safe per-run usage accumulator (#663)."""

from __future__ import annotations

import pytest

from digigraph import usage


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
def test_reset_clears_and_deactivates():
    usage.start()
    usage.record(kind="chat", model="x", prompt_tokens=1, completion_tokens=1)
    usage.reset()
    assert usage.is_active() is False
    assert usage.snapshot()["llm_calls"] == 0
