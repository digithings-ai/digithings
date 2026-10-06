"""digisearch's ingestion routes must equal ``INGEST_ROUTES["digisearch"]``.

Leaf L4a of DIG-1074 (plan leaf L4a on DIG-959, spec §5.4 on DIG-912). L4b
covers digivault and L4c covers digigraph; the test is split three ways only
because it imports a service module and a test under ``tests/db/`` cannot.

This is the guard that stops the registry and the running app drifting apart.
The registry is what the Art. 9 refusal floor consults: a route under a
declared ingestion prefix with no entry in ``INGEST_ROUTES`` is refused. So a
route that ships without a registry entry is not an oversight, it is a 403 that
nobody diagnosed; and a registry entry with no route is dead documentation that
reads as coverage. Both directions fail here.

The oracle is ``app.routes`` — the routes the app actually serves — read through
``digibase.art9.iter_ingest_routes``, which yields each path template that falls
under a declared ingestion prefix. Hand-written route strings are exactly how
this test would become a tautology that drifts with the registry instead of
catching it, so nothing here re-declares a path.

**The mutation assertion is the load-bearing part.** Today the registry and the
app agree, so the plain two-way diff passes the moment it is written and proves
nothing on its own. ``test_unlisted_route_is_reported_then_clears`` attaches a
real route under the declared prefix, asserts the diff reports it, removes it,
and asserts the diff is clean again: the test is demonstrably able to fail, so
its green is evidence.

This file is a test only. It changes no production code; a route genuinely
missing from the registry is a finding to report, not something to patch here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from digisearch.server import app
from fastapi import APIRouter
from fastapi.routing import APIRoute

from digibase import art9

pytestmark = pytest.mark.unit

#: The registry key this file defends. The prefix it filters with comes from
#: ``art9.INGEST_PREFIXES``, not from here — a hard-coded prefix would be a
#: second copy of the scope to keep in step with the first.
APP = "digisearch"

#: A path no real digisearch route serves. Under ``/ingest``, so it is in scope
#: for the enumeration, and absent from the registry, so the diff must flag it.
PROBE_PATH = "/ingest/__art9_registry_probe__"


# ── the diff ─────────────────────────────────────────────────────────────────


def _template(path: str) -> str:
    """Normalise a path template the way ``art9.is_registered`` normalises a lookup.

    ``APIRouter(prefix="/ingest")`` with a route declared at ``"/"`` reports
    ``.path == "/ingest/"``, so a bare string comparison would report both
    ``/ingest/`` as unserved *and* ``/ingest`` as unserved for one registered
    route. ``art9.is_registered`` strips the trailing slash for exactly this
    reason; the diff has to agree with it or it invents a failure out of a
    registered route. Only the trailing slash is touched — nothing here can make
    two different templates compare equal.
    """
    return path.rstrip("/") or "/"


def _served_templates() -> set[str]:
    """Every ingestion path template the running app serves."""
    return {_template(path) for path in art9.iter_ingest_routes(app.routes, APP)}


def _registered_templates() -> set[str]:
    """Every path template the registry claims for digisearch."""
    return {_template(path) for path in art9.INGEST_ROUTES[APP]}


def _diff() -> tuple[set[str], set[str]]:
    """``(served_but_unregistered, registered_but_unserved)``, both directions."""
    served, registered = _served_templates(), _registered_templates()
    return served - registered, registered - served


def _probe_route(path: str) -> APIRoute:
    """A real FastAPI route object, built by a router the way the app builds one.

    A ``SimpleNamespace(path=...)`` would be read fine by the enumeration, but
    the point of the mutation assertion is to prove the diff reacts to the same
    objects the framework emits — so the probe is an ``APIRoute`` off a real
    ``APIRouter`` and its ``.path`` is the router's own template.
    """
    router = APIRouter()

    @router.post(path)
    async def _probe() -> dict[str, bool]:
        return {"probe": True}

    (route,) = router.routes
    assert isinstance(route, APIRoute)
    return route


@contextmanager
def _attached(route: APIRoute) -> Iterator[None]:
    """Install ``route`` on the live app, and always take it back off.

    Removal is by identity, not by path, and it happens in a ``finally`` so a
    failing assertion cannot leave a probe route behind for the next test to
    trip over — a shared module-level app is exactly where that leaks.
    """
    app.routes.append(route)
    try:
        yield
    finally:
        app.routes[:] = [existing for existing in app.routes if existing is not route]


# ── 1. the diff, on the app as it stands ─────────────────────────────────────


def test_registry_and_running_app_agree_in_both_directions() -> None:
    served_but_unregistered, registered_but_unserved = _diff()

    assert served_but_unregistered == set(), (
        "digisearch serves ingestion routes that INGEST_ROUTES['digisearch'] does "
        f"not list: {sorted(served_but_unregistered)}. A route under a declared "
        "ingestion prefix with no registry entry is refused by the Art. 9 floor, so "
        "either the route does not ingest caller-supplied content and belongs outside "
        "the declared prefix, or it needs a registry entry. Leaf L10 owns "
        "digisearch/src/digisearch/server.py and those registry entries."
    )
    assert registered_but_unserved == set(), (
        "INGEST_ROUTES['digisearch'] lists routes the running app does not serve: "
        f"{sorted(registered_but_unserved)}. The route was renamed or removed and the "
        "registry entry was not, so the entry reads as coverage that does not exist."
    )


def test_the_comparison_is_not_vacuous() -> None:
    """Guard the green above: an empty side on both ends would also be green.

    Cheap, and it is the only thing that distinguishes "the registry and the app
    agree" from "the enumeration found nothing and the registry is empty".
    """
    assert _served_templates(), "digisearch serves no route under its declared prefix"
    assert _registered_templates(), "INGEST_ROUTES['digisearch'] is empty"


# ── 2. the mutation assertion: the diff can fail, in both directions ─────────


def test_unlisted_route_is_reported_then_clears() -> None:
    """The obvious version of this test passes on the day it is written.

    So it has to prove it can fail. A real route is attached under the declared
    ingestion prefix, the diff has to name it, the route is removed, and the
    diff has to go quiet again. A test that cannot go red is not a guard.
    """
    route_only_before, registry_only_before = _diff()
    assert route_only_before == set(), f"baseline is not clean: {sorted(route_only_before)}"
    assert registry_only_before == set(), f"baseline is not clean: {sorted(registry_only_before)}"

    probe = _probe_route(PROBE_PATH)
    with _attached(probe):
        # The enumeration must see it: if a prefix match quietly excluded this
        # route, the diff would be "clean" here and that is the same bug as a
        # route nobody registered.
        assert PROBE_PATH in _served_templates()

        served_but_unregistered, registered_but_unserved = _diff()
        assert served_but_unregistered == {PROBE_PATH}
        assert registered_but_unserved == set(), "attaching a route added a phantom entry"

    # Removed: clean again, and the app is back to how it was found.
    assert PROBE_PATH not in _served_templates()
    served_but_unregistered, registered_but_unserved = _diff()
    assert served_but_unregistered == set()
    assert registered_but_unserved == set()


def test_registry_entry_with_no_route_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, proved the same way.

    ``INGEST_ROUTES`` is a read-only proxy, so the only way to stand a bogus
    entry in front of the diff is to swap the module attribute for the duration
    of one test — which is what ``monkeypatch`` undoes. ``INGEST_PREFIXES`` is
    deliberately *not* patched: the enumeration must keep filtering on the real
    declared scope, or this would prove nothing about the registry side.
    """
    phantom = "/ingest/__art9_registry_phantom__"
    patched = dict(art9.INGEST_ROUTES[APP])
    patched[phantom] = art9.ROUTE_KIND_INGEST
    monkeypatch.setattr(art9, "INGEST_ROUTES", {**art9.INGEST_ROUTES, APP: patched})

    served_but_unregistered, registered_but_unserved = _diff()

    assert registered_but_unserved == {phantom}
    assert served_but_unregistered == set(), "patching the registry invented a served route"


# ── 3. the diff reads templates, not concrete request paths ──────────────────


def test_a_trailing_slash_route_matches_its_registry_entry() -> None:
    """FastAPI reports ``/ingest/`` for a route declared at ``"/"`` under the prefix.

    Without normalisation that is a false positive on both sides at once, and a
    false positive here trains the next reader to loosen the diff. The registry
    entry stays the single source of the path.
    """
    trailing = _probe_route("/ingest/")
    with _attached(trailing):
        assert "/ingest/" in {path for path in art9.iter_ingest_routes(app.routes, APP)}, (
            "the enumeration stopped reporting the raw router template"
        )
        served_but_unregistered, registered_but_unserved = _diff()

    assert served_but_unregistered == set(), (
        f"trailing-slash route reported as unserved: {sorted(served_but_unregistered)}"
    )
    assert registered_but_unserved == set(), (
        "trailing-slash route reported as unserved in the registry: "
        f"{sorted(registered_but_unserved)}"
    )
