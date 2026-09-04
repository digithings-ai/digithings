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
_CHARACTERIZATION_DOC = (
    """# Title

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
"""
    * 20
)


@pytest.mark.unit
def test_fixed_chunker() -> None:
    doc = Document(id="d1", content="a" * 1000, source="x", doc_type="txt")
    ch = FixedSizeChunker(chunk_size=100)
    chunks = ch.chunk(doc)
    assert len(chunks) >= 10
    assert all(c.doc_id == "d1" for c in chunks)


@pytest.mark.unit
def test_recursive_chunker() -> None:
    doc = Document(
        id="d1", content="Para one.\n\nPara two.\n\nPara three.", source="x", doc_type="txt"
    )
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
def test_recursive_chunker_oversized_part_after_nonempty_current_is_split() -> None:
    """Issue #2153 follow-up: a markdown table (or other delimiter-sparse run)
    longer than chunk_size must be sub-split even when it arrives while
    `current` already holds buffered prior text. Previously this path
    concatenated the oversized part directly into `current` with no size
    check, so it (or the merged result) was later flushed verbatim, exceeding
    chunk_size."""
    intro = "Intro paragraph before the table talks about nothing in particular.\n\n"
    header = "| Col A | Col B | Col C | Col D |\n"
    sep_row = "| --- | --- | --- | --- |\n"
    rows = "".join(
        f"| value-a-{i} | value-b-{i} | value-c-{i} | value-d-{i} |\n" for i in range(120)
    )
    table = header + sep_row + rows
    assert len(table) > 2000, "fixture table must exceed chunk_size to exercise the bug"

    doc = Document(id="d", content=intro + table, source="x", doc_type="md")
    chunks = RecursiveChunker().chunk(doc)

    assert len(chunks) > 1
    assert all(len(c.content) <= 2000 for c in chunks)
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert [c.id for c in chunks] == [f"d_{i}" for i in range(len(chunks))]


