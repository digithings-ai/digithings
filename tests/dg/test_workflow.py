"""Unit tests for run_digigraph_workflow (Phase 0 + Phase 1 edge cases)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.workflow import run_digigraph_workflow


@pytest.mark.unit
class TestRunDigigraphWorkflow:
    """run_digigraph_workflow contract. Integration with digiquant in e2e."""

    def test_returns_workflow_result(self) -> None:
        req = WorkflowRequest(prompt="Backtest tech")
        result = run_digigraph_workflow(req)
        assert isinstance(result, WorkflowResult)
        assert result.message

    def test_when_digiquant_unreachable_returns_failure_gracefully(self) -> None:
        req = WorkflowRequest(prompt="Backtest tech")
        result = run_digigraph_workflow(req)
        assert isinstance(result, WorkflowResult)
        assert result.message
        if not result.success:
            assert result.backtest_result is None or isinstance(result.backtest_result, dict)

    def test_empty_prompt_returns_failure(self) -> None:
        """Empty prompt fails; no fallbacks. Research returns error, workflow fails."""
        req = WorkflowRequest(prompt="")
        result = run_digigraph_workflow(req)
        assert isinstance(result, WorkflowResult)
        assert result.success is False
        assert "prompt" in result.message.lower() or "error" in result.message.lower()

    def test_workflow_error_propagates_to_result(self) -> None:
        """When graph returns error in state, WorkflowResult has success=False and message contains error."""

        def _mock_invoke(initial: dict, config: dict | None = None, **_kwargs: object) -> dict:
            return {
                "prompt": initial.get("prompt"),
                "strategy_name": "x",
                "symbols": ["A"],
                "backtest_result": None,
                "error": "digiquant connection refused",
            }

        with patch("digigraph.workflow.build_workflow_graph") as m:
            m.return_value.invoke = _mock_invoke
            result = run_digigraph_workflow(WorkflowRequest(prompt="backtest tech"))
        assert result.success is False
        assert result.backtest_result is None
        assert "error" in result.message.lower() or "connection" in result.message.lower()

    def test_workflow_error_logs_workflow_end(self) -> None:
        """When graph returns error, workflow_end is still logged with success=False."""

        def _mock_invoke(initial: dict, config: dict | None = None, **_kwargs: object) -> dict:
            return {"error": "fake error", "backtest_result": None}

        with patch("digigraph.workflow.build_workflow_graph") as m_build:
            m_build.return_value.invoke = _mock_invoke
            with patch("digigraph.workflow.dg_audit_log") as m_audit:
                run_digigraph_workflow(WorkflowRequest(prompt="x"))
        workflow_end_calls = [
            c for c in m_audit.call_args_list if len(c[0]) > 0 and c[0][0] == "workflow_end"
        ]
        assert len(workflow_end_calls) == 1
        payload = workflow_end_calls[0][1].get("payload", {})
        assert payload.get("success") is False
        assert "error" in payload
        assert payload.get("workflow_id")
        starts = [c for c in m_audit.call_args_list if c[0][0] == "workflow_start"]
        assert starts and starts[0][1]["payload"].get("workflow_id") == payload.get("workflow_id")

    def test_session_id_passed_through_request(self) -> None:
        """WorkflowRequest with session_id is accepted (session_id in state for future use)."""
        req = WorkflowRequest(prompt="tech backtest", session_id="sess-123")
        result = run_digigraph_workflow(req)
        assert isinstance(result, WorkflowResult)
        assert result.message


@pytest.mark.unit
def test_invoke_passes_durability_sync() -> None:
    """durability defaults to \"async\" (checkpoint persisted concurrently with the next
    step) — too weak for the DIGI_INTERRUPT_AFTER_RESEARCH breakpoint and the /resume
    endpoint, both of which assume the checkpoint at the pause point is actually durable
    before a client can act on it."""
    with patch("digigraph.workflow.build_workflow_graph") as m_build:
        m_build.return_value.invoke.return_value = {"error": None}
        run_digigraph_workflow(WorkflowRequest(prompt="test"))
    _, kwargs = m_build.return_value.invoke.call_args
    assert kwargs.get("durability") == "sync"


@pytest.mark.unit
def test_via_stream_passes_durability_sync() -> None:
    from digigraph.workflow import run_digigraph_workflow_via_stream

    with patch("digigraph.workflow.build_workflow_graph") as m_build:
        m_build.return_value.stream.return_value = iter([])
        m_build.return_value.get_state.return_value = None
        run_digigraph_workflow_via_stream(WorkflowRequest(prompt="test"))
    _, kwargs = m_build.return_value.stream.call_args
    assert kwargs.get("durability") == "sync"


@pytest.mark.unit
def test_streaming_passes_durability_sync() -> None:
    from queue import Queue

    from digigraph.workflow import run_digigraph_workflow_streaming

    with patch("digigraph.workflow.build_workflow_graph") as m_build:
        m_build.return_value.stream.return_value = iter([])
        m_build.return_value.get_state.return_value = None
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="test"), Queue())
    _, kwargs = m_build.return_value.stream.call_args
    assert kwargs.get("durability") == "sync"


@pytest.mark.unit
def test_a_disconnected_client_does_not_wedge_the_worker() -> None:
    """A cancelled stream must not block on a queue nobody is draining any more.

    ``server.py`` bounds the queue (``maxsize=256``) and its SSE generator breaks out
    of the ``get`` loop the instant ``cancel_event`` is set -- which is what a client
    disconnect does, via ``GeneratorExit`` -- without draining what is left. A blocking
    ``put`` then waits on a reader that will never return, and it waits *inside* the
    worker, so the worker never reaches its ``finally``. That ``finally`` clears the
    request's BYOK credentials from this thread's context copy, so the hang would
    strand a user's plaintext API key in a leaked non-daemon thread for the lifetime
    of the process. One undelivered event is enough to cause it.
    """
    from queue import Empty, Queue
    from threading import Event, Thread

    from digigraph.workflow import run_digigraph_workflow_streaming

    queue: Queue = Queue(maxsize=2)
    queue.put(("content", "undrained backlog"))
    queue.put(("content", "undrained backlog"))
    assert queue.full(), "the queue has to be full or a blocking put would not block"

    cancel_event = Event()
    cancel_event.set()
    finished = Event()

    def run() -> None:
        with patch("digigraph.workflow.build_workflow_graph") as m_build:
            m_build.return_value.stream.return_value = iter(
                [{"type": "custom", "ns": (), "data": ("content", "mid-node token")}]
            )
            m_build.return_value.get_state.return_value = None
            run_digigraph_workflow_streaming(WorkflowRequest(prompt="test"), queue, cancel_event)
        finished.set()

    # daemon: if this regresses the thread never returns, and pytest still has to exit.
    Thread(target=run, daemon=True).start()
    assert finished.wait(5), "the worker wedged on a full queue after the client left"

    # Dropped, not force-fed: the backlog is untouched and nothing was appended.
    assert queue.get_nowait() == ("content", "undrained backlog")
    assert queue.get_nowait() == ("content", "undrained backlog")
    with pytest.raises(Empty):
        queue.get_nowait()


@pytest.mark.unit
def test_a_slow_consumer_still_gets_backpressure() -> None:
    """Dropping events is for a *gone* consumer, never a merely slow one.

    The bound on the queue is deliberate: a graph that outruns the client has to wait
    for it. Pinned because the cheap way to fix the wedge above -- ``put_nowait`` with
    the ``Full`` swallowed -- silently drops events from live streams instead.
    """
    import time
    from queue import Queue
    from threading import Event, Thread

    from digigraph.workflow import _EMIT_POLL_SECONDS, _emit_event

    queue: Queue = Queue(maxsize=1)
    queue.put(("content", "first"))
    drained = Event()

    def drain_late() -> None:
        # Longer than one poll interval, so at least one ``put`` attempt times out and
        # the retry loop -- not a single lucky attempt -- is what delivers the event.
        time.sleep(_EMIT_POLL_SECONDS * 3)
        queue.get()
        drained.set()

    reader = Thread(target=drain_late, daemon=True)
    reader.start()
    _emit_event(queue, Event(), ("content", "second"))
    reader.join(5)

    assert drained.is_set(), "the reader never ran, so this proves nothing"
    assert queue.get_nowait() == ("content", "second")


@pytest.mark.unit
def test_streaming_digigraph_error_channel_requires_error_code() -> None:
    """The SSE digigraph_error contract is gated on error_code — not every error."""
    from queue import Queue
    from types import SimpleNamespace

    from digigraph.workflow import run_digigraph_workflow_streaming

    def _collect_events(final: dict) -> list[tuple]:
        queue: Queue = Queue()
        with patch("digigraph.workflow.build_workflow_graph") as m_build:
            m_build.return_value.stream.return_value = iter([])
            m_build.return_value.get_state.return_value = SimpleNamespace(values=final)
            run_digigraph_workflow_streaming(WorkflowRequest(prompt="test"), queue)
        events: list[tuple] = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return events

    without_code = _collect_events({"error": "Internal stack trace at db.internal:5432"})
    assert ("error",) not in {e[0] for e in without_code}
    assert any(e == ("content", "Error: Internal stack trace at db.internal:5432") for e in without_code)

    quota_message = "Free-tier model quota is exhausted."
    with_code = _collect_events(
        {"error": quota_message, "error_code": "free_quota_exceeded"}
    )
    error_events = [e for e in with_code if e[0] == "error"]
    assert error_events == [
        ("error", {"code": "free_quota_exceeded", "message": quota_message})
    ]
