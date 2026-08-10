# Content-aware segmentation for digisearch chunking + digivault notes

**Date:** 2026-08-11
**Status:** Approved (design), not yet implemented

## Problem

Today, every source document ingested by `scripts/docs_onboard/` and `digisearch`'s
`/ingest` path is treated identically regardless of structure:

- **digivault**: one note per document, whole body, no matter the size. A
  100+ page PDF becomes a single vault note — too much context for one chat
  turn to usefully draw on.
- **digisearch**: `RecursiveChunker` (`digisearch/src/digisearch/ingestion/chunkers/recursive.py`)
  splits the flattened document text into ~512-**character** chunks
  (`chunk_size: int = 512`) with 64-char overlap, ignoring any natural
  document structure. Two concrete problems found this session:
  1. **PDF page boundaries are discarded before chunking.** `PDFParser`
     (`digisearch/src/digisearch/ingestion/parsers/pdf.py`) extracts text
     page-by-page but joins every page into one flat string
     (`"\n".join(...)`) before returning a `Document`. No page number
     survives to chunk metadata, so a citation can never say "page 12."
  2. **512 is characters, not tokens** (~128 tokens) — well below the
     ~512-token (~2000-character) chunk size validated as a strong default
     across current RAG benchmarks (see Research below).
- **OpenAPI ingestion is shallow**, not badly chunked: `openapi_to_markdown()`
  (`scripts/docs_onboard/ingest_openapi.py`) emits only a title, description,
  and a bare list of path strings — no parameters, no request/response
  schemas. There's nothing substantial to chunk per-operation yet.

## Research (informs the design, not just decoration)

