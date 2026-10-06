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

import re
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
    "ScreenResult",
    "category_order",
    "check_route",
    "field_names",
    "is_registered",
    "is_under_prefix",
    "iter_ingest_routes",
    "no_match_reason",
    "route_kind",
    "screen_request",
    "screen_text",
    "value_patterns",
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


# ── detection ────────────────────────────────────────────────────────────────

#: The eight ids in §5.5 table order. `ART9_CATEGORIES` is a `frozenset`, so its
#: iteration order is not a contract; this tuple is, and `categories` is reported
#: in it. The two are asserted equal in `tests/db/test_art9_detect.py`, so a
#: ninth category added to the frozenset fails there rather than silently never
#: appearing in a result.
category_order: tuple[str, ...] = (
    "health",
    "genetic",
    "biometric",
    "racial_or_ethnic_origin",
    "political_opinions",
    "religious_or_philosophical_beliefs",
    "trade_union_membership",
    "sex_life_or_sexual_orientation",
)

#: §5.5 field names per category, matched as **substrings** of the lowercased key.
#:
#: This is exactly what `digibase.audit._key_is_sensitive` does — the technique
#: §5.5 names as already proven in this codebase — so the substring rule is
#: deliberately **not** narrowed to exact keys or to word boundaries. It
#: over-triggers, and that is the accepted trade: `healthcheck_url`,
#: `medical_billing_code`, `grace_period` (contains `race`), `trades` (contains
#: `trade`) and `philosophical` all trip. Leaf L13 owns the false-positive battery
#: (`tests/db/test_art9_false_positives.py`) and settles which of those to narrow
#: or accept; narrowing here would pre-empt it and silently change the contract.
field_names: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "health": ("diagnosis", "health_status", "medical"),
        "genetic": ("genotype", "genetic", "dna", "snp"),
        "biometric": ("biometric",),
        "racial_or_ethnic_origin": ("ethnicity", "race"),
        "political_opinions": ("political", "party_affiliation"),
        "religious_or_philosophical_beliefs": ("religion", "religious", "philosophical"),
        "trade_union_membership": ("union_membership", "trade_union"),
        "sex_life_or_sexual_orientation": ("sexual_orientation", "sex_life"),
    }
)

# §5.5's value-position identifier patterns: health and NHS record numbers, dates
# of birth, genetic markers and biometric template descriptors.
#
# Each is anchored on a shape that does not occur by accident, because the
# unanchored version of all three is worthless:
#
# - a bare 10-digit run is a phone number, so a record number needs its label;
# - a bare ISO date is a timestamp, so a date of birth needs its label;
# - `rs4988235`, `BRCA1`, `chr17:43124095:G>T` and `c.68_69delAG` have no neutral
#   twin, so those need no label; a template does, since "template" is a common
#   word on its own.

_nhs_number_re = re.compile(
    r"\b(?:nhs|health)\s*(?:record\s*)?(?:number|no\.?|#)\s*[:#]?\s*\d[\d\s-]{7,}\d",
    re.IGNORECASE,
)
_record_number_re = re.compile(
    r"\b(?:medical|patient|health)\s*(?:record|file)\s*(?:number|no\.?|#)"
    r"\s*[:#]?\s*\d[\d\s-]{4,}\d",
    re.IGNORECASE,
)
_date_of_birth_re = re.compile(
    r"\b(?:date\s*of\s*birth|birth\s*date|d\.?o\.?b\.?)\s*[:#=]?\s*"
    r"(?:(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])"
    r"|(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2})",
    re.IGNORECASE,
)
_brca_marker_re = re.compile(r"\bbrca[12]\b", re.IGNORECASE)
_rs_id_re = re.compile(r"\brs\d{3,}\b", re.IGNORECASE)
_genotype_call_re = re.compile(
    r"\b(?:(?:chr)?[0-9]{1,2}|x|y|mt)[:.][0-9]+[:. ]?[acgt]*[acgt]>[acgt]"
    r"|c\.[0-9]+_?[0-9]*(?:del|dup|ins|inv|[acgt]>)[a-z]*",
    re.IGNORECASE,
)
_biometric_template_re = re.compile(
    r"\b(?:(?:biometric|fingerprint|finger\s+print|face|iris|voice)"
    r"\s+(?:template|descriptor|embedding|vector)"
    r"|minutiae)\b",
    re.IGNORECASE,
)

#: ``(category, signal) -> pattern``. The signal becomes the last field of the
#: `reason` code, so it is a fixed vocabulary: a reason is assembled from this
#: table, never from the input that matched.
value_patterns: Mapping[tuple[str, str], re.Pattern[str]] = MappingProxyType(
    {
        ("health", "nhs_number"): _nhs_number_re,
        ("health", "record_number"): _record_number_re,
        ("health", "date_of_birth"): _date_of_birth_re,
        ("genetic", "brca_marker"): _brca_marker_re,
        ("genetic", "rs_id"): _rs_id_re,
        ("genetic", "genotype_call"): _genotype_call_re,
        ("biometric", "biometric_template"): _biometric_template_re,
    }
)

#: Containers that must not be decoded or iterated as text.
_opaque_scalars = (bytes, bytearray, memoryview)

#: The reason code for a payload that tripped nothing. There is no category to
#: name, and a consumer parsing `reason` needs to be able to tell that apart from
#: a hit.
no_match_reason = "art9:no_match"


