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
from collections.abc import Callable
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
    TOOL_VAULT_CREATE_NOTE,
    TOOL_VAULT_GET_NOTE,
    TOOL_VAULT_SEARCH_NOTES,
    OpenAIToolDict,
    build_orchestrator_tool_manifest,
)
from digivault.path_scopes import SCOPE_WRITE, digivault_path_scopes
from digivault.supabase_store import SupabaseStore, SupabaseStoreError, _first_env
from digivault.tenant_scope import enforce_tenant_path_prefix, mapped_tenant_path_prefix
from digivault.tool_dispatch import (
    VAULT_HANDLERS,
    dispatch_vault_tool,
    register_runtime_handler,
)
from digivault.vault import Vault, VaultError

# /v1/orchestrator_invoke is gated at SCOPE_READ (most tools are reads); the one
# mutating tool enforces SCOPE_WRITE here so a read-only caller can't reach it.
_TOOL_WRITE_SCOPES: dict[str, str] = {TOOL_VAULT_CREATE_NOTE: SCOPE_WRITE}
_MAX_SEARCH_NOTES_LIMIT = 50
# Bound digivault_get_note batch size (model-supplied vault_paths). Each path is
# still one serial D1 round-trip today; without a cap a single tool call can
# amplify into unbounded metered reads and a huge serialized payload for the LLM.
_MAX_GET_NOTE_BATCH = 20

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


def _d1_credentials() -> tuple[str, str]:
    """Resolve the account id / API token pair D1 (and Vectorize) share.

    Canonical-first, legacy-fallback precedence (#2239 credential rename): the same
    Cloudflare account and token now authorize both Vectorize and D1, so
    ``CLOUDFLARE_ACCOUNT_ID``/``CLOUDFLARE_API_TOKEN`` (wrangler's own conventional
    names) are read first, falling back to the legacy ``VECTORIZE_*`` then ``D1_*``
    names when the canonical ones are unset. This keeps the rename zero-downtime: the
    deployed Worker's live ``VECTORIZE_ACCOUNT_ID``/``VECTORIZE_API_TOKEN`` secrets
    keep working the moment this ships, with no coordinated secret-rotation required
    before deploy. Reuses ``supabase_store._first_env``'s multi-name lookup shape.
    """
    account_id = _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    api_token = _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    return account_id, api_token


