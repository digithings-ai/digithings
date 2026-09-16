"""Per-response SSE usage chunks must be isolated across concurrent streams (#3982).

The accumulator the streaming path reads is request-scoped: two overlapping
``_stream_completions_progressive`` runs each report only their own provider usage.
The regression is barrier-synced -- both workers record before either stream
snapshots -- so a process-global accumulator deterministically reports the other
run's tokens (and wipes them on ``reset()``).
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
from digigraph.http_api.streaming import _stream_completions_progressive
from digigraph.models import ChatCompletionRequest

from digigraph import usage

pytestmark = pytest.mark.unit

# Bounded so a genuine deadlock fails the suite instead of hanging it.
_WORKFLOW_TIMEOUT_SECONDS = 15.0
_JOIN_TIMEOUT_SECONDS = 20.0


@pytest.fixture(autouse=True)
def _reset_global_usage() -> None:
    usage.reset()
    yield
    usage.reset()


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="digigraph-rag",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )


def _usage_totals(chunks: list[str]) -> list[dict[str, int]]:
    totals: list[dict[str, int]] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload: dict[str, Any] = json.loads(line.removeprefix("data: "))
            if payload.get("usage") is not None:
                totals.append(payload["usage"])
    return totals


def _stream() -> Any:
    return _stream_completions_progressive(_request(), "hi", None)


def test_single_stream_emits_its_own_usage_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-concurrent path keeps emitting the provider-reported totals."""

    def fake_workflow(_req: Any, queue: Any, _cancel: Any) -> None:
        usage.record(kind="chat", model="test-model", prompt_tokens=5, completion_tokens=7)
        queue.put(("done", None))

    monkeypatch.setattr(
        "digigraph.server.run_digigraph_workflow_streaming",
        fake_workflow,
    )
    chunks = list(_stream())
    assert _usage_totals(chunks) == [
        {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    ]


def test_each_concurrent_stream_reports_only_its_own_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two barrier-synced streams: each must report 3+3, never 6+6 or nothing.

    Both workers record before either generator snapshots, which is the exact
    interleaving that a process-global accumulator cannot survive: the second
    ``start()`` clears the first run's call and the first ``reset()`` clears the
    second run's snapshot window.
    """
    barrier = threading.Barrier(2, timeout=_WORKFLOW_TIMEOUT_SECONDS)

    def fake_workflow(_req: Any, queue: Any, _cancel: Any) -> None:
        usage.record(kind="chat", model="test-model", prompt_tokens=3, completion_tokens=3)
        barrier.wait()
        queue.put(("done", None))

    monkeypatch.setattr(
        "digigraph.server.run_digigraph_workflow_streaming",
        fake_workflow,
    )

    results: dict[str, list[str]] = {}

    def consume(name: str, stream: Any) -> None:
        results[name] = list(stream)

    threads = [threading.Thread(target=consume, args=(name, _stream())) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_JOIN_TIMEOUT_SECONDS)

    assert not any(thread.is_alive() for thread in threads), "stream did not finish"
    for name in ("a", "b"):
        assert _usage_totals(results[name]) == [
            {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6}
        ], f"stream {name} reported the wrong usage"