@dataclass(frozen=True)
class ScreenResult:
    """What screening one payload found, and what to do about it.

    ``categories`` is the subset of `category_order` that matched, in that
    order and de-duplicated, so a caller can render or iterate it without sorting.
    Empty pairs with ``decision == "allow"``.

    ``redacted`` is ``None`` on every path in this leaf: masking is L2, and there
    is nothing to hand back until the redaction exists. The field is here so the
    L2 diff is additive instead of a signature break.

    ``reason`` is a stable machine code — ``art9:<category>:<signal>``, or
    ``no_match_reason``. It never carries the matched value. The reason travels into
    logs, metrics labels and error envelopes, and echoing a special-category value
    there would copy that data into the one place least able to hold it.

    ``exception_ref`` is echoed on every result, so a caller can always see the
    Art. 9(2) letter a `mask` rested on.
    """

    categories: tuple[str, ...]
    redacted: Any
    decision: Literal["allow", "mask", "refuse"]
    reason: str
    exception_ref: str | None = None


def _match_key(key: str) -> tuple[str, ...]:
    """Categories whose §5.5 field names occur as substrings of ``key``.

    Lowercased substring matching, mirroring `digibase.audit._key_is_sensitive`.
    Every match is returned rather than the first: ``medical_religion`` really
    does carry a health category *and* a belief, and reporting one of them would
    understate what the payload holds.
    """
    lowered = key.lower()
    return tuple(
        category
        for category in category_order
        if any(field in lowered for field in field_names[category])
    )


def _match_value(value: str) -> tuple[tuple[str, str], ...]:
    """The ``(category, signal)`` pairs whose value pattern occurs in ``value``."""
    return tuple(key for key, pattern in value_patterns.items() if pattern.search(value))


def _scan(node: Any, found: set[tuple[str, str]], seen: set[int]) -> None:
    """Collect every ``(category, signal)`` hit reachable from ``node``.

    Mapping keys go through the field-name table and string values through the
    identifier patterns; a key that trips two categories records both. Container
    identity is tracked in ``seen`` so a shared or self-referential payload
    terminates instead of recursing until the stack gives out — a request body is
    caller-supplied, so a cycle must not be a denial of service. Bytes are not
    decoded: decoding here would mean guessing an encoding.
    """
    if isinstance(node, str):
        found.update(_match_value(node))
        return
    if isinstance(node, _opaque_scalars):
        return
    if id(node) in seen:
        return
    seen.add(id(node))

    if isinstance(node, Mapping):
        for key, value in node.items():
            for category in _match_key(key if isinstance(key, str) else str(key)):
                found.add((category, "field_name"))
            _scan(value, found, seen)
        return
    if isinstance(node, Iterable):
        for item in node:
            _scan(item, found, seen)


def _decide(
    found: set[tuple[str, str]], exception_ref: str | None
) -> tuple[tuple[str, ...], Literal["allow", "mask", "refuse"], str]:
    """Order the hits into ``(categories, decision, reason)``.

    `reason` reports the first hit in `category_order`, so the same payload
    always yields the same code whatever order its keys were inserted in. Within a
    category a field-name hit outranks a value-pattern hit: the key is the
    stronger signal, and the value may have matched by accident.

    ``mask`` is reachable only alongside an ``exception_ref`` and is never the
    default. §2.4 is explicit that masking a row requires already holding it, and
    holding it is the processing Art. 9(1) prohibits — so `refuse` is the floor and
    `mask` is the exceptional path. A `mask` with no letter is a configuration
    error rather than a decision, and it belongs to leaf L2: raising from a
    detection-only leaf would make it throw on input it is meant to classify.
    """
    if not found:
        return (), "allow", no_match_reason

    categories = tuple(
        category for category in category_order if any(c == category for c, _ in found)
    )
    category, signal = min(
        found,
        key=lambda hit: (category_order.index(hit[0]), hit[1] != "field_name"),
    )
    decision: Literal["allow", "mask", "refuse"] = "mask" if exception_ref else "refuse"
    return categories, decision, f"art9:{category}:{signal}"


def screen_text(value: str, *, exception_ref: str | None = None) -> ScreenResult:
    """Screen a bare string for Art. 9 special-category data.

    This is the identifier-pattern half of the detector and it is deliberately
    narrow: it finds high-precision values — NHS and record numbers, dates of
    birth, BRCA markers, rs-IDs, genotype calls, biometric template descriptors —
    and **not** prose. A sentence asserting a political opinion or a union
    membership returns ``allow``, because no pattern detects those in prose at
    usable precision (§5.6). Coverage of all eight categories comes from the field
    names in `screen_request`, not from here.

    ``redacted`` is ``None`` in this leaf; masking is L2.
    """
    found: set[tuple[str, str]] = set(_match_value(value))
    categories, decision, reason = _decide(found, exception_ref)
    return ScreenResult(
        categories=categories,
        redacted=None,
        decision=decision,
        reason=reason,
        exception_ref=exception_ref,
    )


def screen_request(payload: Any, *, exception_ref: str | None = None) -> ScreenResult:
    """Screen an arbitrary request payload for the eight Art. 9 categories.

    Walks mappings and iterables, so a ``diagnosis`` nested four levels down
    inside a list of dicts is found exactly like one at the top. Mapping keys go
    through the §5.5 field-name table and string values through the identifier
    patterns; numbers, booleans, ``None`` and bytes carry no category of their
    own.

    A payload that trips nothing returns ``decision == "allow"`` with
    ``reason == no_match_reason``. A payload that trips anything returns ``refuse``,
    or ``mask`` when the caller supplies an Art. 9(2) letter as ``exception_ref``.

    Every container is walked once, so shared subtrees and cycles terminate rather
    than recurse.
    """
    found: set[tuple[str, str]] = set()
    _scan(payload, found, set())
    categories, decision, reason = _decide(found, exception_ref)
    return ScreenResult(
        categories=categories,
        redacted=None,
        decision=decision,
        reason=reason,
        exception_ref=exception_ref,
    )