- Page-level chunking won NVIDIA's PDF benchmark (0.648 accuracy, lowest
  variance across document types) — validates page as the natural PDF unit.
  [(Firecrawl)](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- Naive semantic/"smart" chunking can *underperform* plain structural
  chunking when it over-fragments: Vectara's Feb 2026 benchmark (50 academic
  papers, 7 strategies) ranked recursive 512-**token** splitting first at 69%
  accuracy; semantic chunking scored 54%, producing fragments averaging only
  ~43 tokens. [(Vectara)](https://www.vectara.com/blog/is-semantic-chunking-worth-the-computational-cost)
  Lesson: structural boundaries (page, heading) are good; don't chase finer
  fragmentation beyond that.
- ~512 tokens (~2000 characters) is the validated default chunk size.
  [(Firecrawl)](https://www.firecrawl.dev/blog/best-chunking-strategies-rag),
  [(Denser)](https://denser.ai/blog/rag-chunking-strategies/)
- Hierarchical (parent/child) chunking — small chunks for retrieval
  precision, larger parent context (page/section) for the LLM — is the
  documented way to get both precision and completeness.
  [(Databricks)](https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089),
  [(Weaviate)](https://weaviate.io/blog/chunking-strategies-for-rag)
- Metadata enrichment (page number, heading path, source) lifts QA accuracy
  from ~50-60% to ~72-75%, independent of the chunking algorithm.
  [(Unstructured)](https://unstructured.io/blog/chunking-for-rag-best-practices)
- HTML: convert to Markdown, then split on heading structure — matches this
  pipeline's existing `html_to_markdown.py` step.
  [(Zilliz)](https://zilliz.com/learn/beginner-guide-to-website-chunking-and-embedding-for-your-genai-applications),
  [(IBM)](https://www.ibm.com/architectures/papers/rag-cookbook/chunking)
- Overlap value is contested (one Jan 2026 analysis found no measurable
  benefit); current 64/512 (~12.5%) is defensible either way and is **not**
  changed by this design.
  [(Airbyte)](https://airbyte.com/agentic-data/ag-document-chunking-best-practices)

## Goals

1. Generic and pluggable — must work for any onboarding client (digithings,
   OCC, or a future one), not hardcoded to today's two corpora.
2. PDF pages and Markdown headings become real structural boundaries that
   chunks and vault notes respect and never cross.
3. A segment (page or heading-section) **is** the chunk whenever it fits a
   size ceiling — no forced sub-splitting of short pages. Only segments that
   exceed the ceiling get sub-split, by the existing recursive splitter,
   re-tuned to a token-based (~512 token / ~2000 char) size instead of the
   current 512 characters.
4. Every chunk and every vault note carries its segment's citation metadata
   (page number / heading path / operation) regardless of which path
   (whole-segment or sub-split) produced it.
5. Fully backward compatible: segmentation is an **opt-in overlay**. A
   `Document` that doesn't populate segments behaves exactly as it does
   today — no other consumer of `digisearch`'s `Document`/`Chunk` models
   breaks.
6. OpenAPI specs become genuinely useful content (full per-operation detail)
   rather than a bare path list — which then benefits from the same generic
   heading segmenter with no OpenAPI-specific splitting logic.

## Non-goals (this design)

- **PDF image/diagram intelligence** (vision-based extraction or per-region
  OCR for diagrams/charts embedded in an otherwise-text-layer PDF). Today's
  OCR fallback (`pytesseract`+`pdf2image`) is all-or-nothing — it only
  engages when the *entire* PDF has no text layer. Improving in-page image
  understanding is a distinct, separately-scoped problem from chunking and
  is tracked as its own issue (filed alongside this spec, not designed here).
- Changing the 64-char/12.5% chunk overlap — evidence is mixed and this
  isn't the lever under discussion.
- Re-ingesting the existing digithings/OCC corpora — this spec covers the
  pipeline change only. A follow-up clean re-ingest (same verified,
  single-process procedure established in `docs/projects/digithings/GAPLOG.md`
  and `docs/projects/online-compliance-center/GAPLOG.md`) is a separate,
  later operational step once the code ships.

## Design

### Data model

`digisearch/src/digisearch/core/models.py`:

- New `Segment` model: `{index: int, label: str, text: str, metadata: dict}`.
  `label` examples: `"page:12"`, `"heading:Authentication > Rotating Keys"`,
  `"operation:POST /v1/ingest"`.
- `Document` gains an optional field: `segments: list[Segment] | None = None`.
  `None` (the default) means "no known structure" — identical to today's
  behavior everywhere downstream.

### Parsers — who populates `segments`

- **`PDFParser`** (`digisearch/src/digisearch/ingestion/parsers/pdf.py`):
  already iterates pages internally to extract text (`pdfplumber`/`pymupdf`
  both parse page-by-page). Change it to also collect each page's text as a
  `Segment(label=f"page:{n}")`, in addition to the existing flattened
  `content` string (kept for any consumer that isn't segment-aware yet).
- **New generic heading segmenter** — a small pure function,
  `heading_segments(markdown_text: str) -> list[Segment]`, in a new module
  (e.g. `digisearch/src/digisearch/ingestion/segmenters/heading.py`,
  alongside the existing `chunkers/` package). Splits on `#`/`##`/`###`
  boundaries; each segment's label is a heading breadcrumb (e.g.
  `"heading:Authentication > Rotating Keys"`). Returns an empty list for
  content with no headings (callers fall back to `segments=None` behavior).
  Applied to:
  - `MarkdownParser` output.
  - Crawled HTML *after* the existing `html_to_markdown.py` conversion step.
  - The enriched OpenAPI markdown (see below) — this is what turns "one
    thin note per API service" into "one note per operation," for free.
- Everything else (CSV, DOCX, short plaintext, short marketing HTML with no
  headings) leaves `segments=None` — unchanged, one-chunk/one-note behavior.

### digisearch chunking

- `RecursiveChunker.chunk_size` default changes from `512` (characters) to a
  token-approximated ceiling of **~2000 characters** (~512 tokens at a
  ~4-chars/token heuristic — no new tokenizer dependency introduced). This
  is a direct, immediate fix applied globally, independent of segmentation.
- New segment-aware orchestration wraps the chunker: if `doc.segments` is
  populated, each segment's text is chunked **independently** — a segment
  under the size ceiling comes back as exactly one chunk (satisfying
  "segment = chunk when it fits"); a segment over the ceiling is sub-split
  by the same recursive logic, never crossing into a neighboring segment's
  text. If `doc.segments` is `None`, the whole document is chunked exactly
  as today (single pass, no segment boundaries) — this is the backward-compat
  path.
- Every resulting chunk's metadata gets its owning segment's `label` merged
  in alongside the existing fields (`doc_id`, `chunk_index`, `source_url`,
  etc.), so a citation can say "page 12" or "§ Authentication > Rotating
  Keys" instead of just a bare chunk index.

### digivault vault notes

`write_vault_notes.py`: when a classified page's parsed `Document` has
segments, write **one note per segment** instead of one note for the whole
document:

- Note name: `<doc-slug>__<segment-label-slug>` (e.g.
  `admin-guide-occ__p012`, `digikey-openapi__post-v1-ingest`).
- Each segment note's frontmatter includes `segment_label` and
  `parent_doc` (pointing back to the source document's slug).
- One **parent "hub" note** per source document is also written, holding
  the document-level metadata/summary and an ordered list of
  `[[wikilink]]`s to every child segment note — using digivault's existing
  wikilink/backlink support (`Vault.write_note` / `Vault.rename` already
  maintain these).
- **Degenerate case:** if segmentation yields exactly one segment (e.g. a
  single-page PDF), no hub note is created — the one segment note stands
  alone as the document's note, avoiding pointless indirection for content
  that didn't actually need splitting.
- When `segments` is absent (`None`), today's single one-note-per-document
  behavior is unchanged.

### OpenAPI enrichment

`ingest_openapi.py`'s `openapi_to_markdown()` is rewritten to emit one
`##`-level heading section per operation — method, path, summary,
parameters, request body schema, response schema — pulled from the same
parsed OpenAPI JSON already loaded today, instead of the current bare path
list. This content then flows through the generic heading segmenter above
with no OpenAPI-specific segmentation code required.

### Backward compatibility / rollout

This ships as a pure additive capability:

- No existing `Document`/`Chunk` consumer breaks — `segments` is optional
  and defaults to `None`.
- No corpus is re-ingested as part of this work. Once merged, a follow-up
  clean re-ingest (same single-process, verified procedure used for the
  digithings/OCC corpora this session) is a separate, later step to actually
  regenerate segment-aware notes/chunks for existing clients.
- The `chunk_size` default change (512 chars → ~2000 chars) takes effect
  immediately for any *new* ingestion, including the non-segmented fallback
  path — existing indexed content is unaffected until re-ingested.

## Testing

- `heading_segments()`: markdown with headings returns correctly-labeled,
  ordered segments; markdown with no headings returns `[]`.
- `PDFParser`: emits exactly one segment per PDF page, in order, matching
  page count; flattened `content` still present for non-segment-aware
  callers.
- Segment-aware chunking: a segment under the size ceiling returns exactly
  one chunk; a segment over the ceiling returns multiple chunks, none of
  which contain text from a neighboring segment.
- `write_vault_notes.py`: a segmented document produces N+1 notes (N
  segments + 1 hub) with correct wikilinks; a non-segmented document
  produces exactly 1 note (regression check against today's behavior).
- `openapi_to_markdown()`: given a fixture OpenAPI spec, output contains one
  `##` heading per operation with parameters/schemas present.

## Separately filed (not part of this spec's implementation)

An issue for PDF image/diagram intelligence — evaluating vision-model-based
extraction or per-region OCR for diagrams/charts/screenshots embedded in
otherwise-text-layer PDFs, beyond today's all-or-nothing
no-text-layer-at-all OCR fallback.
