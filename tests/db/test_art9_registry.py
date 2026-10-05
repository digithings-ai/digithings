"""Art. 9 ingestion registry: categories, declared scope, refusal floor.

Leaf L0 of DIG-1070. This module holds the shared registry that the Art. 9
filter consults. It performs **no detection** — that is leaf L1 (DIG-1071) — and
it is **not mounted** anywhere; `digibase` is a library.

The load-bearing test in this file is
`test_route_outside_every_declared_prefix_is_untouched`. The refusal floor is
scoped: a route under a declared ingestion prefix with no registry entry is
refused, and a route outside every declared prefix is left alone. Widening that
into "refuse every unregistered route" would 403 `/health`, `/metrics`, the CORS
preflight and every read endpoint in the stack. Do not "fix" that test.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI

import digibase
from digibase import art9

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────


def _route(path: str, methods: list[str] | None = None) -> SimpleNamespace:
    """A stand-in for a flat FastAPI route object.

    Only `.path` is read by the registry, so a `SimpleNamespace` is enough for
    the unit-level cases. The nesting shapes that actually matter — what
    `include_router` and `app.mount` produce — are exercised against real
    FastAPI objects further down, because guessing at their shape is how a
    helper ends up walking something the framework never emits.
    """
    return SimpleNamespace(path=path, methods=methods or ["POST"])


def _digigraph_like_app() -> FastAPI:
    """A real `FastAPI` shaped like digigraph: one `APIRouter(prefix="/v1")`."""
    v1 = APIRouter(prefix="/v1")

    @v1.post("/chat/completions")
    def _chat() -> None: ...

    @v1.get("/models")
    def _models() -> None: ...

    app = FastAPI()
    app.include_router(v1)
    return app


# ── 1. categories ────────────────────────────────────────────────────────────


def test_art9_categories_is_exactly_the_eight_ids() -> None:
    assert art9.ART9_CATEGORIES == frozenset(
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


def test_art9_categories_is_immutable() -> None:
    assert isinstance(art9.ART9_CATEGORIES, frozenset)


def test_art9_categories_has_no_near_miss_ids() -> None:
    """A typo'd id would be a category that silently never matches anything."""
    for near_miss in ("Health", "genetics", "biometrics", "ethnic_origin", "union_membership"):
        assert near_miss not in art9.ART9_CATEGORIES


# ── 2. registered vs unregistered ────────────────────────────────────────────


def test_registered_route_under_declared_prefix_is_registered() -> None:
    assert art9.is_registered("digisearch", "/ingest")
    assert art9.is_registered("digisearch", "/ingest/url")


def test_unregistered_route_under_declared_prefix_is_not_registered() -> None:
    assert not art9.is_registered("digisearch", "/ingest/not-a-route")


def test_out_of_scope_route_is_not_registered() -> None:
    assert not art9.is_registered("digisearch", "/health")
    assert not art9.is_registered("digivault", "/v1/status")


def test_unknown_app_is_never_registered() -> None:
    assert not art9.is_registered("nosuchapp", "/ingest")


# ── 3. the refusal floor ─────────────────────────────────────────────────────


def test_unregistered_route_under_declared_prefix_is_refused_naming_the_route() -> None:
    decision = art9.check_route("digisearch", "/ingest/not-a-route")

    assert decision.decision == "refuse"
    assert decision.reason == "art9:route_unregistered:/ingest/not-a-route"
    assert decision.prefix == "/ingest"


def test_refusal_reason_names_the_route_not_a_category() -> None:
    """The *code* half of the reason carries no category; the route half may.

    A path can legitimately contain a category word — `/ingest/health` — so the
    invariant is that the stable code names the route and never names a category.
    Asserting the whole string is category-free would only pass by luck of the
    path chosen.
    """
    namespace, code, route = art9.check_route("digivault", "/v1/notes/bogus").reason.split(":", 2)

    assert namespace == "art9"
    assert route == "/v1/notes/bogus"
    for category in art9.ART9_CATEGORIES:
        assert category not in f"{namespace}:{code}"


