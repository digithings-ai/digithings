# Content-Aware Chunking & Vault Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give PDFs page-level and Markdown/HTML/OpenAPI heading-level structural boundaries that both digisearch chunks and digivault notes respect, replacing the flat 512-character recursive splitter and one-note-per-document vault behavior.

**Architecture:** A new `Segment` dataclass and an optional `Document.segments` list act as an opt-in overlay — parsers that can detect structure populate it, everything else leaves it empty and behaves exactly as today. A `SegmentAwareChunker` wraps any existing `Chunker`: a segment under the size ceiling becomes exactly one chunk, a segment over it is sub-split by the inner chunker and never crosses into a neighbor. `write_vault_notes.py` writes one note per segment plus a linking hub note when a document has more than one segment.

**Tech Stack:** Python 3.12, stdlib dataclasses (NOT pydantic — see Global Constraints), pytest with `-m unit`, ruff at line-length 100.

**Source spec:** `docs/superpowers/specs/2026-08-11-content-aware-chunking-design.md`

## Global Constraints

- **`digisearch/src/digisearch/core/models.py` uses stdlib `@dataclass`, NOT pydantic.** Do not convert these to `BaseModel` — the contract is consumed by ~20 modules and 15 test files. Bare `@dataclass` decorator, no `frozen=`/`slots=`/`kw_only=`.
- **Field ordering:** `Document` has 4 required fields (`id`, `content`, `source`, `doc_type`) then defaulted ones. Any new field MUST have a default and be appended after `chunks`, or dataclass construction raises "non-default argument follows default argument".
- **Optional-collection convention in `models.py`:** `field(default_factory=list)` / `field(default_factory=dict)` — never a bare `= []`. Optional scalars: `X | None = None` (PEP 604, no `Optional[]`).
- **`digisearch.core.models` must stay import-cheap.** The top-level package uses a PEP 562 lazy `__getattr__`; do not add heavy imports (fastapi/mcp/typer are forbidden — see `tests/ds/test_parsers.py::_FORBIDDEN_ON_PARSER_IMPORT`).
- **ruff:** `line-length = 100`, `target-version = "py312"` (root `ruff.toml`). Everything under `tests/` must also be ruff-clean.
- **`Chunk` is always constructed with all five fields as keywords**, explicitly including `embedding=None` even though it defaults to `None`. Match verbatim.
- **Test markers:** `tests/ds/` uses a per-test `@pytest.mark.unit` decorator. `tests/scripts/docs_onboard/` uses module-level `pytestmark = pytest.mark.unit`. Follow whichever directory you are writing in.
- **All tests annotate `-> None`** and start with `from __future__ import annotations`.
- **Naming:** digi product names are always lowercase in prose/docstrings/commits (repo `CLAUDE.md`).
- **Name collision awareness:** `digisearch/src/digisearch/atlas_search.py` already has an unrelated `segment: str | None = None` *search filter* parameter. It has nothing to do with `Document.segments`. Do not touch it.
- **Repo rule:** update `{component}/ARCHITECTURE.md` after any interface change (Task 8 covers this).

---

### Task 1: `Segment` dataclass + `Document.segments` field

**Files:**
- Modify: `digisearch/src/digisearch/core/models.py:9-29`
- Modify: `digisearch/src/digisearch/core/__init__.py` (whole file, 5 lines)
- Modify: `digisearch/src/digisearch/__init__.py:28-45`
- Test: `tests/ds/test_segments.py` (create)

**Interfaces:**
- Consumes: nothing (foundation task).
- Produces: `Segment(index: int, label: str, text: str, metadata: dict[str, Any])` importable from `digisearch.core.models`; `Document.segments: list[Segment]` defaulting to `[]`.

**Design note:** The spec wrote `segments: list[Segment] | None = None`. Use `field(default_factory=list)` instead — it mirrors the `chunks` field directly above it, and empty-vs-absent is not a distinction any consumer needs (every consumer guards with `if not doc.segments:`, which handles both). This is a deliberate, documented deviation.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_segments.py`:

```python
"""Tests for the Segment data contract and Document.segments overlay."""

from __future__ import annotations

import pytest

from digisearch.core.models import Document, Segment


@pytest.mark.unit
def test_segment_fields() -> None:
    seg = Segment(index=0, label="page:1", text="hello")
    assert seg.index == 0
    assert seg.label == "page:1"
    assert seg.text == "hello"
    assert seg.metadata == {}


@pytest.mark.unit
def test_document_segments_defaults_empty() -> None:
    doc = Document(id="d1", content="x", source="s", doc_type="txt")
    assert doc.segments == []


@pytest.mark.unit
def test_document_accepts_segments() -> None:
    segs = [Segment(index=0, label="page:1", text="a"), Segment(index=1, label="page:2", text="b")]
    doc = Document(id="d1", content="ab", source="s", doc_type="pdf", segments=segs)
    assert len(doc.segments) == 2
    assert doc.segments[1].label == "page:2"


@pytest.mark.unit
def test_segment_exported_from_core_package() -> None:
    from digisearch.core import Segment as CoreSegment

    assert CoreSegment is Segment
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_segments.py -m unit -v --tb=short`
Expected: FAIL with `ImportError: cannot import name 'Segment' from 'digisearch.core.models'`

- [ ] **Step 3: Add the `Segment` dataclass**

In `digisearch/src/digisearch/core/models.py`, insert this class immediately **before** the existing `@dataclass class Document:` (line 9), keeping one blank line between classes:

```python
@dataclass
class Segment:
    """Structural unit of a Document: a PDF page, markdown section, or API operation."""

    index: int  # 0-based position within the parent Document
    label: str  # "page:12", "heading:Auth > Rotating Keys", "operation:POST /v1/ingest"
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Add the `segments` field to `Document`**

In the same file, append this line to the `Document` class body, **after** the existing `chunks: list["Chunk"] = field(default_factory=list)` line:

```python
    segments: list["Segment"] = field(default_factory=list)  # structural units; empty = unstructured
```

The `Document` class body now reads in full:

```python
@dataclass
class Document:
    """Document ingested into digisearch. Passed between modules (digiflow, digigraph)."""

    id: str
    content: str
    source: str  # file path, URL, or identifier
    doc_type: str  # "pdf", "html", "docx", etc.
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list["Chunk"] = field(default_factory=list)
    segments: list["Segment"] = field(default_factory=list)  # structural units; empty = unstructured
```

