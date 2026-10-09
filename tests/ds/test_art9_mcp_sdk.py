"""Art. 9 screening on digisearch's non-HTTP surfaces (DIG-1083 leaf 10).

Two acceptance tests live here.

**AT7** — ``POST /v1/monitors/exa_webhook`` is screened *despite being the
route the auth policy exempts*. The trap this file exists for: that route is
outside every ingest prefix, so ``digibase.check_route`` returns
``allow`` with ``prefix=None`` and leaf 3's admission middleware passes it
through **without reading the body**. A path-keyed floor cannot see a surface
that has no path, so the screen has to come from an explicit registry entry.

**AT8** — the MCP surface and the SDK entry are screened or refused by that
same registry. ``digibase``'s registry is keyed by HTTP path templates and
therefore structurally cannot see a pathless MCP tool call or an in-process
SDK call; without an entry here, *not* screening them would be invisible.

Every refusal assertion is driven by ``decision == "refuse"``, never by
``redacted``: leaf 1 leaves ``redacted`` as ``None`` on every path (masking is
leaf 2), so a redacted-based assertion would pass structurally on an absent
subject. Every tripping payload is proven tripping first.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator

import pytest
from digibase.art9 import check_route, screen_request
from digikey.integrations.service_middleware import digisearch_path_scopes
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from digisearch import client as art9
from digisearch import mcp_server, server

pytestmark = pytest.mark.unit

#: The marker above is REQUIRED, not decorative. ``test-digisearch.yml`` runs
#: ``pytest tests/ds/ -m unit``; a file without the marker collects 0 items and
#: prints a green line having asserted nothing.

#: Trips on a *field name*: ``genotype`` is one of leaf 1's ``field_names``
#: substrings for the genetic category.
TRIPPING_FIELD_NAME = {"genotype": "patient-1", "nhs_number": "943 476 5919"}
#: Trips on a *value pattern*: ``\brs\d{3,}\b`` is leaf 1's (genetic, rs_id).
TRIPPING_VALUE = {"title": "genotype call rs1234 for subject 4"}
BENIGN = {"title": "release notes for digisearch 2.4.0", "count": 3}

#: A payload shaped like an EXA webhook event that carries an Art. 9 signal in
#: free text. It is faithful to the route's own schema on purpose: the screen
#: must fire on what the route really receives, not on a synthetic shape.
EXA_TRIPPING = {
    "event": "update",
    "data": {"monitorId": "exa-monitor-1", "title": "genotype call rs1234 uploaded"},
}
#: Same shape, no signal, and no monitor id either: ``exa_monitor_id_from_payload``
#: rejects it with 422 **before** the monitor store is ever touched, so the
#: negative control never reads or writes client state on disk.
EXA_BENIGN_UNRESOLVABLE = {"event": "update", "data": {}}

EXA_WEBHOOK_PATH = "/v1/monitors/exa_webhook"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _result_shape(result: object) -> object:
    """Assert a screen result is a ``ScreenResult``-shaped object.

    The digisearch registry delegates to ``digibase.art9.screen_request``, but
    a refusal for an unregistered surface is built locally. Asserting the shape
    first lets every test below assert on ``decision`` without caring which of
    the two produced it.
    """
    for name in ("decision", "categories", "reason"):
        assert hasattr(result, name), f"screen result is missing {name!r}"
    assert result.decision in {"allow", "mask", "refuse"}
    assert isinstance(result.categories, tuple)
    assert isinstance(result.reason, str)
    return result


def _served_templates() -> dict[str, set[str]]:
    """Every ``app.routes`` path template mapped to its methods.

    This is the oracle leaf 4a uses and the only permitted source of registry
    keys (F3): a hand-written route string in the registry would make the diff
    below a tautology.
    """
    served: dict[str, set[str]] = {}
    for route in server.app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        served.setdefault(route.path, set()).update(methods)
    return served


def _registered_http_templates() -> set[str]:
    return {
        surface[len(art9.SURFACE_KIND_HTTP) + 1 :]
        for surface, kind in server.AUTH_EXEMPT_SURFACES.items()
        if kind == art9.SURFACE_KIND_HTTP
    }


def _digikey_exempt_templates() -> set[str]:
    """Templates digikey itself treats as public.

    Read from digikey rather than from ``server._digisearch_path_scopes`` so the
    diff below compares the registry against an *independent* source instead of
    against a second copy of the same expression.
    """
    return {
        path
        for path, methods in _served_templates().items()
        if any(digisearch_path_scopes(method, path) is None for method in methods)
    }


@contextlib.contextmanager
def _attached(route: APIRoute) -> Iterator[None]:
    """Attach a real ``APIRoute`` to the running app, then remove it by identity."""
    server.app.routes.append(route)
    try:
        yield
    finally:
        for index, existing in enumerate(server.app.routes):
            if existing is route:
                del server.app.routes[index]
                break
        else:  # pragma: no cover - only reached if the route was lost
            raise AssertionError("probe route was not attached to app.routes")


def _probe_route(path: str) -> APIRoute:
    async def _endpoint() -> dict[str, bool]:  # pragma: no cover - never called
        return {"ok": True}

    return APIRoute(path=path, endpoint=_endpoint, methods=["POST"])


def _server_with_observed_tool() -> tuple[FastMCP, list[str]]:
    """A throwaway FastMCP whose tool body records that it was entered.

    The body is a local list append, so a call that is screened never reaches
    the network and the negative control is hermetic.
    """
    entered: list[str] = []

    server_obj = FastMCP("art9-probe", json_response=True)

    @server_obj.tool()
    def probe(text: str) -> str:
        entered.append(text)
        return f"echo:{text}"

    return server_obj, entered


def _call(server_obj: FastMCP, **arguments: object) -> object:
    """Dispatch through the real server-side tool path, not a client-facing one."""
    return asyncio.run(
        server_obj._tool_manager.call_tool("probe", arguments, convert_result=False)  # noqa: SLF001
    )


# --------------------------------------------------------------------------
# positive controls — prove the payloads trip before asserting they are refused
# --------------------------------------------------------------------------


def test_the_tripping_payloads_really_trip_the_detector() -> None:
    """Positive control: the detector refuses both, and allows the benign one.

    Without this, every refusal assertion below could be passing because the
    screen never runs at all.
    """
    for payload in (TRIPPING_FIELD_NAME, TRIPPING_VALUE, EXA_TRIPPING):
        result = _result_shape(screen_request(payload))
        assert result.decision == "refuse", f"payload did not trip: {payload!r}"
        assert result.categories, "refusal carried no category"
        assert result.reason.startswith("art9:")
    allowed = _result_shape(screen_request(BENIGN))
    assert allowed.decision == "allow"
    assert allowed.reason == "art9:no_match"


def test_the_field_name_hit_outranks_the_value_hit_in_the_reason() -> None:
    """A payload carrying both signals refuses for the field name.

    Pins which reason reaches a caller when two categories are present, so a
    change in leaf 1's tie-break cannot silently rewrite this leaf's contract.
    """
    result = _result_shape(screen_request({"genetic": "x", "biometric": "y"}))
    assert result.decision == "refuse"
    assert result.reason == "art9:genetic:field_name"


# --------------------------------------------------------------------------
# AT8 — the registry itself
# --------------------------------------------------------------------------


def test_the_mcp_and_sdk_surfaces_are_registered() -> None:
    assert art9.ART9_SURFACES[art9.SURFACE_MCP] == art9.SURFACE_KIND_MCP
    assert art9.ART9_SURFACES[art9.SURFACE_SDK_INGEST] == art9.SURFACE_KIND_SDK
    assert art9.art9_surface_kind(art9.SURFACE_MCP) == art9.SURFACE_KIND_MCP


def test_the_registry_view_is_read_only() -> None:
    with pytest.raises(TypeError):
        art9.ART9_SURFACES["mcp"] = "something-else"  # type: ignore[index]


def test_declaring_a_surface_is_visible_and_reversible() -> None:
    name = "mcp:test-art9-mcp-sdk"
    try:
        art9.declare_art9_surface(name, art9.SURFACE_KIND_MCP)
        assert art9.ART9_SURFACES[name] == art9.SURFACE_KIND_MCP
        assert art9.art9_surface_kind(name) == art9.SURFACE_KIND_MCP
    finally:
        art9._surfaces.pop(name, None)  # noqa: SLF001
    assert name not in art9.ART9_SURFACES


def test_an_unregistered_surface_is_refused_whatever_the_payload() -> None:
    """F11: a missing registration is a refusal, not a silent pass.

    This is what makes the *absence* of a registry entry detectable. If an
    unknown surface screened as ``allow``, a surface nobody registered would be
    indistinguishable from a surface that was screened and found clean.
    """
    for payload in (BENIGN, TRIPPING_VALUE, None):
        result = _result_shape(art9.screen_art9_surface("mcp:not-declared", payload))
        assert result.decision == "refuse"
        assert result.reason == f"{art9.SURFACE_UNREGISTERED}:mcp:not-declared"
        assert result.categories == ()


def test_a_registered_surface_delegates_to_the_detector() -> None:
    refused = _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, TRIPPING_VALUE))
    assert refused.decision == "refuse"
    assert refused.categories == ("genetic",)
    allowed = _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, BENIGN))
    assert allowed.decision == "allow"


def test_require_art9_clear_raises_only_on_refusal() -> None:
    assert art9.require_art9_clear(art9.SURFACE_MCP, BENIGN) is None
    with pytest.raises(art9.Art9SurfaceRefusal) as excinfo:
        art9.require_art9_clear(art9.SURFACE_MCP, TRIPPING_VALUE)
    assert excinfo.value.surface == art9.SURFACE_MCP
    assert excinfo.value.result.categories == ("genetic",)


def test_the_refusal_reason_survives_the_json_a_client_receives() -> None:
    """The reason is what reaches an MCP client, so it must be serialisable."""
    result = _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, TRIPPING_VALUE))
    assert json.loads(json.dumps({"reason": result.reason}))["reason"] == result.reason


# --------------------------------------------------------------------------
# AT8 — the digisearch MCP surface
# --------------------------------------------------------------------------


def test_every_registered_digisearch_mcp_tool_is_screened() -> None:
    """The screen is installed on *every* tool, not on a sample.

    ``create_mcp_with_indexes`` registers no tools, so the tool set is fixed at
    import time by the ``@mcp.tool()`` decorators. Asserting equality with the
    live count means a tool added later without a screen fails this test.
    """
    tools = mcp_server.mcp._tool_manager.list_tools()  # noqa: SLF001
    assert tools, "the digisearch MCP server exposes no tools to screen"
    assert mcp_server.ART9_SCREENED_TOOLS == len(tools)
    for tool in tools:
        assert getattr(tool.fn, "__art9_screened__", False), tool.name


def test_a_screened_tool_keeps_its_name() -> None:
    """The wrapper must not change the name the tool is advertised under."""
    for tool in mcp_server.mcp._tool_manager.list_tools():  # noqa: SLF001
        assert tool.fn.__name__ == tool.name


def test_a_tool_call_tripping_a_category_is_refused_before_the_body_runs() -> None:
    server_obj, entered = _server_with_observed_tool()
    assert mcp_server.install_art9_surface_screen(server_obj) == 1
    with pytest.raises(ToolError) as excinfo:
        _call(server_obj, text=TRIPPING_VALUE["title"])
    assert entered == [], "the tool body ran despite a tripping payload"
    cause = excinfo.value.__cause__
    assert isinstance(cause, art9.Art9SurfaceRefusal)
    assert cause.result.categories == ("genetic",)
    assert cause.result.reason.startswith("art9:")


def test_a_benign_tool_call_still_reaches_the_body() -> None:
    """Negative control: the screen is not simply refusing everything."""
    server_obj, entered = _server_with_observed_tool()
    assert mcp_server.install_art9_surface_screen(server_obj) == 1
    assert _call(server_obj, text="hello") == "echo:hello"
    assert entered == ["hello"]


def test_the_mcp_screen_guard_can_go_red() -> None:
    """The mutation assertion: undo the screen and the same call succeeds.

    Reading a guard's green as evidence it fires is the empty-vs-empty trap.
    Removing the wrapper in place, asserting the guard goes red, and restoring
    it in a ``finally`` is the only way to know the test can fail.
    """
    server_obj, entered = _server_with_observed_tool()
    assert mcp_server.install_art9_surface_screen(server_obj) == 1
    tool = server_obj._tool_manager.get_tool("probe")  # noqa: SLF001
    screened_fn = tool.fn
    original_fn = tool.fn.__wrapped__ if hasattr(tool.fn, "__wrapped__") else None
    assert original_fn is not None, "the wrapper records nothing to restore"
    try:
        tool.fn = original_fn
        assert _call(server_obj, text=TRIPPING_VALUE["title"]) is not None
        assert entered == [TRIPPING_VALUE["title"]]
    finally:
        tool.fn = screened_fn
    with pytest.raises(ToolError):
        _call(server_obj, text=TRIPPING_VALUE["title"])
    assert entered == [TRIPPING_VALUE["title"]]


def test_installing_the_screen_twice_is_idempotent_not_an_error() -> None:
    """Re-installing over screened tools is a no-op, not a fail-closed event.

    "Wrapped zero tools" has two causes — a server with no tools (a real gap)
    and an already-screened server (a no-op) — and conflating them makes a
    legitimate second install raise.
    """
    server_obj, _ = _server_with_observed_tool()
    assert mcp_server.install_art9_surface_screen(server_obj) == 1
    assert mcp_server.install_art9_surface_screen(server_obj) == 0


def test_a_server_with_no_tools_fails_closed() -> None:
    """The guard that makes absence visible is itself asserted here."""
    empty = FastMCP("art9-empty", json_response=True)
    with pytest.raises(RuntimeError, match=r"0 digisearch MCP tools"):
        mcp_server.install_art9_surface_screen(empty)


def test_an_object_without_a_tool_manager_fails_closed() -> None:
    with pytest.raises(RuntimeError):
        mcp_server.install_art9_surface_screen(object())


# --------------------------------------------------------------------------
# AT8 — the SDK entry
# --------------------------------------------------------------------------


def test_the_sdk_ingest_entry_is_registered_and_screened() -> None:
    assert art9.art9_surface_kind(art9.SURFACE_SDK_INGEST) == art9.SURFACE_KIND_SDK


def test_sdk_ingest_refuses_before_it_touches_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """``DigiSearch.ingest`` is screened at the entry, not only at ``index_chunks``.

    Leaf 6 screens the ``index_chunks`` seam. That seam is not reachable on
    every call: when a configured index exists, ``ingest`` short-circuits
    straight to ``idx.add(...)``. The spy proves which side of the screen the
    refusal happened on.
    """
    entered: list[str] = []

    def _spy(self: object, name: str) -> None:  # pragma: no cover - never reached
        entered.append(name)

    monkeypatch.setattr(art9.DigiSearch, "get_index", _spy)
    client = object.__new__(art9.DigiSearch)
    doc = art9.Document(
        id="doc-1",
        content="genotype call rs1234",
        source="unit-test",
        doc_type="text",
        metadata={},
        chunks=[],
        segments=[],
    )
    with pytest.raises(art9.Art9SurfaceRefusal) as excinfo:
        client.ingest(doc)
    assert entered == [], "the SDK reached the index before the screen ran"
    assert excinfo.value.surface == art9.SURFACE_SDK_INGEST
    assert excinfo.value.result.categories == ("genetic",)


def test_sdk_ingest_allows_a_clean_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control for the SDK entry: a clean doc is not refused."""
    seen: list[int] = []

    class _Index:
        def add(self, chunks: object) -> None:  # pragma: no cover - never reached
            seen.append(1)

    monkeypatch.setattr(art9.DigiSearch, "get_index", lambda self, name: _Index())
    client = object.__new__(art9.DigiSearch)
    doc = art9.Document(
        id="doc-2",
        content="release notes",
        source="unit-test",
        doc_type="text",
        metadata={},
        chunks=[],
        segments=[],
    )
    assert client.ingest(doc) == 0
    assert seen == []


