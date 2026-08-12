"""digivault HTTP API — Obsidian-style vault management for the Digi ecosystem.

Operates on the vault directory named by ``DIGIVAULT_ROOT``. The vault is re-read
from disk on each request (a documentation vault is small and correctness beats
caching), so there is no index to fall out of sync.
"""

from __future__ import annotations

import json
import logging
import os
import time as _time
from collections import deque as _deque
from threading import Lock as _Lock
from typing import (
    Any,  # score:allow untyped any — frontmatter / orchestrator argument maps are arbitrary
)

from digibase.cors import install_cors
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware
from digikey.scopes import scope_grants_required
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from digivault import __version__
from digivault.d1_errors import D1StoreError
from digivault.d1_store import D1Store, normalize_vault_path, resolve_path_prefix
from digivault.local_search import search_local_vault
from digivault.models import LintReport, Note, NoteDetail
from digivault.orchestrator_tools import (
    DEFAULT_SEARCH_NOTES_LIMIT,
    TOOL_VAULT_BACKLINKS,
    TOOL_VAULT_CREATE_NOTE,
    TOOL_VAULT_LINT,
    TOOL_VAULT_SEARCH_NOTES,
    TOOL_VAULT_SEARCH_TAG,
    OpenAIToolDict,
    build_orchestrator_tool_manifest,
)
from digivault.path_scopes import SCOPE_WRITE, digivault_path_scopes
from digivault.supabase_store import SupabaseStore, SupabaseStoreError
from digivault.vault import Vault, VaultError

# /v1/orchestrator_invoke is gated at SCOPE_READ (most tools are reads); the one
# mutating tool enforces SCOPE_WRITE here so a read-only caller can't reach it.
_TOOL_WRITE_SCOPES: dict[str, str] = {TOOL_VAULT_CREATE_NOTE: SCOPE_WRITE}
_MAX_SEARCH_NOTES_LIMIT = 50

logger = logging.getLogger(__name__)

app = FastAPI(
    title="digivault",
    description=(
        "Obsidian-style markdown vault management for digithings "
        "(frontmatter, wikilinks, backlinks, tags, lint). "
        "Interactive docs: `/docs` (Swagger) and `/redoc`."
    ),
    version=__version__,
)
install_metrics(app, service="digivault", version=__version__)
install_cors(app, service="digivault")
app.add_middleware(DigiAuthMiddleware, service="digivault", path_scopes=digivault_path_scopes)

# ── rate limiting (per-IP sliding window; mirrors digisearch/server.py) ──────
_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/v1/orchestrator_tools": (30, 60),
    "/v1/orchestrator_invoke": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/healthz"}


