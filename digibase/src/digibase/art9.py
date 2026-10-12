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
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Literal

__all__ = [
    "ART9_CATEGORIES",
    "INGEST_PREFIXES",
    "INGEST_ROUTES",
    "mask_token",
    "ROUTE_KIND_INGEST",
    "ROUTE_KIND_READ",
    "ROUTE_UNREGISTERED",
    "Art9ConfigurationError",
    "RouteDecision",
    "ScreenResult",
    "art9_event_type",
    "audit_record",
    "category_order",
    "check_route",
    "field_names",
    "is_registered",
    "is_under_prefix",
    "iter_ingest_routes",
    "mask_token",
    "no_match_reason",
    "route_kind",
    "screen_and_apply",
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
#: over-triggers, and that is the accepted trade: `medical_billing_code`,
#: `dna_sequence_length`, `political_alerts` and `grace_period` (contains
#: `race`) all trip. Leaf L13 owns the false-positive battery
#: (`tests/db/test_art9_false_positives.py`) and settles which of those to narrow
#: or accept; narrowing here would pre-empt it and silently change the contract.
#:
#: The substring rule cuts both ways, and these stay **allowed** because §5.5
#: names the longer form and not the shorter substring: `healthcheck_url` (the
#: table lists `health_status`, not `health`), `trades` (the table lists
#: `trade_union`, not `trade`) and `undiagnosed` (it lists `diagnosis`, not
#: `diagnos`). Pinned by
#: `test_keys_whose_substrings_are_not_section_5_5_names_stay_allowed`.
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
    r"\b(?:nhs|health)\s*(?:record\s*)?(?:number|no\.?|#)\s*(?:[:#]\s*)?\d[\d\s-]{7,}\d",
    re.IGNORECASE,
)
_record_number_re = re.compile(
    r"\b(?:medical|patient|health)\s*(?:record|file)\s*(?:number|no\.?|#)"
    r"\s*(?:[:#]\s*)?\d[\d\s-]{4,}\d",
    re.IGNORECASE,
)
_date_of_birth_re = re.compile(
    r"\b(?:date\s*of\s*birth|birth\s*date|d\.?o\.?b\.?)\s*(?:[:#=]\s*)?"
    r"(?:(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])"
    r"|(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2})",
    re.IGNORECASE,
)
_brca_marker_re = re.compile(r"\bbrca[12]\b", re.IGNORECASE)
_rs_id_re = re.compile(r"\brs\d{3,}\b", re.IGNORECASE)
_genotype_call_re = re.compile(
    r"\b(?:(?:chr)?[0-9]{1,2}|x|y|mt)[:.][0-9]+[:. ]?[acgt]*[acgt]>[acgt]"
    r"|c\.[0-9]+(?:_[0-9]*)?(?:del|dup|ins|inv|[acgt]>)[a-z]*",
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


def _scan(node: Any, found: set[tuple[str, str]], seen: set[int], alive: list[Any]) -> None:
    """Collect every ``(category, signal)`` hit reachable from ``node``.

    Mapping keys go through the field-name table and string values through the
    identifier patterns; a key that trips two categories records both. Container
    identity is tracked in ``seen`` so a shared or self-referential payload
    terminates instead of recursing until the stack gives out — a request body is
    caller-supplied, so a cycle must not be a denial of service. Bytes are not
    decoded: decoding here would mean guessing an encoding.

    ``alive`` holds a strong reference to every object whose id is in ``seen``.
    The set alone is not enough: an ephemeral container — a generator or a lazy
    row iterator — is released as the walk rebinds, and CPython recycles its
    address, so the next object can collide on an id that is still in the set and
    be skipped unscanned. On a streamed payload that fails open, which for a
    detector means allowing data it was asked to refuse. Keeping the objects
    alive pins their ids to the objects they were taken from.
    """
    if isinstance(node, str):
        found.update(_match_value(node))
        return
    if isinstance(node, _opaque_scalars):
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    alive.append(node)

    if isinstance(node, Mapping):
        for key, value in node.items():
            for category in _match_key(key if isinstance(key, str) else str(key)):
                found.add((category, "field_name"))
            _scan(value, found, seen, alive)
        return
    if isinstance(node, Iterable):
        for item in node:
            _scan(item, found, seen, alive)


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
    # Two value patterns in one category tie on the first two keys, and `min` over
    # a set falls back to set iteration order — which is hash-seed randomised, so
    # the same payload would emit a different reason per process and scatter the
    # label series `reason` is meant to key. The signal name breaks the tie.
    category, signal = min(
        found,
        key=lambda hit: (category_order.index(hit[0]), hit[1] != "field_name", hit[1]),
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
    _scan(payload, found, set(), [])
    categories, decision, reason = _decide(found, exception_ref)
    return ScreenResult(
        categories=categories,
        redacted=None,
        decision=decision,
        reason=reason,
        exception_ref=exception_ref,
    )


# ── masking, the audit record, and irreversibility ────────────────────────────

#: Leaf L2 (DIG-1084). The value a masked field is replaced with. A **constant**,
#: never a function of the value it replaced — see `mask_payload`.
#:
#: Lowercase because leaf L0's `test_module_exposes_no_public_name_outside_the_registry_surface`
#: refuses every module-level global whose name is upper-case, so that nobody can
#: add a runtime-switchable `ART9_MODE`. L1's `no_match_reason` is lowercase for
#: the same reason. The decision this leaf needs to make configurable is therefore
#: a **parameter** (`screen_and_apply`'s own default), not a global: a caller
#: passes `decision=`, and there is no global for anyone to reassign.
mask_token = "[ART9_MASKED]"

#: ``event_type`` for the audit line a caller emits around a screening decision.
art9_event_type = "art9_screening_decision"


class Art9ConfigurationError(ValueError):
    """`mask` was requested with no Art. 9(2) exception letter behind it.

    Raised instead of falling back to `refuse`. A fallback would make a
    misconfigured deployment look like a correctly refusing one: the caller sees
    a working screen and never learns the mask it asked for cannot legally run.
    §2.4 is explicit that masking a row requires already holding it, and holding
    it is the processing Art. 9(1) prohibits — so a mask without a letter is not
    a decision, it is a configuration error.
    """


def _resolve_decision(decision: str, exception_ref: str | None) -> str:
    """Validate ``decision`` against the letter it depends on.

    `refuse` is always legal — it is the floor and needs no authorisation.
    `mask` requires a non-blank ``exception_ref``: a letter that is empty or
    whitespace is not a citation, and accepting one would put the mask behind a
    check that can be satisfied by a missing config value.
    """
    if decision == "refuse":
        return decision
    if decision != "mask":
        raise Art9ConfigurationError(f"decision must be 'refuse' or 'mask', got {decision!r}")
    if exception_ref is None or not exception_ref.strip():
        raise Art9ConfigurationError(
            "mask requires an Art. 9(2) exception_ref naming the authorising "
            "letter; masking without one is refused, not silently downgraded"
        )
    return decision


def _mask_key(key: Any, value: Any, out: dict[Any, Any], seen: dict[int, Any]) -> None:
    """Mask ``value`` when ``key`` names a category, else recurse into it.

    ``seen`` is threaded through rather than re-created per key: a caller-supplied
    payload can point back at itself, and a fresh set at each hop would lose the
    cycle guard exactly one level below where it was needed.
    """
    name = key if isinstance(key, str) else str(key)
    if _match_key(name):
        out[key] = mask_token
        return
    out[key] = mask_payload(value, _seen=seen)


def mask_payload(payload: Any, *, _seen: dict[int, Any] | None = None) -> Any:
    """Return a copy of ``payload`` with every Art. 9 value replaced by `mask_token`.

    **Irreversible, and that is the point.** The replacement is a module
    constant, never a function of the value it replaces, so there is nothing to
    invert: no key store, no token, no digest, no original sidecar. A per-value
    digest would be reversible in the only sense that matters — an attacker who
    can guess candidate values recovers the original by recomputing, with no
    access to anything this module holds. Two different secrets under the same
    field name mask to the *same* token, which is what
    ``test_mask_is_not_derived_from_the_value`` pins.

    The whole value under a matching key is dropped, not just the matched span:
    a §5.5 field name marks the *value* as the category, so masking the span and
    keeping the rest would keep the data. Value-pattern hits on an otherwise
    ordinary string replace that string.

    Structure is preserved where it is safe to do so — a list stays a list, a
    nested mapping stays a mapping — so a masked payload is still a valid payload
    shape for the caller's own schema validation. Cycles terminate: an id already
    being walked is left alone rather than recursed into.
    """
    seen: dict[int, Any] = {} if _seen is None else _seen
    if isinstance(payload, _opaque_scalars):
        return mask_token
    if isinstance(payload, str):
        return mask_token if _match_value(payload) else payload
    if isinstance(payload, Mapping):
        marker = id(payload)
        if marker in seen:
            return payload
        seen[marker] = payload
        out: dict[Any, Any] = {}
        for key, value in payload.items():
            _mask_key(key, value, out, seen)
        return out
    if isinstance(payload, (set, frozenset)):
        marker = id(payload)
        if marker in seen:
            return payload
        seen[marker] = payload
        return type(payload)(mask_token for _ in payload)
    if isinstance(payload, (list, tuple)):
        marker = id(payload)
        if marker in seen:
            return payload
        seen[marker] = payload
        masked = [mask_payload(item, _seen=seen) for item in payload]
        return type(payload)(masked) if isinstance(payload, tuple) else masked
    if isinstance(payload, Iterable):
        # A generator or other one-shot iterator: consumed into a list, because
        # there is no in-place way to mask one and a partially consumed iterator
        # is worse than a materialised copy.
        return [mask_payload(item, _seen=seen) for item in payload]
    return payload


def _masked_field_names(payload: Any, *, _seen: dict[int, Any] | None = None) -> int:
    """How many top-level-and-nested values `mask_payload` replaced.

    A count, and only a count: the *names* of the affected keys can themselves
    be category-bearing (`health_status` is a field name), so the audit stream
    records how many, never which.
    """
    seen: dict[int, Any] = {} if _seen is None else _seen
    if isinstance(payload, (str, bytes, bytearray, memoryview)):
        return 1 if isinstance(payload, str) and _match_value(payload) else 0
    if isinstance(payload, Mapping):
        marker = id(payload)
        if marker in seen:
            return 0
        seen[marker] = payload
        total = 0
        for key, value in payload.items():
            name = key if isinstance(key, str) else str(key)
            if _match_key(name):
                total += 1
            else:
                total += _masked_field_names(value, _seen=seen)
        return total
    if isinstance(payload, (set, frozenset, list, tuple)):
        marker = id(payload)
        if marker in seen:
            return 0
        seen[marker] = payload
        return sum(_masked_field_names(item, _seen=seen) for item in payload)
    if isinstance(payload, Iterable):
        return sum(_masked_field_names(item, _seen=seen) for item in payload)
    return 0


def screen_and_apply(
    payload: Any,
    *,
    decision: str = "refuse",
    exception_ref: str | None = None,
) -> ScreenResult:
    """Screen ``payload`` and apply ``decision`` to it. Leaf L2's entry point.

    The single place the decision policy lives. `screen_request` and
    `screen_text` remain detection-only and keep reporting `mask` for anything
    handed an ``exception_ref``; this function is what actually performs the
    mask, and it is the only one that can raise.

    - ``allow``  → the payload is returned untouched, `redacted` stays `None`.
    - ``refuse`` → `redacted` stays `None`. A refused payload is not handed
      back: returning a partially masked copy of something we just refused would
      invite the caller to persist it.
    - ``mask``   → `redacted` holds the irreversibly masked copy, and only when
      ``exception_ref`` names a letter. Without one this raises
      `Art9ConfigurationError` rather than downgrading to `refuse`.

    Raises `Art9ConfigurationError` before doing any work if ``decision`` is
    ``mask`` with no letter, so a misconfigured caller learns about it on the
    first request instead of at the first audit review.
    """
    _resolve_decision(decision, exception_ref)
    screened = screen_request(payload)
    if screened.decision == "allow":
        return replace(screened, redacted=None, exception_ref=exception_ref)
    if decision == "refuse":
        return replace(screened, decision="refuse", redacted=None, exception_ref=exception_ref)
    return replace(
        screened,
        decision="mask",
        redacted=mask_payload(payload),
        exception_ref=exception_ref,
    )


def audit_record(result: ScreenResult, *, payload: Any = None) -> dict[str, Any]:
    """The audit stream's view of one screening decision.

    Carries the category ids, the decision, the reason code and the letter — the
    facts an auditor needs to reconstruct *why a request was handled this way*,
    and none of the things they must not have. The matched value never appears:
    `reason` is a machine code assembled from the tables above, and no value in
    the returned mapping is derived from the payload.

    **This is not the egress record.** Where the call went, and the digest of
    what was sent, belong to the outbound seam (DIG-1139). Writing either here
    would duplicate a record that has to stay consistent with the transport's
    own view, and a duplicated digest is how an unkeyed fallback creeps back in.
    ``test_audit_record_carries_no_destination_and_no_digest`` pins the boundary.

    ``payload`` is the **original** request body, accepted only so the count of
    replaced values can be taken from it. It is read, never stored and never
    serialised: it contributes a number and nothing else. Omit it and the count
    is 0, which is correct for every `refuse` — nothing was replaced.
    """
    return {
        "art9_categories": list(result.categories),
        "art9_decision": result.decision,
        "art9_reason": result.reason,
        "art9_masked_fields": _masked_field_names(payload) if payload is not None else 0,
        "art9_exception_ref": result.exception_ref,
    }
