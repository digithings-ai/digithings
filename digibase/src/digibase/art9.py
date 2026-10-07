"""Art. 9 ingestion registry: categories, declared scope, and the refusal floor.

Leaf L0 of DIG-1070. This module holds the shared registry the Art. 9 filter
consults. It performs **no detection** — field names, identifier patterns,
``screen_text`` and ``screen_request`` are leaf L1 (DIG-1071) in this same file.
Nothing here is mounted: `digibase` is a library with no server, no port and no
persistent state, and importing this module has no side effects.

The registry answers one question per route: *is this an ingestion route, and if
so, is it a route somebody looked at?* Two failure modes are fatal, and both
are guarded by tests in ``tests/db/test_art9_registry.py``:

- **Full-route default-deny.** Refusing every unregistered route would 403
  ``/health``, ``/healthz``, ``/metrics``, the OpenAPI docs, CORS preflight and
  every read endpoint in the stack. The floor is scoped: only routes under a
  *declared* ingestion prefix are refused, and only when they carry no registry
  entry. Everything outside every declared prefix is untouched.
- **Silently unscreened ingestion.** A new route under a declared prefix with no
  registry entry is refused naming the route, so it cannot ship unnoticed. This
  is what the wave-2 route-enumeration diff tests (L4a/L4b/L4c) build on.

``decision`` defaults to ``refuse`` and there is no module-level global that
flips it. An ``exception_ref`` (leaf L1) is how a caller earns a narrower
outcome, never a flag set at import time.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

__all__ = [
    "ART9_CATEGORIES",
    "INGEST_PREFIXES",
    "INGEST_ROUTES",
    "ROUTE_KIND_INGEST",
    "ROUTE_KIND_READ",
    "ROUTE_UNREGISTERED",
    "RouteDecision",
    "check_route",
    "is_registered",
    "is_under_prefix",
    "iter_ingest_routes",
    "route_kind",
]

# ── categories ───────────────────────────────────────────────────────────────

#: The eight GDPR Art. 9(1) special-category ids. Exactly these, nothing else:
#: a ninth id would be a category that matches nothing, and a renamed one would
#: silently stop matching everything it used to.
ART9_CATEGORIES: frozenset[str] = frozenset(
    {
        "health",
        "genetic",
        "biometric",
        "racial_or_ethnic_origin",
        "political_opinions",
        "religious_or_philosophical_beliefs",
        "trade_union_membership",
        "sex_life_or_sexual_orientation",
    }
)

# ── route kinds ──────────────────────────────────────────────────────────────

#: A route that writes caller-supplied content into storage.
ROUTE_KIND_INGEST = "ingest"

#: A route under a declared ingestion prefix that carries no caller-supplied
#: content. It stays registered so the diff tests see it, but nothing is
#: screened. `digivault`'s ``GET /v1/notes/{name}`` is the motivating case.
ROUTE_KIND_READ = "read"

# ── the registry ─────────────────────────────────────────────────────────────

#: Ingestion prefixes declared per app. Scopes the refusal floor: a route is
#: refused only when it falls under one of these *and* carries no registry entry.
#:
#: Prefix matching is segment-aware — ``/ingest`` does not cover ``/ingested``.
#: Never declare ``"/"``: that would match every absolute path and turn the
#: scoped deny into exactly the full-route default-deny this registry exists to
#: prevent. ``tests/db/test_art9_registry.py`` fails if one appears.
INGEST_PREFIXES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "digisearch": ("/ingest",),
        "digivault": ("/v1/notes",),
        "digigraph": ("/v1/chat",),
    }
)

#: Ingestion routes per app: path template -> kind.
#:
#: Keys are the router's own path templates, read off ``app.routes``, never
#: hand-written strings that can drift from the router. The L4a/L4b/L4c diff
#: tests compare these against a live ``app.routes`` in both directions.
#:
#: Note the kind, not just presence: ``GET /v1/notes`` and ``POST /v1/notes``
#: share one path template, and the registry is keyed by path template, so a
#: route that reads and a route that ingests can only be told apart by their
#: value. That is also why ``digivault``'s read routes are listed — omitting
#: them would refuse working reads. ``/v1/notes`` is the one collision with no
#: way out: ``GET`` on it lists notes and ``POST`` on it creates one, so the
#: template takes the strict kind and the read is screened too.
INGEST_ROUTES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "digisearch": MappingProxyType(
            {
                "/ingest": ROUTE_KIND_INGEST,
                "/ingest/url": ROUTE_KIND_INGEST,
            }
        ),
        "digivault": MappingProxyType(
            {
                "/v1/notes": ROUTE_KIND_INGEST,
                "/v1/notes/by-path": ROUTE_KIND_READ,
                "/v1/notes/batch": ROUTE_KIND_INGEST,
                "/v1/notes/prune-children": ROUTE_KIND_READ,
                "/v1/notes/{name}": ROUTE_KIND_READ,
                "/v1/notes/{name}/backlinks": ROUTE_KIND_READ,
                "/v1/notes/{name}/frontmatter": ROUTE_KIND_INGEST,
                "/v1/notes/{name}/rename": ROUTE_KIND_INGEST,
            }
        ),
        "digigraph": MappingProxyType(
            {
                "/v1/chat/completions": ROUTE_KIND_INGEST,
            }
        ),
    }
)

#: Stable reason code for a route under a declared prefix with no entry. The
#: matched route is appended, never a category — the reason says which route went
#: unreviewed, not what was found in it.
ROUTE_UNREGISTERED = "art9:route_unregistered"


@dataclass(frozen=True)
class RouteDecision:
    """The refusal floor's verdict for one route.

    ``decision`` is ``"refuse"`` whenever the route falls under a declared
    ingestion prefix and carries no registry entry; ``"allow"`` means either the
    route is registered or it is outside every declared prefix. Only a caller
    holding an ``exception_ref`` (leaf L1) can reach a narrower outcome.
    """

    decision: Literal["allow", "refuse"]
    reason: str | None = None
    prefix: str | None = None

    @property
    def refused(self) -> bool:
        return self.decision == "refuse"


# ── prefix matching ──────────────────────────────────────────────────────────


def _normalize(path: str) -> str:
    """Strip trailing slashes so ``/ingest/`` and ``/ingest`` match alike."""
    return path.rstrip("/") or "/"


def is_under_prefix(path_template: str, prefix: str) -> bool:
    """Whether ``path_template`` sits under ``prefix``, matching whole segments.

    Segment-aware on purpose: a plain ``startswith`` would let ``/ingest`` cover
    ``/ingested``, and a registry that over-covers its own scope is a refusal
    floor that refuses routes nobody declared.
    """
    path = _normalize(path_template)
    base = _normalize(prefix)
    if path == base:
        return True
    return path.startswith(f"{base}/") if base != "/" else path.startswith("/")


def _matching_prefix(app: str, path_template: str) -> str | None:
    """The first declared prefix of ``app`` that covers ``path_template``."""
    for prefix in INGEST_PREFIXES.get(app, ()):
        if is_under_prefix(path_template, prefix):
            return prefix
    return None


# ── the public surface ───────────────────────────────────────────────────────


def is_registered(app: str, path_template: str) -> bool:
    """Whether ``(app, path_template)`` has an entry in the ingestion registry.

    This is the check that makes an unscreened ingestion route impossible to add
    quietly: a route under a declared prefix with no entry here is refused.

    Presence, not kind: this answers "did somebody look at this route", not "does
    this route ingest". Use ``route_kind`` for the latter — a ``read`` route is
    registered and therefore allowed, it simply carries no content to screen.

    The lookup normalises the same way ``is_under_prefix`` does, or the two would
    disagree: ``APIRouter(prefix="/ingest")`` with a route declared at ``"/"``
    really does report ``.path == "/ingest/"``, and refusing that would 403 a
    registered ingestion route and break the L4 two-way diff on both sides.
    """
    return route_kind(app, path_template) is not None


def route_kind(app: str, path_template: str) -> str | None:
    """The registered kind of ``(app, path_template)``, or ``None`` if unregistered."""
    routes = INGEST_ROUTES.get(app, {})
    return routes.get(path_template) or routes.get(_normalize(path_template))


def check_route(app: str, path_template: str) -> RouteDecision:
    """Apply the refusal floor to one **path template**.

    Refuses a route that falls under one of ``app``'s declared ingestion
    prefixes and has no registry entry, naming the route in the reason. Leaves a
    route outside every declared prefix untouched — health, metrics, CORS and
    reads must never 403 because this registry forgot about them.

    ``path_template`` is the router's own template (``/v1/notes/{name}``), not a
    concrete request path. This function does no path-to-template resolution: a
    request to ``/v1/notes/weekly.md`` is not in the registry under that name and
    would be refused. The caller resolves the template from the match — Starlette
    puts the matched route at ``request.scope["route"]`` — and refuses when
    nothing matched at all. Leaf L3 owns that middleware; this leaf only owns the
    registry it will consult.
    """
    prefix = _matching_prefix(app, path_template)
    if prefix is None:
        return RouteDecision(decision="allow")
    if is_registered(app, path_template):
        return RouteDecision(decision="allow", prefix=prefix)
    return RouteDecision(
        decision="refuse",
        reason=f"{ROUTE_UNREGISTERED}:{path_template}",
        prefix=prefix,
    )


def _effective_routes(route: Any) -> list[Any] | None:
    """FastAPI's own resolution of an included router, or ``None`` if not one.

    ``include_router`` produces a lazy ``_IncludedRouter`` whose children's
    ``.path`` is *not* reliably the served path: a router's own ``prefix`` is
    baked into its routes at declaration time, but a prefix inherited through a
    **nested** ``include_router`` is not, so ``APIRouter(prefix="/v1/chat")``
    including a bare router serves ``/v1/chat/completions`` while the route
    object still reads ``/completions``. Re-deriving that algebra here is how a
    diff test ends up comparing the wrong strings, so the framework's own
    resolution is asked instead.

    Probed with ``getattr`` rather than imported: ``art9`` keeps no FastAPI
    dependency, and on a FastAPI old enough to flatten routes onto the parent app
    this returns ``None`` and the plain ``.path`` walk below is already correct.
    """
    resolve = getattr(route, "effective_candidates", None)
    if not callable(resolve):
        return None
    return list(resolve())


def _iter_paths(routes: Iterable[Any], prefix: str = "") -> Iterator[str]:
    """Yield every path template under ``routes``, descending into nested apps.

    Three shapes, and they concatenate differently:

    - a plain route: its ``.path`` is the template.
    - ``include_router``'s ``_IncludedRouter``: resolved by the framework through
      ``effective_candidates()`` above, which handles the lazy prefix algebra.
      digigraph mounts its whole ``/v1`` router this way, so reading only
      top-level ``.path`` would make every digigraph route invisible and let the
      L4c diff pass on an empty set.
    - ``app.mount``'s ``Mount``: it has ``.routes`` and its children are
      *relative*, so the mount path has to be prepended or a mounted ingestion
      endpoint reads as one opaque ``/v1/notes`` entry.
    """
    for route in routes:
        resolved = _effective_routes(route)
        if resolved is not None:
            yield from _iter_paths(resolved, prefix=prefix)
            continue
        path = getattr(route, "path", None)
        if isinstance(path, str):
            yield f"{prefix}{path}"
        included = getattr(route, "original_router", None)
        if included is not None:
            # Unresolvable lazy include: fall back to the router's own routes.
            yield from _iter_paths(getattr(included, "routes", ()), prefix=prefix)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            # Relative children: the mount path is the prefix they hang off.
            yield from _iter_paths(
                nested, prefix=f"{prefix}{path}" if isinstance(path, str) else prefix
            )


def iter_ingest_routes(routes: Iterable[Any], app: str) -> Iterator[str]:
    """Yield each path template in ``routes`` that sits under a declared prefix.

    The enumeration half of the route-enumeration diff: L4a/L4b/L4c walk a live
    ``app.routes``, filter it down to the ingestion set with this, and compare it
    to ``INGEST_ROUTES[app]`` in both directions. A registered route with no
    matching route and an unmatched route with no entry both fail.

    Yields *every* in-scope template, not only the ones already registered — an
    unrecognised route is exactly what the diff needs to see. Deduplicated,
    order-preserving, and it tolerates route objects with no ``.path``.
    """
    prefixes = INGEST_PREFIXES.get(app, ())
    if not prefixes:
        return
    seen: set[str] = set()
    for path in _iter_paths(routes):
        if path in seen:
            continue
        if any(is_under_prefix(path, prefix) for prefix in prefixes):
            seen.add(path)
            yield path
