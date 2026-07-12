"""DigiVault HTTP API — Obsidian-style vault management for the Digi ecosystem.

Operates on the vault directory named by ``DIGIVAULT_ROOT``. The vault is re-read
from disk on each request (a documentation vault is small and correctness beats
caching), so there is no index to fall out of sync.
"""

from __future__ import annotations

import logging
import os
import time as _time
from collections import deque as _deque
from threading import Lock as _Lock
from typing import Any  # noqa: ANN401 — frontmatter / orchestrator argument maps are arbitrary

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
from digivault.models import LintReport, Note
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
    title="DigiVault",
    description="Obsidian-style markdown vault management (frontmatter, wikilinks, backlinks, tags).",
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
    """Build the Supabase-backed store for full-text search (independent of DIGIVAULT_ROOT)."""
    try:
        return SupabaseStore.from_env()
    except SupabaseStoreError as exc:
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


class SetFrontmatterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: dict[str, Any] = Field(..., description="Frontmatter keys to merge")


class RenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_name: str = Field(..., min_length=1)


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


@app.get("/v1/notes/{name}", response_model=Note)
def get_note(name: str) -> Note:
    note = _open_vault().get_note(name)
    if note is None:
        raise HTTPException(status_code=404, detail=f"No such note: {name!r}")
    return note


@app.post("/v1/notes", response_model=Note, status_code=201)
def create_note(req: CreateNoteRequest) -> Note:
    fm: dict[str, Any] = {}
    if req.title:
        fm["title"] = req.title
    if req.tags:
        fm["tags"] = req.tags
    try:
        return _open_vault().create_note(req.name, frontmatter=fm, body=req.body, subdir=req.subdir)
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
    """Return OpenAI-style tool definitions owned by DigiVault (for DigiGraph)."""
    return OrchestratorToolsResponse(tools=build_orchestrator_tool_manifest())


@app.post("/v1/orchestrator_invoke", response_model=OrchestratorInvokeResponse)
def orchestrator_invoke(
    req: OrchestratorInvokeRequest, request: Request
) -> OrchestratorInvokeResponse:
    """Execute one DigiVault orchestrator tool by name (hub dispatch)."""
    tool = (req.tool or "").strip()
    args = req.arguments if isinstance(req.arguments, dict) else {}
    _require_tool_scope(request, tool)

    # Supabase-backed full-text search is independent of DIGIVAULT_ROOT (the local
    # filesystem vault) — it reads the vault mirrored into Postgres instead.
    if tool == TOOL_VAULT_SEARCH_NOTES:
        query = str(args.get("query") or "").strip()
        if not query:
            return OrchestratorInvokeResponse(ok=False, tool=tool, error="query is required")
        try:
            limit = int(args["limit"]) if args.get("limit") else DEFAULT_SEARCH_NOTES_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_SEARCH_NOTES_LIMIT
        limit = max(1, min(limit, _MAX_SEARCH_NOTES_LIMIT))
        hits = _open_supabase_store().search(query, limit=limit)
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