- [ ] **Step 5: Export from `digisearch.core`**

Replace the whole of `digisearch/src/digisearch/core/__init__.py` with:

```python
"""digisearch core models and config."""

from digisearch.core.models import Chunk, Document, Query, Result, Segment

__all__ = ["Chunk", "Document", "Query", "Result", "Segment"]
```

- [ ] **Step 6: Export from the top-level package**

In `digisearch/src/digisearch/__init__.py`, make three edits.

Add to the `_LAZY` dict (line ~28) so it reads:

```python
_LAZY: dict[str, str] = {
    "DigiSearch": "digisearch.client",
    "Chunk": "digisearch.core.models",
    "Document": "digisearch.core.models",
    "Query": "digisearch.core.models",
    "Result": "digisearch.core.models",
    "Segment": "digisearch.core.models",
}
```

Add `"Segment"` to the `__all__` list (line ~35).

Add `Segment` to the `if TYPE_CHECKING:` import (line ~45):

```python
    from digisearch.core.models import Chunk, Document, Query, Result, Segment
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/ds/test_segments.py -m unit -v --tb=short`
Expected: PASS (4 passed)

- [ ] **Step 8: Verify nothing else broke**

Run: `pytest tests/ds/ -m unit -v --tb=short`
Expected: PASS — same count as before plus 4 (baseline was "200 passed, 3 skipped" per `.github/workflows/test-digisearch.yml`, so expect 204 passed, 3 skipped).

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 9: Commit**

```bash
git add digisearch/src/digisearch/core/models.py digisearch/src/digisearch/core/__init__.py digisearch/src/digisearch/__init__.py tests/ds/test_segments.py
git commit -m "feat(digisearch): add Segment contract and optional Document.segments overlay"
```

---

### Task 2: Raise `RecursiveChunker` default chunk size to ~512 tokens

**Files:**
- Modify: `digisearch/src/digisearch/ingestion/chunkers/recursive.py:17-20`
- Modify: `digisearch/src/digisearch/cli.py:18,21`
- Modify: `digisearch/src/digisearch/server.py:665`
- Modify: `digisearch/src/digisearch/atlas_ingest.py:211`
- Modify: `scripts/reindex_digithings_guide.py:75`
- Test: `tests/ds/test_chunkers.py` (modify)

**Interfaces:**
- Consumes: nothing.
- Produces: `DEFAULT_CHUNK_CHARS = 2000` and `DEFAULT_CHUNK_OVERLAP = 250`, importable from `digisearch.ingestion.chunkers.recursive`. Later tasks import `DEFAULT_CHUNK_CHARS` as the segment size ceiling.

**Rationale (from spec):** the current `chunk_size=512` counts **characters** (~128 tokens), well below the ~512-token benchmarked default. 2000 characters ≈ 512 tokens at ~4 chars/token. Overlap scales with it to hold the existing ~12.5% ratio (64/512 → 250/2000). No tokenizer dependency is introduced.

- [ ] **Step 1: Write the failing test**

Append to `tests/ds/test_chunkers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_chunkers.py -m unit -v --tb=short`
Expected: FAIL with `ImportError: cannot import name 'DEFAULT_CHUNK_CHARS'`

- [ ] **Step 3: Add the constants and change the defaults**

In `digisearch/src/digisearch/ingestion/chunkers/recursive.py`, add these constants immediately after the `logger = logging.getLogger(__name__)` line:

```python
# ~512 tokens at a ~4-chars/token heuristic — the benchmarked default chunk size for
# general RAG. Deliberately character-based: no tokenizer dependency is introduced.
DEFAULT_CHUNK_CHARS = 2000
DEFAULT_CHUNK_OVERLAP = 250  # ~12.5%, holding the previous 64/512 ratio
```

Then change the `__init__` signature (line 17) from `def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:` to:

```python
    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
```

Leave the three body lines (`self.chunk_size = ...`, `self.chunk_overlap = ...`, `self._separators = [...]`) exactly as they are.

- [ ] **Step 4: Update the five explicit call sites**

Every production caller currently passes `RecursiveChunker(chunk_size=512, chunk_overlap=64)` explicitly, which would silently keep the old behavior. Replace that exact string with a bare `RecursiveChunker()` in each of these locations:

- `digisearch/src/digisearch/cli.py` lines 18 and 21
- `digisearch/src/digisearch/server.py` line 665
- `digisearch/src/digisearch/atlas_ingest.py` line 211
- `scripts/reindex_digithings_guide.py` line 75

Verify none remain:

```bash
grep -rn "chunk_size=512, chunk_overlap=64" digisearch/src scripts
```
Expected: only hits inside `tests/` (leave test call sites that deliberately pin a size alone).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/ds/test_chunkers.py tests/ds/test_query_sensitive_seed.py -m unit -v --tb=short`
Expected: PASS

- [ ] **Step 6: Run the full digisearch suite**

Run: `pytest tests/ds/ -m unit -v --tb=short`
Expected: PASS. If a test asserts an exact chunk count against the old 512-char size, update that test's expectation — the size change is intentional and the test is asserting the old default, not a behavior contract.

Run: `ruff check digisearch/src scripts tests`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add digisearch/src/digisearch/ingestion/chunkers/recursive.py digisearch/src/digisearch/cli.py digisearch/src/digisearch/server.py digisearch/src/digisearch/atlas_ingest.py scripts/reindex_digithings_guide.py tests/ds/test_chunkers.py
git commit -m "feat(digisearch): raise default chunk size from 512 chars to ~512 tokens"
```

---

### Task 3: Generic markdown heading segmenter

**Files:**
- Create: `digisearch/src/digisearch/ingestion/segmenters/__init__.py`
- Create: `digisearch/src/digisearch/ingestion/segmenters/heading.py`
- Test: `tests/ds/test_heading_segmenter.py` (create)

**Interfaces:**
- Consumes: `Segment` from Task 1.
- Produces: `heading_segments(markdown_text: str, *, max_split_level: int = 3) -> list[Segment]` — returns `[]` when the text has no headings at or above `max_split_level`. Labels are `"heading:<breadcrumb>"` where breadcrumb joins ancestor headings with `" > "`. Leading text before the first heading becomes a segment labeled `"heading:(intro)"`. Tasks 6 and 7 both call this.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_heading_segmenter.py`:

```python
"""Tests for the generic markdown heading segmenter."""

from __future__ import annotations

import pytest