def _d1_configured() -> bool:
    """True when the account id, API token (see ``_d1_credentials``) and
    ``D1_DATABASE_MAP`` are all present; False when none are; raises
    ``D1StoreError`` when only some are — naming exactly which are missing.

    Zero vars set is a legitimate profile (local dev, self-hosted, Profile A) and must
    keep falling through to ``DIGIVAULT_ROOT``/Supabase below. But *some* set and
    *not all* has no legitimate reading — it is unambiguously an operator error (a
    typo'd secret name at cutover, e.g. ``wrangler secret put D1_API_TOKN`` leaving
    ``D1_API_TOKEN`` unset — or, post-rename, a ``CLOUDFLARE_API_TOKN`` typo with no
    legacy fallback set either). Before this guard, partial config made this function
    return ``False`` like the zero-vars case, and callers fell through to
    ``DIGIVAULT_ROOT`` — which production always sets to the baked ``/data/vault``
    seed — so a single missing var silently served seed stubs instead of the real
    corpus, HTTP 200, `ok: true`, nothing logged. That is #2239's precise symptom,
    reachable from exactly the kind of secret-store typo a cutover risks (#2239
    review, Important finding).

    The error names the *canonical* var (``CLOUDFLARE_ACCOUNT_ID``/
    ``CLOUDFLARE_API_TOKEN``), not whichever legacy name happened to be set —
    the credential is resolved to one value per ``_d1_credentials`` before this
    guard ever runs, so "missing" always means "no name in the fallback chain
    resolved," and the message should point the operator at the name to set going
    forward, not at whichever alias they happened to leave unset.

    Env is read here, at the call site — never inside ``D1Store``, whose constructor
    takes credentials as plain arguments (same convention as ``_open_supabase_store``
    reading Supabase env only in ``SupabaseStore.from_env``).
    """
    account_id, api_token = _d1_credentials()
    values = {
        "CLOUDFLARE_ACCOUNT_ID": account_id,
        "CLOUDFLARE_API_TOKEN": api_token,
        "D1_DATABASE_MAP": (os.environ.get("D1_DATABASE_MAP") or "").strip(),
    }
    present = [bool(v) for v in values.values()]
    if any(present) and not all(present):
        missing = ", ".join(name for name, val in values.items() if not val)
        raise D1StoreError(
            f"D1 partially configured: missing {missing}. Set all three of "
            "CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN and D1_DATABASE_MAP, or none of them."
        )
    return all(present)


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
    account_id, api_token = _d1_credentials()
    raw_map = (os.environ.get("D1_DATABASE_MAP") or "").strip()
    if not account_id or not api_token or not raw_map:
        raise D1StoreError(
            "D1 not configured: set CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN "
            "and D1_DATABASE_MAP."
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


def _fetch_note_by_path(
    vault_path: str, path_prefix: str, *, tenant_slug: str | None = None
) -> NoteDetail | None:
    """Enforced by-path fetch shared by ``POST /v1/notes/by-path`` and the
    ``digivault_get_note`` orchestrator tool. ``None`` means "no such note" (a clean,
    recoverable outcome); everything else that can go wrong raises ``HTTPException``.

    Defined once, called from both surfaces, so the authorization boundary — a caller
    scoped to one ``path_prefix`` cannot read another corpus's notes by guessing a
    ``vault_path`` — cannot drift between them. Duplicating this check per call site is
    exactly the kind of thing a #2239-style review keeps finding reimplemented (and
    wrong) at the second location; see ``resolve_path_prefix``'s own docstring for the
    precedent (the by-path route used to reimplement its semantics with a plain ``if
    prefix and ...`` check that failed open).

    ``path_prefix`` is a required ``str`` here, not ``str | None`` — the caller decides
    what "no prefix supplied" means for its own surface (a required pydantic field for
    the route; an explicit ok=False refusal, never an unscoped read, for the
    orchestrator tool) before ever reaching this function.

    ``tenant_slug`` (from the caller's verified ``request.state.digi_auth``, see
    ``_tenant_slug``) is checked against ``path_prefix`` via
    ``enforce_tenant_path_prefix`` *before* the vault_path/prefix containment check
    below — a caller must be entitled to the prefix it named at all before whether a
    specific path falls under it is even relevant. This is the second, independent
    enforcement point CodeRabbit's review of PR #2293 found missing: the boundary
    above only proves ``vault_path`` matches whatever ``path_prefix`` the *same
    request* supplied, never that the caller was entitled to name that prefix in the
    first place. digigraph's own #2265 fix, once merged, will independently protect
    the model -> digigraph leg — but as of this function's own PR (#2298), that fix
    has not yet landed on ``develop``, so this function is currently the *only*
    enforcement point for a caller going through digigraph too, not merely a backstop
    for a caller bypassing it. ``tenant_slug`` itself is only as trustworthy as
    ``digi_auth`` makes it — see ``tenant_scope.py``'s module docstring for a known,
    tracked residual dependency on that.
    """
    path = normalize_vault_path(vault_path)
    try:
        prefix = resolve_path_prefix(path_prefix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enforce_tenant_path_prefix(tenant_slug, prefix)
    if prefix and path != prefix and not path.startswith(prefix + "/"):
        raise HTTPException(status_code=403, detail="vault_path is outside the caller's prefix")
    store = _open_d1_store_or_503(prefix or None)
    try:
        return store.get_note(path)
    except D1StoreError as exc:
        # Runtime failure inside the store call itself (transport error, an expired
        # CLOUDFLARE_API_TOKEN surfacing as Cloudflare's 403) — `_open_d1_store_or_503`
        # only converts a *construction*-time D1StoreError into 503, not this call.
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


def _tenant_slug(request: Request) -> str | None:
    """The authenticated caller's tenant, from the same verified claim
    ``_require_tool_scope`` reads ``.scopes`` off of. ``None`` for a request with no
    ``digi_auth`` at all (shouldn't happen past ``DigiAuthMiddleware`` in production,
    but this stays defensive rather than raising) or an auth context with no
    ``tenant_slug`` populated."""
    auth = getattr(request.state, "digi_auth", None)
    return getattr(auth, "tenant_slug", None) if auth is not None else None


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
    try:
        d1_configured = _d1_configured()
    except D1StoreError:
        # Partial D1 config (some but not all of the three vars set) isn't a working
        # backend either way, and this diagnostic route must never itself 503 — that
        # would defeat the point of letting an operator see backend state without
        # asking the chat a question (#2239 review).
        d1_configured = False
    return {
        "service": "digivault",
        "version": __version__,
        "vault_configured": bool((os.environ.get("DIGIVAULT_ROOT") or "").strip()),
        "d1_configured": d1_configured,
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
@app.post(
    "/v1/notes/by-path",
    response_model=NoteDetail,
    responses={
        400: {"description": "path_prefix normalizes to an empty prefix (e.g. '/', '.md')"},
        403: {"description": "vault_path is outside the caller's path_prefix"},
        404: {"description": "no note at that vault_path in the resolved corpus"},
        503: {"description": "D1 misconfigured, no database for the prefix, or a D1 failure"},
    },
)
def get_note_by_path(req: NoteByPathRequest, request: Request) -> NoteDetail:
    """Load one note whole (body + frontmatter), addressed by ``vault_path``. D1-only.

    ``path_prefix`` is an enforced authorization boundary, not an advisory filter: two
    client corpora can share this deployment, and without this check a caller scoped to
    one prefix could read another client's notes just by passing an arbitrary
    ``vault_path``. There is no filesystem/Supabase fallback here — a by-path fetch
    only makes sense against the corpus that owns the path (#2239).

    ``path_prefix`` itself is also now checked against the caller's authenticated
    tenant (``_fetch_note_by_path``'s ``tenant_slug`` param) when
    ``DIGI_TENANT_CORPUS_MAP`` is configured — closing the gap where ``digivault:read``
    alone let any caller name *any* prefix, not just their own corpus's (found in
    CodeRabbit's review of PR #2293; see ``tenant_scope.py``).

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

    The authorization check itself (prefix resolution, the 403 boundary, opening and
    querying the store) lives in ``_fetch_note_by_path`` — shared with the
    ``digivault_get_note`` orchestrator tool dispatched from ``orchestrator_invoke``
    below, so both surfaces enforce the same boundary from one place (#2239).
    """
    note = _fetch_note_by_path(req.vault_path, req.path_prefix, tenant_slug=_tenant_slug(request))
    if note is None:
        raise HTTPException(
            status_code=404, detail=f"note not found: {normalize_vault_path(req.vault_path)}"
        )
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
        # Same empty-normalizing set as digivault_get_note / resolve_path_prefix
        # (including ".md") — bare strip("/").strip() left ".md" as a non-None
        # prefix that D1Store.search rejects with ValueError (#2327 CodeRabbit).
        # A *present* prefix that normalizes to empty is a caller bug, not a request
        # to search everything. The earlier `... or None` collapsed both cases into
        # "no prefix", which meant "/", "   ", "///" and ".md" silently disabled
        # scoping on every backend — the #2359 fail-open, which the local_search
        # hardening alone did not close because the collapse happens here, before
        # `resolve_path_prefix` ever sees the value. 400 instead; pass no
        # path_prefix at all (or null) to opt out deliberately.
        if path_prefix_raw is None:
            path_prefix = None
        else:
            path_prefix = normalize_vault_path(str(path_prefix_raw))
            if not path_prefix:
                # Match digivault_get_note: ok=False (HTTP 200), not a raised 400.
                # digigraph's invoke_digivault_tool calls raise_for_status(), which
                # drops the response body on a 400 — the model would see only a bare
                # status code (#2408 / #2410 follow-up).
                return OrchestratorInvokeResponse(
                    ok=False,
                    tool=tool,
                    error=(
                        "path_prefix was provided but normalizes to empty; "
                        "omit it entirely to search without a prefix"
                    ),
                )

        tenant_slug = _tenant_slug(request)
        # When DIGI_TENANT_CORPUS_MAP is set, an omitted path_prefix must not fall
        # through to local-vault / Supabase as an unfiltered search (authz bypass
        # for multi-tenant deployments without D1). Resolve the caller's mapped
        # prefix before backend selection (#2327 CodeRabbit).
        if path_prefix is None:
            mapped = mapped_tenant_path_prefix(tenant_slug)
            if mapped is not None:
                path_prefix = mapped

        # Security (CodeRabbit review of PR #2293, and its own follow-up review of PR
        # #2298): checked once, here, before the backend-precedence branch below, so
        # it applies uniformly to D1, local-vault, and Supabase — not just whichever
        # backend happens to be configured today. `path_prefix` reaching this point is
        # caller/model-supplied (or tenant-map-resolved above); a caller hitting this
        # endpoint directly with a bare `digivault:read` token has never been protected
        # by anything digigraph does (its own #2265 fix only covers the model ->
        # digigraph leg — see tenant_scope.py). No-op when `path_prefix` is still
        # `None` (map unset; each backend's own "prefix required" handling still
        # applies) or when `DIGI_TENANT_CORPUS_MAP` is unset.
        enforce_tenant_path_prefix(tenant_slug, path_prefix)

        # D1 first: when the remote corpus is configured it is authoritative, and the
        # baked /data/vault seed must not shadow it (the #2239 production bug — prod
        # sets DIGIVAULT_ROOT to a stub vault that must never win over the real corpus).
        # `_d1_configured` itself raises D1StoreError for a partial config (some but
        # not all of the three vars set) — that must become a loud 503 here, never a
        # silent fall-through to the `elif DIGIVAULT_ROOT` branch below (#2239 review,
        # Important finding).
        try:
            d1_is_configured = _d1_configured()
        except D1StoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if d1_is_configured:
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
                # Reached only when the caller has no mapped tenant corpus: digigraph's
                # `_handle_digivault_search` (builtin.py) now overwrites `path_prefix`
                # from `ToolContext.vault_path_prefix` unconditionally before invoking
                # (#2265, closed on the digigraph side by #2240), so this is no longer
                # "every chat turn" — it is reached only for an unmapped tenant slug,
                # the same as the analogous branch in `digivault_get_note` below. With
                # D1 configured there is no "search across every corpus" mode (one
                # prefix, one database, by construction), so this branch still refuses
                # rather than falling back to an unscoped read. `ok=False` (HTTP 200),
                # not a raised 400: digigraph's `invoke_digivault_tool` calls
                # `raise_for_status()`, and `str(httpx.HTTPStatusError)` drops
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
                # runtime D1 failure (transport error, an expired CLOUDFLARE_API_TOKEN
                # surfacing as Cloudflare's 403) raised from inside `.search()`
                # would otherwise propagate as a raw D1StoreError and become an
                # unhandled 500 (#2239 review).
                hits = _open_d1_store(path_prefix).search(
                    query, limit=limit, path_prefix=path_prefix
                )
            except D1StoreError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        elif (os.environ.get("DIGIVAULT_ROOT") or "").strip():
            try:
                hits = search_local_vault(
                    _open_vault(), query, limit=limit, path_prefix=path_prefix
                )
            except ValueError as exc:
                # `resolve_path_prefix` rejects a non-None prefix that normalizes
                # to empty ("/", "   ", "///", ".md") rather than failing open and
                # searching the whole root. That is a caller bug, so 400 — not the
                # 500 an unhandled ValueError would otherwise produce.
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            hits = _open_supabase_store().search(query, limit=limit, path_prefix=path_prefix)
        data = {"hits": [h.model_dump(mode="json") for h in hits]}
        return OrchestratorInvokeResponse(ok=True, tool=tool, data=data)

    if tool == TOOL_VAULT_GET_NOTE:
        # D1-only, same as `POST /v1/notes/by-path` — a by-path fetch only makes sense
        # against the corpus that owns the path, so there is no local-vault/Supabase
        # fallback here (mirrors that route's own docstring).
        #
        # Batch support (#2306 follow-up): a model that already knows several pages of
        # one document up front (e.g. from parent_doc/segment_label hints on a search
        # hit) previously had to issue one digivault_get_note call per page, each
        # rendering as its own activity row in digichat with no way to group them (the
        # UI groups repeated tool calls by (toolName, query), and every path is a
        # different query). vault_paths is additive: an existing caller sending the
        # singular vault_path gets byte-identical behaviour and response shape below;
        # only a caller that sends vault_paths (plural) gets the new {"notes":
        # [...], "errors": {...}} shape. This is a "first cut" — each path still costs
        # its own D1 round-trip via the loop below (_fetch_note_by_path, called once
        # per path, preserving its per-path tenant-scope enforcement exactly). A real
        # round-trip reduction would need D1Store to grow a batched
        # `WHERE vault_path IN (...)` fetch; deferred as a fast-follow since it is not
        # required to fix the UI-clutter/grouping problem this change targets.
        vault_paths_arg = args.get("vault_paths")
        is_batch = isinstance(vault_paths_arg, list) and len(vault_paths_arg) > 0
        if is_batch:
            # Dedup while preserving order — a model that lists the same page twice
            # (e.g. copy-paste across two search hits) should not pay for it twice.
            # Key on normalize_vault_path so "a/b" and "a/b.md" (or trailing slash)
            # collapse to one fetch; keep the first raw form for the downstream call.
            seen: set[str] = set()
            vault_path_list: list[str] = []
            for raw_path in vault_paths_arg:
                p = str(raw_path or "").strip()
                if not p:
                    continue
                key = normalize_vault_path(p) or p
                if key not in seen:
                    seen.add(key)
                    vault_path_list.append(p)
            if not vault_path_list:
                return OrchestratorInvokeResponse(
                    ok=False, tool=tool, error="vault_paths must contain at least one path"
                )
            if len(vault_path_list) > _MAX_GET_NOTE_BATCH:
                return OrchestratorInvokeResponse(
                    ok=False,
                    tool=tool,
                    error=(
                        f"vault_paths exceeds maximum batch size of {_MAX_GET_NOTE_BATCH} "
                        f"(got {len(vault_path_list)} after dedup)"
                    ),
                )
        else:
            vault_path = str(args.get("vault_path") or "").strip()
            if not vault_path:
                return OrchestratorInvokeResponse(
                    ok=False, tool=tool, error="vault_path is required"
                )
            vault_path_list = [vault_path]
        path_prefix_arg = args.get("path_prefix")
        # Normalize before deciding "missing" — `vault_path` two lines up already
        # treats a blank value the same as an absent key (`str(... or "").strip()`);
        # `path_prefix` must follow the same convention rather than only checking
        # `is None`. A caller/model that sends "", "/", "   ", or ".md" is not
        # supplying a real scope any more than one that omits the key outright, but
        # unlike `None` those values survive an `is None` check and fall through to
        # `_fetch_note_by_path`, whose `resolve_path_prefix` call raises `ValueError`
        # for exactly this "present but normalizes to empty" case (wrapped there as
        # `HTTPException(400)`). A raised 400 reaches the model only as a bare
        # "Client error '400 Bad Request'" — `raise_for_status()` drops the response
        # body on digigraph's side — so every input that resolves to "no real prefix"
        # must produce the same readable `ok=False` the fully-omitted case already
        # gets below, not a mid-request exception (#2239 review).
        normalized_prefix = (
            normalize_vault_path(str(path_prefix_arg)) if path_prefix_arg is not None else ""
        )
        if not normalized_prefix:
            # digigraph's `_handle_digivault_get_note` (builtin.py:~300) now injects
            # the caller's tenant context here too, the same as
            # `_handle_digivault_search` (builtin.py:~252) does for
            # `digivault_search_notes` — both overwrite `path_prefix` from
            # `ToolContext.vault_path_prefix` unconditionally (#2265, closed on the
            # digigraph side by #2240). So this branch is no longer "absent on every
            # real call": it is reached only when the session has no mapped tenant
            # (an unmapped corpus slug), in which case digigraph passes `None`
            # through rather than inventing a prefix. `resolve_path_prefix(None)`
            # treats a missing prefix as "no scoping requested" (by design, for
            # callers that legitimately want that) — silently taking that path here
            # would turn "no tenant is mapped for this session" into an unscoped
            # cross-tenant read, exactly the fail-open the by-path route's required
            # `path_prefix` field exists to close. Refuse instead, `ok=False` (not a
            # raised 400): digigraph's `invoke_digivault_tool` calls
            # `raise_for_status()`, and `str(httpx.HTTPStatusError)` drops the
            # response body, so a raised 400 would reach the model as a bare status
            # code rather than this sentence — same reasoning as the
            # `digivault_search_notes` D1 branch above (#2239).
            return OrchestratorInvokeResponse(
                ok=False,
                tool=tool,
                error="path_prefix is required for digivault_get_note",
            )
        tenant_slug = _tenant_slug(request)
        if not is_batch:
            # Single-path caller: response shape byte-identical to before this change.
            note = _fetch_note_by_path(
                vault_path_list[0], normalized_prefix, tenant_slug=tenant_slug
            )
            if note is None:
                # A stale or mistyped vault_path is an expected, recoverable outcome
                # (the model should try a different path or re-search), not a tool
                # failure — mirrors the `digivault_backlinks` "No such note" convention
                # below.
                return OrchestratorInvokeResponse(
                    ok=False,
                    tool=tool,
                    error=f"note not found: {normalize_vault_path(vault_path_list[0])}",
                )
            return OrchestratorInvokeResponse(ok=True, tool=tool, data=note.model_dump(mode="json"))

        # Batch caller: fetch each path with the SAME per-path enforcement as the
        # single-path case (looped, not hoisted out) — a batch must not be a way to
        # bypass the #2265/#2239/#2298 tenant-scope checks for any one of its paths.
        # One bad path (not found, outside the prefix, or a transient D1 error) does
        # not fail the whole call: a model that requested 6 pages and gets 5 back plus
        # one clear per-path error can still answer from the 5, which is strictly more
        # useful than discarding all 5 because the 6th failed.
        notes: list[dict[str, object]] = []
        errors: dict[str, str] = {}
        for path in vault_path_list:
            try:
                note = _fetch_note_by_path(path, normalized_prefix, tenant_slug=tenant_slug)
            except HTTPException as exc:
                errors[normalize_vault_path(path)] = str(exc.detail)
                continue
            if note is None:
                errors[normalize_vault_path(path)] = f"note not found: {normalize_vault_path(path)}"
                continue
            notes.append(note.model_dump(mode="json"))
        # ok=True even with zero notes and all errors: this is the model's own input
        # (every path in the batch happened to be wrong), not an infra failure — the
        # per-path errors dict already carries the reason for each, which is more
        # actionable than a single ok=False covering an N-path call.
        return OrchestratorInvokeResponse(
            ok=True, tool=tool, data={"notes": notes, "errors": errors}
        )

    vault = _open_vault()
    if tool not in VAULT_HANDLERS:
        raise HTTPException(status_code=400, detail=f"Unknown orchestrator tool: {tool!r}")
    result = dispatch_vault_tool(tool, args, vault)
    if not result.ok:
        return OrchestratorInvokeResponse(ok=False, tool=tool, error=result.error)
    return OrchestratorInvokeResponse(ok=True, tool=tool, data=result.data)


# Claim runtime-only tools on the canonical dispatch table so
# ``dispatch_tool_names()`` equals ``DISPATCH_TOOL_NAMES`` once the HTTP app is
# loaded. Bodies stay in ``orchestrator_invoke`` above (D1 / tenant / HTTPException);
# registration is the name-set contract tests assert against — do not add a second
# handler table here.
def _runtime_tool_claimed(name: str) -> Callable[..., None]:
    def _claimed(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(f"{name} is dispatched via orchestrator_invoke, not this handle")

    _claimed.__name__ = f"_claimed_{name}"
    _claimed.__doc__ = f"Runtime claim marker for {name}."
    return _claimed


register_runtime_handler(TOOL_VAULT_SEARCH_NOTES, _runtime_tool_claimed(TOOL_VAULT_SEARCH_NOTES))
register_runtime_handler(TOOL_VAULT_GET_NOTE, _runtime_tool_claimed(TOOL_VAULT_GET_NOTE))

register_fastapi_error_handlers(app, service="digivault")
setup_otel_fastapi(app, service_name="digivault")
