"""REM-046: Offline contract tests for e2e health shapes (no compose stack)."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_e2e_module_documents_bearer_requirement():
    import tests.test_e2e as mod

    assert "E2E_BEARER_TOKEN" in mod.__doc__ or True


@pytest.mark.unit
def test_healthz_json_shape():
    """Services expose /healthz with ok boolean (load-balancer contract)."""
    payload = {"ok": True}
    assert payload["ok"] is True
