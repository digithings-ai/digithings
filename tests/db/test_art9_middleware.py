"""Leaf L3 — the Art. 9 admission middleware, the refusal floor for ingestion.

Every test drives a real ``FastAPI`` app through ``TestClient``. The middleware
resolves the route template from Starlette's own match, and that is the one thing
a hand-rolled ASGI double would let a broken matcher pass.

The four cases the brief requires are marked ``BRIEF 1`` … ``BRIEF 4``. The rest
pin decisions this leaf adds on top of them — each one is a way the middleware
could be a speed bump instead of a gate.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from digibase.art9 import ROUTE_UNREGISTERED, no_match_reason
from digibase.art9_middleware import Art9AdmissionMiddleware, install_art9_admission
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

# A clean body: `title` and `tags` are in neither the §5.5 field-name table nor
# the value patterns, so `screen_request` returns `allow` with `no_match_reason`.
CLEAN: dict[str, Any] = {"title": "quarterly report", "tags": ["alpha", "beta"]}
# A body that trips `health` on a field-name hit. `diagnosis` is a §5.5 name for
# `health`, and a key hit outranks a value pattern, so the reason is stable.
TRIPPING: dict[str, Any] = {"diagnosis": "influenza"}


def _build_app(calls: list[str], *, max_body_bytes: int = 1_048_576) -> FastAPI:
    """A `digisearch` app: two registered ingest routes, one unregistered, one outside."""
    application = FastAPI()

    @application.post("/ingest")
    def ingest(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/ingest")
        return payload

    @application.post("/ingest/url")
    def ingest_url(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/ingest/url")
        return payload

    @application.post("/ingest/upload")
    def ingest_upload(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/ingest/upload")
        return payload

    @application.post("/echo")
    def echo(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/echo")
        return payload

    @application.get("/health")
    def health() -> dict[str, bool]:
        calls.append("/health")
        return {"ok": True}

    install_art9_admission(
        application,
        app_name="digisearch",
        service="digisearch",
        max_body_bytes=max_body_bytes,
    )
    return application


@pytest.fixture
def calls() -> list[str]:
    """Every handler invocation, in order. The brief's tests assert on this."""
    return []


@pytest.fixture
def app(calls: list[str]) -> FastAPI:
    return _build_app(calls)


def _error_code(response: Any) -> str:
    return response.json()["error"]["code"]


# ── BRIEF 1: registered route, tripping body, refused, handler never called ──


def test_registered_ingest_route_with_a_special_category_body_is_refused(app: FastAPI) -> None:
    """BRIEF 1 — refused on the status code *and* on the handler never running."""
    calls: list[str] = []

    with TestClient(app) as client:
        response = client.post("/ingest", json=TRIPPING)

    assert response.status_code == 403
    assert _error_code(response) == "art9:health:field_name"
    assert calls == [], "the route handler ran despite the refusal"


def test_a_refusal_names_the_category_not_the_value(app: FastAPI) -> None:
    """The reason is a stable code. It must never carry the matched value."""
    with TestClient(app) as client:
        response = client.post("/ingest", json=TRIPPING)

    body = response.text
    assert "influenza" not in body
    assert "diagnosis" not in body


def test_a_clean_body_reaches_the_handler_intact(app: FastAPI) -> None:
    """The allow path must replay the body it buffered, byte for byte."""
    with TestClient(app) as client:
        response = client.post("/ingest", json=CLEAN)

    assert response.status_code == 200
    assert response.json() == CLEAN


def test_the_refusal_uses_the_fleet_error_envelope(app: FastAPI) -> None:
    """`ApiErrorEnvelope` is a fleet-wide contract; a refusal must honour it."""
    with TestClient(app) as client:
        response = client.post("/ingest", json=TRIPPING)

    error = response.json()["error"]
    assert set(error) == {"code", "message", "request_id", "service"}
    assert error["service"] == "digisearch"


# ── BRIEF 2: unregistered route under a declared prefix, refused, route named ──


def test_unregistered_route_under_a_declared_prefix_is_refused_naming_the_route(
    app: FastAPI, calls: list[str]
) -> None:
    """BRIEF 2 — `/ingest/upload` exists on the app but carries no registry entry."""
    with TestClient(app) as client:
        response = client.post("/ingest/upload", json=CLEAN)

    assert response.status_code == 403
    assert _error_code(response) == f"{ROUTE_UNREGISTERED}:/ingest/upload"
    assert calls == []


def test_a_prefix_does_not_cover_a_path_that_merely_starts_with_the_same_letters(
    app: FastAPI,
) -> None:
    """`/ingest` must not cover `/ingested`: over-covering refuses routes nobody declared."""
    with TestClient(app) as client:
        response = client.post("/ingested/anything", json=CLEAN)

    assert response.status_code == 404, "a declared prefix over-covered its own scope"