from digisearch.ingestion.segmenters.heading import heading_segments

_DOC = """# API Guide

Intro paragraph.

## Authentication

How auth works.

### Rotating Keys

Rotate them often.

## Ingestion

How ingest works.
"""


@pytest.mark.unit
def test_no_headings_returns_empty() -> None:
    assert heading_segments("just a paragraph\n\nand another\n") == []


@pytest.mark.unit
def test_splits_on_headings() -> None:
    segs = heading_segments(_DOC)
    assert [s.label for s in segs] == [
        "heading:API Guide",
        "heading:API Guide > Authentication",
        "heading:API Guide > Authentication > Rotating Keys",
        "heading:API Guide > Ingestion",
    ]


@pytest.mark.unit
def test_segments_are_indexed_in_order() -> None:
    segs = heading_segments(_DOC)
    assert [s.index for s in segs] == [0, 1, 2, 3]


@pytest.mark.unit
def test_segment_text_includes_its_heading_and_body() -> None:
    segs = heading_segments(_DOC)
    auth = segs[1]
    assert auth.text.startswith("## Authentication")
    assert "How auth works." in auth.text
    assert "Rotate them often." not in auth.text


@pytest.mark.unit
def test_preamble_before_first_heading_becomes_intro_segment() -> None:
    segs = heading_segments("stray preamble\n\n## First\n\nbody\n")
    assert segs[0].label == "heading:(intro)"
    assert "stray preamble" in segs[0].text
    assert segs[1].label == "heading:First"


@pytest.mark.unit
def test_max_split_level_ignores_deeper_headings() -> None:
    segs = heading_segments(_DOC, max_split_level=2)
    assert [s.label for s in segs] == [
        "heading:API Guide",
        "heading:API Guide > Authentication",
        "heading:API Guide > Ingestion",
    ]
    assert "### Rotating Keys" in segs[1].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_heading_segmenter.py -m unit -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.ingestion.segmenters'`

- [ ] **Step 3: Create the package init**

Create `digisearch/src/digisearch/ingestion/segmenters/__init__.py` with exactly one line (matching the sibling `chunkers/__init__.py` convention, which exports nothing):

```python
"""Segmenters: split a document into structural units before chunking."""
```

- [ ] **Step 4: Write the segmenter**

Create `digisearch/src/digisearch/ingestion/segmenters/heading.py`:

```python
"""Generic markdown heading segmenter. Used for markdown, converted HTML, and OpenAPI."""

from __future__ import annotations

import re

from digisearch.core.models import Segment

# ATX headings only ("# Title"). Setext ("Title\n===") is not used by this pipeline's
# html_to_markdown output or by any repo doc, so it is deliberately unsupported.
_HEADING = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*$", re.MULTILINE)

INTRO_LABEL = "heading:(intro)"


def heading_segments(markdown_text: str, *, max_split_level: int = 3) -> list[Segment]:
    """Split markdown at headings of level <= ``max_split_level``.

    Returns an empty list when the text contains no qualifying heading, which callers
    treat as "no known structure" and fall back to whole-document handling.
    """
    if not markdown_text.strip():
        return []
    matches = [m for m in _HEADING.finditer(markdown_text) if len(m.group(1)) <= max_split_level]
    if not matches:
        return []

    segments: list[Segment] = []
    preamble = markdown_text[: matches[0].start()].strip()
    if preamble:
        segments.append(Segment(index=0, label=INTRO_LABEL, text=preamble))

    stack: list[tuple[int, str]] = []  # (level, heading text) ancestor chain
    for position, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        breadcrumb = " > ".join(text for _, text in stack)
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown_text)
        body = markdown_text[match.start() : end].strip()
        if not body:
            continue
        segments.append(
            Segment(
                index=len(segments),
                label=f"heading:{breadcrumb}",
                text=body,
                metadata={"heading": heading, "level": level},
            )
        )
    return segments
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/ds/test_heading_segmenter.py -m unit -v --tb=short`
Expected: PASS (6 passed)

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add digisearch/src/digisearch/ingestion/segmenters/ tests/ds/test_heading_segmenter.py
git commit -m "feat(digisearch): add generic markdown heading segmenter"
```

---

### Task 4: PDF parser emits one segment per page

**Files:**
- Modify: `digisearch/src/digisearch/ingestion/parsers/pdf.py:53-70,88-131`
- Test: `tests/ds/test_pdf_segments.py` (create)

**Interfaces:**
- Consumes: `Segment` from Task 1.
- Produces: `PDFParser.parse()` returns a `Document` whose `segments` holds one `Segment` per page, labeled `f"page:{n}"` (1-based) with `metadata={"page": n}`. `Document.content` keeps the existing flattened join, unchanged, for non-segment-aware callers.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_pdf_segments.py`:

```python
"""Tests for PDF page segmentation."""

from __future__ import annotations

import pytest

from digisearch.ingestion.parsers import pdf as pdf_module
from digisearch.ingestion.parsers.pdf import PDFParser


@pytest.mark.unit
def test_pdf_parser_emits_one_segment_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(
        pdf_module,
        "_extract_pages",
        lambda raw: ["page one text", "page two text", "page three text"],
    )
    doc = PDFParser().parse(b"%PDF-fake")
    assert [s.label for s in doc.segments] == ["page:1", "page:2", "page:3"]
    assert [s.index for s in doc.segments] == [0, 1, 2]
    assert doc.segments[1].text == "page two text"
    assert doc.segments[1].metadata == {"page": 2}


@pytest.mark.unit
def test_pdf_parser_content_still_flattened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(pdf_module, "_extract_pages", lambda raw: ["alpha", "beta"])
    doc = PDFParser().parse(b"%PDF-fake")
    assert doc.content == "alpha\nbeta"
    assert doc.doc_type == "pdf"


@pytest.mark.unit
def test_pdf_parser_skips_blank_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(pdf_module, "_extract_pages", lambda raw: ["real", "   ", "also real"])
    doc = PDFParser().parse(b"%PDF-fake")
    assert [s.label for s in doc.segments] == ["page:1", "page:3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_pdf_segments.py -m unit -v --tb=short`
Expected: FAIL with `AttributeError: <module 'digisearch.ingestion.parsers.pdf'> has no attribute '_extract_pages'`

- [ ] **Step 3: Refactor extraction to be page-aware**

