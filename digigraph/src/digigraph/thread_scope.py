"""JWT subject binding for LangGraph checkpoint thread IDs (REM-025/026)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from starlette.requests import Request


def auth_subject_from_request(request: Request) -> str | None:
    auth = getattr(request.state, "digi_auth", None)
    if auth is not None:
        sub = getattr(auth, "subject", None)
        if sub and str(sub).strip():
            return str(sub).strip()
    return None


def workflow_thread_id(subject: str | None, session_id: str | None) -> str:
    """Build a checkpoint thread id; never use a shared ``default`` namespace."""
    sid = (session_id or "").strip() or uuid.uuid4().hex
    if not subject:
        return sid
    prefix = f"{subject}:"
    if sid.startswith(prefix):
        return sid
    return f"{prefix}{sid}"


def resolve_client_thread_id(subject: str | None, thread_id: str) -> str:
    """Normalize a client-supplied thread id to the scoped checkpoint key."""
    tid = (thread_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="thread_id required")
    if not subject:
        return tid
    prefix = f"{subject}:"
    if tid.startswith(prefix):
        return tid
    return f"{prefix}{tid}"


def assert_thread_access(subject: str | None, thread_id: str) -> None:
    """Reject cross-tenant thread reads when JWT subject is present."""
    if not subject:
        return
    prefix = f"{subject}:"
    if not thread_id.startswith(prefix):
        raise HTTPException(
            status_code=403, detail="Thread access denied for authenticated subject"
        )