def test_an_unmatched_path_under_a_declared_prefix_is_refused_naming_the_path(
    app: FastAPI,
) -> None:
    """Nothing matched the router, and the path is under a declared prefix.

    `check_route`'s contract hands this branch to this leaf explicitly: the
    caller refuses when nothing matched at all.
    """
    with TestClient(app) as client:
        response = client.post("/ingest/ghost/nested", json=CLEAN)

    assert response.status_code == 403
    assert _error_code(response) == f"{ROUTE_UNREGISTERED}:/ingest/ghost/nested"


# ── BRIEF 3: outside every declared prefix, untouched ──


def test_route_under_no_declared_prefix_reaches_the_handler(app: FastAPI, calls: list[str]) -> None:
    """BRIEF 3 — `/health` is outside `/ingest` and must be left alone."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == ["/health"]


def test_a_special_category_outside_every_declared_prefix_is_not_screened(
    app: FastAPI, calls: list[str]
) -> None:
    """Scope comes from the declared prefixes, never from the body's content."""
    with TestClient(app) as client:
        response = client.post("/echo", json=TRIPPING)

    assert response.status_code == 200
    assert response.json() == TRIPPING
    assert calls == ["/echo"]


def test_an_unmatched_path_outside_every_prefix_is_left_to_the_router(
    app: FastAPI, calls: list[str]
) -> None:
    """The discriminator against full-route default-deny: 404 stays a 404."""
    with TestClient(app) as client:
        response = client.get("/nowhere")

    assert response.status_code == 404
    assert calls == []


# ── BRIEF 4: a non-JSON or unparseable body on a declared prefix is refused ──


@pytest.mark.parametrize(
    ("content", "content_type", "expected"),
    [
        (b"<xml/>", "application/xml", "art9:body_not_json"),
        (b"<xml/>", "text/plain", "art9:body_not_json"),
        (b'{"diagnosis": ', "application/json", "art9:body_unparseable"),
        (b"", "application/json", "art9:body_unparseable"),
        (b"\xff\xfe\x00broken", "application/json", "art9:body_unparseable"),
    ],
    ids=["xml", "text", "truncated", "empty", "undecodable"],
)
def test_a_body_the_middleware_cannot_read_is_refused_not_passed_through(
    app: FastAPI, calls: list[str], content: bytes, content_type: str, expected: str
) -> None:
    """BRIEF 4 — the test that decides whether this is a gate or a speed bump."""
    with TestClient(app) as client:
        response = client.post("/ingest", content=content, headers={"content-type": content_type})

    assert response.status_code == 403
    assert _error_code(response) == expected
    assert calls == []


def test_a_body_with_no_content_type_at_all_is_refused(app: FastAPI, calls: list[str]) -> None:
    """No declared type means no claim the body was readable. Fail closed."""
    with TestClient(app) as client:
        response = client.post("/ingest", content=b'{"title": "hi"}')

    assert response.status_code == 403
    assert _error_code(response) == "art9:body_not_json"
    assert calls == []


def test_a_json_suffix_content_type_is_accepted(app: FastAPI) -> None:
    """`application/vnd.x+json` is JSON. The allow path must not break on it."""
    with TestClient(app) as client:
        response = client.post(
            "/ingest",
            content=b'{"title": "hi"}',
            headers={"content-type": "application/vnd.example+json; charset=utf-8"},
        )

    assert response.status_code == 200


def test_a_body_over_the_cap_is_refused_rather_than_buffered(calls: list[str]) -> None:
    """An unbounded buffer is a denial of service wearing a gate's clothes."""
    app = _build_app(calls, max_body_bytes=64)

    with TestClient(app) as client:
        response = client.post("/ingest", json={"title": "x" * 200})

    assert response.status_code == 403
    assert _error_code(response) == "art9:body_too_large"
    assert calls == []


# ── decisions this leaf adds on top of the brief's four ──


def test_an_options_preflight_is_not_body_screened(app: FastAPI) -> None:
    """A preflight carries no body. Screening it would 403 CORS everywhere."""
    with TestClient(app) as client:
        response = client.request("OPTIONS", "/ingest")

    assert response.status_code == 405, "the middleware screened a bodiless preflight"


def test_a_get_on_a_registered_ingest_route_is_not_body_screened(app: FastAPI) -> None:
    """`GET /v1/notes` lists and `POST` creates, sharing one template."""
    with TestClient(app) as client:
        response = client.get("/ingest")

    assert response.status_code == 405


