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
def test_twin_entry_prefers_http_source_url_over_tmp_path() -> None:
    """URL-ingested chunks carry a tmp-staging ``path`` alongside the shared
    http ``source_url``; identity must be the URL or same-URL duplicates
    regress (#4856 review)."""
    from types import SimpleNamespace

    from digisearch.server import _twin_entry

    def url_result(tmp_path: str) -> SimpleNamespace:
        return SimpleNamespace(
            chunk=SimpleNamespace(
                content="spec body",
                metadata={
                    "source_url": "https://example.com/openapi.json",
                    "path": tmp_path,
                },
            )
        )

    entries = [
        _twin_entry(url_result("/tmp/ingest-a/page.md"), 0),
        _twin_entry(url_result("/tmp/ingest-b/page.md"), 1),
    ]
    assert [e["path"] for e in entries] == [
        "https://example.com/openapi.json",
        "https://example.com/openapi.json",
    ]
    out = dedupe_namespace_copies(entries)
    assert len(out) == 1
    assert out[0]["url"] == "https://example.com/openapi.json"


@pytest.mark.unit
def test_twin_entry_prefers_vault_path_over_file_source_url() -> None:
    """File-ingested chunks carry a file-derived ``source_url`` (e.g. the
    ingest location); identity must come from the vault namespace (#4856)."""
    from types import SimpleNamespace

    from digisearch.server import _twin_entry

    result = SimpleNamespace(
        chunk=SimpleNamespace(
            content="body text",
            metadata={
                "source_url": "/app/.tmp-twins/twin-a.md",
                "path": "twins/live-guide.md",
                "vault_path": "twins/live-guide.md",
            },
        )
    )
    assert _twin_entry(result, 0)["path"] == "twins/live-guide.md"


@pytest.mark.unit
def test_twin_entry_uses_http_source_url_as_identity_fallback() -> None:
    """URL-ingested chunks with no vault path keep the https URL as identity
    and as the keep-signal (#4856)."""
    from types import SimpleNamespace

    from digisearch.server import _twin_entry

    result = SimpleNamespace(
        chunk=SimpleNamespace(
            content="body text",
            metadata={"source_url": "https://example.com/openapi.json"},
        )
    )
    entry = _twin_entry(result, 0)
    assert entry["path"] == "https://example.com/openapi.json"
    assert entry["url"] == "https://example.com/openapi.json"


@pytest.mark.unit
def test_twin_entry_ignores_file_source_url_without_vault_path() -> None:
    """A bare file path is an ingest-location artifact, never an identity:
    without a vault path the entry stays ungroupable (#4856)."""
    from types import SimpleNamespace

    from digisearch.server import _twin_entry

    result = SimpleNamespace(
        chunk=SimpleNamespace(
            content="body text",
            metadata={"source_url": "/app/.tmp-twins/twin-a.md"},
        )
    )
    assert _twin_entry(result, 0)["path"] == ""


@pytest.mark.unit
def test_run_query_collapses_file_shape_twins_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File-ingested twins (file-derived source_url + vault_path twins, same
    body) come back as ONE hit through POST /query (#4856)."""
    import os

    if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"):
        pytest.skip("stub-backend test needs real backends disabled")
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")

    from digisearch.core.models import Chunk
    from digisearch.search import add_chunks
    from digisearch.server import app
    from fastapi.testclient import TestClient

    from tests.digi_test_jwt import auth_headers

    idx = "__unit_test_ns_file_twins__"
    body = "Zephyrian file-shape twin body shared by both namespaces."
    add_chunks(
        idx,
        [
            Chunk(
                id="live-f",
                content=body,
                doc_id="live-fd",
                embedding=None,
                metadata={
                    "source_url": "/app/.tmp-twins/twin-a.md",
                    "path": "twins/live-guide.md",
                    "vault_path": "twins/live-guide.md",
                },
            ),
            Chunk(
                id="pref-f",
                content=body,
                doc_id="pref-fd",
                embedding=None,
                metadata={
                    "source_url": "/app/.tmp-twins/twin-b.md",
                    "path": "clients/digithings/twins/live-guide.md",
                    "vault_path": "clients/digithings/twins/live-guide.md",
                },
            ),
        ],
    )
    client = TestClient(app, headers=auth_headers())
    r = client.post("/query", json={"text": "Zephyrian file-shape", "index_name": idx, "top_k": 10})
    assert r.status_code == 200
    hits = r.json().get("results") or []
    assert len(hits) == 1


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