In `digisearch/src/digisearch/ingestion/parsers/pdf.py`, replace the two existing extractor functions (currently `_extract_text_pdfplumber` and `_extract_text_pymupdf`, which each `"\n".join(...)` internally) with page-list versions plus a dispatcher:

```python
def _extract_pages_pdfplumber(raw: bytes) -> list[str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _extract_pages_pymupdf(raw: bytes) -> list[str]:
    import pymupdf

    doc = pymupdf.open(stream=raw, filetype="pdf")
    return [p.get_text() for p in doc]


def _extract_pages(raw: bytes) -> list[str]:
    """Per-page text. Page boundaries are preserved here and become Document.segments."""
    if _PDF_IMPL == "pdfplumber":
        return _extract_pages_pdfplumber(raw)
    if _PDF_IMPL == "pymupdf":
        return _extract_pages_pymupdf(raw)
    return []
```

Then **delete** the `PDFParser._extract_bytes` method entirely. After Step 4 below, `parse()` calls `_extract_pages` directly and the OCR fallback calls `_extract_text_ocr`, so `_extract_bytes` has no remaining caller. Confirm with:

```bash
grep -rn "_extract_bytes" digisearch/src tests
```
Expected: no output.

- [ ] **Step 4: Populate `segments` in `parse()`**

In `PDFParser.parse()`, the existing code computes `content` then builds the `Document` at line ~127. Change the parse body so it captures pages alongside content. Replace the two branches that currently set `content` and `raw` with:

```python
        if isinstance(source, bytes):
            raw = source
            src_str = "<bytes>"
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"PDF source not found: {source}")
            raw = path.read_bytes()
            src_str = str(path)
        pages = _extract_pages(raw)
        content = "\n".join(pages)
```

Leave the entire existing `if not content.strip():` OCR-fallback block exactly as it is — it reassigns `content` and does not need page awareness (a scanned PDF with no text layer has no usable page boundaries either).

Then, immediately before the existing `doc_id = str(uuid.uuid4())` line, add:

```python
        segments: list[Segment] = []
        for number, page_text in enumerate(pages, start=1):
            stripped = page_text.strip()
            if not stripped:
                continue
            segments.append(
                Segment(
                    index=len(segments),
                    label=f"page:{number}",
                    text=stripped,
                    metadata={"page": number},
                )
            )
```

Finally, add `segments=segments` to the existing `Document(...)` construction so it reads:

```python
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="pdf",
            metadata={},
            segments=segments,
        )
```

Add `Segment` to the existing model import at the top of the file:

```python
from digisearch.core.models import Document, Segment
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/ds/test_pdf_segments.py -m unit -v --tb=short`
Expected: PASS (3 passed)

- [ ] **Step 6: Verify the import-isolation probe still passes**

`tests/ds/test_parsers.py` asserts the pdf parser imports without pulling in the server stack. Run:

Run: `pytest tests/ds/test_parsers.py -m unit -v --tb=short`
Expected: PASS — including `test_pdf_parser_imports_without_server_stack`.

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add digisearch/src/digisearch/ingestion/parsers/pdf.py tests/ds/test_pdf_segments.py
git commit -m "feat(digisearch): preserve PDF page boundaries as Document.segments"
```

---

### Task 5: `SegmentAwareChunker`

**Files:**
- Create: `digisearch/src/digisearch/ingestion/chunkers/segment_aware.py`
- Test: `tests/ds/test_segment_aware_chunker.py` (create)

**Interfaces:**
- Consumes: `Segment`/`Document`/`Chunk` (Task 1), `DEFAULT_CHUNK_CHARS` (Task 2), the `Chunker` ABC.
- Produces: `SegmentAwareChunker(inner: Chunker | None = None, *, max_segment_chars: int = DEFAULT_CHUNK_CHARS)` implementing `chunk(self, doc: Document) -> list[Chunk]`. Every emitted chunk carries `segment_label` and `segment_index` in its metadata. Task 6 does not use this; the digisearch `/ingest` path (Task 7's follow-on wiring) does.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_segment_aware_chunker.py`:

```python
"""Tests for segment-aware chunking."""

from __future__ import annotations

import pytest

from digisearch.core.models import Document, Segment
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker


@pytest.mark.unit
def test_falls_back_to_inner_when_no_segments() -> None:
    doc = Document(id="d1", content="word " * 800, source="s", doc_type="txt")
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) >= 2
    assert all(c.doc_id == "d1" for c in chunks)
    assert all("segment_label" not in c.metadata for c in chunks)


@pytest.mark.unit
def test_short_segment_becomes_exactly_one_chunk() -> None:
    segs = [
        Segment(index=0, label="page:1", text="short page one"),
        Segment(index=1, label="page:2", text="short page two"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 2
    assert chunks[0].content == "short page one"
    assert chunks[0].metadata["segment_label"] == "page:1"
    assert chunks[1].metadata["segment_index"] == 1


@pytest.mark.unit
def test_oversized_segment_is_subsplit_without_crossing_boundaries() -> None:
    segs = [
        Segment(index=0, label="page:1", text="alpha " * 900),
        Segment(index=1, label="page:2", text="beta"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    page_one = [c for c in chunks if c.metadata["segment_label"] == "page:1"]
    page_two = [c for c in chunks if c.metadata["segment_label"] == "page:2"]
    assert len(page_one) > 1
    assert len(page_two) == 1
    assert all("beta" not in c.content for c in page_one)
    assert page_two[0].content == "beta"


@pytest.mark.unit
def test_chunk_ids_and_indices_are_sequential_across_segments() -> None:
    segs = [
        Segment(index=0, label="page:1", text="gamma " * 900),
        Segment(index=1, label="page:2", text="delta"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert [c.id for c in chunks] == [f"d1_{i}" for i in range(len(chunks))]
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


@pytest.mark.unit
def test_blank_segments_are_skipped() -> None:
    segs = [
        Segment(index=0, label="page:1", text="   "),
        Segment(index=1, label="page:2", text="real content"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].metadata["segment_label"] == "page:2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_segment_aware_chunker.py -m unit -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.ingestion.chunkers.segment_aware'`

- [ ] **Step 3: Write the chunker**

Create `digisearch/src/digisearch/ingestion/chunkers/segment_aware.py`:

```python
"""Segment-aware chunker. A structural segment is one chunk unless it exceeds the ceiling."""

from __future__ import annotations

from digisearch.core.models import Chunk, Document, Segment
from digisearch.ingestion.chunkers.base import Chunker
from digisearch.ingestion.chunkers.recursive import DEFAULT_CHUNK_CHARS, RecursiveChunker


class SegmentAwareChunker(Chunker):
    """Chunk within ``Document.segments``, never across them.

    A segment at or under ``max_segment_chars`` becomes exactly one chunk — page-level
    retrieval for the common case. Only oversized segments are sub-split, by ``inner``.
    Documents with no segments fall through to ``inner`` unchanged.
    """

    def __init__(
        self,
        inner: Chunker | None = None,
        *,
        max_segment_chars: int = DEFAULT_CHUNK_CHARS,
    ) -> None:
        self.inner = inner if inner is not None else RecursiveChunker()
        self.max_segment_chars = max_segment_chars

    def chunk(self, doc: Document) -> list[Chunk]:
        if not doc.segments:
            return self.inner.chunk(doc)
        chunks: list[Chunk] = []
        for segment in doc.segments:
            for content in self._segment_contents(doc, segment):
                chunks.append(
                    Chunk(
                        id=f"{doc.id}_{len(chunks)}",
                        content=content,
                        doc_id=doc.id,
                        embedding=None,
                        metadata={
                            "chunk_index": len(chunks),
                            "segment_label": segment.label,
                            "segment_index": segment.index,
                        },
                    )
                )
        return chunks

    def _segment_contents(self, doc: Document, segment: Segment) -> list[str]:
        """One string per chunk this segment yields: itself, or its sub-split parts."""
        text = segment.text.strip()
        if not text:
            return []
        if len(text) <= self.max_segment_chars:
            return [text]
        sub_doc = Document(
            id=doc.id,
            content=text,
            source=doc.source,
            doc_type=doc.doc_type,
            metadata=dict(doc.metadata),
        )
        return [c.content for c in self.inner.chunk(sub_doc) if c.content.strip()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_segment_aware_chunker.py -m unit -v --tb=short`
Expected: PASS (5 passed)

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/ingestion/chunkers/segment_aware.py tests/ds/test_segment_aware_chunker.py
git commit -m "feat(digisearch): add SegmentAwareChunker respecting structural boundaries"
```

---

### Task 6: Per-segment digivault notes with a hub note

**Files:**
- Modify: `scripts/docs_onboard/write_vault_notes.py:50-92,153-194`
- Test: `tests/scripts/docs_onboard/test_write_vault_notes.py` (modify)

**Interfaces:**
- Consumes: `heading_segments` (Task 3), PDF `Document.segments` (Task 4).
- Produces: `write_vault_notes(manifest, workspace, vault) -> int` — unchanged signature, but now returns child+hub note count for multi-segment documents. New module-private helpers `_segment_slug(segment) -> str` and `_hub_body(title, child_names) -> str`.

**Behavior contract:**
- 0 or 1 segments → exactly one note, byte-identical to today (regression-protected below).
- N > 1 segments → N child notes named `f"{slug}__{_segment_slug(seg)}"` plus one hub note named `slug` whose body is an ordered `[[wikilink]]` list. Return count is N+1.

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/docs_onboard/test_write_vault_notes.py`:

```python
def test_multi_segment_pdf_writes_children_and_hub(tmp_path: Path) -> None:
    from digisearch.core.models import Document as DsDocument
    from digisearch.core.models import Segment

    ws = Workspace.create(tmp_path / "work")
    pdf_path = ws.root / "assets" / "guide.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-fake")
    ws.append_source_map(
        SourceMapEntry(
            local_path="assets/guide.pdf",
            source_url="https://example.com/guide.pdf",
            content_type="application/pdf",
        )
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="https://example.com/guide.pdf",
                final_url="https://example.com/guide.pdf",
                content_type="application/pdf",
                title="Guide",
                depth=0,
                discovered_from="seed",
            ),
            page_class=PageClass.pdf,
            score=100.0,
            reasons=("pdf",),
        )
    )

    parsed = DsDocument(
        id="x",
        content="page one\npage two",
        source=str(pdf_path),
        doc_type="pdf",
        segments=[
            Segment(index=0, label="page:1", text="page one", metadata={"page": 1}),
            Segment(index=1, label="page:2", text="page two", metadata={"page": 2}),
        ],
    )
    monkey_target = "scripts.docs_onboard.write_vault_notes._pdf_document"
    with mock.patch(monkey_target, return_value=parsed):
        writer = _RecordingWriter()
        manifest = OnboardManifest(
            client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
        )
        count = write_vault_notes(manifest, ws, writer)

    assert count == 3
    names = [call["name"] for call in writer.calls]
    hub = slug_for_url("https://example.com/guide.pdf")
    assert names == [f"{hub}__p001", f"{hub}__p002", hub]
    hub_call = writer.calls[-1]
    assert f"[[{hub}__p001]]" in hub_call["body"]
    assert f"[[{hub}__p002]]" in hub_call["body"]
    assert hub_call["frontmatter"]["segment_count"] == 2
    child = writer.calls[0]
    assert child["body"] == "page one\n"
    assert child["frontmatter"]["segment_label"] == "page:1"
    assert child["frontmatter"]["segment_index"] == 0
    assert child["frontmatter"]["parent_doc"] == hub


def test_single_segment_document_writes_one_note(tmp_path: Path) -> None:
    ws = Workspace.create(tmp_path / "work")
    local = ws.root / "files" / "readme.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("# Readme\n\nJust one section.\n", encoding="utf-8")
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="repo://acme/README.md",
                final_url="repo://acme/README.md",
                content_type="text/markdown",
                title="Readme",
                depth=0,
                local_path="files/readme.md",
                discovered_from="repo_source",
            ),
            page_class=PageClass.repo_doc,
            score=90.0,
            reasons=("repo",),
        )
    )
    writer = _RecordingWriter()
    manifest = OnboardManifest(
        client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
    )
    count = write_vault_notes(manifest, ws, writer)
    assert count == 1
    assert "__" not in writer.calls[0]["name"]
    assert "segment_label" not in writer.calls[0]["frontmatter"]
```

Add this recording writer helper near the top of the same test file (below the imports), if one does not already exist — check first and reuse the existing double if the file already has one:

```python
class _RecordingWriter:
    """NoteWriter double that records every write_note call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "name": name,
                "frontmatter": dict(frontmatter or {}),
                "body": body,
                "subdir": subdir,
                "overwrite": overwrite,
            }
        )
        return {"ok": True}
```

