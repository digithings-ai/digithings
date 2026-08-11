"""Tests for chunkers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from digisearch.core.models import Document
from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
from digisearch.ingestion.chunkers.recursive import RecursiveChunker

# Multi-paragraph, multi-section document used to characterize existing chunk
# boundaries/counts on normally-delimited text (issue #2180 regression net).
_CHARACTERIZATION_DOC = """# Title

Paragraph one has a few sentences. It talks about nothing in particular. This is
just filler content meant to exercise the recursive chunker's delimiter search
across paragraph, sentence, and word boundaries in a realistic way.

Paragraph two continues the document. It also has multiple sentences within it.
Some of these sentences are a bit longer than others, to vary the rhythm of the
text and make sure the chunker handles ordinary prose correctly.

## Section heading

Paragraph three starts a new section. It discusses a different topic entirely,
spanning several lines of text that wrap naturally without any unusual
formatting or embedded binary content.

Paragraph four wraps up the section with a short summary sentence. Then it adds
one more sentence for good measure, so the paragraph is not too short.

## Another section

Paragraph five is the final paragraph in this characterization fixture. It is
here to ensure the chunker exercises its merge-and-overlap logic across more
than a handful of paragraphs before the document ends.
""" * 20


@pytest.mark.unit
def test_fixed_chunker() -> None:
    doc = Document(id="d1", content="a" * 1000, source="x", doc_type="txt")
    ch = FixedSizeChunker(chunk_size=100)
    chunks = ch.chunk(doc)
    assert len(chunks) >= 10
    assert all(c.doc_id == "d1" for c in chunks)


@pytest.mark.unit
def test_recursive_chunker() -> None:
    doc = Document(id="d1", content="Para one.\n\nPara two.\n\nPara three.", source="x", doc_type="txt")
    ch = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    chunks = ch.chunk(doc)
    assert len(chunks) >= 1
    assert chunks[0].content


@pytest.mark.unit
def test_recursive_chunker_default_size_is_token_scaled() -> None:
    from digisearch.ingestion.chunkers.recursive import (
        DEFAULT_CHUNK_CHARS,
        DEFAULT_CHUNK_OVERLAP,
    )

    assert DEFAULT_CHUNK_CHARS == 2000
    assert DEFAULT_CHUNK_OVERLAP == 250
    ch = RecursiveChunker()
    assert ch.chunk_size == DEFAULT_CHUNK_CHARS
    assert ch.chunk_overlap == DEFAULT_CHUNK_OVERLAP


@pytest.mark.unit
def test_recursive_chunker_respects_larger_default() -> None:
    doc = Document(id="d2", content="word " * 600, source="x", doc_type="txt")
    chunks = RecursiveChunker().chunk(doc)
    assert all(len(c.content) <= 2000 for c in chunks)
    assert len(chunks) <= 3


@pytest.mark.unit
def test_recursive_chunker_delimiter_free_run_does_not_recurse_forever() -> None:
    """Issue #2180: a run longer than chunk_size with none of the separators
    (no \\n\\n\\n, \\n\\n, \\n, '. ', or ' ') must be hard-split, not crash with
    RecursionError."""
    doc = Document(id="d3", content="A" * 6000, source="x", doc_type="txt")
    chunks = RecursiveChunker().chunk(doc)
    assert len(chunks) > 0
    assert all(len(c.content) <= 2000 for c in chunks)
    assert all(c.doc_id == "d3" for c in chunks)


@pytest.mark.unit
def test_recursive_chunker_characterization_normal_text_unchanged() -> None:
    """Regression net for issue #2180: pins the exact chunk count and content
    the recursive chunker produces on ordinary delimited prose today. Confirmed
    to pass against the pre-fix implementation — must still pass byte-identical
    after the delimiter-free-run fix lands."""
    doc = Document(id="arch", content=_CHARACTERIZATION_DOC, source="x", doc_type="md")
    chunks = RecursiveChunker().chunk(doc)

    assert len(chunks) == 13

    expected_hashes = [
        "95c1562430ae9551b6114aa451f248ac770b43c27d4004e16f0c78c7b5666c49",
        "c54eafffd6e2d1e31697c41f9a34a81d0711753d6c4d571613281004b0fdfde1",
        "dd1da227862f5d576ab23f0051acd912a5440583d94970aaeed5aa5781597284",
        "4c2451590f2e8360e00b3ce0173f4b6991635135eb8a8af89755420d199ddb1c",
        "aa17fd4a330a2422f95ffe8df5b3f5797bf10ce5af0ec66e7083f62299ac6848",
        "952ef1a3de4bd9d24645cb9996056ba74606315a68dab610a7d4a28a5ab93f51",
        "c54eafffd6e2d1e31697c41f9a34a81d0711753d6c4d571613281004b0fdfde1",
        "dd1da227862f5d576ab23f0051acd912a5440583d94970aaeed5aa5781597284",
        "4c2451590f2e8360e00b3ce0173f4b6991635135eb8a8af89755420d199ddb1c",
        "aa17fd4a330a2422f95ffe8df5b3f5797bf10ce5af0ec66e7083f62299ac6848",
        "952ef1a3de4bd9d24645cb9996056ba74606315a68dab610a7d4a28a5ab93f51",
        "c54eafffd6e2d1e31697c41f9a34a81d0711753d6c4d571613281004b0fdfde1",
        "c6c2614b710deca843a14a7182a0a6cb8515e6c19ee723f20b9470111aeba0a6",
    ]
    actual_hashes = [hashlib.sha256(c.content.encode()).hexdigest() for c in chunks]
    assert actual_hashes == expected_hashes

    # Indices are sequential with no gaps, and ids follow doc_id_idx.
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert [c.id for c in chunks] == [f"arch_{i}" for i in range(len(chunks))]


@pytest.mark.unit
def test_real_markdown_file_chunking_matches_recorded_fingerprint() -> None:
    """Chunks digisearch/ARCHITECTURE.md and pins count + per-chunk hashes. This
    is the byte-identical-behavior proof required by issue #2180: run against
    the old and new implementation and diff the fingerprints."""
    arch_path = Path(__file__).resolve().parents[2] / "digisearch" / "ARCHITECTURE.md"
    content = arch_path.read_text(encoding="utf-8")
    doc = Document(id="arch", content=content, source=str(arch_path), doc_type="md")
    chunks = RecursiveChunker().chunk(doc)

    assert len(chunks) == 35
    hashes = [hashlib.sha256(c.content.encode()).hexdigest()[:16] for c in chunks]
    assert hashes == [
        "2a6c63aff18cb155",
        "1d6bd0e31f071177",
        "7d66a347da720ba0",
        "ca676e74fb701d4e",
        "619afb8cf00d0076",
        "415f566722403afb",
        "28e404859ca4cd4e",
        "bee5fa38b170d902",
        "1985cd389cfd5f7b",
        "be26d567b57a7f71",
        "80578aa2dbbb641d",
        "1f9fe54a7f6c6f25",
        "d5254b1949a222f4",
        "243ff0c181b7b584",
        "6603c2da6eeb5309",
        "fcdcaec22e1e3e41",
        "190ed70936eb7d21",
        "099d2b19e8b490e1",
        "87306183f1831fe5",
        "e15576236dd1ba07",
        "f2687d4521d1e069",
        "112fe01c18768a54",
        "cdf4f0c7a56c56e7",
        "0a11a1bc22b44bfa",
        "741194a852e5c01a",
        "217c7d169b90a8be",
        "e98012ae08e70074",
        "b71ec72c2899ffb5",
        "29de67e95062e3e5",
        "639c7be2de9cab92",
        "52577945850ebd78",
        "bb9bb59e5e5a14e4",
        "401b4845a0001f15",
        "7a03bc65c4601e37",
        "22f9d694bae83638",
    ]
