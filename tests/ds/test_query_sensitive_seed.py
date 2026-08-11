"""Regression: diverse corpus + different queries → different top digisearch docs."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.core.evidence_metadata import merge_document_metadata_into_chunks
from digisearch.core.models import Query
from digisearch.ingestion.chunkers.recursive import RecursiveChunker
from digisearch.ingestion.registry import ParserRegistry
from digisearch.search import _stub as stub_mod


def _ingest_md_files(paths: list[Path], index: str) -> int:
    registry = ParserRegistry()
    chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    total = 0
    for path in paths:
        doc = registry.parse(path)
        chunks = chunker.chunk(doc)
        merge_document_metadata_into_chunks(doc, chunks)
        stub_mod.add_chunks(index, chunks)
        total += len(chunks)
    return total


@pytest.mark.unit
def test_stub_ingest_is_query_sensitive_with_diverse_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    stub_mod._stub_index.clear()

    root = tmp_path / "seed"
    root.mkdir()
    (root / "jwt-auth.md").write_text(
        "# JWT authentication\n\nRS256 JWKS digikey scoped bearer tokens.\n",
        encoding="utf-8",
    )
    (root / "chroma-rag.md").write_text(
        "# Chroma RAG\n\nRecursive chunk embed hybrid query digisearch collection.\n",
        encoding="utf-8",
    )
    (root / "vault-notes.md").write_text(
        "# Vault notes\n\nObsidian wikilinks frontmatter path_prefix digivault.\n",
        encoding="utf-8",
    )

    total = _ingest_md_files(sorted(root.glob("*.md")), "diverse_docs")
    assert total >= 3

    chunks = stub_mod._stub_index["diverse_docs"]
    paths = {str((c.metadata or {}).get("path") or "") for c in chunks}
    assert any(p.endswith("jwt-auth.md") for p in paths)
    assert all((c.metadata or {}).get("title") for c in chunks)

    auth = stub_mod.query_index(
        Query(text="RS256 JWKS digikey", top_k=1), index_name="diverse_docs"
    )
    rag = stub_mod.query_index(
        Query(text="hybrid query digisearch", top_k=1), index_name="diverse_docs"
    )
    assert auth.results and rag.results
    assert auth.results[0].chunk.doc_id != rag.results[0].chunk.doc_id
    assert "jwt" in (auth.results[0].chunk.metadata or {}).get("path", "").lower()
    assert "chroma" in (rag.results[0].chunk.metadata or {}).get("path", "").lower()


@pytest.mark.unit
def test_profile_a_seed_dir_has_diverse_paths() -> None:
    """Structure check for the CF stack seed (counts + unique filenames)."""
    seed = Path("frontend/digithings-stack-cloudflare/container/seed/digithings_docs")
    if not seed.is_dir():
        pytest.skip("seed dir not present in this checkout")
    files = sorted(p.name for p in seed.glob("*.md"))
    assert len(files) >= 6
    assert "digikey-auth.md" in files
    assert "digisearch-rag.md" in files
    assert "digivault-notes.md" in files
    assert len(set(files)) == len(files)
