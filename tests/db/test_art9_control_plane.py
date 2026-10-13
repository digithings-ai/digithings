"""Art. 9 control-plane registry: declared, non-ingestion prefixes and routes.

Leaf 12a of DIG-1174 (plan leaf L12a on DIG-959, `plan` document §1.2 and §8 on
DIG-1065). The registry itself landed in leaf L0 (DIG-1070) as
`INGEST_PREFIXES`/`INGEST_ROUTES`; this leaf adds the second, explicitly
declared registry that lets `POST /internal/art9/screen` be registered **on
purpose** instead of quietly.

Why a second registry at all: putting `/internal/art9/screen` into
`INGEST_ROUTES` would make the Art. 9 admission middleware screen the screening
endpoint. The middleware would inspect a transcript and refuse before the
handler ever adjudicates it, so any transcript containing an Art. 9 field name
could never be adjudicated at all — the gate refusing to gate. So the route is
declared as *control plane* and the admission middleware treats control-plane
routes as out of scope, exactly like routes outside every declared ingestion
prefix.

**The symmetry is the point of this leaf.** A route under a declared
control-plane prefix with no `CONTROL_PLANE_ROUTES` entry fails the same
two-way set difference that an unregistered ingestion route fails, so the next
person to add `/internal/whatever` cannot do it quietly either. The exemption is
declared, not silent.

Two normalising rules are load-bearing and are inherited from the ingestion side
rather than reinvented:

- the **served** side is trailing-slash normalised, the **registry** side is read
  raw, because `routes.get(path) or routes.get(_normalize(path))` applies the
  normalisation to the lookup and never to the stored key. Normalising both sides
  makes a key written `"/internal/art9/screen/"` compare equal to the served
  `"/internal/art9/screen"`, the diff goes green, and the lookup still misses.
- the diff is a plain `served - registered` / `registered - served`, which is the
  same expression as `_diff()` in `tests/ds/test_art9_route_registry.py`.

**The mutation assertion is the load-bearing part.** The registry and the app
agree on the day this is written, so a plain diff passes immediately and proves
nothing. `test_synthetic_control_plane_route_is_reported_then_clears` attaches a
real route under the declared prefix, asserts the diff reports it, removes it,
and asserts the diff is clean again: the test is demonstrably able to fail, so
its green is evidence.

**What this file does not own.** The two-way diff over digisearch's *live* app
is leaf 4a (DIG-1074), and the route `/internal/art9/screen` itself is leaf 12b.
So this file does not assert `registered - served` is empty: today
`CONTROL_PLANE_ROUTES["digisearch"]` declares a route no service serves yet, and
it is leaf 4a's diff — running after 12b — that holds the two together.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from digibase import art9

pytestmark = pytest.mark.unit

#: The app whose control-plane prefix this file defends. The prefix itself is
#: read off ``art9.CONTROL_PLANE_PREFIXES``, never hard-coded here: a literal
#: would be a second copy of the scope to keep in step with the first.
APP = "digisearch"

#: A path no real service serves. Under ``/internal/art9``, so it is in scope for
#: the enumeration, and absent from the registry, so the diff must flag it.
PROBE_PATH = "/internal/art9/__art9_control_plane_probe__"


# ── the diff ─────────────────────────────────────────────────────────────────
# Same shape as the ingestion side's `_diff()` in
# `tests/ds/test_art9_route_registry.py`, which is why this file can be written
# against a locally built app rather than importing digisearch's: a test under
# `tests/db/` cannot import a service module, which is the whole reason that
# guard is split three ways by app.


def _served_template(path: str) -> str:
    """Normalise the *served* template only — see the module docstring."""
    return path.rstrip("/") or "/"


def _served_templates(routes: Iterator[str]) -> set[str]:
    """Every control-plane path template the app serves.

    Scoped by the declared **prefix**, not by the registry, for the same reason
    `art9.iter_ingest_routes` is: an unrecognised route is exactly what the diff
    needs to see, so filtering by membership would make the diff vacuously clean.
    """
    prefixes = art9.CONTROL_PLANE_PREFIXES.get(APP, ())
    return {
        _served_template(path)
        for path in routes
        if any(art9.is_under_prefix(path, prefix) for prefix in prefixes)
    }


def _registered_templates() -> set[str]:
    """Every path template the control-plane registry claims, exactly as stored.

    Not normalised, for the reason in `_served_template`.
    """
    return set(art9.CONTROL_PLANE_ROUTES[APP])


def _diff(routes: Iterator[str]) -> tuple[set[str], set[str]]:
    """``(served_but_unregistered, registered_but_unserved)``, both directions."""
    served, registered = _served_templates(routes), _registered_templates()
    return served - registered, registered - served


def _unregistered(app: FastAPI) -> set[str]:
    """The served-but-unregistered half of the diff, for a built app."""
    served_but_unregistered, _ = _diff(iter(art9._iter_paths(app.routes)))
    return served_but_unregistered


def _probe_route(path: str) -> APIRoute:
    """A real FastAPI route object, built by a router the way an app builds one."""
    router = APIRouter()

    @router.post(path)
    async def _probe() -> dict[str, bool]:
        return {"probe": True}

    (route,) = router.routes
    assert isinstance(route, APIRoute)
    return route


@contextmanager
def _attached(app: FastAPI, route: APIRoute) -> Iterator[None]:
    """Install ``route`` on ``app``, and always take it back off.

    Removal is by identity, not by path, and happens in a ``finally`` so a
    failing assertion cannot leave a probe route behind for the next test.
    """
    app.routes.append(route)
    try:
        yield
    finally:
        app.routes[:] = [existing for existing in app.routes if existing is not route]


def _app_serving(*paths: str) -> FastAPI:
    """A FastAPI serving exactly ``paths``, built the way a service builds them."""
    router = APIRouter()
    for path in paths:
        router.add_api_route(path, lambda: None, methods=["POST"])
    app = FastAPI()
    app.include_router(router)
    return app


# ── 1. an undeclared route under a declared prefix is reported ────────────────


def test_control_plane_route_under_declared_prefix_is_reported_missing() -> None:
    """The mirror of the ingestion refusal: an undeclared route fails the diff.

    This is the leaf's load-bearing behaviour. Without it, `/internal/` is a
    carve-out nobody has to look at, and the exemption stops being reviewable.
    """
    app = _app_serving("/internal/art9/screen", PROBE_PATH)

    served_but_unregistered, _ = _diff(iter(art9._iter_paths(app.routes)))

    assert served_but_unregistered == {PROBE_PATH}
    assert "/internal/art9/screen" not in served_but_unregistered, (
        "the registered route must not read as unregistered"
    )


def test_a_route_under_no_declared_control_plane_prefix_is_untouched() -> None:
    """Outside every declared control-plane prefix, nothing changes.

    Including ``/internal/other`` — `/internal/` is reserved fleet-wide, but only
    the *declared sub-prefix* scopes the diff, so a sibling service's
    `/internal/…` route is not this registry's business. Declaring `/internal/`
    itself would make every internal route in the fleet a diff failure.
    """
    app = _app_serving(
        "/health",
        "/metrics",
        "/ingest/url",
        "/internal/other/thing",
        "/internal/art9ish/thing",
        "/v1/notes",
    )

    served, _registered = _diff(iter(art9._iter_paths(app.routes)))

    assert served == set()
    for path in ("/health", "/internal/other/thing", "/internal/art9ish/thing"):
        assert art9.is_control_plane(APP, path) is False


# ── 2. the two registries must not overlap ────────────────────────────────────


def test_no_ingestion_route_is_also_control_plane() -> None:
    """`is_control_plane` is false for every ingestion route in the registry.

    If these two sets overlapped, a route would be both screened and out of
    scope, and the resolution order would decide which — silently, per request.
    """
    for app_name, routes in art9.INGEST_ROUTES.items():
        for path in routes:
            assert art9.is_control_plane(app_name, path) is False, (
                f"{app_name}{path} is in both registries"
            )


def test_no_control_plane_route_is_also_registered_as_ingestion() -> None:
    """The converse direction, and the one the screen route actually turns on.

    `is_registered()` keeps its ingestion-only meaning: a control-plane route is
    not an ingestion route, so the admission middleware never screens it.
    """
    for app_name, routes in art9.CONTROL_PLANE_ROUTES.items():
        for path in routes:
            assert art9.is_registered(app_name, path) is False
            assert art9.route_kind(app_name, path) is None


def test_control_plane_prefixes_do_not_cover_ingestion_prefixes() -> None:
    """A declared control-plane prefix must not swallow an ingestion prefix.

    This is the structural form of the same invariant: if `/internal/art9` were
    a prefix of, say, `/ingest`, the classification would depend on which table
    was consulted first rather than on what the route is.
    """
    for app_name, control_prefixes in art9.CONTROL_PLANE_PREFIXES.items():
        for control in control_prefixes:
            for ingest in art9.INGEST_PREFIXES.get(app_name, ()):
                assert art9.is_under_prefix(ingest, control) is False


# ── 3. the registry is declared, immutable, and minimal ──────────────────────


def test_the_screen_route_is_registered_with_its_purpose_code() -> None:
    """The one v1 entry, with the purpose code the audit record needs."""
    assert art9.CONTROL_PLANE_PREFIXES["digisearch"] == ("/internal/art9",)
    assert art9.CONTROL_PLANE_ROUTES["digisearch"] == {
        "/internal/art9/screen": "art9_screen",
    }
    assert art9.is_control_plane("digisearch", "/internal/art9/screen") is True


def test_no_control_plane_prefix_is_declared_bare_root() -> None:
    """A bare `/` or `/internal` would re-create full-route default scope.

    Same reason `INGEST_PREFIXES` forbids it: a prefix that covers every absolute
    path turns a scoped diff into one that fails on the whole app.
    """
    for app_name, prefixes in art9.CONTROL_PLANE_PREFIXES.items():
        for prefix in prefixes:
            assert prefix not in ("/", "/internal"), f"{app_name} declares {prefix!r}"


def test_control_plane_registry_is_not_mutable_at_runtime() -> None:
    """The exemption cannot be widened by assigning into it at runtime.

    `CONTROL_PLANE_ROUTES["digisearch"]["/internal/anything"] = "…"` would exempt
    an undeclared route with no flag and no import — the exact hole this leaf
    exists to close.
    """
    with pytest.raises(TypeError):
        art9.CONTROL_PLANE_ROUTES["digisearch"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        art9.CONTROL_PLANE_ROUTES["digisearch"]["/internal/backdoor"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        art9.CONTROL_PLANE_PREFIXES["digisearch"] = ()  # type: ignore[index]


# ── 4. the mutation assertion ────────────────────────────────────────────────


def test_synthetic_control_plane_route_is_reported_then_clears() -> None:
    """The diff is demonstrably able to fail.

    Without this the diff passes the moment it is written — the registry and the
    app agree on day one — so its green would be evidence of nothing at all.
    """
    app = _app_serving("/internal/art9/screen")

    assert _unregistered(app) == set(), "control: the diff is not clean before the mutation"
    with _attached(app, _probe_route(PROBE_PATH)):
        assert _unregistered(app) == {PROBE_PATH}
    assert _unregistered(app) == set(), "the diff did not clear after removal"


def test_a_declared_control_plane_route_nobody_serves_is_reported() -> None:
    """The other direction: a registry entry with no route behind it.

    Leaf 12b adds `/internal/art9/screen` to digisearch and leaf 4a runs this
    against the live app, so the entry is not dead documentation for long. This
    pins the direction now, against a local app, so leaf 4a inherits a check
    that already fails when it matters.
    """
    app = _app_serving("/health")

    _served_but_unregistered, registered_but_unserved = _diff(iter(art9._iter_paths(app.routes)))

    assert registered_but_unserved == {"/internal/art9/screen"}
