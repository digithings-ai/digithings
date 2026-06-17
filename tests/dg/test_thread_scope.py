"""REM-025/026: JWT subject thread binding."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from digigraph.thread_scope import (
    assert_thread_access,
    resolve_client_thread_id,
    workflow_thread_id,
)


@pytest.mark.unit
def test_workflow_thread_id_never_uses_default() -> None:
    tid = workflow_thread_id(None, None)
    assert tid != "default"
    assert len(tid) >= 8


@pytest.mark.unit
def test_workflow_thread_id_prefixes_subject() -> None:
    assert workflow_thread_id("user-1", "sess-a") == "user-1:sess-a"


@pytest.mark.unit
def test_assert_thread_access_denies_cross_subject() -> None:
    with pytest.raises(HTTPException) as exc:
        assert_thread_access("alice", "bob:thread-1")
    assert exc.value.status_code == 403


@pytest.mark.unit
def test_resolve_client_thread_id_adds_prefix() -> None:
    assert resolve_client_thread_id("alice", "t1") == "alice:t1"
