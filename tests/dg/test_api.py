"""API tests for digigraph FastAPI app (integration with TestClient)."""

from __future__ import annotations

from types import SimpleNamespace
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
        # Patch target must match the name bound in digigraph.server (where the
        # endpoint calls it), not digigraph.workflow (where it's defined) --
        # patch() only rebinds the name in the module you tell it to.
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult

            m.return_value = WorkflowResult(
                success=True,
                message="Done",
                backtest_result={"status": "ok", "symbols": ["AAPL"]},
            )
            r = client.post("/workflow", json=SAMPLE_WORKFLOW_PAYLOAD)
        m.assert_called_once()
        assert r.status_code == 200
        data = r.json()
        for field in SAMPLE_WORKFLOW_RESULT_FIELDS:
            assert field in data
        assert data["success"] is True
        assert data["message"] == "Done"
        assert data["backtest_result"] == {"status": "ok", "symbols": ["AAPL"]}

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

    def test_list_models_returns_project_rag(self, client: TestClient) -> None:
        r = client.get("/v1/models")
        assert r.status_code == 200
        data = r.json()
        assert data.get("object") == "list"
        models = data.get("data", [])
        assert len(models) >= 1
        ids = [m.get("id") for m in models]
        assert "digigraph-rag" in ids

    def test_chat_completions_returns_openai_format(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult

            m.return_value = WorkflowResult(
                success=True, message="Found 3 docs.", backtest_result=None
            )
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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
        r = client.post("/v1/chat/completions", json={"model": "digigraph-rag", "messages": []})
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
                    "model": "digigraph-rag",
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

    def test_chat_completions_stream_project_rag_alone_uses_neutral_formatter(
        self, client: TestClient
    ) -> None:
        """model=digigraph-rag alone must not enable Open WebUI <details> chrome."""

        def fake_streaming(req, queue, cancel_event=None):
            queue.put(("tool_call", {"name": "digisearch", "arguments": {"query": "test q"}}))
            queue.put(("tool_result", {"content": "Snippet from index."}))
            queue.put(("content", "Final answer here."))
            queue.put(("done", None))

        with patch("digigraph.server.run_digigraph_workflow_streaming", side_effect=fake_streaming):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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
                    "model": "digigraph-rag",
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

    def test_chat_completions_threads_require_tool_calls_header(self, client: TestClient) -> None:
        """X-Require-Tool-Calls: 1 reaches the WorkflowRequest passed to run_digigraph_workflow."""
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult

            m.return_value = WorkflowResult(success=True, message="ok", backtest_result=None)
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "digigraph-rag",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                headers={"X-Require-Tool-Calls": "1"},
            )
        assert r.status_code == 200
        m.assert_called_once()
        call_arg = m.call_args[0][0]
        assert call_arg.require_tool_calls is True


@pytest.mark.unit
class TestDigiSubjectTrustBoundary:
    """CWE-639 IDOR regression (finding: digi_subject reaches the Store namespace
    unverified). `digi_subject` is a client-writable field on `WorkflowRequest`, used
    both for checkpoint thread_id scoping and, since Task 7, as the Store namespace
    key in supervisor_node (a subject's stored response_language preference). Before
    this fix, server.py's _digi_fields_from_request only overrode digi_subject when
    auth.subject was truthy -- a conditional-only override that left the client's own
    value untouched whenever auth was absent, or present with an empty subject claim.

    These tests exercise _with_digi_request_context directly (the function that
    builds the trusted WorkflowRequest from HTTP request + auth state) with a
    lightweight fake Request, covering all three trust states. See ARCHITECTURE.md
    §6.10."""

    @staticmethod
    def _fake_request(*, digi_auth: object | None) -> SimpleNamespace:
        state = SimpleNamespace(digi_auth=digi_auth, digi_bearer=None)
        return SimpleNamespace(state=state, headers={})

    def test_authenticated_real_subject_is_preserved(self) -> None:
        """(a) Existing behavior preserved: a verified, non-empty auth.subject still
        wins over -- and overwrites -- whatever the client sent in the request body."""
        from digigraph.models import WorkflowRequest
        from digigraph.server import _with_digi_request_context
        from digikey.models import DigiAuthContext

        auth = DigiAuthContext(subject="verified-user-1")
        req = WorkflowRequest(prompt="hi", digi_subject="client-claimed-user")
        out = _with_digi_request_context(self._fake_request(digi_auth=auth), req)
        assert out.digi_subject == "verified-user-1"

    def test_no_auth_object_forces_digi_subject_to_none(self) -> None:
        """(b) The core regression: with NO auth object at all on request.state, a
        client-supplied digi_subject must NOT survive into the returned
        WorkflowRequest -- it must be forced to None regardless of what the client
        sent in the request body, since it would otherwise key the Store namespace
        (supervisor_node) with an unverified, attacker-chosen value."""
        from digigraph.models import WorkflowRequest
        from digigraph.server import _with_digi_request_context

        req = WorkflowRequest(prompt="hi", digi_subject="attacker-controlled-subject")
        out = _with_digi_request_context(self._fake_request(digi_auth=None), req)
        assert out.digi_subject is None

    def test_auth_object_with_empty_subject_forces_digi_subject_to_none(self) -> None:
        """(c) The specific gap CodeRabbit flagged, distinct from (b): an auth object
        IS present, but its subject claim is empty/falsy. A conditional-only override
        (`if auth.subject: updates["digi_subject"] = auth.subject`) leaves the
        "digi_subject" key entirely absent from `updates` in this case, so
        `req.model_copy(update=updates)` would never touch -- let alone clear -- the
        client's own digi_subject value. Must still be forced to None."""
        from digigraph.models import WorkflowRequest
        from digigraph.server import _with_digi_request_context
        from digikey.models import DigiAuthContext

        auth = DigiAuthContext(subject="")
        req = WorkflowRequest(prompt="hi", digi_subject="attacker-controlled-subject")
        out = _with_digi_request_context(self._fake_request(digi_auth=auth), req)
        assert out.digi_subject is None