@pytest.mark.unit
def test_real_markdown_file_chunking_matches_recorded_fingerprint() -> None:
    """Chunks digisearch/ARCHITECTURE.md and pins count + per-chunk hashes. This
    is the byte-identical-behavior proof required by issue #2180: run against
    the old and new implementation and diff the fingerprints.

    digisearch/ARCHITECTURE.md contains three sections (heading blocks with no
    blank line inside) that pre-#2153-fix produced oversized chunks (2999,
    3616, 2149 chars) via the concatenate-into-`current` bug. The fingerprint
    was first recorded post-fix at count 36 (up from 35, as those three
    sections sub-split into within-budget pieces) — and the size assertion
    pins that fixed invariant going forward. Count and hashes were
    re-recorded at 42 for #2201 (Vectorize backend docs added to
    ARCHITECTURE.md), then again at 43 for the #2201 final-review fixes (the
    index-naming-coupling and fetch-all-clamp paragraphs added to the
    Vectorize section), then hashes only (count unchanged at 43) when the
    same #2201 branch corrected the index-naming caveat from "unresolved" to
    "verified 2026-08-11 against the live account", then to count 44 when the
    same branch reworded that caveat again to fix a false claim about
    Cloudflare's docs (advisory naming guidance is stated in prose, not
    silent) — the reworded paragraph pushed the same chunk over the size
    budget and it split into two: the chunker did not change, only the
    fixture content changed, so this fingerprint is expected to be
    regenerated whenever ARCHITECTURE.md's prose changes materially — it is
    not itself a chunker-behavior assertion beyond the ``<= 2000`` size
    invariant.     Hashes only (count unchanged at 44) re-recorded for #2239's
    Cloudflare credential rename (VECTORIZE_ACCOUNT_ID/VECTORIZE_API_TOKEN ->
    CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN with legacy fallback) --
    prose-only changes to the Vectorize section and the env var reference table.
    Hashes only again (count still 44) for #2330's CodeRabbit body follow-up:
    the production-inventory paragraph now documents the D1_ACCOUNT_ID /
    D1_API_TOKEN credential fallback chain — fixture prose only.
    Re-recorded at count 46 for CHR-88 / #403 (Chonkie chunking docs + module
    map in ARCHITECTURE.md) — fixture prose only; RecursiveChunker unchanged.
    Hashes only (count still 46) for #2225 embedder-lock note in the Vectorize
    operational section — fixture prose only.
    Hashes only (count still 46) for #2219 Vectorize fail-loud docs — multi-tenant
    / Vectorize filter paragraphs in ARCHITECTURE.md; RecursiveChunker unchanged.
    Hashes only (count still 46) for #2437 Chroma EmbeddingProvider / schema
    versioning docs in §(f) — fixture prose only.
    Re-recorded at count 45 for #1189 (canonical ``pipeline/ingest.py`` docs +
    module map in ARCHITECTURE.md) — fixture prose only; RecursiveChunker
    unchanged.
    Re-recorded at count 46 for #1177 (embed pipeline factory + query.mode
    semantics docs in ARCHITECTURE.md) — fixture prose only; RecursiveChunker
    unchanged.
    Re-recorded at count 47 for #2441 (DIGISEARCH_RERANK_ENABLED / BGE v2-m3
    wiring docs in ARCHITECTURE.md) — fixture prose only; RecursiveChunker
    unchanged.
    Re-recorded at count 48 for #402 (RetrievalBackend protocol + pgvector /
    LightRAG docs in ARCHITECTURE.md) — fixture prose only; RecursiveChunker
    unchanged.
    """
    arch_path = Path(__file__).resolve().parents[2] / "digisearch" / "ARCHITECTURE.md"
    content = arch_path.read_text(encoding="utf-8")
    doc = Document(id="arch", content=content, source=str(arch_path), doc_type="md")
    chunks = RecursiveChunker().chunk(doc)

    assert len(chunks) == 48
    assert all(len(c.content) <= 2000 for c in chunks)
    hashes = [hashlib.sha256(c.content.encode()).hexdigest()[:16] for c in chunks]
    assert hashes == [
        "2a6c63aff18cb155",
        "05ee1579bfb41def",
        "7e6b7b2044358888",
        "cea76b9e90df056e",
        "6f61da3b9ed54d44",
        "5c87a98eae4b4c24",
        "5c44b3a1c81aaae0",
        "4fe2b5f10b829673",
        "e446cea04444b3a8",
        "214d58d9d1d9d220",
        "90a5a2d345e53200",
        "24d4f4910f267916",
        "8b3750ac2215c89e",
        "5c929ad2654944ce",
        "80578aa2dbbb641d",
        "1f9fe54a7f6c6f25",
        "bb49fa9bd8d8d792",
        "674f45e22421aa20",
        "f4a0993928428a57",
        "819ebadc3320ecc2",
        "9febcd11d9848e18",
        "8c403dc89d35fe82",
        "d60ae7116f9e57ec",
        "ec4e79e9d9714f36",
        "e04f2c804b4baa0c",
        "2ec8256cb4695f07",
        "16bea1bbfea529fc",
        "00bffb9020b848f5",
        "078cbca3f2c3b3e1",
        "8e8ba68329d0d6db",
        "6b71a6ae799786a7",
        "e5be9f0e5832575d",
        "5276cf81c056f97a",
        "3e4e414a6f3c0c5e",
        "79e1479908a647a2",
        "5881d77c9811fa5d",
        "217c7d169b90a8be",
        "e98012ae08e70074",
        "9496728548f7cd2a",
        "11a2313f67dd5137",
        "a0c3eeac2a656b2f",
        "44050a77e280c022",
        "79ae674b8661ea64",
        "fc586dc7c2348d1e",
        "ac8dbe83a57bf4f4",
        "8b8c754092fe534f",
        "059d9ccf5c138f8c",
        "22f9d694bae83638",
    ]
