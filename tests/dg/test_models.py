"""Unit tests for DigiGraph Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from digigraph.models import ChatMessage, WorkflowRequest, WorkflowResult


@pytest.mark.unit
class TestChatMessage:
    def test_content_string(self) -> None:
        m = ChatMessage(role="user", content="hello")
        assert m.content == "hello"

    def test_content_ai_sdk_parts_list(self) -> None:
        m = ChatMessage(
            role="user",
            content=[{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}],
        )
        assert m.content == "Hello world"

    def test_content_none_becomes_empty(self) -> None:
        m = ChatMessage(role="user", content=None)  # type: ignore[arg-type]
        assert m.content == ""


@pytest.mark.unit
class TestWorkflowRequest:
    """WorkflowRequest model."""

    def test_minimal_valid(self) -> None:
        req = WorkflowRequest(prompt="Backtest tech")
        assert req.prompt == "Backtest tech"
        assert req.session_id is None

    def test_with_session_id(self) -> None:
        req = WorkflowRequest(prompt="x", session_id="sess-1")
        assert req.session_id == "sess-1"

    def test_with_allowed_tools(self) -> None:
        req = WorkflowRequest(prompt="x", allowed_tools=["digisearch"])
        assert req.allowed_tools == ["digisearch"]

    def test_missing_prompt_raises(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowRequest.model_validate({})


@pytest.mark.unit
class TestWorkflowResult:
    """WorkflowResult model."""

    def test_success_with_backtest(self) -> None:
        r = WorkflowResult(
            success=True,
            message="Done",
            backtest_result={"status": "ok", "total_return_pct": 1.25},
        )
        assert r.success is True
        assert r.backtest_result["status"] == "ok"

    def test_failure_without_backtest(self) -> None:
        r = WorkflowResult(success=False, message="DigiQuant unreachable", backtest_result=None)
        assert r.success is False
        assert r.backtest_result is None

    def test_serialize_roundtrip(self) -> None:
        r = WorkflowResult(success=True, message="x", backtest_result={"a": 1})
        data = r.model_dump()
        r2 = WorkflowResult.model_validate(data)
        assert r2.success == r.success
        assert r2.backtest_result == r.backtest_result