def test_a_dataclass_document_is_converted_before_screening() -> None:
    """A ``Document`` is not a mapping; screening the raw object would find nothing."""
    doc = art9.Document(
        id="doc-3",
        content="x",
        source="unit-test",
        doc_type="text",
        metadata={},
        chunks=[],
        segments=[],
    )
    screenable = art9._as_screenable(doc)  # noqa: SLF001
    assert isinstance(screenable, dict)
    assert _result_shape(screen_request(screenable)).decision == "allow"
    tripping = art9._as_screenable(  # noqa: SLF001
        art9.Document(
            id="doc-4",
            content="x",
            source="unit-test",
            doc_type="text",
            metadata={"genotype": "rs1234"},
            chunks=[],
            segments=[],
        )
    )
    assert _result_shape(screen_request(tripping)).decision == "refuse"


# --------------------------------------------------------------------------
# AT7 — the exa_webhook route
# --------------------------------------------------------------------------


def test_the_exa_webhook_route_is_below_both_path_keyed_floors() -> None:
    """The trap, stated as an assertion so a future prefix change is caught.

    Auth exempts this route, and ``digibase``'s registry has no entry for it —
    so leaf 3's admission middleware screens nothing here. Both halves are
    asserted, including the ``allow`` decision, because ``allow`` is exactly
    what a reader would misread as "covered".
    """
    assert server._digisearch_path_scopes("POST", EXA_WEBHOOK_PATH) is None  # noqa: SLF001
    decision = check_route("digisearch", EXA_WEBHOOK_PATH)
    assert decision.decision == "allow"
    assert decision.prefix is None
    # And the contrast: a route the floor does cover.
    assert check_route("digisearch", "/ingest").prefix == "/ingest"


