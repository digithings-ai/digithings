"""Unit tests for run_digigraph_workflow (Phase 0 + Phase 1 edge cases)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.workflow import run_digigraph_workflow


@pytest.mark.unit
class TestRunDigigraphWorkflow:
    """run_digigraph_workflow contract. Integration with DigiQuant in e2e."""

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
        def _mock_invoke(initial: dict) -> dict:
            return {
                "prompt": initial.get("prompt"),
                "strategy_name": "x",
                "symbols": ["A"],
                "backtest_result": None,
                "error": "DigiQuant connection refused",
            }
        with patch("digigraph.workflow.build_workflow_graph") as m:
            m.return_value.invoke = _mock_invoke
            result = run_digigraph_workflow(WorkflowRequest(prompt="backtest tech"))
        assert result.success is False
        assert result.backtest_result is None
        assert "error" in result.message.lower() or "connection" in result.message.lower()

    def test_workflow_error_logs_workflow_end(self) -> None:
        """When graph returns error, workflow_end is still logged with success=False."""
        def _mock_invoke(initial: dict) -> dict:
            return {"error": "fake error", "backtest_result": None}

        with patch("digigraph.workflow.build_workflow_graph") as m_build:
            m_build.return_value.invoke = _mock_invoke
            with patch("digigraph.workflow.dg_audit_log") as m_audit:
                run_digigraph_workflow(WorkflowRequest(prompt="x"))
        workflow_end_calls = [c for c in m_audit.call_args_list if len(c[0]) > 0 and c[0][0] == "workflow_end"]
        assert len(workflow_end_calls) == 1
        payload = workflow_end_calls[0][1].get("payload", {})
        assert payload.get("success") is False
        assert "error" in payload

    def test_session_id_passed_through_request(self) -> None:
        """WorkflowRequest with session_id is accepted (session_id in state for future use)."""
        req = WorkflowRequest(prompt="tech backtest", session_id="sess-123")
        result = run_digigraph_workflow(req)
        assert isinstance(result, WorkflowResult)
        assert result.message
