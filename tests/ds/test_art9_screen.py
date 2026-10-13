"""Service surface tests for POST /internal/art9/screen (DIG-1176). Offline only.

The route is fail-closed: a transcript reaches the caller's storage only on a
200 carrying decision "allow". Everything else refuses.
"""

from __future__ import annotations

import pytest
from digikey.integrations.service_middleware import _PUBLIC_PATHS, digisearch_path_scopes
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

SCREEN_URL = "/internal/art9/screen"

# A field name that trips the "genetic" category. Verified to trip on the
# stack parent: screen_request({"genetic": "x"}).decision == "refuse".
TRIPPING_FIELD = "genetic"
# The sensitive value that must never leave the process.
RAW_VALUE = "GH-FINGERPRINT-0123456789-DO-NOT-LOG"


def _clean_payload() -> dict:
    return {
        "surface": "chat",
        "conversation_id": "conv-1",
        "messages": [{"role": "user", "parts": [{"type": "text", "text": "hello"}]}],
        "exception_ref": None,
    }


def _tripping_payload() -> dict:
    payload = _clean_payload()
    payload["messages"] = [
        {"role": "user", "parts": [{"type": "text", "text": "hello"}]},
        {"role": "assistant", TRIPPING_FIELD: RAW_VALUE},
    ]
    return payload


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def test_a_tripping_body_is_refused_with_category_ids_and_no_raw_value(client: TestClient) -> None:
    """1. A body tripping a category -> 422 art9_refused, ids only, never the value."""
    response = client.post(SCREEN_URL, json=_tripping_payload())

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "art9_refused"
    assert body["categories"] == ["genetic"]
    # The decision is never allow, and the response never carries a redacted value.
    assert body["decision"] != "allow"
    assert "redacted" not in body
    # The sensitive value appears nowhere in the body, headers or reason code.
    assert RAW_VALUE not in response.text
    assert TRIPPING_FIELD not in body["reason"] or body["reason"] == "art9:genetic:field_name"


def test_a_clean_body_is_allowed(client: TestClient) -> None:
    """2. A clean body -> 200 allow."""
    response = client.post(SCREEN_URL, json=_clean_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "allow"
    assert body["categories"] == []
    assert body["reason"] == "art9:no_match"


def test_a_mask_is_treated_as_a_refusal_not_a_pass(client: TestClient) -> None:
    """3. mask -> 422, never 200. v1 has no lawful basis to store a masked transcript."""
    payload = _tripping_payload()
    payload["exception_ref"] = "ART9-2-LETTER-42"

    response = client.post(SCREEN_URL, json=payload)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "art9_refused"
    assert response.json()["decision"] != "allow"
    assert response.json()["exception_ref"] == "ART9-2-LETTER-42"


def test_both_size_bounds_are_enforced(client: TestClient) -> None:
    """4. 413 on an oversize body AND on over 500 messages -- both, not one."""
    oversized = _clean_payload()
    oversized["messages"] = [
        {"role": "user", "parts": [{"type": "text", "text": "x" * (1024 * 1024 + 64)}]}
    ]
    # Hold the statuses in names: a raw assert on the call would put a 1 MiB
    # payload into the failure report, which is unreadable and hides the cause.
    oversize_status = client.post(SCREEN_URL, json=oversized).status_code

    too_many = _clean_payload()
    too_many["messages"] = [{"role": "user", "parts": [{"type": "text", "text": "x"}]}] * 501
    too_many_status = client.post(SCREEN_URL, json=too_many).status_code

    assert oversize_status == 413, f"oversize body returned {oversize_status}"
    assert too_many_status == 413, f"501 messages returned {too_many_status}"


def test_a_failing_screener_is_502_never_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Screener unreachable -> 502, and there is no retry that eventually admits."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("screening hop unavailable")

    monkeypatch.setattr("digisearch.art9_screen.screen_request", _boom)

    response = client.post(SCREEN_URL, json=_clean_payload())

    assert response.status_code == 502, response.text
    assert response.json()["code"] == "art9_screen_unavailable"


def test_the_route_is_authenticated_and_not_public() -> None:
    """6. Absent from _PUBLIC_PATHS, registered, and reachable only through auth."""
    # The route must actually exist. DigiAuthMiddleware runs BEFORE routing, so a
    # bare 401 would be returned for a path that does not exist either: without
    # this assertion the whole guard passes on an unimplemented endpoint.
    # The schema is the stable public surface; app.routes holds an _IncludedRouter
    # wrapper rather than a flattened route on FastAPI 0.141.
    assert SCREEN_URL in app.openapi()["paths"]

    assert SCREEN_URL not in _PUBLIC_PATHS
    assert digisearch_path_scopes("POST", SCREEN_URL) is not None

    # The negative control: no credential -> 401.
    anonymous = TestClient(app)
    assert anonymous.post(SCREEN_URL, json=_clean_payload()).status_code == 401

    # The positive control, and the load-bearing one: the same request WITH a
    # credential must get past the middleware. Without it, the 401 above is
    # indistinguishable from the route being absent.
    authenticated = TestClient(app, headers=auth_headers())
    assert authenticated.post(SCREEN_URL, json=_clean_payload()).status_code != 401