def test_resolve_require_tool_calls_chat_from_body() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[], require_tool_calls=True)
    assert _resolve_require_tool_calls_chat(req, _Req()) is True


def test_resolve_require_tool_calls_chat_from_header() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return "1" if name == "X-Require-Tool-Calls" else None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[])
    assert _resolve_require_tool_calls_chat(req, _Req()) is True


def test_resolve_require_tool_calls_chat_none_when_absent() -> None:
    from digigraph.models import ChatCompletionRequest
    from digigraph.server import _resolve_require_tool_calls_chat

    class _Headers:
        def get(self, name: str) -> str | None:
            return None

    class _Req:
        headers = _Headers()

    req = ChatCompletionRequest(messages=[])
    assert _resolve_require_tool_calls_chat(req, _Req()) is None


@pytest.mark.unit
class TestCorpusTrustBoundary:
    """CWE-639 regression: when DIGI_TENANT_CORPUS_MAP is set, client body/headers
    must not select another tenant's digisearch index (digisearch has no
    server-side tenant→index bind). Mirrors digivault's enforce_tenant_path_prefix."""

    @staticmethod
    def _fake_request(
        *,
        digi_auth: object | None,
        headers: dict[str, str] | None = None,
    ) -> SimpleNamespace:
        state = SimpleNamespace(digi_auth=digi_auth, digi_bearer=None)
        return SimpleNamespace(state=state, headers=headers or {})

    def test_map_overwrites_body_and_hostile_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digigraph.models import WorkflowRequest
        from digigraph.server import _with_digi_request_context
        from digikey.models import DigiAuthContext

        monkeypatch.setenv(
            "DIGI_TENANT_CORPUS_MAP",
            (
                '{"digithings":{"digisearchIndex":"digithings_docs",'
                '"vaultPathPrefix":"clients/digithings"},'
                '"occ":{"digisearchIndex":"occ_help",'
                '"vaultPathPrefix":"clients/online-compliance-center"}}'
            ),
        )
        auth = DigiAuthContext(subject="user-1", tenant_slug="digithings")
        req = WorkflowRequest(
            prompt="hi",
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        )
        out = _with_digi_request_context(
            self._fake_request(
                digi_auth=auth,
                headers={
                    "x-digi-corpus-index": "occ_help",
                    "x-digi-vault-prefix": "clients/online-compliance-center",
                },
            ),
            req,
        )
        assert out.digisearch_index == "digithings_docs"
        assert out.vault_path_prefix == "clients/digithings"

    def test_map_clears_body_when_tenant_unmapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digigraph.models import WorkflowRequest
        from digigraph.server import _with_digi_request_context
        from digikey.models import DigiAuthContext

        monkeypatch.setenv(
            "DIGI_TENANT_CORPUS_MAP",
            '{"occ":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/occ"}}',
        )
        auth = DigiAuthContext(subject="user-1", tenant_slug="digithings")
        req = WorkflowRequest(prompt="hi", digisearch_index="occ_help")
        out = _with_digi_request_context(self._fake_request(digi_auth=auth), req)
        assert out.digisearch_index is None
        assert out.vault_path_prefix is None
