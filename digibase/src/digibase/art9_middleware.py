"""Art. 9 admission middleware — the refusal floor in front of ingestion routes.

A separate component from `digibase.service_auth`, by design (finding F4 on
DIG-912). `DigiAuthMiddleware` asks ``path_scopes`` for a route's scopes and
``None`` means **public**. Scoped default-deny is the semantic inverse: absent
means refuse. Inverting that inside the auth middleware would turn every
screening bug into an auth outage that takes health, metrics, CORS and every
read endpoint down with it, and would mean debugging two systems during an
incident. So: one new gate, sharing nothing with authentication, mounted per app
by whichever leaf owns that app.

Nothing here reads or writes an auth context and nothing here imports
``digibase.service_auth``. Three of the surfaces this will protect are
unauthenticated by default, so a refusal here has to hold with no authenticated
principal at all.

It is pure ASGI rather than ``@app.middleware("http")`` for the reason
``digibase.metrics`` gives: ``add_middleware`` runs *before* the router, so
``scope["route"]`` is not set yet and the path template has to be resolved here.

The shape of the floor, in order:

1. Resolve the route template from Starlette's own match.
2. ``check_route`` refuses a template that sits under a declared ingestion prefix
   and carries no registry entry, naming the template. When *nothing* matched the
   router at all, the decision is retaken on the concrete path, so a 404 outside
   every declared prefix is still a 404 and the gate never becomes the
   full-route default-deny this registry exists to prevent.
3. A template under no declared prefix has no opinion here and is passed
   through, whatever its body carries. ``RouteDecision.prefix`` is the
   discriminator: ``allow`` on its own is ambiguous between "registered under a
   declared prefix" and "under none", and only the first is in scope.
4. Anything that survives the above and cannot carry a body — ``GET``, ``HEAD``,
   ``OPTIONS``, ``TRACE`` — is passed straight through. A CORS preflight is the
   load-bearing case.
5. Otherwise the body is buffered (bounded), required to be JSON, and screened.
   A body that cannot be read is refused rather than forwarded: a gate that lets
   unreadable payloads through is a speed bump with a badge.
6. Only ``refuse`` blocks. ``screen_request`` reaches ``mask`` solely when handed
   an ``exception_ref``, and this middleware never supplies one — the letter
   behind an Art. 9(2) exception is not a decision this gate is entitled to make.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from digibase.art9 import ROUTE_UNREGISTERED, check_route, screen_request
from digibase.errors import json_error_response

__all__ = ["Art9AdmissionMiddleware", "install_art9_admission"]

#: Returned by `_match_route_template` when no route claimed the request.
_unmatched = "<unmatched>"

#: Methods that cannot carry a request body. Deliberately excludes ``DELETE``:
#: it can, and skipping it would be a hole shaped like a convenience.
_bodiless_methods = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Refusal codes for a body the middleware could not read. Each is a distinct
#: string and none is a prefix of another, so an exact grep for one cannot match
#: another — the reason code is the only thing a consumer has to go on.
_reason_body_not_json = "art9:body_not_json"
_reason_body_unparseable = "art9:body_unparseable"
_reason_body_too_large = "art9:body_too_large"

_refusal_message = (
    "Refused by the Art. 9 admission middleware. The request was not processed. "
    "See the error code for the reason."
)


def _match_route_template(app: FastAPI, scope: Scope) -> str:
    """The router's own path template for this request, or `_unmatched`.

    The same resolution `digibase.metrics._match_route_template` performs, kept
    local rather than imported: that one is private to the metrics module and a
    shared helper for a gate would couple this component to a metric.
    """
    for route in app.router.routes:
        try:
            match, _ = route.matches(scope)
        except (TypeError, AttributeError, ValueError):
            continue
        if match == Match.FULL:
            template = getattr(route, "path", None)
            if template:
                return str(template)
    return _unmatched


def _content_type(scope: Scope) -> str:
    """The request's declared content type, lowercased and without parameters."""
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name == b"content-type":
            return raw_value.split(b";", 1)[0].strip().lower().decode("latin-1")
    return ""


def _is_json(content_type: str) -> bool:
    """Whether `content_type` declares JSON, including the ``+json`` suffix."""
    return content_type == "application/json" or content_type.endswith("+json")


def _decode_body(body: bytes, content_type: str) -> tuple[Any, str | None]:
    """``(payload, refusal_reason)`` — a reason means there is no payload.

    A body with no declared JSON type is refused rather than sniffed: this gate
    cannot know that an unparseable body is harmless, and guessing is how a gate
    becomes a speed bump.
    """
    if not _is_json(content_type):
        return None, _reason_body_not_json
    try:
        return json.loads(body), None
    except (ValueError, RecursionError):
        # `ValueError` covers JSONDecodeError and UnicodeDecodeError; the empty
        # body is a ValueError too. RecursionError is a caller-shaped stack
        # exhaustion attempt and is refused like any other unreadable body.
        return None, _reason_body_unparseable


