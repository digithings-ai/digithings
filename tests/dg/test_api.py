"""API tests for DigiGraph FastAPI app (integration with TestClient)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app

SAMPLE_WORKFLOW_PAYLOAD = {"prompt": "Build me a mean-reversion stat-arb on tech"}
SAMPLE_WORKFLOW_RESULT_FIELDS = ["success", "message", "backtest_result"]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.unit
class TestHealth:
    """GET /health."""

    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200

    def test_returns_json_with_service(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.json().get("service") == "digigraph"
        assert r.json().get("status") == "ok"


@pytest.mark.unit
class TestWorkflow:
    """POST /workflow (run_digigraph_workflow)."""

    def test_returns_200_with_valid_prompt(self, client: TestClient) -> None:
        with patch("digigraph.workflow.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult
            m.return_value = WorkflowResult(
                success=True,
                message="Done",
                backtest_result={"status": "ok", "symbols": ["AAPL"]},
            )
            r = client.post("/workflow", json=SAMPLE_WORKFLOW_PAYLOAD)
        assert r.status_code == 200
        data = r.json()
        for field in SAMPLE_WORKFLOW_RESULT_FIELDS:
            assert field in data

    def test_calls_workflow_with_request_body(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult
            m.return_value = WorkflowResult(success=True, message="", backtest_result={})
            client.post("/workflow", json={"prompt": "Build me a stat-arb on tech"})
            m.assert_called_once()
            call_arg = m.call_args[0][0]
            assert call_arg.prompt == "Build me a stat-arb on tech"

    def test_validation_rejects_missing_prompt(self, client: TestClient) -> None:
        r = client.post("/workflow", json={})
        assert r.status_code == 422


@pytest.mark.unit
class TestTestLlm:
    """GET /test_llm (LLM sanity check, same path as workflow research node)."""

    def test_returns_200_and_ok_model_reply(self, client: TestClient) -> None:
        with patch("digigraph.server.chat_completion") as m:
            m.return_value = "OK"
            with patch("digigraph.server.get_model_for_mode") as mode_m:
                mode_m.return_value = "ollama-cloud/minimax-m2.5:cloud"
                r = client.get("/test_llm")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "model" in data
        assert "reply" in data

    def test_returns_ok_false_on_llm_error(self, client: TestClient) -> None:
        with patch("digigraph.server.chat_completion") as m:
            m.side_effect = RuntimeError("Connection refused")
            r = client.get("/test_llm")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is False
        assert "error" in data
