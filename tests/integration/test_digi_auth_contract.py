"""DigiAuth middleware contract: JWT required for protected routes; health exempt."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app
from tests.digi_test_jwt import mint_test_jwt


@pytest.mark.unit
def test_digigraph_health_no_bearer() -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200


@pytest.mark.unit
def test_digigraph_workflow_401_without_bearer() -> None:
    client = TestClient(app)
    r = client.post("/workflow", json={"prompt": "x"})
    assert r.status_code == 401
    assert r.json().get("code") == "unauthorized"


@pytest.mark.unit
def test_digigraph_workflow_403_insufficient_scope() -> None:
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {mint_test_jwt(scopes=['digisearch:query'])}"},
    )
    r = client.post("/workflow", json={"prompt": "x"})
    assert r.status_code == 403
    assert r.json().get("code") == "insufficient_scope"


@pytest.mark.unit
def test_digigraph_workflow_200_with_workflow_scope() -> None:
    from unittest.mock import patch

    from digigraph.models import WorkflowResult

    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {mint_test_jwt(scopes=['digigraph:workflow'])}"},
    )
    with patch("digigraph.workflow.run_digigraph_workflow") as m:
        m.return_value = WorkflowResult(success=True, message="ok", backtest_result=None)
        r = client.post("/workflow", json={"prompt": "Build stat-arb"})
    assert r.status_code == 200


@pytest.mark.unit
def test_digigraph_503_when_jwt_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)
    monkeypatch.delenv("DIGIKEY_PUBLIC_KEY_PEM", raising=False)
    client = TestClient(app)
    r = client.post("/workflow", json={"prompt": "x"})
    assert r.status_code == 503
    assert r.json().get("code") == "auth_not_configured"