def test_the_exa_webhook_route_has_an_explicit_surface() -> None:
    surface = f"{art9.SURFACE_KIND_HTTP}:{EXA_WEBHOOK_PATH}"
    assert server.AUTH_EXEMPT_SURFACES.get(surface) == art9.SURFACE_KIND_HTTP
    assert _result_shape(art9.screen_art9_surface(surface, EXA_TRIPPING)).decision == "refuse"
    assert _result_shape(art9.screen_art9_surface(surface, BENIGN)).decision == "allow"


def test_registered_http_surfaces_match_the_running_app() -> None:
    """F3: the keys come from ``app.routes``, and agree in both directions."""
    served = set(_served_templates())
    registered = _registered_http_templates()
    assert registered, "no auth-exempt surface is registered"
    expected = _digikey_exempt_templates() | {EXA_WEBHOOK_PATH}
    assert registered == expected
    assert not (registered - served), "a registered template is not served by the app"
    assert not (served - registered), "an auth-exempt route is not registered"


def test_a_newly_exempt_route_is_registered_when_it_appears() -> None:
    """The mutation assertion for the registry.

    A hand-written key cannot react to a new route; a derived one can. The
    probe route is attached to the real ``app.routes`` and the policy function
    is widened for it, so the registration must grow — then shrink back when
    the route is gone. If the registry were a literal, both halves would pass
    while proving nothing, which is why the probe must also be *absent* from
    the baseline.
    """
    probe_path = "/art9-probe-exempt"
    baseline = dict(server.AUTH_EXEMPT_SURFACES)
    assert probe_path not in _registered_http_templates()
    real_policy = server._digisearch_path_scopes  # noqa: SLF001

    def _widened(method: str, path: str) -> object:
        if path == probe_path:
            return None
        return real_policy(method, path)

    with _attached(_probe_route(probe_path)):
        server._digisearch_path_scopes = _widened  # type: ignore[assignment]  # noqa: SLF001
        try:
            grown = dict(server._register_auth_exempt_surfaces())  # noqa: SLF001
        finally:
            server._digisearch_path_scopes = real_policy  # type: ignore[assignment]  # noqa: SLF001
    surface = f"{art9.SURFACE_KIND_HTTP}:{probe_path}"
    assert grown.get(surface) == art9.SURFACE_KIND_HTTP
    assert set(grown) - set(baseline) == {surface}
    # Removing the route must remove the entry again: no orphans.
    assert server._register_auth_exempt_surfaces() == baseline  # noqa: SLF001


