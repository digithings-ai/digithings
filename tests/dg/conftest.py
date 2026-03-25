"""DigiGraph unit tests: enable opt-in HTTP routes by default (see server gated_sensitive_endpoints)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _digigraph_enable_sensitive_http_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_ENABLE_DEBUG_ENDPOINTS", "1")
    monkeypatch.setenv("DIGI_ENABLE_THREAD_API", "1")
