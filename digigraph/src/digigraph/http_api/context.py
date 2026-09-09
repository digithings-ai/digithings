"""Request → WorkflowRequest digikey field injection and thread config."""

from __future__ import annotations

from fastapi import HTTPException, Request

from digigraph.models import WorkflowRequest
from digigraph.thread_scope import (
    assert_thread_access,
    auth_subject_from_request,
    resolve_client_thread_id,
    workflow_thread_id,
)


def _digi_fields_from_request(http_request: Request) -> dict[str, str | None]:
    from digigraph.corpus_routing import (
        TenantCorpusMapError,
        load_tenant_corpus_map,
        resolve_corpus_override,
    )

    bearer = getattr(http_request.state, "digi_bearer", None)
    auth = getattr(http_request.state, "digi_auth", None)
    updates: dict[str, str | None] = {"digi_bearer": bearer}
    # digi_subject keys the cross-thread Store namespace (supervisor_node,
    # ARCHITECTURE.md §6.10) and, via workflow_thread_id, the checkpoint thread_id — so
    # it must NEVER survive from a client-supplied WorkflowRequest.digi_subject unless
    # backed by verified auth (CWE-639 IDOR). This key must always be present in
    # `updates` (never merely omitted): `req.model_copy(update=updates)` in
    # _with_digi_request_context only clears a field when its key is explicitly present
    # here — an absent key leaves the client's original value untouched. So this is an
    # unconditional assignment, not a conditional override: it sets the verified
    # `auth.subject` when `auth` is present and its `subject` claim is non-empty, and
    # explicitly `None` in every other case — no `auth` object at all, OR an `auth`
    # object present with an empty/falsy `subject` claim. Both are real overrides, not
    # skips, because the key is always present.
    updates["digi_subject"] = auth.subject if (auth is not None and auth.subject) else None
    tenant_from_auth: str | None = None
    if auth is not None:
        if auth.key_prefix:
            updates["digi_trace_key_prefix"] = auth.key_prefix
        if auth.tenant_slug:
            updates["digi_trace_tenant"] = auth.tenant_slug
            tenant_from_auth = auth.tenant_slug
        if auth.project_id:
            updates["digi_trace_project_id"] = auth.project_id
        if auth.jti:
            updates["digi_trace_jti"] = auth.jti
    # Mirror digivault tenant_scope: set-but-broken DIGI_TENANT_CORPUS_MAP is 503,
    # never silently treated as unset (which would re-enable client corpus headers).
    try:
        corpus_map = load_tenant_corpus_map()
    except TenantCorpusMapError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    corpus = resolve_corpus_override(
        headers=http_request.headers,
        tenant_slug=tenant_from_auth,
        corpus_map=corpus_map,
    )
    # Same CWE-639 class as digi_subject: when DIGI_TENANT_CORPUS_MAP is configured,
    # digisearch_index / vault_path_prefix / research_system_prompt_override must be
    # written unconditionally so a client body value cannot survive into graph state
    # (digisearch has no server-side tenant→index bind; digivault does for prefixes).
    if corpus_map:
        updates["digisearch_index"] = corpus.digisearch_index
        updates["vault_path_prefix"] = corpus.vault_path_prefix
        updates["research_system_prompt_override"] = corpus.research_system_prompt
    else:
        if corpus.digisearch_index:
            updates["digisearch_index"] = corpus.digisearch_index
        if corpus.vault_path_prefix:
            updates["vault_path_prefix"] = corpus.vault_path_prefix
        if corpus.research_system_prompt:
            updates["research_system_prompt_override"] = corpus.research_system_prompt
    # Per-request response language (X-Digi-Language) — a per-request signal, not a
    # tenant-derived value, so it's read directly rather than via resolve_corpus_override.
    # Never interpolated into a prompt (resolve_language_directive only ever emits
    # mapped display names for curated 2-char codes), but capped defensively before
    # it reaches WorkflowRequest/checkpointed state — an arbitrarily long header value
    # has no business sitting in checkpoint storage. Curated codes are 2 characters,
    # so 16 is generous headroom, not a functional constraint.
    lang = http_request.headers.get("x-digi-language")
    if lang and lang.strip():
        updates["response_language"] = lang.strip().lower()[:16]
    from digigraph.retrieval import resolve_force_tool

    force_raw = http_request.headers.get("x-digi-force-tool")
    resolved_force = resolve_force_tool(force_raw)
    if resolved_force:
        updates["force_tool"] = resolved_force
    return updates


def _with_digi_request_context(http_request: Request, req: WorkflowRequest) -> WorkflowRequest:
    updates = _digi_fields_from_request(http_request)
    subject = updates.get("digi_subject")
    if subject:
        updates["session_id"] = workflow_thread_id(subject, req.session_id)
    return req.model_copy(update=updates)


def _thread_config(http_request: Request, thread_id: str) -> dict:
    subject = auth_subject_from_request(http_request)
    scoped = resolve_client_thread_id(subject, thread_id)
    assert_thread_access(subject, scoped)
    return {"configurable": {"thread_id": scoped}}
