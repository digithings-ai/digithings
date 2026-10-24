# Semantic ticket search for the OCC chat (local multilingual embeddings)

> **Issue:** #4756 — `feat(zammad): semantic ticket search over local multilingual embeddings`
> **Status:** spec (implementation not started; no branch yet)
> **Related:** #4717 (windowed aggregate tools, shipped), #2438 (multilingual EmbeddingProvider spike, OPEN),
> #2436 (gold eval set for occ_help docs domain, OPEN — ticket domain needs its own pairs),
> #3879 (remote-MCP dotless-DNS guard), #2306 (OCC tenant prompt, shipped)

**Goal:** answer topic-style OCC questions ("most popular ticket topic of the past month",
"how do I fix <problem statement>") with semantic retrieval over ticket content + metadata,
durable as the ticket system grows.

**Non-goals:** title normalization hacks and term-count heuristics (explicitly rejected —
fragile across DE/EN spelling variants); Zammad-side taxonomy changes (customer instance,
out of our hands); Reports-API integration (profile-gated, coarse buckets); indexing
tickets into the `occ_help` docs corpus (privacy-sensitive cross-corpus mixing, separate epic
if ever); any write path to Zammad (server stays read-only by design).

**Mandate:** the embedding model is LOCAL and MULTILINGUAL. Ticket content contains customer
PII; it must not leave our boundary to a third-party embedding API. No new external network
exposure (so polling sync, not a Zammad webhook — a webhook would trip the human gate).

---

## 1. Global constraints (bind every implementation task)

- Read-only fail-closed: GET only, `zammad error:` paths, validate-before-HTTP, never partial results.
- Privacy: `internal:true` articles never reach anonymous chat (two-layer rule, §6);
  customer emails masked `k***@domain` at render (existing `_mask_customer`).
- BFF pattern: new MCP tool runs server-side in `zammad-mcp`; no upstream URL, token, or
  store path reaches the browser.
- `ruff check` + `ruff format` clean, line length 100; Pydantic v2 models for new configs;
  lowercase digi names in prose (digisearch, digichat, digivault, digigraph).
- Polars-only applies to digisearch core; `scripts/zammad_mcp/` stays stdlib (+ `polars`
  via `digisearch.core.tables` where aggregation is needed). No pandas anywhere.
- Every change traces to #4756 (`task/4756-<slug>` branch or `Fixes #4756` in PR body).
- Human gate NOT triggered: no digikey/auth/JWT, no live-trading, no new external service
  (Zammad + Chroma-local + ONNX-local are all in-boundary already-wired deps).

---

## 2. Architecture (three parts, one trust boundary)

```
Zammad REST (read-only)          stack container                  digigraph → digichat
                         ┌─────────────────────────┐
tickets/search ──poll──▶ │ zammad-sync (new)       │  Chroma PersistentClient
by_ticket/{id} ─────────▶ │  chunk → embed → upsert │  path CHROMA_PATH (new volume)
/users/{id} (names) ────▶ │  high-water: updated_at │  collection: zammad_tickets
                         └─────────────────────────┘
                                           ▲
                         ┌─────────────────┴───────┐
                         │ zammad-mcp (existing)   │──▶ prefixed tool
                         │  + zammad_semantic_     │    zammad_semantic_search
                         │    search (new tool)    │
                         └─────────────────────────┘
```

- **Sync** (`scripts/zammad_mcp/sync.py`, new supervisor program `zammad-sync`): poll
  `GET /api/v1/tickets/search?query=updated_at:>=<high-water>&sort_by=updated_at&order_by=desc&limit=500`,
  fetch articles per changed ticket, chunk, embed, upsert. Cadence 15 min (freshness SLA).
- **Store**: Chroma `PersistentClient(path=$CHROMA_PATH)`, reusing
  `digisearch/indexes/backends/chroma.py` (already a container dep via
  `digisearch[chromadb]` — zero new dependencies). Collection `zammad_tickets` with
  `embedding_model_id` metadata pin (existing convention).