Ensure the test file's imports include (merge with what is already there — do not duplicate):

```python
from pathlib import Path
from typing import Any  # score:allow untyped any — NoteWriter test double records open dicts
from unittest import mock

import pytest

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_vault_notes import write_vault_notes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/docs_onboard/test_write_vault_notes.py -m unit -v --tb=short`
Expected: FAIL — `AttributeError: <module 'scripts.docs_onboard.write_vault_notes'> does not have the attribute '_pdf_document'`

- [ ] **Step 3: Expose the parsed PDF Document**

In `scripts/docs_onboard/write_vault_notes.py`, replace the existing `_pdf_text(path)` function with a Document-returning version plus a thin text wrapper (the text wrapper keeps the existing call shape working):

```python
def _pdf_document(path: Path) -> Any:
    """Parsed digisearch Document for a PDF (carries page segments)."""
    try:
        from digisearch.ingestion.registry import ParserRegistry
    except ImportError as exc:  # pragma: no cover - exercised when digisearch missing
        raise RuntimeError(
            "PDF vault notes require digisearch. Install with: pip install -e ./digisearch"
        ) from exc
    return ParserRegistry().parse(path)


def _pdf_text(path: Path) -> str:
    """Extract PDF text via digisearch parsers (no pdfplumber vendored here)."""
    doc = _pdf_document(path)
    return (doc.content or "").strip() + "\n"
```

- [ ] **Step 4: Add the segment helpers**

Add these two module-private helpers to the same file, immediately after `_markdown_title_from_body`:

```python
def _segment_slug(segment: Segment) -> str:
    """Filesystem-safe suffix identifying a segment within its parent document."""
    page = segment.metadata.get("page")
    if isinstance(page, int):
        return f"p{page:03d}"
    raw = segment.label.split(":", 1)[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return (slug or f"seg{segment.index:03d}")[:48]


def _hub_body(title: str, child_names: list[str]) -> str:
    """Body for the parent note linking every child segment note in order."""
    lines = [f"# {title}", "", f"This document has {len(child_names)} sections:", ""]
    lines.extend(f"- [[{name}]]" for name in child_names)
    lines.append("")
    return "\n".join(lines)
```

Add the imports these need at the top of the file (merge into the existing import block):

```python
import re

from digisearch.core.models import Segment
from digisearch.ingestion.segmenters.heading import heading_segments
```

Note `re` may already be imported (the file uses `_H1 = re.compile(...)`) — do not duplicate it.

- [ ] **Step 5: Return segments from `_note_body_for`**

Change `_note_body_for` to return a 3-tuple. Update its signature and docstring:

```python
def _note_body_for(
    classified: ClassifiedPage, workspace: Workspace
) -> tuple[str, str, list[Segment]]:
    """Return (title, markdown body, structural segments) for a classified page."""
```

Then update each `return` inside it:

- The PDF branch: replace `body = _pdf_text(...)` and its return with:

```python
        parsed = _pdf_document(workspace.root / entry.local_path)
        body = (parsed.content or "").strip() + "\n"
        return title, body, list(parsed.segments)
```

- Every other branch that currently returns `title, body` becomes `return title, body, heading_segments(body)`.
- Every early/fallback branch that currently returns `title, ""` becomes `return title, "", []`.

- [ ] **Step 6: Write children plus a hub in the main loop**

In `write_vault_notes`, change the unpack line and replace the single `vault.write_note(...)` call. The loop body becomes:

