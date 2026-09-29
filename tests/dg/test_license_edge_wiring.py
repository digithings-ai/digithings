"""Edge license scope wiring (spec §7): corpus + web-search gates, plain-open.

Pins the HTTP boundary where ``evaluate_hosted_license`` is enforced: corpus
headers require ``digisearch-corpus``; web-search opt-in (chat body-or-header,
``/workflow`` body) requires ``hosted-web-search``; refusals are 403
``insufficient_license_scope`` naming the missing scope; plain inference stays
open with absent, garbage, or unscoped licenses.
"""

from __future__ import annotations

import os
import time
import uuid
from unittest.mock import patch

import jwt
import pytest
from digigraph.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

CHAT_PAYLOAD = {"model": "digigraph-rag", "messages": [{"role": "user", "content": "hi"}]}
WORKFLOW_PAYLOAD = {"prompt": "summarize the tech portfolio"}
CORPUS_HEADERS = {"X-Digi-Corpus-Index": "pytest-idx"}


def _mint_license(services: object = "absent", *, exp: int | None = None, sub: str = "x"):
    """Mint a license JWT the test digikey keypair verifies.

    Signed with the same key the middleware checks (``conftest`` configures
    ``DIGIKEY_PUBLIC_KEY_PEM``) and ``iss`` from ``license_issuer_default``,
    so no env patching is needed and operator auth keeps working.
    """
    from digikey.license_verify import license_issuer_default

    priv_pem = os.environ["_PYTEST_DIGIKEY_PRIVATE_PEM"]
    license_id = f"lic-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    claims: dict = {
        "sub": sub,
        "iss": license_issuer_default(),
        "aud": "digichat-license",
        "iat": now,
        "exp": exp if exp is not None else now + 90 * 86400,
        "jti": license_id,
        "license_id": license_id,
        "tenant_slug": sub,
        "hosts": ["datatapstream.com"],
        "kind": "digichat-license",
    }
    if services != "absent" and services is not None:
        claims["services"] = list(services)  # type: ignore[arg-type]
    return str(jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": "t1"}))


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.fixture(autouse=True)
def _no_corpus_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)


def _ok_result():
    from digigraph.models import WorkflowResult

    return WorkflowResult(success=True, message="ok", backtest_result={})


def _assert_denial(response, missing_scope: str) -> None:
    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "insufficient_license_scope"
    assert missing_scope in data["message"]