async def _read_body(receive: Receive, max_bytes: int) -> tuple[bytes, bool, bool]:
    """``(body, too_large, disconnected)`` for a buffered request body.

    Buffers up to `max_bytes` and stops growing past it. A body over the cap is
    refused rather than buffered: an unbounded buffer is a denial of service
    wearing a gate's clothes.
    """
    chunks: list[bytes] = []
    size = 0
    too_large = False
    while True:
        message = await receive()
        if message.get("type") == "http.disconnect":
            return b"", False, True
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > max_bytes:
            too_large = True
        else:
            chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks), too_large, False


def _replay(body: bytes, receive: Receive) -> Receive:
    """A `receive` that hands the buffered body back once, then the real one.

    Splicing the buffered bytes in front is what lets the allow path forward a
    body it has already read.
    """
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


async def _refuse(
    scope: Scope, receive: Receive, send: Send, *, reason: str, service: str | None
) -> None:
    """Answer 403 in the fleet's `ApiErrorEnvelope` shape.

    `request` is not passed to `json_error_response`, so `request_id` is `None`:
    there is no `Request` at this layer, and inventing one would put a number in
    a correlation field that never carried it.
    """
    response = json_error_response(
        status_code=403,
        code=reason,
        message=_refusal_message,
        service=service,
    )
    await response(scope, receive, send)


class Art9AdmissionMiddleware:
    """Refuse unregistered and special-category requests under declared prefixes.

    `app_name` keys the registry: it must match a key of
    `digibase.art9.INGEST_PREFIXES`, because that is what scopes the floor. An
    app name with no declared prefix has no floor and screens nothing, which is
    the correct reading of "outside every declared prefix" rather than a
    configuration error.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        fastapi_app: FastAPI,
        app_name: str,
        service: str | None = None,
        max_body_bytes: int = 1_048_576,
    ) -> None:
        self.app = app
        self.fastapi_app = fastapi_app
        self.app_name = app_name
        self.service = service
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        template = _match_route_template(self.fastapi_app, scope)
        decision = check_route(self.app_name, template)
        if not decision.refused and template == _unmatched:
            # Nothing claimed this request. Deciding on the concrete path keeps
            # the floor inside the declared prefixes instead of turning every
            # 404 into a 403.
            decision = check_route(self.app_name, str(scope.get("path") or "/"))

        if decision.refused:
            await _refuse(
                scope,
                receive,
                send,
                reason=decision.reason or ROUTE_UNREGISTERED,
                service=self.service,
            )
            return

        if decision.prefix is None:
            # `allow` alone is ambiguous: it covers both "registered under a
            # declared prefix" and "under no declared prefix at all". Only the
            # first carries an opinion. `RouteDecision.prefix` is the
            # discriminator, and skipping here is what keeps the floor inside
            # the prefixes instead of screening the whole application.
            await self.app(scope, receive, send)
            return

        if str(scope.get("method", "GET")).upper() in _bodiless_methods:
            await self.app(scope, receive, send)
            return

        body, too_large, disconnected = await _read_body(receive, self.max_body_bytes)
        if disconnected:
            await self.app(scope, receive, send)
            return
        if too_large:
            await _refuse(
                scope,
                receive,
                send,
                reason=_reason_body_too_large,
                service=self.service,
            )
            return

        payload, refusal = _decode_body(body, _content_type(scope))
        if refusal is not None:
            await _refuse(scope, receive, send, reason=refusal, service=self.service)
            return

        result = screen_request(payload)
        if result.decision == "refuse":
            await _refuse(scope, receive, send, reason=result.reason, service=self.service)
            return

        await self.app(scope, _replay(body, receive), send)


def install_art9_admission(
    app: FastAPI,
    *,
    app_name: str,
    service: str | None = None,
    max_body_bytes: int = 1_048_576,
) -> None:
    """Mount `Art9AdmissionMiddleware` on `app`.

    This leaf mounts it nowhere: leaves 8, 9 and 10 mount it on digisearch,
    on digigraph and digivault, and on digillm's MCP app respectively, and each
    owns its own mount point. `app.add_middleware(Art9AdmissionMiddleware, …)`
    is equally supported and is what those leaves' own lines are free to use.
    """
    app.add_middleware(
        Art9AdmissionMiddleware,
        fastapi_app=app,
        app_name=app_name,
        service=service or app_name,
        max_body_bytes=max_body_bytes,
    )
