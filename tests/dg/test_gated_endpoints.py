"""Opt-in gates for debug and thread/file HTTP routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app
from tests.digi_test_jwt import auth_headers


@pytest.mark.unit
def test_test_llm_404_when_debug_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ENABLE_DEBUG_ENDPOINTS", raising=False)
    monkeypatch.setenv("DIGI_ENABLE_THREAD_API", "1")
    with patch("digigraph.server.completion_text", return_value="OK"):
        with patch("digigraph.server.get_model_for_mode", return_value="m"):
            r = TestClient(app, headers=auth_headers()).get("/test_llm")
    assert r.status_code == 404


@pytest.mark.unit
def test_debug_input_messages_404_when_debug_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ENABLE_DEBUG_ENDPOINTS", raising=False)
    monkeypatch.setenv("DIGI_ENABLE_THREAD_API", "1")
    r = TestClient(app, headers=auth_headers()).get("/v1/debug/input_messages")
    assert r.status_code == 404


@pytest.mark.unit
def test_threads_state_404_when_thread_api_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_ENABLE_DEBUG_ENDPOINTS", "1")
    monkeypatch.delenv("DIGI_ENABLE_THREAD_API", raising=False)
    r = TestClient(app, headers=auth_headers()).get("/threads/t1/state")
    assert r.status_code == 404
