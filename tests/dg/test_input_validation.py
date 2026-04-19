"""Pydantic v2 HTTP input-validation tests for DigiGraph.

Covers:
- Malformed JSON and missing required fields → 422 with Pydantic-formatted error body.
- Unknown / extra fields rejected by ``extra="forbid"`` request models → 422.
- Well-formed requests still reach the handler → 200.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app
from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.mark.unit
class TestWorkflowValidation:
    """POST /workflow → WorkflowRequest (extra='forbid')."""

    def test_malformed_json_returns_422(self, client: TestClient) -> None:
        r = client.post(
            "/workflow",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    def test_missing_required_prompt_returns_422(self, client: TestClient) -> None:
        r = client.post("/workflow", json={"session_id": "s"})
        assert r.status_code == 422
        body = r.json()
        # Shared digibase error shape: {"error": {"code": "validation_error", ...}}
        assert body.get("error", {}).get("code") == "validation_error"

    def test_extra_field_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/workflow",
            json={"prompt": "ok", "evil_field": "should-be-rejected"},
        )
        assert r.status_code == 422
        assert r.json().get("error", {}).get("code") == "validation_error"

    def test_well_formed_request_returns_200(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            from digigraph.models import WorkflowResult

            m.return_value = WorkflowResult(success=True, message="Done", backtest_result={})
            r = client.post("/workflow", json={"prompt": "hello"})
        assert r.status_code == 200


@pytest.mark.unit
class TestResumeThreadValidation:
    """POST /threads/{thread_id}/resume → ResumeThreadRequest (extra='forbid')."""

    def test_extra_field_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_ENABLE_THREAD_API", "1")
        r = client.post(
            "/threads/abc/resume",
            json={"resume": "x", "bogus": True},
        )
        assert r.status_code == 422
        assert r.json().get("error", {}).get("code") == "validation_error"
