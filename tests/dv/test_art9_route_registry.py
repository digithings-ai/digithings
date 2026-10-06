"""The digivault half of the Art. 9 route-enumeration diff (leaf L4b, DIG-1075).

This is the guard that stops `INGEST_ROUTES["digivault"]` and the running app
drifting apart. The registry is a hand-maintained list of path templates; the app
is the router's own `app.routes`. Nothing makes them agree except a test like this
one, and the only comparable test that existed (registry vs the spec document) is
finding F3 on DIG-912: two hand-written artefacts drift *together*, so comparing
them proves nothing about the code that actually serves requests.

The oracle is therefore the live router, never a list written in this file:

- the ingestion side comes from `art9.iter_ingest_routes(app.routes, "digivault")`
  — leaf L0's (DIG-1070) enumerator, imported and called, not re-implemented, so
  the prefix semantics and the `include_router` prefix algebra stay in one place;
- the registry side comes from `art9.INGEST_ROUTES["digivault"]`;
- the diff runs **both ways**, because either drift is a bug: a route nobody
  registered would be silently unscreened, and a registry entry for a route that
  no longer exists is a claim about the app that is no longer true.

Nothing here compares against a hand-written set of expected routes. That is the
tautology this file exists to prevent: a hand-written expected list would be
edited in the same commit that added the route it is missing, and the test would
go on passing. **Do not "fix" a failure here by adding the route to this file.**

`test_diff_reports_a_synthetic_unregistered_route` is the load-bearing test. The
obvious version of this file — enumerate, diff, assert equal — passes the day it
is written, because today the registry and the app genuinely do agree. So the file
also has to prove the diff *can* fail: it attaches a synthetic route under a
declared ingestion prefix, asserts the diff reports exactly it and nothing else,
removes it, and asserts clean again. `test_diff_reports_a_registry_entry_with_no_route`
does the same for the opposite direction. Without those two, every other test in
this file is evidence of nothing.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from digibase import art9
from digivault import server

pytestmark = pytest.mark.unit

#: The app key in the Art. 9 registry. Matches `digibase.art9.INGEST_PREFIXES`.
APP = "digivault"

#: Attached by the mutation test, under a declared ingestion prefix and
#: deliberately absent from the registry. Never add this to `INGEST_ROUTES`.
_SYNTHETIC_PATH = "/v1/notes/__art9_unregistered_probe__"

#: A diff with nothing wrong with it. Written as a literal, not built from the
#: live app, so "clean again" cannot be satisfied by an empty enumeration.
_CLEAN: dict[str, list[str]] = {"routes_only": [], "registry_only": []}


# ── helpers ──────────────────────────────────────────────────────────────────


def _app_paths(app: Any) -> list[str]:
    """Every top-level path template on ``app``, in declaration order."""
    return [r.path for r in app.routes if isinstance(getattr(r, "path", None), str)]


def _route_registry_diff(app: Any) -> dict[str, list[str]]:
    """Diff the app's ingestion routes against the registry, in both directions.

    ``routes_only`` is a route the app serves under a declared ingestion prefix
    with no registry entry — silently unscreened, and the failure this whole file
    is about. ``registry_only`` is a registry entry with no matching route.

    The registry is read through the ``art9`` module attribute rather than a
    from-import, so ``monkeypatch.setattr(art9, "INGEST_ROUTES", ...)`` is
    observed here. That is what lets the reverse-direction mutation test drive
    this function instead of reimplementing half of it.
    """
    live = set(art9.iter_ingest_routes(app.routes, APP))
    registered = set(art9.INGEST_ROUTES[APP])
    return {
        "routes_only": sorted(live - registered),
        "registry_only": sorted(registered - live),
    }


def _synthetic_endpoint() -> None:
    """Endpoint for the synthetic route. The route object is never called."""
    return None


# ── the diff ─────────────────────────────────────────────────────────────────


def test_registry_and_live_routes_agree() -> None:
    """The registry and the running app describe the same set of routes."""
    assert _route_registry_diff(server.app) == _CLEAN


def test_enumeration_is_not_vacuous() -> None:
    """Guard the guard: the diff is only meaningful over a real route set.

    Every way this file can pass for the wrong reason, in one place:

    - an empty enumeration would make ``routes_only`` trivially empty, so assert
      the live set is non-empty;
    - a prefix filter that matched nothing would too;
    - a prefix filter that matched *everything* would also make ``routes_only``
      non-empty but would leave the scoped-floor property untested, so assert at
      least one real route falls outside every declared prefix;
    - matching resolved request paths instead of templates would drop every
      path-parameterised route, so assert a ``{placeholder}`` template survived.
    """
    live = set(art9.iter_ingest_routes(server.app.routes, APP))
    prefixes = art9.INGEST_PREFIXES[APP]
    paths = _app_paths(server.app)

    assert live, "no ingestion routes enumerated — the diff would pass vacuously"
    assert prefixes, "digivault declares no ingestion prefix — nothing is guarded"
    assert all(
        any(art9.is_under_prefix(path, prefix) for prefix in prefixes) for path in live
    ), f"enumeration returned a route under no declared prefix: {sorted(live)}"
    assert any("{" in path for path in live), (
        f"no path-parameter template enumerated — the router's templates are not "
        f"being read: {sorted(live)}"
    )
    assert [p for p in paths if not any(art9.is_under_prefix(p, prefix) for prefix in prefixes)], (
        "every route on the app fell under a declared ingestion prefix — the "
        "prefix filter is not filtering"
    )


# ── the mutation assertions ──────────────────────────────────────────────────


def test_diff_reports_a_synthetic_unregistered_route() -> None:
    """A route under a declared prefix with no registry entry is reported.

    Proves the ``routes_only`` half of the diff can fail. A synthetic route is
    attached to the real app object and the diff is required to report exactly
    that path — not merely to contain it, so a mutation that also perturbed an
    existing route cannot hide here — and then the app is restored and the diff
    is required to be clean again.

    Restoring in ``finally`` matters: `server.app` is module-level and shared
    with every other test in ``tests/dv``, so a failure below must not leak a
    phantom route into `tests/dv/test_server.py`.
    """
    app = server.app
    snapshot = list(app.router.routes)
    try:
        app.add_api_route(
            _SYNTHETIC_PATH,
            _synthetic_endpoint,
            methods=["POST"],
            name="art9_unregistered_probe",
        )

        assert _route_registry_diff(app) == {
            "routes_only": [_SYNTHETIC_PATH],
            "registry_only": [],
        }

        decision = art9.check_route(APP, _SYNTHETIC_PATH)
        assert decision.refused
        assert decision.reason == f"{art9.ROUTE_UNREGISTERED}:{_SYNTHETIC_PATH}"
    finally:
        app.router.routes[:] = snapshot

    assert _route_registry_diff(app) == _CLEAN
    assert _SYNTHETIC_PATH not in _app_paths(app)


def test_diff_reports_a_registry_entry_with_no_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """A registry entry with no matching route is reported.

    The mirror of the test above, and separately load-bearing: a diff that only
    computed ``live - registered`` would pass here forever while the registry
    kept claiming routes the app stopped serving.

    The dropped key is derived from the registry itself rather than typed in, so
    this file still contains no hand-written expected-route list.
    """
    registry = dict(art9.INGEST_ROUTES[APP])
    dropped = sorted(registry)[-1]
    patched = MappingProxyType({k: v for k, v in registry.items() if k != dropped})

    with monkeypatch_registry(patched):
        assert _route_registry_diff(server.app) == {
            "routes_only": [],
            "registry_only": [dropped],
        }

    assert _route_registry_diff(server.app) == _CLEAN


# ── the floor agrees with the registry ───────────────────────────────────────


def test_refusal_floor_allows_every_enumerated_route() -> None:
    """`check_route` must not refuse any route this file proved is registered.

    The same invariant from the middleware's side, against the live app rather
    than a synthetic one: leaf L0 tests `check_route` on stand-in routes, nobody
    has checked it against digivault's real `app.routes`.
    """
    for path in sorted(set(art9.iter_ingest_routes(server.app.routes, APP))):
        decision = art9.check_route(APP, path)
        assert not decision.refused, f"{path} is enumerated but refused: {decision}"