def test_refusal_reason_carries_the_stable_code() -> None:
    reason = art9.check_route("digigraph", "/v1/chat/nope").reason

    assert reason is not None
    assert reason.startswith("art9:route_unregistered:")


def test_route_unregistered_code_is_published() -> None:
    """Downstream leaves match on the code, so it is part of the public surface."""
    assert art9.ROUTE_UNREGISTERED == "art9:route_unregistered"
    assert digibase.ROUTE_UNREGISTERED == art9.ROUTE_UNREGISTERED


def test_registry_symbols_are_re_exported_from_the_package() -> None:
    for name in (
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
    ):
        assert name in digibase.__all__, f"digibase must re-export {name}"
        assert getattr(digibase, name) is getattr(art9, name)


def test_registered_route_under_declared_prefix_is_allowed() -> None:
    decision = art9.check_route("digisearch", "/ingest")

    assert decision.decision == "allow"
    assert decision.reason is None


def test_route_outside_every_declared_prefix_is_untouched() -> None:
    """F1 scoping — scoped deny only, never a full-route default-deny.

    Refusing every unregistered route would 403 liveness probes, metrics, the
    OpenAPI docs, CORS preflight and every read endpoint in the stack.
    """
    untouched = [
        ("digisearch", "/health"),
        ("digisearch", "/healthz"),
        ("digisearch", "/metrics"),
        ("digisearch", "/docs"),
        ("digisearch", "/openapi.json"),
        ("digisearch", "/redoc"),
        ("digisearch", "/query"),
        ("digisearch", "/v1/orchestrator_tools"),
        ("digisearch", "/v1/web_search"),
        ("digisearch", "/indexes"),
        ("digivault", "/healthz"),
        ("digivault", "/v1/status"),
        ("digivault", "/v1/tags/{tag}"),
        ("digivault", "/v1/lint"),
        ("digigraph", "/health"),
        ("digigraph", "/files/{path:path}"),
        ("digigraph", "/workflow"),
        ("digigraph", "/threads/{thread_id}/state"),
        ("digigraph", "/v1/models"),
    ]
    for app, path in untouched:
        decision = art9.check_route(app, path)
        assert decision.decision == "allow", f"{app} {path} must be untouched"
        assert decision.reason is None, f"{app} {path} must be untouched"


def test_prefix_match_is_segment_aware() -> None:
    """`/ingested` shares a string prefix with `/ingest` but is not under it."""
    decision = art9.check_route("digisearch", "/ingested")

    assert decision.decision == "allow"
    assert not art9.is_registered("digisearch", "/ingested")


def test_unknown_app_has_no_ingestion_scope() -> None:
    decision = art9.check_route("nosuchapp", "/ingest")

    assert decision.decision == "allow"


def test_module_exposes_no_public_name_outside_the_registry_surface() -> None:
    """Every module-level constant is part of the declared registry surface.

    `decision` is a fixed default, not a switch someone can flip at runtime, and
    the way to keep it that way is to refuse new module-level globals by name —
    a guessed list of forbidden names (`ART9_MODE`, `FAIL_OPEN`, …) cannot.
    """
    declared = {
        "ART9_CATEGORIES",
        "INGEST_PREFIXES",
        "INGEST_ROUTES",
        "ROUTE_KIND_INGEST",
        "ROUTE_KIND_READ",
        "ROUTE_UNREGISTERED",
    }

    assert {name for name, value in vars(art9).items() if name.isupper()} == declared


def test_route_decision_is_frozen() -> None:
    """A decision that can be flipped after `check_route` returns is not a floor."""
    decision = art9.check_route("digisearch", "/ingest/unlisted")

    with pytest.raises(AttributeError):
        decision.decision = "allow"  # type: ignore[misc]


