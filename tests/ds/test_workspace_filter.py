"""Workspace filter enforcement for DigiSearch query paths."""

from __future__ import annotations

import pytest

from digisearch.core.models import Chunk, Query
from digisearch.core.workspace_filter import merge_workspace_filter
from digisearch.search._stub import _stub_index, query_index


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    _stub_index.clear()


@pytest.mark.unit
def test_workspace_filter_excludes_other_tenant_chunks() -> None:
    _stub_index["default"] = [
        Chunk(id="a", content="alpha tenant doc", doc_id="d1", metadata={"workspace_id": "t1"}),
        Chunk(id="b", content="beta tenant doc", doc_id="d2", metadata={"workspace_id": "t2"}),
    ]
    q = Query(
        text="tenant",
        top_k=5,
        filters=merge_workspace_filter({}, "t1"),
        workspace_id="t1",
    )
    resp = query_index(q, index_name="default")
    assert len(resp.results) == 1
    assert resp.results[0].chunk.metadata.get("workspace_id") == "t1"
