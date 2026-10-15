## digisearch Integration (#199)

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

Finalized research documents in Supabase `documents` are indexed
into digisearch's vector store so the execution exploration agent and
digichat can semantically search the research library.

**Helper module:** `digisearch/src/digisearch/research_ingest.py`

- `ingest_research_payload(row, *, index_name=None)` — pure function: takes a
  pre-fetched `documents` row dict, runs it through the standard
  `RecursiveChunker(512, 64)` (same as `POST /ingest`), stamps research
  metadata onto each chunk, and upserts into the configured digisearch
  index. Returns an `IndexedDocument` summary.
- `ingest_research_document(client, date, document_key, *, index_name=None)` —
  Supabase-aware wrapper: fetches the row by `(date, document_key)` then
  forwards to the pure helper. Returns `None` when the row is absent so
  late or out-of-order triggers no-op rather than raise.
- `fetch_research_row(client, date, document_key)` — read-only single-row
  selector mirroring the access pattern in `supabase_io.load_prior_context`.

**Index name:** the default index for research is `"research"`,
overridable via the `DIGISEARCH_ATLAS_INDEX` env var. Keep it separate
from the generic `"default"` index so cross-tenant queries cannot leak.

**Chunk metadata stamped at ingest:**

| Key | Source | Filter use |
| --- | --- | --- |
| `source` | constant `"research"` | tag every research chunk |
| `date` | row `date` (`YYYY-MM-DD`) | `eq` match |
| `date_ordinal` | derived `int YYYYMMDD` | range `gt/ge/lt/le` |
| `doc_type` | row `doc_type` | `eq` (e.g. `Daily Digest`) |
| `segment` | row `segment` | `eq` (e.g. `technology`) |
| `sector` | row `sector` | `eq` (analyst notes) |
| `run_type` | row `run_type` (legacy column) | `eq` — historical rows may show `baseline`/`delta`; new daily runs use `cadence=daily` |
| `category` | row `category` | `eq` (default `research`) |
| `document_key` | row `document_key` | `eq` natural key |
| `title` | row `title` | display only |
| `asset_class` | hoisted from `payload.asset_class` | `eq` |

`date_ordinal` exists because the in-memory stub and the Chroma backend
compare numerically for `gt/ge/lt/le` — ISO date strings would fail
coercion and silently drop the filter. Callers should pass integers like
`20260420` to the MCP tool's `date_from_ymd` / `date_to_ymd` args.

**MCP tool:** `search_strategies(query, top_k, date_from_ymd, date_to_ymd,
doc_type, segment, sector, run_type, index_name)` in
`digisearch/src/digisearch/mcp_server.py`. Returns up to `top_k` typed
hits with shape `{chunk_id, doc_id, score, content, content_length,
metadata}`. The tool defaults to the research index and AND-combines all
non-null filters via digisearch's structured-filter pipeline (`Query.filters
= {"structured": [...]}`); empty filter args become a plain hybrid search.

**Idempotency:** `ingest_research_payload` derives both `Document.id` and
chunk ids deterministically from `(date, document_key)`. Re-ingesting the
same row replaces the prior chunks rather than appending duplicates — the
contract every test in `tests/ds/test_research_ingest.py` asserts. The same
deterministic ids let the Chroma backend's id-collision upsert behavior do
the same job in production.

**Triggering — current state (pull-based):** research's `publish_phase`
(`digiquant/src/digiquant/research/phases/publish_phase.py`)
writes to Supabase. A poller or follow-up explicit call is responsible
for driving `ingest_research_document` against each `(date, document_key)`
returned in `state.published`.

**Punted — digistore eventing (#57):** real-time research publish →
digisearch reindex via digistore events is out of scope for #199 because
digistore is not yet implemented. Once it lands, the natural wiring is
either (a) call `ingest_research_document` directly at the end of
`publish_phase`, or (b) push the natural keys onto a queue that
`ingest_worker.py` (currently a placeholder per
`digisearch/ARCHITECTURE.md`) drains.

---

<!-- #1736 -->
