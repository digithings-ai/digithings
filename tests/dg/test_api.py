"""API tests for digigraph FastAPI app (integration with TestClient)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digigraph.server import app
from fastapi.testclient import TestClient

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
    """GET /v1/models, POST /v1/chat/completions (expose digigraph as model)."""

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

            m.return_value = WorkflowResult(
                success=True, message="Found 3 docs.", backtest_result=None
            )
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "search for X"}],
                },
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

    def test_chat_completions_multi_turn_preserves_assistant_history(
        self, client: TestClient
    ) -> None:
        """digichat posts the full UI history; assistant turns must reach the workflow prompt."""
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult

            m.return_value = WorkflowResult(success=True, message="ok", backtest_result=None)
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sitaas-rag",
                    "messages": [
                        {"role": "user", "content": "What is digigraph?"},
                        {
                            "role": "assistant",
                            "content": "digigraph is the orchestration hub.",
                        },
                        {"role": "user", "content": "Say more about that."},
                    ],
                },
            )
        assert r.status_code == 200
        m.assert_called_once()
        prompt = m.call_args[0][0].prompt
        assert "What is digigraph?" in prompt
        assert "digigraph is the orchestration hub." in prompt
        assert "Say more about that." in prompt

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
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
            )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/event-stream")
        body = r.text
        assert "data: " in body
        assert "[DONE]" in body
        assert "chat.completion.chunk" in body

    def test_chat_completions_stream_sitaas_rag_alone_uses_neutral_formatter(
        self, client: TestClient
    ) -> None:
        """model=sitaas-rag alone must not enable Open WebUI <details> chrome."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "test q"}}))
            queue.put(("tool_result", {"content": "Snippet from index."}))
            queue.put(("content", "Final answer here."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "search"}],
                    "stream": True,
                },
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" not in body
        assert "Tool:" in body or "digisearch" in body  # neutral formatter
        assert "Final" in body and "here" in body
        assert "data: [DONE]" in body

    def test_chat_completions_stream_openwebui_header_enables_details(
        self, client: TestClient
    ) -> None:
        """X-Response-Format: openwebui enables <details> tool blocks (Open WebUI Method 4)."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "test q"}}))
            queue.put(("tool_result", {"content": "Snippet from index."}))
            queue.put(("content", "Final answer here."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                headers={"X-Response-Format": "openwebui"},
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "search"}],
                    "stream": True,
                },
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" in body
        assert "tool call" in body.lower() and "digisearch" in body
        assert "test q" in body
        assert "Snippet from index" in body
        assert "Final" in body and "here" in body
        assert "data: [DONE]" in body

    def test_chat_completions_stream_openwebui_format_body_enables_details(
        self, client: TestClient
    ) -> None:
        """openwebui_format=true in the JSON body enables <details> tool blocks."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "q"}}))
            queue.put(("tool_result", {"content": "hit"}))
            queue.put(("content", "Answer."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                    "openwebui_format": True,
                },
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" in body
        assert "digisearch" in body
        assert "Answer" in body

    def test_chat_completions_stream_suppress_omits_openwebui_chrome(
        self, client: TestClient
    ) -> None:
        """X-Suppress-Tool-Stream drops <details> and <thinking> even with openwebui header."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "test q"}}))
            queue.put(("tool_result", {"content": "Snippet from index."}))
            queue.put(("reasoning", "internal chain of thought"))
            queue.put(("content", "Final answer here."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                headers={
                    "X-Suppress-Tool-Stream": "1",
                    "X-Response-Format": "openwebui",
                },
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "search"}],
                    "stream": True,
                },
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" not in body
        assert "<thinking>" not in body
        assert "Tool call" not in body
        assert "internal chain of thought" not in body
        assert "Final" in body and "here" in body

    def test_chat_completions_stream_plain_format_opts_out_of_openwebui(
        self, client: TestClient
    ) -> None:
        """X-Response-Format: plain disables Open WebUI formatter despite openwebui_format=true."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "q"}}))
            queue.put(("tool_result", {"content": "hit"}))
            queue.put(("content", "Answer."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                headers={"X-Response-Format": "plain"},
                json={
                    "model": "sitaas-rag",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                    "openwebui_format": True,
                },
            )
        assert r.status_code == 200
        body = r.text
        assert "<details>" not in body
        assert "Tool:" in body or "digisearch" in body  # neutral formatter
        assert "Answer" in body