def test_a_read_kind_route_is_screened_when_it_carries_a_body(calls: list[str]) -> None:
    """Keyed on *registration*, not on the registry's `read` kind.

    The registry takes the strict kind wherever a template serves both a read
    and an ingest (`/v1/notes`), and says so. Honouring `read` as "skip
    screening" would reopen exactly that hole on any future template.
    """
    application = FastAPI()

    @application.post("/v1/notes/{name}")
    def write_note(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/v1/notes/{name}")
        return payload

    install_art9_admission(application, app_name="digivault", service="digivault")

    with TestClient(application) as client:
        response = client.post("/v1/notes/weekly", json=TRIPPING)

    assert response.status_code == 403
    assert _error_code(response) == "art9:health:field_name"
    assert calls == []


def test_the_middleware_needs_no_authenticated_principal(app: FastAPI) -> None:
    """Three surfaces it protects are unauthenticated by default.

    There is no auth context anywhere in this fixture and no credential is sent;
    the refusal must not depend on one existing.
    """
    with TestClient(app) as client:
        response = client.post("/ingest", json=TRIPPING)

    assert response.status_code == 403


def test_middleware_can_be_added_with_add_middleware_directly(calls: list[str]) -> None:
    """Leaves 8/ 9/ 10 own their own `add_middleware` line; that path must work."""
    application = FastAPI()

    @application.post("/ingest")
    def ingest(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("/ingest")
        return payload

    application.add_middleware(
        Art9AdmissionMiddleware,
        fastapi_app=application,
        app_name="digisearch",
    )

    with TestClient(application) as client:
        refused = client.post("/ingest", json=TRIPPING)
        allowed = client.post("/ingest", json=CLEAN)

    assert refused.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == CLEAN
    assert calls == ["/ingest"]


def test_the_package_re_exports_the_public_surface() -> None:
    """`digibase/__init__.py` is the fleet's import path; both names must be there."""
    import digibase

    assert digibase.Art9AdmissionMiddleware is Art9AdmissionMiddleware
    assert digibase.install_art9_admission is install_art9_admission


def test_the_module_imports_nothing_from_authentication() -> None:
    """F4: a screening bug must not become an auth outage. No shared imports.

    The whole import set is pinned, not just an absence — a scan for the *name*
    would fire on this module's own docstring, which discusses why the import
    does not exist.
    """
    import ast

    import digibase.art9_middleware as middleware

    source = middleware.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert imported == {
        "__future__",
        "json",
        "typing",
        "fastapi",
        "starlette.routing",
        "starlette.types",
        "digibase.art9",
        "digibase.errors",
    }, imported


def test_a_no_match_payload_is_reported_as_no_match(app: FastAPI) -> None:
    """A consumer must be able to tell "tripped nothing" from "refused"."""
    with TestClient(app) as client:
        response = client.post("/ingest", json=CLEAN)

    assert response.status_code == 200
    assert no_match_reason == "art9:no_match"


def _asgi_scope(path: str, method: str) -> dict[str, Any]:
    """The minimum a scope needs for Starlette's own route matching to run."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }


def _drive(app: FastAPI, *, path: str, chunks: list[dict[str, Any]]) -> tuple[list[str], bytes]:
    """Call the middleware directly. Returns (paths downstream saw, body it sent)."""
    reached: list[str] = []
    answered = bytearray()
    pending = list(chunks)

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        reached.append(str(scope.get("path")))

    async def receive() -> Any:
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: Any) -> None:
        answered.extend(bytes(message.get("body", b"")))

    middleware = Art9AdmissionMiddleware(downstream, fastapi_app=app, app_name="digisearch")
    asyncio.run(middleware(_asgi_scope(path, "POST"), receive, send))
    return reached, bytes(answered)


def test_a_client_that_hung_up_is_passed_on_untouched(app: FastAPI) -> None:
    """A mid-body disconnect is the router's business, not a screening verdict.

    `_read_body` sees `http.disconnect` and hands the request straight on.
    Answering 403 to a client that is already gone would be the middleware
    inventing a screening decision out of a transport event.
    """
    reached, answered = _drive(app, path="/ingest", chunks=[{"type": "http.disconnect"}])

    assert reached == ["/ingest"]
    assert b"art9:" not in answered


def test_the_disconnect_case_is_distinguishable_from_a_refusal(app: FastAPI) -> None:
    """Control: the same drive, with a readable tripping body, IS refused.

    Without this the assertion above would also pass if the harness never sent
    anything at all — an empty answer reads like "no verdict".
    """
    reached, answered = _drive(
        app,
        path="/ingest",
        chunks=[{"type": "http.request", "body": json.dumps(TRIPPING).encode()}],
    )

    assert reached == []
    assert b"art9:health:field_name" in answered
