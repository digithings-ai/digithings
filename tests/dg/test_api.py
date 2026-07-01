"""API tests for DigiGraph FastAPI app (integration with TestClient)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app
from tests.digi_test_jwt import auth_headers

SAMPLE_WORKFLOW_PAYLOAD = {"prompt": "Build me a mean-reversion stat-arb on tech"}
SAMPLE_WORKFLOW_RESULT_FIELDS = ["success", "message", "backtest_result"]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


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
        with patch("digigraph.server.completion_text") as m:
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
        with patch("digigraph.server.completion_text") as m:
            m.side_effect = RuntimeError("Connection refused")
            r = client.get("/test_llm")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is False
        assert "error" in data


@pytest.mark.unit
class TestOpenAICompatible:
    """GET /v1/models, POST /v1/chat/completions (expose DigiGraph as model)."""

    def test_model_info_returns_model_and_mode(self, client: TestClient) -> None:
        r = client.get("/v1/model-info")
        assert r.status_code == 200
        data = r.json()
        assert "model" in data
        assert "mode" in data
        assert "base_url" in data

    def test_list_models_returns_sitaas_rag(self, client: TestClient) -> None:
        r = client.get("/v1/models")
        assert r.status_code == 200
        data = r.json()
        assert data.get("object") == "list"
        models = data.get("data", [])
        assert len(models) >= 1
        ids = [m.get("id") for m in models]
        assert "sitaas-rag" in ids

    def test_chat_completions_returns_openai_format(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult
            m.return_value = WorkflowResult(success=True, message="Found 3 docs.", backtest_result=None)
            r = client.post(
                "/v1/chat/completions",
                json={"model": "sitaas-rag", "messages": [{"role": "user", "content": "search for X"}]},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("object") == "chat.completion"
        assert "choices" in data
        assert len(data["choices"]) >= 1
        assert data["choices"][0].get("message", {}).get("content") == "Found 3 docs."
        assert "usage" in data

    def test_chat_completions_accepts_ai_sdk_content_parts(self, client: TestClient) -> None:
        """Vercel AI SDK sends user messages as content: [{type: text, text: ...}]."""
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult
            m.return_value = WorkflowResult(success=True, message="ok", backtest_result=None)
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sitaas-rag",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "search for X"}]},
                    ],
                },
            )
        assert r.status_code == 200
        m.assert_called_once()
        call_kw = m.call_args[0][0]
        assert "search for X" in call_kw.prompt

    def test_chat_completions_empty_messages(self, client: TestClient) -> None:
        r = client.post("/v1/chat/completions", json={"model": "sitaas-rag", "messages": []})
        assert r.status_code == 200
        data = r.json()
        assert "No messages provided" in data["choices"][0]["message"]["content"]

    def test_chat_completions_stream_returns_sse(self, client: TestClient) -> None:
        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("content", "Hi"))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                json={"model": "sitaas-rag", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/event-stream")
        body = r.text
        assert "data: " in body
        assert "[DONE]" in body
        assert "chat.completion.chunk" in body

    def test_chat_completions_stream_includes_tool_details_blocks(self, client: TestClient) -> None:
        """Progressive stream includes <details> block for tool call/result (Open WebUI Method 4; summary = 🔧 Tool Call: name)."""
        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "test q"}}))
            queue.put(("tool_result", {"content": "Snippet from index."}))
            queue.put(("content", "Final answer here."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                json={"model": "sitaas-rag", "messages": [{"role": "user", "content": "search"}], "stream": True},
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" in body
        assert "tool call" in body.lower() and "digisearch" in body
        assert "test q" in body
        assert "Snippet from index" in body
        assert "Final" in body and "here" in body
        assert "data: [DONE]" in body
