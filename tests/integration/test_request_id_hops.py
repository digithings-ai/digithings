"""End-to-end X-Request-ID propagation across three service hops (task #213).

Gives us confidence that the *mechanics* of middleware + outbound helper
survive chaining, not just each service in isolation. Three bare FastAPI apps
stand in for DigiChat/DigiGraph/DigiSearch — the real service code already
exercises the same primitives at unit level; what we're asserting here is
that the id survives two hops of service-to-service forwarding when each hop
uses :func:`digibase.http.outbound_service_headers`.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request

from digibase.http import (
    current_request_id,
    install_request_id_middleware,
    outbound_service_headers,
)


pytestmark = pytest.mark.unit


def _leaf_app(seen: list[str]) -> FastAPI:
    """Terminal service — records the id it saw, echoes it back."""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/leaf")
    def leaf(request: Request) -> dict[str, str | None]:
        rid = current_request_id()
        seen.append(rid or "")
        return {"request_id": rid, "state": getattr(request.state, "request_id", None)}

    return app


def _middle_app(leaf: FastAPI, seen: list[str]) -> FastAPI:
    """Hop 2 — forwards to leaf using the shared outbound helper."""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/fanout")
    async def fanout(request: Request) -> dict[str, object]:
        rid = current_request_id()
        seen.append(rid or "")
        transport = httpx.ASGITransport(app=leaf)
        async with httpx.AsyncClient(transport=transport, base_url="http://leaf") as client:
            headers = outbound_service_headers(rid, bearer_token=None)
            r = await client.get("/leaf", headers=headers)
        return {
            "middle": rid,
            "downstream": r.json(),
            "downstream_header": r.headers.get("X-Request-ID"),
        }

    return app


def _entry_app(middle: FastAPI, seen: list[str]) -> FastAPI:
    """Hop 1 — simulates DigiChat BFF originating the request."""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/entry")
    async def entry(request: Request) -> dict[str, object]:
        rid = current_request_id()
        seen.append(rid or "")
        transport = httpx.ASGITransport(app=middle)
        async with httpx.AsyncClient(transport=transport, base_url="http://middle") as client:
            headers = outbound_service_headers(rid, bearer_token=None)
            r = await client.get("/fanout", headers=headers)
        return {
            "entry": rid,
            "next": r.json(),
            "next_header": r.headers.get("X-Request-ID"),
        }

    return app


async def _call(entry: FastAPI, headers: dict[str, str] | None) -> httpx.Response:
    transport = httpx.ASGITransport(app=entry)
    async with httpx.AsyncClient(transport=transport, base_url="http://entry") as client:
        return await client.get("/entry", headers=headers or {})


def test_request_id_survives_three_hops_when_client_supplies_id() -> None:
    seen: list[str] = []
    leaf = _leaf_app(seen)
    middle = _middle_app(leaf, seen)
    entry = _entry_app(middle, seen)

    r = asyncio.run(_call(entry, {"X-Request-ID": "rid-3hops"}))

    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "rid-3hops"
    assert seen == ["rid-3hops", "rid-3hops", "rid-3hops"]
    body = r.json()
    assert body["entry"] == "rid-3hops"
    assert body["next_header"] == "rid-3hops"
    assert body["next"]["middle"] == "rid-3hops"
    assert body["next"]["downstream_header"] == "rid-3hops"
    assert body["next"]["downstream"]["request_id"] == "rid-3hops"


def test_generated_id_at_entry_propagates_to_leaf() -> None:
    """No inbound header → entry generates an id; same id must reach the leaf."""
    seen: list[str] = []
    leaf = _leaf_app(seen)
    middle = _middle_app(leaf, seen)
    entry = _entry_app(middle, seen)

    r = asyncio.run(_call(entry, None))

    assert r.status_code == 200
    generated = r.headers["X-Request-ID"]
    assert len(generated) == 32
    assert seen == [generated, generated, generated]
