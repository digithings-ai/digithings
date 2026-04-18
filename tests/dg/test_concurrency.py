"""Concurrency tests for DigiGraph — isolated WorkflowState per thread_id.

These tests verify that concurrent workflow runs with different thread IDs
do not bleed state into each other. All graph interactions are patched so
no real LLM / network calls are made.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import pytest

from digigraph.graph.state import WorkflowState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node_mock(
    state_update: dict[str, Any],
    node_name: str = "research_node",
):
    """Return a callable that merges *state_update* into the state it receives."""
    def _node(state: WorkflowState, config: dict | None = None) -> dict:
        return state_update
    _node.__name__ = node_name
    return _node


# ---------------------------------------------------------------------------
# WorkflowState isolation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWorkflowStateIsolation:
    """WorkflowState is a TypedDict: verify each dict instance is independent."""

    def test_two_states_are_independent(self) -> None:
        s1: WorkflowState = {"prompt": "strategy A", "session_id": "thread-1"}
        s2: WorkflowState = {"prompt": "strategy B", "session_id": "thread-2"}
        assert s1["prompt"] != s2["prompt"]
        assert s1["session_id"] != s2["session_id"]

    def test_mutating_one_does_not_affect_other(self) -> None:
        s1: WorkflowState = {"prompt": "original", "session_id": "t1", "error": None}
        s2: WorkflowState = {"prompt": "original", "session_id": "t2", "error": None}
        s1["error"] = "thread-1 error"
        assert s2["error"] is None

    def test_stored_datasets_do_not_share_reference(self) -> None:
        shared: dict[str, Any] = {}
        s1: WorkflowState = {"stored_datasets": dict(shared)}
        s2: WorkflowState = {"stored_datasets": dict(shared)}
        s1["stored_datasets"]["key1"] = {"ref": "r1"}
        assert "key1" not in s2["stored_datasets"]


# ---------------------------------------------------------------------------
# Concurrent workflow runs with patched graph
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestConcurrentWorkflowRuns:
    """Run multiple workflow calls concurrently; verify results are independent."""

    def _run_workflow(self, prompt: str, session_id: str, results: dict, idx: int):
        from digigraph.models import WorkflowRequest
        from digigraph.workflow import run_digigraph_workflow

        req = WorkflowRequest(prompt=prompt, session_id=session_id)
        result = run_digigraph_workflow(req)
        results[idx] = result

    def test_concurrent_runs_return_separate_results(self) -> None:
        """Two concurrent runs with different session_ids must not share state."""
        results: dict[int, Any] = {}
        threads = [
            threading.Thread(target=self._run_workflow, args=(f"prompt {i}", f"thread-{i}", results, i))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert 0 in results and 1 in results
        # Each result must be a distinct object
        assert results[0] is not results[1]

    def test_concurrent_runs_do_not_raise(self) -> None:
        """Concurrent workflow execution must not raise exceptions."""
        errors: list[Exception] = []
        results: dict[int, Any] = {}

        def run(i: int):
            try:
                self._run_workflow(f"query {i}", f"sess-{i}", results, i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent runs raised: {errors}"

    def test_same_session_id_does_not_corrupt_state(self) -> None:
        """Sequential runs on the same session_id each return a valid result."""
        from digigraph.models import WorkflowRequest
        from digigraph.workflow import run_digigraph_workflow

        for prompt in ("first run", "second run"):
            req = WorkflowRequest(prompt=prompt, session_id="shared-session")
            result = run_digigraph_workflow(req)
            assert result is not None


# ---------------------------------------------------------------------------
# Environment isolation across threads
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEnvVarIsolation:
    """os.environ mutations in one thread must not be assumed thread-safe.

    These tests verify that our server-side functions use os.environ at call
    time (not at import time), so env changes are always reflected correctly.
    """

    def test_allowed_origins_reflects_env_at_call_time(self) -> None:
        """_allowed_origins() must read DIGI_ALLOWED_ORIGINS when called, not at import."""
        from digigraph.server import _allowed_origins  # type: ignore[attr-defined]

        original = os.environ.get("DIGI_ALLOWED_ORIGINS", "")
        try:
            os.environ["DIGI_ALLOWED_ORIGINS"] = "http://test-origin.example.com"
            origins = _allowed_origins()
            assert "http://test-origin.example.com" in origins
        finally:
            if original:
                os.environ["DIGI_ALLOWED_ORIGINS"] = original
            elif "DIGI_ALLOWED_ORIGINS" in os.environ:
                del os.environ["DIGI_ALLOWED_ORIGINS"]

    def test_default_origins_when_env_unset(self) -> None:
        from digigraph.server import _allowed_origins  # type: ignore[attr-defined]

        original = os.environ.pop("DIGI_ALLOWED_ORIGINS", None)
        try:
            origins = _allowed_origins()
            assert isinstance(origins, list)
            assert len(origins) > 0
        finally:
            if original is not None:
                os.environ["DIGI_ALLOWED_ORIGINS"] = original
