"""REM-025/026: JWT subject thread binding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from digigraph.thread_scope import (
    assert_thread_access,
    auth_subject_from_request,
    resolve_client_thread_id,
    workflow_thread_id,
)
from fastapi import HTTPException


@pytest.mark.unit
def test_workflow_thread_id_never_uses_default() -> None:
    tid = workflow_thread_id(None, None)
    assert tid != "default"
    assert len(tid) >= 8


@pytest.mark.unit
def test_workflow_thread_id_prefixes_subject() -> None:
    assert workflow_thread_id("user-1", "sess-a") == "user-1:sess-a"


@pytest.mark.unit
def test_workflow_thread_id_keeps_already_prefixed_session() -> None:
    assert workflow_thread_id("user-1", "user-1:sess-a") == "user-1:sess-a"


@pytest.mark.unit
def test_assert_thread_access_denies_cross_subject() -> None:
    with pytest.raises(HTTPException) as exc:
        assert_thread_access("alice", "bob:thread-1")
    assert exc.value.status_code == 403


@pytest.mark.unit
def test_assert_thread_access_allows_same_subject_and_anonymous() -> None:
    assert_thread_access("alice", "alice:thread-1")
    assert_thread_access(None, "anyone:thread-1")


@pytest.mark.unit
def test_resolve_client_thread_id_adds_prefix() -> None:
    assert resolve_client_thread_id("alice", "t1") == "alice:t1"


@pytest.mark.unit
def test_resolve_client_thread_id_idempotent_when_prefixed() -> None:
    assert resolve_client_thread_id("alice", "alice:t1") == "alice:t1"


@pytest.mark.unit
def test_resolve_client_thread_id_rejects_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        resolve_client_thread_id("alice", "  ")
    assert exc.value.status_code == 400
    assert "thread_id required" in str(exc.value.detail)


@pytest.mark.unit
def test_resolve_client_thread_id_without_subject_passthrough() -> None:
    assert resolve_client_thread_id(None, "raw-tid") == "raw-tid"


@pytest.mark.unit
def test_auth_subject_from_request_reads_digi_auth() -> None:
    req = SimpleNamespace(state=SimpleNamespace(digi_auth=SimpleNamespace(subject="  alice  ")))
    assert auth_subject_from_request(req) == "alice"  # type: ignore[arg-type]


@pytest.mark.unit
def test_auth_subject_from_request_missing_auth() -> None:
    req = SimpleNamespace(state=SimpleNamespace())
    assert auth_subject_from_request(req) is None  # type: ignore[arg-type]
