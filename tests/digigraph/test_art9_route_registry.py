"""digigraph's ingestion routes must equal ``INGEST_ROUTES["digigraph"]``.

Leaf L4c of DIG-1076 (plan leaf L4c on DIG-959, spec §5.4 on DIG-912). L4a
covers digisearch and L4b covers digivault; the test is split three ways only
because it imports a service module and a test under ``tests/db/`` cannot.

This is the guard that stops the registry and the running app drifting apart.
The registry is what the Art. 9 refusal floor consults: a route under a declared
ingestion prefix with no entry in ``INGEST_ROUTES`` is refused. So a route that
ships without a registry entry is not an oversight, it is a 403 that nobody
diagnosed; and a registry entry with no route is dead documentation that reads as
coverage. Both directions fail here.

The oracle is ``app.routes`` — the routes the app actually serves — read through
``digibase.art9.iter_ingest_routes``, which yields each path template that falls
under a declared ingestion prefix. Hand-written route strings are exactly how this
test would become a tautology that drifts with the registry instead of catching
it, so nothing here re-declares a real route path.

**Every probe in this file is attached behind ``app.include_router``, not flat on
the app.** digigraph mounts its whole ``/v1`` router that way, so the route object
a probe represents in production is an ``APIRoute`` buried in a lazy
``_IncludedRouter`` rather than a top-level entry. A flat probe would prove the
diff reacts to a shape digigraph does not use, and a future break in the include
traversal would go unnoticed. ``_attached`` therefore installs through the
framework's own ``include_router``.

**The mutation assertion is the load-bearing part.** Today the registry and the
app agree, so the plain two-way diff passes the moment it is written and proves
nothing on its own. ``test_unlisted_route_is_reported_then_clears`` attaches a real
route under the declared prefix, asserts the diff reports it, removes it, and
asserts the diff is clean again: the test is demonstrably able to fail, so its
green is evidence.

This file is a test only. It changes no production code; a route genuinely
missing from the registry is a finding to report, not something to patch here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from digigraph.server import app
from fastapi import APIRouter

from digibase import art9

pytestmark = pytest.mark.unit

#: The registry key this file defends. The scope it filters with comes from
#: ``art9.INGEST_PREFIXES`` rather than from a literal here, so the probe paths
#: below cannot become a second copy of the declared prefix that quietly goes
#: stale: move the prefix and the probes move with it.
APP = "digigraph"

#: The declared ingestion prefix, read off the registry. ``_PREFIX`` is only ever
#: used to build probe paths — the diff itself never filters on it.
_PREFIX = art9.INGEST_PREFIXES[APP][0]

#: Paths no real digigraph route serves. Under the declared prefix, so they are in
#: scope for the enumeration, and absent from the registry, so the diff must flag
#: them.
PROBE_PATH = f"{_PREFIX}/__art9_registry_probe__"
PHANTOM_PATH = f"{_PREFIX}/__art9_registry_phantom__"


@pytest.fixture(autouse=True)
def _app_routes_restored() -> Iterator[None]:
    """Put ``app.routes`` back exactly as it was found, whatever a test does.

    ``app`` is a module-level singleton shared with every other digigraph test, and
    Starlette matches over ``app.routes`` at request time — so a probe route left
    behind would be a live endpoint under a declared ingestion prefix, and the Art.
    9 floor would refuse it. ``_attached`` cleans up after itself; this is the
    backstop for the case where a test fails before or outside that helper.
    """
    before = list(app.routes)
    try:
        yield
    finally:
        app.routes[:] = before


# ── the diff ─────────────────────────────────────────────────────────────────


def _template(path: str) -> str:
    """Normalise a path template the way ``art9.is_registered`` normalises a lookup.

    ``APIRouter(prefix="/v1/chat")`` with a route declared at ``"/"`` reports
    ``.path == "/v1/chat/"``, so a bare string comparison would report both
    ``/v1/chat/`` as unserved *and* ``/v1/chat`` as unserved for one registered
    route. ``art9.is_registered`` strips the trailing slash for exactly this
    reason; the diff has to agree with it or it invents a failure out of a
    registered route. Only the trailing slash is touched — nothing here can make
    two different templates compare equal.
    """
    return path.rstrip("/") or "/"


def _served_templates() -> set[str]:
    """Every ingestion path template the running app serves.

    Reads the live app, not a declared list. ``iter_ingest_routes`` is what
    descends into digigraph's lazy ``include_router(v1)``; a top-level walk of
    ``app.routes`` finds no ingestion route at all, which is why this helper is
    never spelled out inline here.
    """
    return {_template(path) for path in art9.iter_ingest_routes(app.routes, APP)}


def _registered_templates() -> set[str]:
    """Every path template the registry claims for digigraph."""
    return {_template(path) for path in art9.INGEST_ROUTES[APP]}


def _diff() -> tuple[set[str], set[str]]:
    """``(served_but_unregistered, registered_but_unserved)``, both directions."""
    served, registered = _served_templates(), _registered_templates()
    return served - registered, registered - served


@contextmanager
def _attached(path: str) -> Iterator[None]:
    """Serve a real route at ``path`` under the declared prefix, then remove it.

    Attached through ``app.include_router`` so it lands in the same
    ``_IncludedRouter`` shape as every real digigraph route — see the module
    docstring. Removal is by identity rather than by path, and it happens in a
    ``finally`` so a failing assertion cannot leave a probe behind for the next
    test to trip over.
    """
    router = APIRouter()

    @router.post(path)
    async def _probe() -> dict[str, bool]:
        return {"probe": True}

    before = len(app.routes)
    app.include_router(router)
    added = app.routes[before:]
    try:
        yield
    finally:
        for entry in added:
            app.routes[:] = [existing for existing in app.routes if existing is not entry]


# ── 1. the diff, on the app as it stands ─────────────────────────────────────


def test_registry_and_running_app_agree_in_both_directions() -> None:
    served_but_unregistered, registered_but_unserved = _diff()

    assert served_but_unregistered == set(), (
        "digigraph serves ingestion routes that INGEST_ROUTES['digigraph'] does "
        f"not list: {sorted(served_but_unregistered)}. A route under a declared "
        "ingestion prefix with no registry entry is refused by the Art. 9 floor, so "
        "either the route does not ingest caller-supplied content and belongs outside "
        "the declared prefix, or it needs a registry entry. Leaf L9 owns "
        "digigraph/src/digigraph/server.py and those registry entries."
    )
    assert registered_but_unserved == set(), (
        "INGEST_ROUTES['digigraph'] lists routes the running app does not serve: "
        f"{sorted(registered_but_unserved)}. The route was renamed or removed and the "
        "registry entry was not, so the entry reads as coverage that does not exist."
    )


def test_the_comparison_is_not_vacuous() -> None:
    """Guard the green above: an empty side on both ends would also be green.

    The served-side assertion is the one that matters for digigraph. Its only
    ingestion route is mounted behind ``include_router(v1)``, so a diff that failed
    to descend into that lazy include would find nothing, and *every* other test in
    this file would then be comparing an empty set against the registry — green for
    the wrong reason. The registered-side assertion is what separates "the registry
    and the routes agree" from "both were deleted".
    """
    assert _served_templates(), (
        "digigraph serves no route under its declared prefix — the enumeration is "
        "not seeing the routes the app actually serves"
    )
    assert _registered_templates(), "INGEST_ROUTES['digigraph'] is empty"


# ── 2. the mutation assertion: the diff can fail, in both directions ─────────


def test_unlisted_route_is_reported_then_clears() -> None:
    """The obvious version of this test passes on the day it is written.

    So it has to prove it can fail. A real route is served under the declared
    ingestion prefix, the diff has to name it, the route is removed, and the diff
    has to go quiet again. A test that cannot go red is not a guard.
    """
    route_only_before, registry_only_before = _diff()
    assert route_only_before == set(), f"baseline is not clean: {sorted(route_only_before)}"
    assert registry_only_before == set(), f"baseline is not clean: {sorted(registry_only_before)}"

    with _attached(PROBE_PATH):
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

    ``INGEST_ROUTES`` is a read-only proxy, so the only way to stand a bogus entry
    in front of the diff is to swap the module attribute for the duration of one
    test — which is what ``monkeypatch`` undoes. ``INGEST_PREFIXES`` is deliberately
    *not* patched: the enumeration must keep filtering on the real declared scope,
    or this would prove nothing about the registry side.
    """
    patched = dict(art9.INGEST_ROUTES[APP])
    patched[PHANTOM_PATH] = art9.ROUTE_KIND_INGEST
    monkeypatch.setattr(art9, "INGEST_ROUTES", {**art9.INGEST_ROUTES, APP: patched})

    served_but_unregistered, registered_but_unserved = _diff()

    assert registered_but_unserved == {PHANTOM_PATH}
    assert served_but_unregistered == set(), "patching the registry invented a served route"


# ── 3. the diff reads the router's own templates, not concrete request paths ──


def test_a_trailing_slash_route_matches_its_registry_entry() -> None:
    """FastAPI preserves a trailing slash, ``art9.is_registered`` strips one.

    Without normalisation that is a false positive on both sides at once, and a
    false positive here trains the next reader to loosen the diff. The registry
    entry stays the single source of the path.

    L4a's version of this case probes ``/ingest/``, which normalises onto a route
    sitting at the prefix root. digigraph has no such route — its only ingestion
    entry is ``/v1/chat/completions``, one segment deeper — so the probe is the
    trailing-slash form of that entry, which exercises the same normalisation.
    """
    trailing = f"{_PREFIX}/completions/"

    with _attached(trailing):
        raw = set(art9.iter_ingest_routes(app.routes, APP))
        assert trailing in raw, "the enumeration stopped reporting the raw router template"
        served_but_unregistered, registered_but_unserved = _diff()

    assert served_but_unregistered == set(), (
        f"trailing-slash route reported as unserved: {sorted(served_but_unregistered)}"
    )
    assert registered_but_unserved == set(), (
        "trailing-slash route reported as unserved in the registry: "
        f"{sorted(registered_but_unserved)}"
    )
