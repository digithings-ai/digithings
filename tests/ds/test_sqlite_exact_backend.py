"""Unit tests for the local SQLite exact-scan vector backend."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.core.models import Chunk, Query
from digisearch.indexes.backends.sqlite_exact import SQLiteExactBackend


class _Provider:
    model_id = "test"
    dimensions = 3
    version = "1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def _backend(tmp_path: Path, name: str = "idx") -> SQLiteExactBackend:
    return SQLiteExactBackend(
        name, db_path=tmp_path / "index.sqlite3", embedding_provider=_Provider()
    )


def _chunks() -> list[Chunk]:
    return [
        Chunk(
            id="a",
            content="alpha",
            doc_id="doc-a",
            embedding=[1.0, 0.0, 0.0],
            metadata={"tier": "a", "workspace_id": "w1"},
        ),
        Chunk(
            id="b",
            content="beta",
            doc_id="doc-b",
            embedding=[0.0, 1.0, 0.0],
            metadata={"tier": "b", "workspace_id": "w1"},
        ),
        Chunk(
            id="c",
            content="gamma",
            doc_id="doc-c",
            embedding=[1.0, 0.0, 0.0],
            metadata={"tier": "a", "workspace_id": "w2"},
        ),
    ]


@pytest.mark.unit
def test_query_orders_by_cosine_and_honors_top_k_and_skip(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.add(_chunks())

    first = backend.query(Query(text="", embedding=[1.0, 0.0, 0.0], top_k=1))
    assert [result.chunk.id for result in first] == ["a"]
    assert first[0].score == pytest.approx(1.0)

    second = backend.query(Query(text="", embedding=[1.0, 0.0, 0.0], top_k=1, skip=1))
    assert [result.chunk.id for result in second] == ["c"]
    assert second[0].rank == 1


@pytest.mark.unit
def test_structured_and_workspace_filters_apply_before_ranking(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.add(_chunks())

    filtered = backend.query(
        Query(
            text="",
            embedding=[1.0, 0.0, 0.0],
            top_k=10,
            filters={"structured": [{"field": "tier", "op": "eq", "value": "b"}]},
        )
    )
    assert [result.chunk.id for result in filtered] == ["b"]

    workspace = backend.query(
        Query(text="", embedding=[1.0, 0.0, 0.0], top_k=10, workspace_id="w2")
    )
    assert [result.chunk.id for result in workspace] == ["c"]


@pytest.mark.unit
def test_partial_embedding_batch_is_refused(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    chunks = [
        Chunk(id="a", content="alpha", doc_id="d", embedding=[1.0, 0.0, 0.0]),
        Chunk(id="b", content="beta", doc_id="d", embedding=None),
    ]
    with pytest.raises(ValueError, match="partial embedding batch"):
        backend.add(chunks)


@pytest.mark.unit
def test_add_without_embeddings_uses_provider_and_is_idempotent(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    chunk = Chunk(id="a", content="alpha", doc_id="d", metadata={"title": "Alpha"})
    backend.add([chunk])
    backend.add([chunk])
    assert chunk.embedding == [1.0, 0.0, 0.0]
    assert backend.count() == 1


@pytest.mark.unit
def test_delete_update_snapshot_and_health(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.add(_chunks())
    assert backend.health() is True
    assert backend.count() == 3

    backend.delete(["b"])
    assert backend.count() == 2

    backend.update(
        [Chunk(id="c", content="gamma updated", doc_id="doc-c", embedding=[0.0, 0.0, 1.0])]
    )
    assert backend.count() == 2

    file_snapshot = tmp_path / "snapshot.sqlite3"
    backend.snapshot(str(file_snapshot))
    assert file_snapshot.is_file()

    dir_snapshot = tmp_path / "snapshot-dir"
    backend.snapshot(str(dir_snapshot))
    assert (dir_snapshot / "index.sqlite3").is_file()


@pytest.mark.unit
def test_query_embedding_dimension_mismatch_raises(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.add(_chunks())
    with pytest.raises(ValueError, match="dimension mismatch"):
        backend.query(Query(text="", embedding=[1.0, 0.0], top_k=1))


@pytest.mark.unit
def test_default_path_is_anchored_to_digi_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DIGISEARCH_SQLITE_PATH", raising=False)
    monkeypatch.setenv("DIGI_WORKSPACE", str(tmp_path / "workspace"))
    backend = SQLiteExactBackend("idx", embedding_provider=_Provider())
    assert backend._db_path == tmp_path / "workspace" / ".digisearch" / "index.sqlite3"
    backend.close()


@pytest.mark.unit
def test_query_with_total_reports_full_match_count(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.add(_chunks())
    results, total = backend.query_with_total(
        Query(text="", embedding=[1.0, 0.0, 0.0], top_k=1, include_total_count=True)
    )
    assert len(results) == 1
    assert total == 3

    results, total = backend.query_with_total(Query(text="", embedding=[1.0, 0.0, 0.0], top_k=1))
    assert len(results) == 1
    assert total is None


@pytest.mark.unit
def test_list_collections_sees_every_collection_in_the_file(tmp_path: Path) -> None:
    one = _backend(tmp_path, "one")
    two = _backend(tmp_path, "two")
    one.add([Chunk(id="a", content="alpha", doc_id="d", embedding=[1.0, 0.0, 0.0])])
    two.add([Chunk(id="b", content="beta", doc_id="d", embedding=[0.0, 1.0, 0.0])])
    assert one.list_collections() == ["one", "two"]