@pytest.mark.unit
class TestPlainInferenceOpen:
    """No hosted headers/flags: license code never runs, turns serve as today."""

    def test_workflow_plain_no_license_ok(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post("/workflow", json=WORKFLOW_PAYLOAD)
        m.assert_called_once()
        assert r.status_code == 200

    def test_workflow_plain_garbage_license_ok(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/workflow", json=WORKFLOW_PAYLOAD, headers={"X-Digi-License": "garbage"}
            )
        m.assert_called_once()
        assert r.status_code == 200

    def test_chat_plain_no_license_ok(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post("/v1/chat/completions", json=CHAT_PAYLOAD)
        m.assert_called_once()
        assert r.status_code == 200

    def test_chat_plain_garbage_license_ok(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/v1/chat/completions", json=CHAT_PAYLOAD, headers={"X-Digi-License": "xx"}
            )
        m.assert_called_once()
        assert r.status_code == 200


@pytest.mark.unit
class TestCorpusGate:
    """Corpus/vault headers require the ``digisearch-corpus`` scope."""

    def test_corpus_no_license_denied(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post("/workflow", json=WORKFLOW_PAYLOAD, headers=CORPUS_HEADERS)
        m.assert_not_called()
        _assert_denial(r, "digisearch-corpus")

    def test_corpus_garbage_license_denied(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": "not-a-jwt"},
            )
        m.assert_not_called()
        _assert_denial(r, "digisearch-corpus")

    def test_corpus_in_scope_allows(self, client: TestClient) -> None:
        token = _mint_license(["digisearch-corpus"])
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": token},
            )
        m.assert_called_once()
        assert r.status_code == 200
        assert m.call_args[0][0].digisearch_index == "pytest-idx"

    def test_corpus_wrong_scope_denied(self, client: TestClient) -> None:
        token = _mint_license(["hosted-web-search"])
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": token},
            )
        m.assert_not_called()
        _assert_denial(r, "digisearch-corpus")

    def test_corpus_services_absent_entitled(self, client: TestClient) -> None:
        token = _mint_license()
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": token},
            )
        m.assert_called_once()
        assert r.status_code == 200

    def test_corpus_expired_license_denied(self, client: TestClient) -> None:
        token = _mint_license(["digisearch-corpus"], exp=int(time.time()) - 7200)
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": token},
            )
        m.assert_not_called()
        _assert_denial(r, "digisearch-corpus")

    def test_corpus_map_set_ignores_headers_without_gate(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Map-authoritative deployments keep map behavior: ignored client
        headers do not trigger the license gate (trust boundary pinned by
        ``TestCorpusTrustBoundary`` in test_api.py)."""
        monkeypatch.setenv(
            "DIGI_TENANT_CORPUS_MAP",
            '{"pytest-tenant":{"digisearchIndex":"mapped_idx","vaultPathPrefix":"clients/mapped"}}',
        )
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post("/workflow", json=WORKFLOW_PAYLOAD, headers=CORPUS_HEADERS)
        m.assert_called_once()
        assert r.status_code == 200
        assert m.call_args[0][0].digisearch_index == "mapped_idx"

    def test_corpus_identity_free_license_denied(self, client: TestClient) -> None:
        token = _mint_license(["digisearch-corpus"], sub="")
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/workflow",
                json=WORKFLOW_PAYLOAD,
                headers={**CORPUS_HEADERS, "X-Digi-License": token},
            )
        m.assert_not_called()
        _assert_denial(r, "digisearch-corpus")


@pytest.mark.unit
class TestWebSearchGate:
    """Web-search opt-in requires the ``hosted-web-search`` scope."""

    def test_workflow_body_flag_no_license_denied(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post("/workflow", json={**WORKFLOW_PAYLOAD, "enable_web_search": True})
        m.assert_not_called()
        _assert_denial(r, "hosted-web-search")

    def test_workflow_body_flag_in_scope_allows(self, client: TestClient) -> None:
        token = _mint_license(["hosted-web-search"])
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/workflow",
                json={**WORKFLOW_PAYLOAD, "enable_web_search": True},
                headers={"X-Digi-License": token},
            )
        m.assert_called_once()
        assert r.status_code == 200

    def test_chat_header_no_license_denied(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/v1/chat/completions",
                json=CHAT_PAYLOAD,
                headers={"X-Digi-Enable-Web-Search": "1"},
            )
        m.assert_not_called()
        _assert_denial(r, "hosted-web-search")

    def test_chat_header_in_scope_allows(self, client: TestClient) -> None:
        token = _mint_license(["hosted-web-search"])
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = _ok_result()
            r = client.post(
                "/v1/chat/completions",
                json=CHAT_PAYLOAD,
                headers={"X-Digi-Enable-Web-Search": "1", "X-Digi-License": token},
            )
        m.assert_called_once()
        assert r.status_code == 200

    def test_chat_body_flag_no_license_denied(self, client: TestClient) -> None:
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/v1/chat/completions",
                json={**CHAT_PAYLOAD, "enable_web_search": True},
            )
        m.assert_not_called()
        _assert_denial(r, "hosted-web-search")

    def test_chat_streaming_web_no_license_denied(self, client: TestClient) -> None:
        """The gate runs before streaming/non-streaming diverge."""
        with patch("digigraph.server.run_digigraph_workflow") as m:
            r = client.post(
                "/v1/chat/completions",
                json={**CHAT_PAYLOAD, "stream": True},
                headers={"X-Digi-Enable-Web-Search": "1"},
            )
        m.assert_not_called()
        _assert_denial(r, "hosted-web-search")