```python
    for classified in workspace.iter_classified():
        if classified.page_class not in _VAULT_PAGE_CLASSES:
            continue
        try:
            title, body, segments = _note_body_for(classified, workspace)
        except Exception:
            continue
        if not body.strip():
            continue
        url = classified.page.final_url or classified.page.url
        slug = slug_for_url(url)
        tags = ["onboard", classified.page_class.value, f"client:{manifest.client}"]
        frontmatter: dict[str, Any] = {
            "title": title,
            "tags": tags,
            "source_url": url,
            "content_type": classified.page.content_type or classified.page_class.value,
            "ingested_at": ingested_at,
            "client": manifest.client,
            "page_class": classified.page_class.value,
            "type": ("api_reference" if classified.page_class == PageClass.openapi else "reference"),
            "status": "published",
        }
        if len(segments) < 2:
            vault.write_note(
                slug,
                frontmatter=frontmatter,
                body=body,
                subdir=manifest.vault_subdir,
                overwrite=True,
            )
            written += 1
            continue
        child_names: list[str] = []
        for segment in segments:
            child_name = f"{slug}__{_segment_slug(segment)}"
            child_fm = {
                **frontmatter,
                "title": f"{title} — {segment.label}",
                "segment_label": segment.label,
                "segment_index": segment.index,
                "parent_doc": slug,
            }
            vault.write_note(
                child_name,
                frontmatter=child_fm,
                body=segment.text if segment.text.endswith("\n") else segment.text + "\n",
                subdir=manifest.vault_subdir,
                overwrite=True,
            )
            child_names.append(child_name)
            written += 1
        vault.write_note(
            slug,
            frontmatter={**frontmatter, "segment_count": len(segments)},
            body=_hub_body(title, child_names),
            subdir=manifest.vault_subdir,
            overwrite=True,
        )
        written += 1
    return written
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/scripts/docs_onboard/test_write_vault_notes.py -m unit -v --tb=short`
Expected: PASS — including the pre-existing tests in that file (they assert today's single-note behavior and must stay green, since a single-section markdown doc yields 1 segment).

- [ ] **Step 8: Run the whole docs_onboard suite**

Run: `pytest tests/scripts/ -m "unit or baseline" -v --tb=short`
Expected: PASS

Run: `ruff check scripts tests`
Expected: no findings.

- [ ] **Step 9: Commit**

```bash
git add scripts/docs_onboard/write_vault_notes.py tests/scripts/docs_onboard/test_write_vault_notes.py
git commit -m "feat(docs_onboard): write per-segment vault notes with a linking hub note"
```

---

### Task 7: OpenAPI per-operation enrichment

**Files:**
- Modify: `scripts/docs_onboard/ingest_openapi.py:20-54`
- Test: `tests/scripts/docs_onboard/test_ingest_openapi.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks directly; its output is consumed by `heading_segments` (Task 3) via Task 6's vault path.
- Produces: `openapi_to_markdown(path: Path, *, note_type: str) -> str` — unchanged signature, enriched output. Emits one `##` heading per operation, formatted `## {METHOD} {path}`, so the generic heading segmenter yields one segment per endpoint with no OpenAPI-specific splitting logic.

**Contract preserved:** still exactly ONE `.md` file, ONE `ClassifiedPage`, and ONE `SourceMapEntry` per spec file — `ingest_openapi_sources` is not changed at all, and its return int still counts spec files.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/docs_onboard/test_ingest_openapi.py`:

```python
"""Tests for OpenAPI markdown enrichment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digisearch.ingestion.segmenters.heading import heading_segments

from scripts.docs_onboard.ingest_openapi import openapi_to_markdown

pytestmark = pytest.mark.unit

_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "digikey", "version": "0.1.0", "description": "Auth plane."},
    "paths": {
        "/v1/oauth/token": {
            "post": {
                "summary": "Exchange API key for JWT",
                "description": "Trades an opaque API key for a short-lived RS256 JWT.",
                "tags": ["oauth"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/TokenRequest"}
                        }
                    }
                },
                "responses": {"200": {"description": "Successful Response"}},
            }
        },
        "/healthz": {"get": {"summary": "Liveness", "tags": ["health"], "responses": {}}},
    },
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "digikey.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_emits_one_heading_per_operation(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert "## GET /healthz" in md
    assert "## POST /v1/oauth/token" in md


def test_includes_operation_detail(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert "Trades an opaque API key" in md
    assert "TokenRequest" in md
    assert "oauth" in md


def test_operations_become_heading_segments(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert any(label.endswith("GET /healthz") for label in labels)
    assert any(label.endswith("POST /v1/oauth/token") for label in labels)


def test_unparsable_spec_still_returns_markdown(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    md = openapi_to_markdown(bad, note_type="api_reference")
    assert md.startswith("# OpenAPI (unparsed)")


def test_output_ends_with_single_newline(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert md.endswith("\n")
    assert not md.endswith("\n\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/docs_onboard/test_ingest_openapi.py -m unit -v --tb=short`
Expected: FAIL — `assert '## GET /healthz' in md` fails (current output is only a bare path list).

- [ ] **Step 3: Rewrite `openapi_to_markdown`**

In `scripts/docs_onboard/ingest_openapi.py`, replace the entire body of `openapi_to_markdown` (keeping its exact signature) with:

```python
def openapi_to_markdown(path: Path, *, note_type: str) -> str:
    """Build a markdown body from an OpenAPI document: one ``##`` section per operation."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"# OpenAPI (unparsed)\n\nSource: `{path.name}`\n\n```\n{raw[:8000]}\n```\n"
    info = data.get("info") if isinstance(data, dict) else None
    title = "OpenAPI"
    version = ""
    description = ""
    if isinstance(info, dict):
        title = str(info.get("title") or title)
        version = str(info.get("version") or "")
        description = str(info.get("description") or "")
    paths = data.get("paths") if isinstance(data, dict) else None
    path_items = sorted(paths.items()) if isinstance(paths, dict) else []
    lines = [
        f"# {title}",
        "",
        f"> OpenAPI reference (`{note_type}`)" + (f" v{version}" if version else ""),
        "",
    ]
    if description:
        lines.extend([description.strip(), ""])
    lines.append(f"Source file: `{path.as_posix()}`")
    lines.append("Content-Type: application/openapi+json")
    lines.append("")
    for route, item in path_items:
        if not isinstance(item, dict):
            continue
        for method, operation in sorted(item.items()):
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            lines.extend(_operation_lines(route, method, operation))
    return "\n".join(lines).rstrip("\n") + "\n"
```

- [ ] **Step 4: Add the operation formatter and method set**

Add these to the same file, immediately above `openapi_to_markdown`:

```python
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def _schema_name(schema: dict[str, Any]) -> str:
    """Readable name for a schema node: the $ref tail, or its declared type."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    declared = schema.get("type")
    return str(declared) if declared else "object"


def _operation_lines(route: str, method: str, operation: dict[str, Any]) -> list[str]:
    """Markdown for one operation as its own ``##`` section."""
    lines = [f"## {method.upper()} {route}", ""]
    summary = str(operation.get("summary") or "").strip()
    if summary:
        lines.extend([f"**{summary}**", ""])
    detail = str(operation.get("description") or "").strip()
    if detail:
        lines.extend([detail, ""])
    tags = operation.get("tags")
    if isinstance(tags, list) and tags:
        lines.extend([f"Tags: {', '.join(str(t) for t in tags)}", ""])
    operation_id = operation.get("operationId")
    if operation_id:
        lines.extend([f"Operation ID: `{operation_id}`", ""])

    parameters = operation.get("parameters")
    if isinstance(parameters, list) and parameters:
        lines.append("Parameters:")
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            schema = parameter.get("schema")
            kind = _schema_name(schema) if isinstance(schema, dict) else "object"
            required = " (required)" if parameter.get("required") else ""
            location = parameter.get("in", "query")
            lines.append(f"- `{parameter.get('name', '?')}` in {location}: {kind}{required}")
        lines.append("")

    body = operation.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content")
        if isinstance(content, dict):
            for media_type, media in sorted(content.items()):
                schema = media.get("schema") if isinstance(media, dict) else None
                if isinstance(schema, dict):
                    lines.append(f"Request body (`{media_type}`): {_schema_name(schema)}")
            lines.append("")

    responses = operation.get("responses")
    if isinstance(responses, dict) and responses:
        lines.append("Responses:")
        for code, response in sorted(responses.items()):
            text = str(response.get("description") or "") if isinstance(response, dict) else ""
            schema_note = ""
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                for media in content.values():
                    schema = media.get("schema") if isinstance(media, dict) else None
                    if isinstance(schema, dict):
                        schema_note = f" → {_schema_name(schema)}"
                        break
            lines.append(f"- `{code}`: {text}{schema_note}".rstrip())
        lines.append("")
    return lines
```

Add `Any` to the file's typing import at the top (the file currently imports no `typing` names):

```python
from typing import Any  # score:allow untyped any — OpenAPI JSON nodes are open dicts
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scripts/docs_onboard/test_ingest_openapi.py -m unit -v --tb=short`
Expected: PASS (5 passed)

- [ ] **Step 6: Sanity-check against a real spec**

Run:

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from scripts.docs_onboard.ingest_openapi import openapi_to_markdown
md = openapi_to_markdown(Path('docs/openapi/digikey.json'), note_type='api_reference')
print(md[:1200])
print('--- operation sections:', md.count('\n## '))
"
```
Expected: 6 operation sections for `digikey.json` (its 6 paths each have exactly one method), each showing summary/tags/responses.

- [ ] **Step 7: Run the whole docs_onboard suite**

Run: `pytest tests/scripts/ -m "unit or baseline" -v --tb=short`
Expected: PASS

Run: `ruff check scripts tests`
Expected: no findings.

- [ ] **Step 8: Commit**

```bash
git add scripts/docs_onboard/ingest_openapi.py tests/scripts/docs_onboard/test_ingest_openapi.py
git commit -m "feat(docs_onboard): emit per-operation OpenAPI sections for segmentation"
```

---

### Task 8: Wire `SegmentAwareChunker` into the ingest path + update ARCHITECTURE.md

**Files:**
- Modify: `digisearch/src/digisearch/server.py:665`
- Modify: `digisearch/src/digisearch/cli.py:18,21`
- Modify: `digisearch/ARCHITECTURE.md:85,255-270,381,446`
- Test: `tests/ds/test_ingest_segments.py` (create)

**Interfaces:**
- Consumes: `SegmentAwareChunker` (Task 5), PDF segments (Task 4).
- Produces: nothing downstream — this is the terminal wiring task.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_ingest_segments.py`:

```python
"""End-to-end check that segmented documents chunk along their boundaries."""

from __future__ import annotations

import pytest

from digisearch.core.models import Document, Segment
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker


@pytest.mark.unit
def test_segment_metadata_reaches_chunks() -> None:
    doc = Document(
        id="doc-1",
        content="ignored",
        source="https://example.com/guide.pdf",
        doc_type="pdf",
        segments=[
            Segment(index=0, label="page:1", text="intro text", metadata={"page": 1}),
            Segment(index=1, label="page:2", text="body text", metadata={"page": 2}),
        ],
    )
    chunks = SegmentAwareChunker().chunk(doc)
    assert {c.metadata["segment_label"] for c in chunks} == {"page:1", "page:2"}


@pytest.mark.unit
def test_unsegmented_document_is_unchanged_by_wiring() -> None:
    doc = Document(id="doc-2", content="plain text body", source="s", doc_type="txt")
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == "plain text body"
```

- [ ] **Step 2: Run test to verify it passes already**

Run: `pytest tests/ds/test_ingest_segments.py -m unit -v --tb=short`
Expected: PASS — this test guards the contract Task 5 established; it should be green before the wiring change and stay green after.

- [ ] **Step 3: Wire the chunker into the server ingest path**

In `digisearch/src/digisearch/server.py`, change the chunker construction at line ~665 from `RecursiveChunker()` to `SegmentAwareChunker()`, and add the import alongside the existing `RecursiveChunker` import:

```python
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
```

Do the same at both `digisearch/src/digisearch/cli.py` call sites (lines 18 and 21).

Leave `digisearch/src/digisearch/atlas_ingest.py` on `RecursiveChunker()` — Atlas research rows are Supabase text with no structural segments, so wrapping them adds an indirection with no benefit.

- [ ] **Step 4: Run the full digisearch suite**

Run: `pytest tests/ds/ -m unit -v --tb=short`
Expected: PASS

- [ ] **Step 5: Update ARCHITECTURE.md**

In `digisearch/ARCHITECTURE.md`, make four edits:

1. Line ~85 table row — change `| Core models (\`Document\`, \`Chunk\`, \`Query\`, \`Result\`, \`SearchResponse\`) | Implemented | \`core/models.py\` |` to include `Segment`.

2. §4 Data Model (line ~255) — append a `segments` line to the `Document` ASCII tree, moving the `└──` box-drawing character to the new last entry:

```
├── chunks: list[Chunk]        # populated after chunking
└── segments: list[Segment]    # structural units (PDF page, md section); empty = unstructured
```

3. Line ~381 tree comment — change `models.py              # Document, Chunk, Query, Result, SearchResponse` to append `, Segment`.

4. Line ~446 public-surface table — change `| \`Chunk\`, \`Document\`, \`Query\`, \`Result\` | \`digisearch.core.models\` |` to include `Segment`.

Then add a short subsection under §4 documenting the segmentation behavior:

```markdown
#### Segmentation

`Document.segments` is an opt-in structural overlay. Parsers that can detect real
boundaries populate it — `PDFParser` emits one segment per page (`page:12`), and
`ingestion/segmenters/heading.py` splits markdown (including converted HTML and
OpenAPI reference markdown) on `##`/`###` boundaries with a breadcrumb label.
Everything else leaves it empty and behaves exactly as before.

`SegmentAwareChunker` chunks within segments and never across them: a segment at or
under `DEFAULT_CHUNK_CHARS` (2000 chars ≈ 512 tokens) becomes exactly one chunk;
only oversized segments are sub-split by the inner chunker. Every chunk carries
`segment_label` and `segment_index` in its metadata so citations can name the page
or section.
```

- [ ] **Step 6: Validate docs**

Run: `make doc-check`
Expected: no broken internal links.

- [ ] **Step 7: Run everything and commit**

Run: `make test-unit`
Expected: PASS

Run: `ruff check digisearch/src scripts tests && ruff format --check digisearch/src scripts tests`
Expected: no findings.

```bash
git add digisearch/src/digisearch/server.py digisearch/src/digisearch/cli.py digisearch/ARCHITECTURE.md tests/ds/test_ingest_segments.py
git commit -m "feat(digisearch): wire SegmentAwareChunker into ingest and document segmentation"
```

---

## After the plan

Two things are deliberately **not** in this plan, per the spec's non-goals:

1. **Re-ingesting the existing digithings/OCC corpora.** Once this ships, a clean re-ingest is needed to actually regenerate segment-aware notes and chunks. Follow the verified single-process procedure recorded in `docs/projects/digithings/GAPLOG.md` (2026-08-11 rows) — wipe the collection, one process only, verify 1:1 doc_id-per-source before syncing.
2. **PDF image/diagram intelligence** — tracked separately as issue #2148.

Also still open from earlier work: issue #2138 (`run_onboard.py` silently duplicates content when `--workdir` is reused) and #2122 (Chroma `add()` vs `upsert()` non-idempotency). Neither blocks this plan, but #2138 in particular should be fixed before the re-ingest in (1), or the re-ingest can silently duplicate again.