- **Query**: new MCP tool `zammad_semantic_search` in `scripts/zammad_mcp/server.py`;
  metadata `where`-pre-filter → vector rank → ticket IDs + snippets + scores →
  drill-down via existing `get_ticket` / `aggregate_tickets`.

Keyword search stays for what it is good at (ticket numbers `#28312`, exact IDs, quoted
field filters). Docstrings teach the split: exact → `search_tickets`, aboutness → 
`zammad_semantic_search`.

---

## 3. Embedding model (local multilingual — the one hard requirement)

- **Acceptance bar:** a ticket-domain gold set of ~30 (query, known-relevant ticket) pairs,
  half German half English, drawn from real tickets; winning model needs recall@5 ≥ 0.8
  with a frozen seed. (#2436 covers the occ_help docs domain — different corpus, not reusable.)
- **Candidates to evaluate:** `gte-multilingual-base` (#2438 names it; ~300M params, ONNX
  CPU-viable) vs `paraphrase-multilingual-MiniLM-L12-v2` (~118M, smaller/faster, weaker).
  MiniLM-L6-v2 (current `minilm` provider) is English-centric and is the fallback only —
  it does not meet the multilingual mandate.
- **Integration:** new provider branch in `digisearch/embedding/factory.py::_build_raw_provider`
  (currently raises for anything but minilm/openai), selectable via existing
  `DIGISEARCH_EMBEDDING_PROVIDER` env; model file pre-downloaded at Docker build time
  (never at runtime — fail-closed if absent); wrapped in the existing
  `wrap_embedding_pipeline` (cache → batch → provider).
- **Re-embed procedure:** collection metadata pins `embedding_model_id`; model change =
  wipe collection + full backfill (§5 covers the mechanics). Backfill cost is linear and
  bounded (157 tickets today; procedure must stay hands-off at 10k+).
- **Image size budget:** flag the winning model's weight size in the implementation PR;
  if it pushes the stack image unacceptably, split the sync/embed sidecar into its own
  image before optimizing the model.

---

## 4. Collection schema (`zammad_tickets`)

Document chunk (one per article + one title-chunk per ticket):

| field | content |
|---|---|
| `text` | title-chunk: ticket title; article-chunk: `title + "\n" + article body` (title prepend keeps chunks self-describing) |
| `ticket_id` / `number` | internal id + display number (both searchable for drill-down) |
| `article_idx` | 0 = title-chunk, else article position (upsert key = `(ticket_id, article_idx)`) |
| `is_internal` | bool — internal-note chunks embedded (resolution search needs them) but excluded by default at query (§6) |
| `state` / `group` / `priority` | names as stored (filterable) |
| `customer_id` / `owner_id` | ints (filterable; names resolved at render, never stored raw PII beyond what Zammad holds) |
| `created_at` / `updated_at` / `close_at` | ISO dates (range-filterable) |

Chunking via `digisearch.chunking` (repo rule); article bodies cap at existing
`MAX_ARTICLE_BODY_CHARS=4000` before chunking so embed inputs stay bounded.

---

## 5. Sync protocol

- **Backfill:** paginate `list_tickets`-equivalent windowed search to cover history, embed
  + upsert all; idempotent (upsert key), safe to re-run. Also the cold-start story: if
  `$CHROMA_PATH` is empty at boot, sync runs a full backfill before serving — this is the
  durability answer for container-disk uncertainty (see §9 risk 1).
- **Incremental:** persist high-water mark `max(updated_at)` (sidecar file next to the
  Chroma path); each run queries `updated_at:>=<mark>`, re-embeds changed tickets wholly
  (delete-then-upsert by `ticket_id` — handles article edits, state changes, and
  rare deletes uniformly; no tombstone protocol needed).
- **Fail-closed:** Zammad unreachable → keep serving stale index + `stale_since` header in
  tool output (age computed from sync-state file); embed failure → abort run, keep old
  vectors, alert via supervisor log. Never serve a half-written window.
- **Observability:** sync-state file `{last_run, last_success, tickets_indexed, chunks, high_water}`;
  surfaced via extended `ticket_report` header (one line, no new tool).

---

## 6. Privacy & security (load-bearing — review must pin these)

1. **Two-layer internal exclusion:** (a) query-time — `include_internal=false` default adds
   `is_internal != true` to the Chroma `where`-clause; (b) render-time — existing
   internal-article strip in `formatting.py` stays untouched as backstop. Tests pin both
   layers independently (internal chunk present in store, absent from default results AND
   from rendered text).
2. **PII:** customer emails masked at render (existing); no new PII stored beyond Zammad
   fields; embeddings never leave the container (local model — this is the point of §3).
3. **No new exposure:** sync is outbound-poll only; MCP transport keeps existing host
   allowlist; BFF pattern unchanged (store path never leaves the server).

---

## 7. Query tool contract

`zammad_semantic_search(query: str, top_k: int = 8, since_days: int | None = None,
state_category: open|closed|all = "all", include_internal: bool = false)
-> {results: [{ticket_id, number, title, score, snippet, state}], index_stale_since: str | None}`

- Empty/blank query → `ZammadError` (fail-closed, mirrors `search_tickets`).
- `since_days` → `updated_at` lower bound in the `where`-clause (date-only literals,
  per the known full-timestamp parsing gotcha).
- `state_category` reuses the `build_query` open/closed derivation (custom states like
  `gelöst von Dev` classify by `state_type_id`, never by name).
- Scores are cosine similarities (document scale in docstring; no calibrated threshold —
  the model judges relevance, the tool ranks).
- Hybrid guidance in docstring: exact identifiers → `search_tickets`; topics, symptoms,
  "how do I fix X" → this tool; counts/rankings → `aggregate_tickets` on the result IDs.

---

## 8. Worked example — "most popular topic of the past month"

1. `zammad_semantic_search("recurring customer problems", since_days=30, top_k=30)`
   → candidate pool with scores (semantic net, catches DE/EN paraphrases keyword search misses).
2. `aggregate_tickets(group_by="title", since_days=30)` → exact counts per phrasing.
3. Model clusters candidates into topics, cross-checks cluster sizes against exact counts,
   pulls `get_ticket` for one exemplar per top topic.
4. Answer cites ticket numbers + counts; chain is auditable (IDs at every step).

---

## 9. Risks & open questions

1. **Cloudflare container disk durability** (does `$CHROMA_PATH` survive redeploys?).
   Mitigated by cold-start backfill (§5) regardless of the answer — but verify before
   promising freshness SLAs that assume a warm store.
2. **German retrieval quality** — the gold eval (§3) is the gate; if neither candidate
   clears recall@5 ≥ 0.8, escalate (better model vs. scoped hybrid) rather than shipping
   weak semantic search.
3. **Sync lag vs. support urgency** — 15 min SLA means just-filed tickets are invisible
   semantically; docstring must say so (fresh tickets → keyword search).
4. **Corpus growth** — brute-force-fine today; Chroma ANN covers 100k+ vectors; the
   re-embed procedure (§3) must be re-verified if the model changes after growth.

---

## 10. Work breakdown (for implementation planning, not yet a plan)

1. Ticket-domain gold eval set (~30 DE/EN pairs) + recall harness.
2. Multilingual provider eval (candidates, decision, factory branch, build-time download).
3. `sync.py` + backfill + incremental + sync-state + supervisor stanza + volume wiring.
4. `zammad_semantic_search` tool + `format_semantic` (+ stale header) + docstring recipes.
5. Tests: mocked-HTTP suites + privacy pins (both layers) + eval gate + stack test + docs
   (README workflows, ARCHITECTURE.md tables).
6. Live proof: the 10 analytics questions incl. top-topic-of-month, before/after vs keyword.
