"""Tests for the swappable local index factory and backend gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.backend_require import require_real_search_backend, selected_index_backend
from digisearch.client import DigiSearch
from digisearch.core.models import Chunk
from digisearch.indexes.backends.sqlite_exact import SQLiteExactBackend
from digisearch.indexes.factory import get_index
from digisearch.search._stub import route_add_chunks


@pytest.mark.unit
def test_factory_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DIGISEARCH_INDEX_BACKEND", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    index = get_index("idx", db_path=str(tmp_path / "index.sqlite3"))
    assert isinstance(index, SQLiteExactBackend)


@pytest.mark.unit
def test_factory_explicit_sqlite_wins_over_legacy_chroma(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "sqlite")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    index = get_index("idx", db_path=str(tmp_path / "index.sqlite3"))
    assert isinstance(index, SQLiteExactBackend)


@pytest.mark.unit
def test_factory_rejects_remote_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "azure")
    with pytest.raises(ValueError, match="local index backend"):
        get_index("idx")


@pytest.mark.unit
def test_selected_backend_reads_named_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "SQLite")
    assert selected_index_backend() == "sqlite"


@pytest.mark.unit
def test_require_accepts_explicit_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "sqlite")
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    require_real_search_backend()


@pytest.mark.unit
def test_require_accepts_sqlite_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_INDEX_BACKEND", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("VECTORIZE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("VECTORIZE_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.setattr(
        "digisearch.indexes.backends.azure_search.is_azure_configured", lambda: False
    )
    require_real_search_backend()


@pytest.mark.unit
def test_require_rejects_chroma_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "chroma")
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    with pytest.raises(RuntimeError, match="CHROMA_PATH"):
        require_real_search_backend()


@pytest.mark.unit
def test_require_rejects_stub_without_test_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_BACKEND", "stub")
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    with pytest.raises(RuntimeError, match="DIGISEARCH_ALLOW_STUB"):
        require_real_search_backend()


@pytest.mark.unit
def test_azure_only_ingest_fails_instead_of_writing_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGISEARCH_INDEX_BACKEND", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    chunk = Chunk(id="c", content="hello", doc_id="d", embedding=[1.0, 0.0, 0.0])
    with pytest.raises(RuntimeError, match="query-only"):
        route_add_chunks("idx", [chunk])


@pytest.mark.unit
def test_client_defaults_to_sqlite_and_ignores_chroma_persist_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DIGISEARCH_INDEX_BACKEND", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.setenv("DIGISEARCH_SQLITE_PATH", str(tmp_path / "index.sqlite3"))
    monkeypatch.setattr(DigiSearch, "_get_embedder", lambda self: None)

    class _Config:
        def get_index_config(self, _name: str) -> dict:
            return {"persist_path": str(tmp_path / "chroma-dir")}

    client = DigiSearch(config=_Config())  # type: ignore[arg-type]
    index = client.get_index("idx")
    assert isinstance(index, SQLiteExactBackend)
    assert index._db_path == tmp_path / "index.sqlite3"