def _rl_check(request: Request, max_req: int, window: int) -> JSONResponse | None:
    if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return None
    xff = request.headers.get("X-Forwarded-For")
    ip = (
        xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    )
    if ip == "testclient":
        return None
    now = _time.monotonic()
    cutoff = now - window
    with _rl_lock:
        if ip not in _rl_windows:
            _rl_windows[ip] = _deque()
        q = _rl_windows[ip]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_req:
            return json_error_response(
                status_code=429,
                code="rate_limit_exceeded",
                message=f"Rate limit exceeded: {max_req} requests per {window}s.",
                request=request,
                service="digivault",
                headers={"Retry-After": str(window)},
            )
        q.append(now)
    return None


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP rate limiting. orchestrator_invoke: 10/min; others: 30/min."""
    path = request.url.path
    if path not in _UNLIMITED_PATHS:
        max_req, window = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        result = _rl_check(request, max_req, window)
        if result is not None:
            return result
    return await call_next(request)


install_request_id_middleware(app)
install_request_id_logging()


def _vault_root() -> str:
    root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
    if not root:
        raise HTTPException(status_code=503, detail="DIGIVAULT_ROOT is not configured")
    return root


def _open_vault() -> Vault:
    try:
        return Vault(_vault_root())
    except VaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _open_supabase_store() -> SupabaseStore:
    """Build the Supabase-backed store for FTS when DIGIVAULT_ROOT is unset."""
    try:
        return SupabaseStore.from_env()
    except SupabaseStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _d1_configured() -> bool:
    """True when D1 credentials and a database map are all present in the environment.

    Env is read here, at the call site — never inside ``D1Store``, whose constructor
    takes credentials as plain arguments (same convention as ``_open_supabase_store``
    reading Supabase env only in ``SupabaseStore.from_env``).
    """
    return bool(
        (os.environ.get("D1_ACCOUNT_ID") or "").strip()
        and (os.environ.get("D1_API_TOKEN") or "").strip()
        and (os.environ.get("D1_DATABASE_MAP") or "").strip()
    )


def _load_d1_database_map() -> tuple[dict[str, Any], str, str]:
    """Parse and validate ``D1_DATABASE_MAP`` (and the D1 credentials) from the
    environment: JSON well-formedness, object shape, and the "" key guard.

    Split out of ``_open_d1_store`` so this validation runs as its own step,
    independent of any particular ``path_prefix``. ``orchestrator_invoke``'s search
    branch calls this *before* deciding whether the caller even supplied a
    ``path_prefix`` — otherwise a malformed ``D1_DATABASE_MAP`` (bad JSON, wrong
    shape, a forbidden ``""`` key) raised while ``path_prefix`` happens to be ``None``
    was indistinguishable from the ordinary "no path_prefix" case one level up, so
    every one of those distinct config errors collapsed into the same caller-blaming
    400 instead of its own 503 (#2239 review).
    """
    account_id = (os.environ.get("D1_ACCOUNT_ID") or "").strip()
    api_token = (os.environ.get("D1_API_TOKEN") or "").strip()
    raw_map = (os.environ.get("D1_DATABASE_MAP") or "").strip()
    if not account_id or not api_token or not raw_map:
        raise D1StoreError(
            "D1 not configured: set D1_ACCOUNT_ID, D1_API_TOKEN and D1_DATABASE_MAP."
        )
    try:
        database_map = json.loads(raw_map)
    except ValueError as exc:
        raise D1StoreError("D1_DATABASE_MAP is not valid JSON") from exc
    if not isinstance(database_map, dict):
        raise D1StoreError("D1_DATABASE_MAP must be a JSON object of prefix -> database id")
    # Refuse an empty-string key outright, at config-read time, rather than let an
    # operator "fix" the unscoped-search error (see the caller-side handling in
    # orchestrator_invoke below) by adding one. A "" entry would map every prefix
    # that normalizes to empty — None, "", "/", "///", "   ", ".md" — to a real
    # database, arming the exact cross-tenant fail-open the by-path route's
    # `resolve_path_prefix` check (and this function's own callers) are built to
    # refuse. Fail loudly here instead of silently accepting the config that makes
    # it possible (#2239 review).
    if "" in database_map:
        raise D1StoreError(
            "D1_DATABASE_MAP must not map the empty string '' to a database id: doing "
            "so lets any prefix that normalizes to empty resolve to a real corpus, "
            "which turns 'no path_prefix was scoped' into an unscoped cross-tenant "
            "read. Configure a real per-tenant prefix for every entry instead."
        )
    return database_map, account_id, api_token


def _open_d1_store(path_prefix: str | None) -> D1Store:
    """Build a D1Store for the corpus owning ``path_prefix``.

    Each corpus is a separate D1 database (``D1_DATABASE_MAP`` maps a vault prefix to
    a database id), so tenant isolation is structural: a caller scoped to one prefix
    cannot even address another corpus's database, let alone its rows.

    Raises ``D1StoreError`` — not ``HTTPException`` — so this stays a plain, directly
    testable function. The by-path route goes through :func:`_open_d1_store_or_503` to
    convert that into a 503; the search branch in ``orchestrator_invoke`` calls this
    directly because it must also catch a ``D1StoreError`` raised by the subsequent
    ``.search()`` call, not just by this construction step (see its own try/except).
    """
    database_map, account_id, api_token = _load_d1_database_map()
    prefix = normalize_vault_path(path_prefix or "")
    database_id = database_map.get(prefix)
    if not database_id:
        raise D1StoreError(f"no D1 database configured for vault prefix {prefix!r}")
    return D1Store(str(database_id), account_id=account_id, api_token=api_token)


def _open_d1_store_or_503(path_prefix: str | None) -> D1Store:
    """``_open_d1_store``, converting a config failure into HTTP 503 for request handlers."""
    try:
        return _open_d1_store(path_prefix)
    except D1StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _require_tool_scope(request: Request, tool: str) -> None:
    """Enforce SCOPE_WRITE for mutating tools dispatched via /v1/orchestrator_invoke.

    The route itself only requires SCOPE_READ (most tools are reads); this closes
    the gap for the one tool (create_note) that mutates the vault.
    """
    required = _TOOL_WRITE_SCOPES.get(tool)
    if required is None:
        return
    auth = request.state.digi_auth
    if not scope_grants_required(auth.scopes, [required]):
        raise HTTPException(
            status_code=403,
            detail=f"insufficient_scope: {required} required for {tool!r}",
        )


# ── request/response models ────────────────────────────────────────────────
class CreateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="New note name (filename stem)")
    title: str | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    body: str = Field(default="")
    subdir: str = Field(default="", description="Optional subfolder under the vault root")
    overwrite: bool = Field(
        default=False,
        description="When true, upsert via Vault.write_note(overwrite=True) for idempotent ingest",
    )
    frontmatter: dict[str, Any] | None = Field(
        default=None,
        description="Optional extra frontmatter keys merged with title/tags",
    )


class SetFrontmatterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: dict[str, Any] = Field(..., description="Frontmatter keys to merge")


class RenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_name: str = Field(..., min_length=1)


class NoteByPathRequest(BaseModel):
    """Body for ``POST /v1/notes/by-path``: fetch one note whole by its exact vault path."""

    model_config = ConfigDict(extra="forbid")

    vault_path: str = Field(..., min_length=1, description="Exact vault_path to fetch")
    path_prefix: str = Field(
        ...,
        description=(
            "Enforced authorization boundary: vault_path must equal or fall under this "
            "prefix, or the request is rejected with 403. Required — D1_DATABASE_MAP may "
            'never carry a "" entry (see `_load_d1_database_map`\'s guard), so an '
            "omitted path_prefix can never resolve to a corpus and would only ever 503 "
            "at request time; rejected here instead, at the schema boundary (422)."
        ),
    )


class NoteList(BaseModel):
    notes: list[Note]


class BacklinksResponse(BaseModel):
    name: str
    backlinks: list[str]


class OrchestratorToolsResponse(BaseModel):
    tools: list[OpenAIToolDict]
    version: int = 1


class OrchestratorInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class OrchestratorInvokeResponse(BaseModel):
    ok: bool
    service: str = "digivault"
    tool: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None


# ── health / status ────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, secret-free, no downstream checks."""
    return {"ok": True}


@app.get("/v1/status")
def status() -> dict[str, Any]:
    """Operator diagnostic. Reports config presence only — never secrets."""
    return {
        "service": "digivault",
        "version": __version__,
        "vault_configured": bool((os.environ.get("DIGIVAULT_ROOT") or "").strip()),
    }


# ── note routes ────────────────────────────────────────────────────────────
@app.get("/v1/notes", response_model=NoteList)
def list_notes() -> NoteList:
    """List every note in the vault with its tags, links, and backlinks."""
    return NoteList(notes=_open_vault().list_notes())


# Literal path registered ahead of the `{name}` routes below — POST already makes it
# unambiguous (no GET/POST collision exists for "/v1/notes/{name}"), but a literal
# route is kept ahead of a parametrized one on principle, and a test
# (test_by_path_route_is_not_shadowed_by_the_name_route) pins that both resolve
# correctly regardless of registration order.
@app.post("/v1/notes/by-path", response_model=NoteDetail)
def get_note_by_path(req: NoteByPathRequest) -> NoteDetail:
    """Load one note whole (body + frontmatter), addressed by ``vault_path``. D1-only.

    ``path_prefix`` is an enforced authorization boundary, not an advisory filter: two
    client corpora can share this deployment, and without this check a caller scoped to
    one prefix could read another client's notes just by passing an arbitrary
    ``vault_path``. There is no filesystem/Supabase fallback here — a by-path fetch
    only makes sense against the corpus that owns the path (#2239).

    ``path_prefix`` resolution goes through ``resolve_path_prefix`` (shared with
    ``D1Store.search``/``list_notes``) rather than a local ``prefix and ...`` check —
    a #2239 review found the local check treated "a prefix was given but normalizes
    to empty" (``""``, ``"/"``, ``"///"``, ``"   "``, ``".md"``) the same as "no
    scoping requested," which fails open: with a ``""`` key present in
    ``D1_DATABASE_MAP`` every one of those inputs returned another corpus's note
    body with HTTP 200. ``resolve_path_prefix`` raises for exactly that case, which
    this handler turns into ``400`` — a caller/config error, not a scope this route
    can silently ignore. ``path_prefix`` itself is a required field (``422`` if
    omitted) for the same underlying reason: ``D1_DATABASE_MAP`` may never carry a
    ``""`` entry, so an omitted ``path_prefix`` could never resolve to a corpus and
    would only ever ``503`` at request time — rejected up front instead (#2239 review).
    """
    path = normalize_vault_path(req.vault_path)
    try:
        prefix = resolve_path_prefix(req.path_prefix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if prefix and path != prefix and not path.startswith(prefix + "/"):
        raise HTTPException(status_code=403, detail="vault_path is outside the caller's prefix")
    store = _open_d1_store_or_503(prefix or None)
    try:
        note = store.get_note(path)
    except D1StoreError as exc:
        # `_open_d1_store_or_503` only converts a *construction*-time D1StoreError
        # (bad config, no database for this prefix) into 503 — this call is itself
        # outside that wrapper's try/except, so a runtime failure (transport error,
        # an expired D1_API_TOKEN surfacing as Cloudflare's 403) would otherwise
        # propagate as a raw D1StoreError and become an unhandled 500. See #2239 review.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if note is None:
        raise HTTPException(status_code=404, detail=f"note not found: {path}")
    return note


@app.get("/v1/notes/{name}", response_model=Note)
def get_note(name: str) -> Note:
    note = _open_vault().get_note(name)
    if note is None:
        raise HTTPException(status_code=404, detail=f"No such note: {name!r}")
    return note


@app.post("/v1/notes", response_model=Note, status_code=201)
def create_note(req: CreateNoteRequest) -> Note:
    fm: dict[str, Any] = dict(req.frontmatter or {})
    if req.title:
        fm["title"] = req.title
    if req.tags:
        fm["tags"] = req.tags
    try:
        return _open_vault().write_note(
            req.name,
            frontmatter=fm,
            body=req.body,
            subdir=req.subdir,
            overwrite=req.overwrite,
        )
    except VaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/v1/notes/{name}/frontmatter", response_model=Note)
def set_frontmatter(name: str, req: SetFrontmatterRequest) -> Note:
    try:
        return _open_vault().set_frontmatter(name, req.updates)
    except VaultError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/notes/{name}/rename", response_model=Note)
def rename_note(name: str, req: RenameRequest) -> Note:
    try:
        return _open_vault().rename(name, req.new_name)
    except VaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/notes/{name}/backlinks", response_model=BacklinksResponse)
def get_backlinks(name: str) -> BacklinksResponse:
    vault = _open_vault()
    if vault.get_note(name) is None:
        raise HTTPException(status_code=404, detail=f"No such note: {name!r}")
    return BacklinksResponse(name=name, backlinks=list(vault.backlinks(name)))


@app.get("/v1/tags/{tag}", response_model=NoteList)
def search_by_tag(tag: str) -> NoteList:
    return NoteList(notes=_open_vault().search_by_tag(tag))


@app.get("/v1/lint", response_model=LintReport)
def lint() -> LintReport:
    """Validate the vault: unresolved links, missing frontmatter, orphans, tags."""
    return _open_vault().lint()


# ── orchestrator (hub) ─────────────────────────────────────────────────────
@app.post("/v1/orchestrator_tools", response_model=OrchestratorToolsResponse)
def orchestrator_tools() -> OrchestratorToolsResponse:
    """Return OpenAI-style tool definitions owned by digivault (for digigraph)."""
    return OrchestratorToolsResponse(tools=build_orchestrator_tool_manifest())


@app.post("/v1/orchestrator_invoke", response_model=OrchestratorInvokeResponse)
def orchestrator_invoke(
    req: OrchestratorInvokeRequest, request: Request
) -> OrchestratorInvokeResponse:
    """Execute one digivault orchestrator tool by name (hub dispatch)."""
    tool = (req.tool or "").strip()
    args = req.arguments if isinstance(req.arguments, dict) else {}
    _require_tool_scope(request, tool)

    # Search precedence: D1 when configured (wins even over DIGIVAULT_ROOT — see the
    # branch below); else local filesystem vault when DIGIVAULT_ROOT is set (Profile A
    # / client volumes); else Supabase FTS when credentials exist.
    if tool == TOOL_VAULT_SEARCH_NOTES:
        query = str(args.get("query") or "").strip()
        if not query:
            return OrchestratorInvokeResponse(ok=False, tool=tool, error="query is required")
        try:
            limit = int(args["limit"]) if args.get("limit") else DEFAULT_SEARCH_NOTES_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_SEARCH_NOTES_LIMIT
        limit = max(1, min(limit, _MAX_SEARCH_NOTES_LIMIT))
        path_prefix_raw = args.get("path_prefix")
        path_prefix = (
            str(path_prefix_raw).strip().strip("/") if path_prefix_raw is not None else None
        ) or None

        # D1 first: when the remote corpus is configured it is authoritative, and the
        # baked /data/vault seed must not shadow it (the #2239 production bug — prod
        # sets DIGIVAULT_ROOT to a stub vault that must never win over the real corpus).
        if _d1_configured():
            # Validate D1_DATABASE_MAP's shape (JSON, object, no "" key) unconditionally,
            # before ever looking at path_prefix. A config error here is always a real
            # 503, regardless of what the caller passed — hoisted out of
            # `_open_d1_store`'s per-prefix lookup so a malformed map surfaces as
            # itself, never masked by the (also frequent, #2265) no-path_prefix branch
            # below (#2239 review).
            try:
                _load_d1_database_map()
            except D1StoreError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if path_prefix is None:
                # `digivault_search_notes` fires with no `path_prefix` on every chat
                # turn (`always_retrieve_tools`, #2265) — with D1 configured there is
                # no "search across every corpus" mode (one prefix, one database, by
                # construction), so this is a certainty, not an edge case. `ok=False`
                # (HTTP 200), not a raised 400: digigraph's `invoke_digivault_tool`
                # calls `raise_for_status()`, and `str(httpx.HTTPStatusError)` drops
                # the response body, so a raised 400 here would reach the model as a
                # bare status code instead of this sentence (#2239 review). Mirrors the
                # existing `query is required` convention just above.
                return OrchestratorInvokeResponse(
                    ok=False,
                    tool=tool,
                    error="path_prefix is required when the D1 backend is configured",
                )
            try:
                # Wraps the *call*, not just `_open_d1_store`'s construction — a
                # runtime D1 failure (transport error, an expired D1_API_TOKEN
                # surfacing as Cloudflare's 403) raised from inside `.search()`
                # would otherwise propagate as a raw D1StoreError and become an
                # unhandled 500 (#2239 review).
                hits = _open_d1_store(path_prefix).search(
                    query, limit=limit, path_prefix=path_prefix
                )
            except D1StoreError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        elif (os.environ.get("DIGIVAULT_ROOT") or "").strip():
            hits = search_local_vault(_open_vault(), query, limit=limit, path_prefix=path_prefix)
        else:
            hits = _open_supabase_store().search(query, limit=limit, path_prefix=path_prefix)
        data = {"hits": [h.model_dump(mode="json") for h in hits]}
        return OrchestratorInvokeResponse(ok=True, tool=tool, data=data)

    vault = _open_vault()
    try:
        if tool == TOOL_VAULT_SEARCH_TAG:
            notes = vault.search_by_tag(str(args.get("tag") or ""))
            data = {"notes": [n.model_dump(mode="json") for n in notes]}
        elif tool == TOOL_VAULT_BACKLINKS:
            name = str(args.get("name") or "")
            if vault.get_note(name) is None:
                return OrchestratorInvokeResponse(
                    ok=False, tool=tool, error=f"No such note: {name!r}"
                )
            data = {"name": name, "backlinks": list(vault.backlinks(name))}
        elif tool == TOOL_VAULT_LINT:
            data = vault.lint().model_dump(mode="json")
        elif tool == TOOL_VAULT_CREATE_NOTE:
            fm = {"title": args["title"]} if args.get("title") else {}
            note = vault.create_note(
                str(args["name"]), frontmatter=fm, body=str(args.get("body") or "")
            )
            data = note.model_dump(mode="json")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown orchestrator tool: {tool!r}")
    except VaultError as exc:
        return OrchestratorInvokeResponse(ok=False, tool=tool, error=str(exc))
    except KeyError as exc:
        return OrchestratorInvokeResponse(ok=False, tool=tool, error=f"missing argument: {exc}")
    return OrchestratorInvokeResponse(ok=True, tool=tool, data=data)


register_fastapi_error_handlers(app, service="digivault")
setup_otel_fastapi(app, service_name="digivault")
