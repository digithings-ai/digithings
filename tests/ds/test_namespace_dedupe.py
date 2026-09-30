"""Unit tests for cross-namespace result dedupe (#4823).

A serving index can hold the same vault content under two path namespaces
(live paths plus tenant-prefixed copies, e.g. ``clients/digithings/...``)
because vector IDs are path-derived: a re-sync under a new prefix adds
copies instead of overwriting. ``dedupe_namespace_copies`` collapses such
twin entries on exact full-body equality plus suffix-related paths, so one
query result never cites the same content twice.
"""

from __future__ import annotations

import pytest
from digisearch.search.namespace_dedupe import dedupe_namespace_copies


def _entry(path: str, *, content: str = "body text", url: str | None = None) -> dict:
    entry: dict = {"path": path, "content": content}
    if url is not None:
        entry["url"] = url
    return entry


@pytest.mark.unit
def test_collapses_unprefixed_orphan_keeping_prefixed_twin() -> None:
    entries = [
        _entry("digigraph/AGENTS.md"),
        _entry("clients/digithings/digigraph/AGENTS.md"),
    ]
    out = dedupe_namespace_copies(entries)
    assert [e["path"] for e in out] == ["clients/digithings/digigraph/AGENTS.md"]


@pytest.mark.unit
def test_keeps_url_carrier_over_prefixed_twin_without_url() -> None:
    entries = [
        _entry("openapi", url="https://example.com/openapi.json"),
        _entry("clients/digithings/openapi"),
    ]
    out = dedupe_namespace_copies(entries)
    assert len(out) == 1
    assert out[0]["url"] == "https://example.com/openapi.json"


@pytest.mark.unit
def test_no_collapse_on_distinct_content() -> None:
    entries = [
        _entry("digigraph/AGENTS.md", content="alpha"),
        _entry("clients/digithings/digigraph/AGENTS.md", content="beta"),
    ]
    assert len(dedupe_namespace_copies(entries)) == 2


@pytest.mark.unit
def test_no_collapse_on_empty_content() -> None:
    entries = [
        _entry("digigraph/AGENTS.md", content=""),
        _entry("clients/digithings/digigraph/AGENTS.md", content=""),
    ]
    assert len(dedupe_namespace_copies(entries)) == 2


@pytest.mark.unit
def test_no_collapse_on_unrelated_paths() -> None:
    entries = [
        _entry("notes/purpose.md"),
        _entry("archive/other.md"),
    ]
    assert len(dedupe_namespace_copies(entries)) == 2


@pytest.mark.unit
def test_winners_keep_earliest_group_position() -> None:
    entries = [
        _entry("other.md", content="zzz"),
        _entry("digigraph/AGENTS.md"),
        _entry("clients/digithings/digigraph/AGENTS.md"),
    ]
    out = dedupe_namespace_copies(entries)
    assert [e["path"] for e in out] == [
        "other.md",
        "clients/digithings/digigraph/AGENTS.md",
    ]


@pytest.mark.unit
def test_does_not_mutate_input() -> None:
    entries = [
        _entry("digigraph/AGENTS.md"),
        _entry("clients/digithings/digigraph/AGENTS.md"),
    ]
    dedupe_namespace_copies(entries)
    assert len(entries) == 2


@pytest.mark.unit
def test_run_query_collapses_twins_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twin chunks (same body, live + tenant-prefixed vault paths) in the
    stub index come back as ONE hit through POST /query (#4823)."""
    import os

    if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"):
        pytest.skip("stub-backend test needs real backends disabled")
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")

    from digisearch.core.models import Chunk
    from digisearch.search import add_chunks
    from digisearch.server import app
    from fastapi.testclient import TestClient

    from tests.digi_test_jwt import auth_headers

    idx = "__unit_test_ns_twins__"
    body = "Guide purpose body shared by both namespaces."
    add_chunks(
        idx,
        [
            Chunk(
                id="live-0",
                content=body,
                doc_id="live-d",
                embedding=None,
                metadata={"vault_path": "digigraph/AGENTS.md"},
            ),
            Chunk(
                id="pref-0",
                content=body,
                doc_id="pref-d",
                embedding=None,
                metadata={"vault_path": "clients/digithings/digigraph/AGENTS.md"},
            ),
        ],
    )
    client = TestClient(app, headers=auth_headers())
    r = client.post("/query", json={"text": "Guide purpose", "index_name": idx, "top_k": 10})
    assert r.status_code == 200
    hits = r.json().get("results") or []
    assert len(hits) == 1