def test_the_exa_webhook_refuses_a_payload_tripping_a_category() -> None:
    """AT7, end to end: a 403 carrying the screen's reason."""
    with TestClient(server.app) as http:
        response = http.post(EXA_WEBHOOK_PATH, json=EXA_TRIPPING)
    assert response.status_code == 403
    body = response.json()
    reason = json.dumps(body)
    assert "art9:" in reason
    assert "genetic" in reason


def test_the_exa_webhook_still_rejects_an_unresolvable_payload() -> None:
    """Negative control: the screen did not swallow the route's own 422.

    This payload carries no Art. 9 signal and no monitor id, so the route's own
    validation rejects it at 422 — before the monitor store is touched. A 403
    here would mean the screen is refusing payloads it should allow.
    """
    with TestClient(server.app) as http:
        response = http.post(EXA_WEBHOOK_PATH, json=EXA_BENIGN_UNRESOLVABLE)
    assert response.status_code == 422
    assert "art9:" not in response.text


def test_the_exa_webhook_rejects_a_non_json_body() -> None:
    """The route's own 400 is preserved ahead of the screen."""
    with TestClient(server.app) as http:
        response = http.post(
            EXA_WEBHOOK_PATH,
            content=b"not json",
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 400
    assert "art9:" not in response.text


def test_the_admission_middleware_is_mounted_on_the_digisearch_app() -> None:
    """Leaf 3 mounts nothing; this leaf owns the digisearch mount point."""
    mounted = [middleware.cls for middleware in server.app.user_middleware]
    from digibase.art9_middleware import Art9AdmissionMiddleware

    assert Art9AdmissionMiddleware in mounted
    params = next(m for m in server.app.user_middleware if m.cls is Art9AdmissionMiddleware)
    assert params.kwargs["app_name"] == "digisearch"


def test_the_middleware_runs_inside_the_auth_middleware() -> None:
    """Order is load-bearing: auth must reject an unscoped caller first.

    Starlette runs the most recently added middleware outermost, so the screen
    is registered *before* ``DigiAuthMiddleware`` in ``server.py``. If that
    ever inverts, an unauthenticated caller could make the server read and
    screen a body it was going to reject anyway.
    """
    mounted = [middleware.cls for middleware in server.app.user_middleware]
    from digibase.art9_middleware import Art9AdmissionMiddleware
    from digikey import DigiAuthMiddleware

    assert mounted.index(Art9AdmissionMiddleware) < mounted.index(DigiAuthMiddleware)