def test_registry_is_not_mutable_at_runtime() -> None:
    """The floor cannot be turned off by assigning into the registry.

    `INGEST_ROUTES["digisearch"]["/x"] = "ingest"` would allow an unscreened
    ingestion route with no flag and no import — the exact failure this module
    exists to prevent. Read-only mappings close that door.
    """
    with pytest.raises(TypeError):
        art9.INGEST_ROUTES["digisearch"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        art9.INGEST_ROUTES["digisearch"]["/ingest/backdoor"] = "ingest"  # type: ignore[index]
    with pytest.raises(TypeError):
        art9.INGEST_PREFIXES["digisearch"] = ()  # type: ignore[index]


def test_registered_route_under_declared_prefix_reports_its_prefix() -> None:
    decision = art9.check_route("digisearch", "/ingest")

    assert decision.decision == "allow"
    assert decision.prefix == "/ingest"


def test_trailing_slash_on_a_registered_route_is_still_registered() -> None:
    """`APIRouter(prefix="/ingest")` + a route at `"/"` reports `.path == "/ingest/"`.

    Prefix matching normalises, so if the registry lookup did not, this registered
    route would be refused and the L4 two-way diff would report it missing *and*
    report `/ingest` as having no route.
    """
    router = APIRouter(prefix="/ingest")

    @router.post("/")
    def _ingest() -> None: ...

    app = FastAPI()
    app.include_router(router)

    assert art9.check_route("digisearch", "/ingest/").decision == "allow"
    assert list(art9.iter_ingest_routes(app.routes, "digisearch")) == ["/ingest/"]


# ── 4. registry / prefix coherence ───────────────────────────────────────────


@pytest.mark.parametrize("app", sorted(art9.INGEST_ROUTES))
def test_every_registered_route_lives_under_a_declared_prefix(app: str) -> None:
    prefixes = art9.INGEST_PREFIXES.get(app, ())
    for path in art9.INGEST_ROUTES[app]:
        assert any(art9.is_under_prefix(path, prefix) for prefix in prefixes), (
            f"{app} {path} is registered but outside every declared prefix"
        )


@pytest.mark.parametrize("app", sorted(art9.INGEST_ROUTES))
def test_registered_route_values_are_known_kinds(app: str) -> None:
    kinds = {art9.ROUTE_KIND_INGEST, art9.ROUTE_KIND_READ}
    for path, kind in art9.INGEST_ROUTES[app].items():
        assert kind in kinds, f"{app} {path} has unknown kind {kind!r}"


def test_route_kind_is_queryable() -> None:
    """A `read` route is registered *and* distinguishable from an ingest route.

    Presence alone answers "did somebody look at this"; leaves that need to know
    whether there is content to screen have to be able to ask which it is.
    """
    assert art9.route_kind("digisearch", "/ingest") == art9.ROUTE_KIND_INGEST
    assert art9.route_kind("digivault", "/v1/notes/{name}") == art9.ROUTE_KIND_READ
    assert art9.route_kind("digisearch", "/ingest/nope") is None


def test_every_declared_ingestion_route_is_under_a_prefix() -> None:
    """Sanity on the inventory: each app registers something, under its own scope."""
    for app in ("digisearch", "digivault", "digigraph"):
        kinds = set(art9.INGEST_ROUTES[app].values())
        assert art9.ROUTE_KIND_INGEST in kinds, f"{app} declares no ingestion route at all"


@pytest.mark.parametrize("app", sorted(art9.INGEST_PREFIXES))
def test_declared_prefixes_are_normalised(app: str) -> None:
    for prefix in art9.INGEST_PREFIXES[app]:
        assert prefix.startswith("/"), f"{app} prefix {prefix!r} must be absolute"
        assert not prefix.endswith("/"), f"{app} prefix {prefix!r} must not have a trailing slash"
        assert "//" not in prefix, f"{app} prefix {prefix!r} must not have an empty segment"


def test_no_declared_prefix_is_the_root() -> None:
    """`"/"` matches every absolute path — it is global deny wearing a prefix.

    One character in one prefix declaration would 403 health, metrics, CORS and
    every read in the stack, which is the outcome this registry exists to avoid.
    """
    for app, prefixes in art9.INGEST_PREFIXES.items():
        assert "/" not in prefixes, f"{app} declares the root prefix: global default-deny"


def test_every_declared_app_has_a_registry_entry() -> None:
    assert set(art9.INGEST_PREFIXES) == set(art9.INGEST_ROUTES)


# ── 5. route enumeration ─────────────────────────────────────────────────────


def test_iter_ingest_routes_yields_top_level_routes_under_a_prefix() -> None:
    routes = [
        _route("/openapi.json", ["GET"]),
        _route("/healthz", ["GET"]),
        _route("/ingest"),
        _route("/ingest/url"),
        _route("/ingest/rogue"),
        _route("/ingested"),
        _route("/query", ["GET"]),
    ]

    found = list(art9.iter_ingest_routes(routes, "digisearch"))

    assert found == ["/ingest", "/ingest/url", "/ingest/rogue"]


def test_iter_ingest_routes_traverses_a_real_included_router() -> None:
    """`include_router` does not flatten routes onto the parent app.

    digigraph mounts its whole `/v1` router this way. A helper that only reads
    `.path` off top-level route objects sees none of it and the wave-2 diff test
    passes on an empty set. Run against real FastAPI objects on purpose: the
    nesting shape is a framework detail, and a hand-rolled stand-in for it is a
    guess that can encode the opposite of the truth.
    """
    found = list(art9.iter_ingest_routes(_digigraph_like_app().routes, "digigraph"))

    assert found == ["/v1/chat/completions"]


def test_iter_ingest_routes_traverses_nested_routers() -> None:
    inner = APIRouter()

    @inner.post("/completions")
    def _chat() -> None: ...

    outer = APIRouter(prefix="/v1/chat")
    outer.include_router(inner)
    app = FastAPI()
    app.include_router(outer)

    assert list(art9.iter_ingest_routes(app.routes, "digigraph")) == ["/v1/chat/completions"]


def test_iter_ingest_routes_descends_into_a_mounted_sub_app() -> None:
    """`app.mount` children are relative and must be joined with the mount path.

    Without this a mounted ingestion endpoint reads as one opaque `/v1/notes`
    entry, and the L4 diff would compare a mount point against the registry.
    """
    sub = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @sub.post("/by-path")
    def _by_path() -> None: ...

    app = FastAPI()
    app.mount("/v1/notes", sub)

    assert list(art9.iter_ingest_routes(app.routes, "digivault")) == [
        "/v1/notes",
        "/v1/notes/by-path",
    ]


def test_iter_ingest_routes_does_not_double_a_prefix_an_included_router_already_applied() -> None:
    """`include_router` children already carry the parent prefix in `.path`."""
    found = list(art9.iter_ingest_routes(_digigraph_like_app().routes, "digigraph"))

    assert not any(path.startswith("/v1/v1") for path in found)


def test_iter_ingest_routes_reads_the_router_path_template() -> None:
    """Keys come from the router's raw `.path`, not the normalised `.path_format`.

    `path_format` drops the converter, so `/v1/notes/{name}/x/{file:path}` becomes
    `/v1/notes/{name}/x/{file}`. Registry keys have to be the router's own
    template, so that they can never disagree with `app.routes`.
    """
    route = SimpleNamespace(
        path="/v1/notes/{name}/x/{file:path}",
        path_format="/v1/notes/{name}/x/{file}",
    )

    found = list(art9.iter_ingest_routes([route], "digivault"))

    assert found == ["/v1/notes/{name}/x/{file:path}"]


def test_iter_ingest_routes_yields_each_template_once() -> None:
    routes: list[Any] = [_route("/ingest"), _route("/ingest")]

    assert list(art9.iter_ingest_routes(routes, "digisearch")) == ["/ingest"]


def test_iter_ingest_routes_is_empty_for_an_app_with_no_scope() -> None:
    assert list(art9.iter_ingest_routes([_route("/ingest")], "nosuchapp")) == []


def test_iter_ingest_routes_is_empty_for_no_routes() -> None:
    assert list(art9.iter_ingest_routes([], "digisearch")) == []


def test_iter_ingest_routes_tolerates_route_objects_without_a_path() -> None:
    routes: list[Any] = [_route("/ingest"), SimpleNamespace(), _route("/healthz", ["GET"])]

    assert list(art9.iter_ingest_routes(routes, "digisearch")) == ["/ingest"]
