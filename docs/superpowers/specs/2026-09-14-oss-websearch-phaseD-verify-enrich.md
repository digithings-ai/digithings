# Phase D — OSS Verify + Enrich Graph (Websets-like async list building)

**Date:** 2026-09-14
**Owner:** digisearch
**Status:** implementation spec (write-only, no code in this doc)
**Program:** open-source EXA equivalent (EXA kept as paid alternative)

## Erratum (T0, 2026-09-15) — landed-surface alignment

This spec was amended before any Phase D code, per the preflight delta audit
(`.superpowers/sdd/2026-09-14-oss-websearch-phaseD-verify-enrich/phaseD-delta-report.md`).
Where this spec and the landed Phase A/B/C code disagree, landed code wins; the audit's
rulings R1–R13 and intra-spec flags I1–I9 are applied below. Fixture vendoring (R9) landed
with this erratum at `tests/ds/fixtures/websets/` (see its `README.md` for provenance).
Scope of the erratum: **docs + fixtures only, no production code**.

| Ruling | Applied effect |
|---|---|
| R1 | Consumes/Interfaces + rg gate rewritten to the landed `search_web` / `SearXNGWebSearchProvider.search` / `fetch_markdown` / `Citation` / `normalize_url` surface (audit D1–D7, D21) |
| R2 | Candidate page markdown is `fetch_markdown` only; `ingest_url` explicitly out of scope (I1) |
| R3 | Recall seam is `search_web`; no paging exists — v1 caps `max_results ≤ 10` and diversifies queries |
| R4 | `provider: Literal[…]` param struck; `backend: Literal["oss","exa"]` label instead |
| R5 | Store concurrency exactly per Phase C: one connection per instance/thread, WAL + `busy_timeout=5000`, no module `threading.Lock` |
| R6 | Store home keeps `DIGISEARCH_WEBSETS_DB` + `{DIGI_WORKSPACE}` and adopts Phase C's cwd fallback |
| R7 | 3-attempt / 5s-25s delivery + `webhook_deliveries` ledger kept; Phase C signing core shared so `X-digi-signature` is byte-identical |
| R8 | POLL-ONLY v1: webset tick-driver wording struck; monitors are created/listed/triggered manually; scheduled driver deferred (follow-up) |
| R9 | Fixtures vendored (this commit); spec references the vendored paths |
| R10 | MCP tool names unprefixed `websets_*`; orchestrator manifest keeps prefixed `digisearch_websets_*` |
| R11 | Items newest-first (UI pagination); events oldest-first for append-only tailing with explicit `after=` semantics (justified in § Interfaces) |
| R12 | Orchestrator wiring = dispatch branches + manifest entries + `ORCHESTRATOR_TOOL_NAMES` constants |
| R13 | Human gate stays on the webhook-delivery task (new egress) |

## Goal

Build the dataset-building capability of the OSS web-search program: an
async-first, Websets-like verify + enrich pipeline owned by digisearch.

A caller submits a natural-language query + desired count + 1–5 per-result
verification criteria + up to ~10 typed per-item enrichments. The system
builds the list over seconds to minutes (async, never a synchronous tool
call): candidates are generated, each candidate is verified against every
criterion before admission, admitted items are enriched field-by-field with
per-field citations, and the caller polls, receives webhooks, or reads events
until the webset reaches the `idle` terminal state. Finished datasets export
to CSV/JSON.

This phase is the highest build-first value in the program: live testing
showed EXA Websets returning `401: Upgrade to a Pro plan` on the current key
tier, so verification + enrichment-as-a-service is paywalled. The OSS path
ships first; EXA Websets stays a drop-in paid alternative behind the same
object semantics.

Non-goals: replacing Phase A candidate search, replacing Phase B structured
synthesis/grounding, real-time (sub-second) answers, corpus ingest writes.

## Consumes / Produces

- **CONSUMES — Phase A (search/fetch), landed surface only:** candidate recall runs on
  `search_web(WebSearchRequest)` (`digisearch.web_search.service:94` — search only, no
  fetch enrichment), the single recall seam and stub boundary (R3). Candidate
  page markdown comes from `fetch_markdown(url)` (`web_search/fetch.py:52`), which
  downloads once through the digifetch SSRF guard and runs the landed
  `extract_markdown` (`-> str`, `web_search/extractor.py:42`); neither indexes.
  `ingest_url()` is **out of scope** — it writes the corpus via `ingest_source`
  (`pipeline/url_ingest.py:188-194`), violating § Non-goals (R2; flag I1 resolved).
  Direct import within `digisearch` (same-package rule); Phase D never shells out to raw
  SearXNG, never calls `run_web_search` (that wrapper adds its own page-fetch enrichment
  outside the D semaphore), and never calls a backend module directly. Recall backends
  are the landed `auto|searxng|ddgs` (`web_search/service.py:24`) with the landed
  searxng→ddgs failover inside `_search_only` (`service.py:80-91`); a sidecar outage
  fails over to ddgs — never silently to EXA (no EXA fallback path exists on the OSS
  leg). Domain bias uses the landed `include_domains` / `exclude_domains` fields
  (`web_search/models.py:26-27`).
- **CONSUMES — Phase B (structured synthesis with grounding):** verification
  verdicts and enrichment extraction use the Phase B structured-output path
  (schema-pinned LLM extraction whose outputs carry citations). The landed output
  contract is `{"content", "grounding", "text"}` (`web/structured.py:254-266`; wire
  wrapper `{content, grounding}` at `structured.py:136-144`). Enrichment field values
  are only admitted together with their citations.
- **PRODUCES — dataset-building capability:** async websets with verified,
  enriched, citable items; poll/webhook/event delivery; CSV/JSON export; a
  company/people enrichment path that reproduces EXA `category=company`
  inline `entities` (including funding history) for digiquant company
  tracking; a provider capability matrix (free-tier vs pro) recording the
  live 401 finding.

## Architecture

### Async-first execution model (NOT a synchronous tool)

```
create_webset(...) -> {id, status: "running"}          # returns immediately
  │
  ▼  background worker (asyncio tasks on server lifespan)
candidate generation (search_web(WebSearchRequest) per query variant,
  max_results ≤ 10 per call — § count vs max_results; page markdown via
  fetch_markdown())
  │ per candidate
  ▼
verification gate (1-5 criteria; every rule must pass before admission)
  │ admitted only
  ▼
per-item enrichment (typed fields, each with citations)
  │
  ▼  events appended at each transition
status -> "idle" (terminal: all searches settled AND all items settled —
  verification not pending and every enrichment field terminal)
  │
   ├── poll:   GET /v1/websets/{id} + GET .../items
   ├── push:   webhooks (HMAC-signed; shared Phase C signing core)
   │           (Phase C `Watch`es are NOT a fan-out target — see § Interfaces;
   │           a C↔D bridge is a named follow-up, not this spec.
   │           POLL-ONLY v1: there is no scheduled tick driver — webset
   │           monitors are created/listed/triggered manually; the driver is a
   │           named follow-up, see § Tasks, re-scoped sequence note)
   └── export: GET .../export?format=csv|json
```

- No endpoint blocks on pipeline completion. MCP/orchestrator tools are
  split accordingly: a `websets_create` tool (returns the webset id) plus
  `websets_get`, `websets_add_search`, `websets_list_items`, `websets_events`,
  and `websets_export` tools for the follow-up turns.
- In-process asyncio worker (lifespan-managed task group) with a `Runner`
  protocol so a future out-of-process worker can replace it without changing
  the store, service, or HTTP shapes. No celery, no redis, no new infra.
- Persistence is a SQLite-backed `WebsetStore` (same precedent as
  `EmbeddingCache`): one file read from `DIGISEARCH_WEBSETS_DB`, default
  `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3`, resolved by a module-level
  `get_store(db_path=None)` exactly like Phase C's module-level
  `get_store` (`monitors/store.py:368`; there is no `MonitorStore.get_store`
  method — the audit's D10 form is struck). Resolution order mirrors Phase C
  (`monitors/store.py:53-55,375-378`): explicit path → `DIGISEARCH_WEBSETS_DB` →
  `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3` → `./.digisearch/websets.sqlite3`
  (cwd fallback for host/test runs; the old "never CWD" claim is struck per R6/D9 —
  the landed Phase C precedent does fall back to cwd). JSON columns for
  criteria/enrichments/events; `WAL` mode + `PRAGMA busy_timeout=5000` on every
  connect; concurrency is exactly Phase C's (`monitors/store.py:20-25,159-166`):
  **one `sqlite3` connection per instance, thread-bound (`check_same_thread`
  default), one store per thread/request — no module-level `threading.Lock`**
  (R5; the old lock claim is struck). All blocking I/O from the async runner
  goes through `asyncio.to_thread` at the async boundary (concrete lifecycle in
  § Async lifecycle — there is no `asyncio.to_thread`/task-registry precedent in
  `server.py` to inherit). Unit tests run against a temp file and construct the
  store in the handler/test thread; production path never touches
  `DIGISEARCH_ALLOW_STUB`.
- Verification modes: `llm` (default, via digillm structured completion,
  one verdict per criterion with reasoning + references) and `rules`
  (deterministic offline checks: domain allowlist, recency window, keyword
  presence). `rules` exists so unit tests and key-less installs stay green;
  production websets default to `llm` and fail closed: an item whose verification
  cannot produce verdicts is **rejected** (never admitted silently) once its
  candidate pass settles — see § Verification gate for the terminal-state rule
  (flag I9 resolved).
- EXA compatibility shim: `providers/exa_websets.py` is dormant without
  `EXA_API_KEY` (same fail-closed pattern as `web_exa.py`) and maps the
  known `401 Upgrade to a Pro plan` response to a typed
  `ExaWebsetsProRequiredError`, declared explicitly as
  `class ExaWebsetsProRequiredError(ExaError)` in
  `providers/exa_websets.py` (subclass — never a sibling — so existing
  `except ExaError` handlers keep catching it with unchanged meaning; `ExaError`
  lands at `digisearch/web_exa.py:48` and is caught today at `server.py:954` and
  `mcp_server.py:245`), so callers can distinguish "key missing"
  (`ExaNotConfiguredError`) from "tier paywalled". The landed Phase C monitor
  adapter maps the same paywall to `ExaAdapterError("exa_tier_gated")`
  (`monitors/exa_adapter.py:327-343`) — the shim's subclass choice is the
  websets-side equivalent and keeps `except ExaError` working. When a Pro key
  exists, the shim translates the OSS webset request into EXA Websets calls and
  normalizes responses back into the OSS object shapes below — the HTTP/MCP
  surface does not change.

### EXA Websets semantic mirror (drop-in contract)

Object names, terminal state, and event names mirror EXA Websets API
semantics (shapes captured from EXA docs; field naming adapted to repo
conventions — lowercase, no `Digi` prefix):

| Concept | OSS object | Key fields |
|---|---|---|
| webset | `Webset` | `id` (`ws_` + uuid4-hex, no new dep — `uuid.uuid4().hex` per `digibase.http` precedent), `object="webset"`, `status`: `running` \| `idle` \| `failed` \| `cancelled`, `workspace_id: str \| None = None` (tenant isolation, § Cross-phase alignment), `backend: "oss" \| "exa" = "oss"` (R4 label, § Cross-phase alignment), `searches`, `enrichments`, `created_at`, `updated_at` |
| search | `WebsetSearch` | `id` (`wss_` + uuid4-hex), `webset_id`, `query`, `count` (1–100, default 10 — target **verified** items for this search, NOT a result-page size; see `max_results` note below), `status`: `running` \| `idle` \| `failed` \| `cancelled` (flag I6 resolved: `cancel_webset` settles every non-terminal search as `cancelled`), `criteria` (1–5 rules), `backend: "oss" \| "exa" = "oss"` (R4 label) |
| item | `WebsetItem` | `id` (`wsi_` + uuid4-hex), `webset_id`, `url`, `title`, `verification`: `pending` \| `verified` \| `rejected` (`pending` is in-flight/queued only — settled at candidate-pass end, § Verification gate), `criteria_results[]` (verdict + reasoning + references per rule), `enrichments{field: EnrichedField}` (per-field value + citations + terminal status), `created_at` |
| enrichment | `EnrichmentDef` | `id` (`wse_` + uuid4-hex), `name`, `type`: `text` \| `number` \| `date` \| `url` \| `email` \| `phone` \| `options` \| `company_profile`, `description`, `options[]` (only for `options`), `status` |
| webset monitor | `WebsetMonitor` | `id` (`wsm_…`, prefix kept), `object="webset_monitor"`, `webset_id`, `interval_seconds >= 60` (aligned with Phase C `WatchSchedule.interval_seconds`; `cadence_s` struck), `webhook_url`, `created_at`. POLL-ONLY v1 (R8): the interval is recorded schedule metadata for the deferred driver, never executed on a tick; v1 monitor ops are create/list/trigger-manually. There is deliberately **no `status`/`paused` field** — with no scheduled driver a pause state has no observable effect (flag I4 resolved); the `active\|paused` lifecycle belongs to the deferred driver follow-up (§ Tasks, re-scoped sequence note). A webset monitor is explicitly NOT a Phase C `Watch` (R7e; bare `Monitor` is banned — it collides with the Phase C `Watch`/`MonitorRun` family) |
| event | `WebsetEvent` | `id`, `webset_id`, `type`: `item.created` \| `item.enriched` \| `webset.idle` \| `webset.failed`, `payload`, `created_at` (append-only log; delivery state lives in `webhook_deliveries`, never on event rows) |

- `Citation{url, title="", excerpt=""}` (`extra="forbid"`) is owned by the shared
  web-grounding atom `digisearch.web_search.citation` (`citation.py:12`) — the landed
  owner, re-exported by `web_search/__init__.py:3` and aliased by Phase B as
  `GroundingCitation` (`web/grounding_models.py:17`). `WebsetItem`/`EnrichedField` code
  **imports** `Citation` (and `normalize_url`, `citation.py:22`, where URL identity is
  needed) from `digisearch.web_search.citation` — never redefined, never copied (R1).
  `CriterionResult.references` and `EnrichedField.citations` are both `list[Citation]`;
  Phase B joins on exact `url` match against the same type, and Phase C already imports
  the same `normalize_url` (`monitors/dedup.py:36`).
- `count` (webset/search target verified items, 1–100) vs `max_results` (the landed
  Phase A per-call result-page size, 1–10 — `web_search/models.py:28`; the audit's
  `num_results`/`SearXNGBackend.query` names are phantom): different concepts, different
  names, never interchanged. `num_results` 1–100 is an **EXA-shaped** field
  (`server.py:1038`, `Watch.num_results` `monitors/models.py:100`) and appears in
  websets only as the shim's outbound translation. The recalled page size passed into
  `WebSearchRequest.max_results` is `min(10, …)`. **No paging parameter exists**
  (`pageno` is fixed at 1, `web_search/searxng_provider.py:32`; `search_web` exposes no
  page arg) — v1 reaches `count` by **query diversification** (variant queries and
  domain bias across successive `search_web` calls) and accepts the `max_results ≤ 10`
  ceiling per call (R3); a paging extension is a later phase. Because `count` is a target
  and never a backend page size, there is no clamp-from field to record (the Phase C
  `num_results_clamped_from` precedent, `monitors/runner.py:67,324-346`, does not
  apply — audit D25).

- `idle` is the only success-terminal state (webset and search level).
  A webset is `idle` when every search is settled (`idle`/`failed`/`cancelled`,
  flag I6) **and** no item is `pending` verification **and** no item has a
  `pending` enrichment field left (flag I9: verification-pending items are
  settled by the candidate-pass end rule in § Verification gate, so they can never
  block `idle` indefinitely). Enrichment-terminal per (item, field):
  `resolved` (value + ≥1 citation) | `unresolved` (failed with reasoning,
  terminal — keeps `idle` reachable when enrichments fail) | `skipped`
  (never attempted because the webset was cancelled/failed first). An item
  emits `item.enriched` when all its fields are terminal AND at least one
  field resolved; an item whose every field is `unresolved`/`skipped`
  settles silently (still counts as settled for `idle`).
- Events emitted: `item.created` (admitted after verification),
  `item.enriched` (all requested enrichments settled for the item, ≥1
  resolved), `webset.idle`, `webset.failed`. Rejected candidates emit no
  item event (they remain queryable via `items?verification=rejected` for
  audit). Events are generation-scoped: each re-settling flow — `add_search`,
  an `add_enrichment` backfill run, `trigger_monitor` — runs as a new
  `WebsetSearch` and re-emits its terminal events, while the webset status
  never goes backwards (after first completion it stays `idle`, and refresh
  progress is read from the new search's status + events, never from a webset
  status flip — § Async lifecycle). Tests assert the event log as a
  **multiset + `webset.idle`-last** (exact-sequence assertions are banned —
  the concurrent runner does not guarantee inter-item order).

### Verification gate

- Each `WebsetSearch` carries 1–5 `VerificationCriterion{name, rule,
  description}` entries (natural-language rules, e.g. "company is a
  photonics startup founded after 2018").
- `verify_item` evaluates every rule against the candidate's `fetch_markdown`
  output (non-indexing page markdown, truncated to 6000 chars before the
  LLM call — truncation budget recorded as an explicit divergence from
  Phase B's `snippet ≤2000c` / `max_synthesis_chars=12000`: verification
  needs a fuller page than synthesis snippets; see § Cross-phase
  alignment) and returns one `CriterionResult{criterion, passed, reasoning,
  references: list[Citation]}` per rule (shared `Citation`, R1 — title
  defaults to `""`, excerpt carries the supporting quote). Item is admitted
  only if all rules pass; otherwise `rejected` with the failing reasons
  retained.
- Verification-pending settlement (flag I9 resolved): `verification="pending"`
  is the in-flight/queued state only. When a search's candidate pass finishes,
  every item still `pending` (verification errored, page markdown empty, etc.)
  settles `rejected` with one synthetic `CriterionResult` per criterion
  (`passed=false`, `reasoning="verification unavailable: <reason>"`,
  `references=[]`) — fail-closed (never admitted) but terminal, so the
  search/webset can reach `idle`. A crashed run leaves items `pending`; startup
  resume re-drives them (§ Async lifecycle) and only a completed pass settles
  them.
- digismith spans for verification carry only webset/item ids, rule names,
  and pass/fail counts — never page bodies or chunk content.

### Enrichment engine + per-field citations (auditable by construction)

- Each `EnrichmentDef` resolves to one `EnrichedField{value, citations:
  list[Citation], status: resolved | unresolved | skipped, error}` per
  item (shared `Citation`, R1). `citations` is mandatory on success: a
  field with an empty value or empty citations is `status="unresolved"`,
  never silently filled. See § terminal-state rule for when `unresolved` /
  `skipped` settle the item.
- Max 10 active enrichments per webset (11th create → HTTP 400).
- Extraction order per item: the already-fetched `fetch_markdown` page text
  first; if a field is still unresolved, one targeted `fetch_markdown` of the item
  URL (or a follow-up `search_web` call for the field, e.g. "Acme Corp Series B
  amount", then `fetch_markdown` of the hit) and a Phase B schema-pinned
  extraction limited to that field.
- Type validation is strict (pydantic v2): `number` must parse as float,
  `date` as ISO-8601 date, `url`/`email`/`phone` against format validators,
  `options` must equal one of `options[]`.

### Company/people enrichment (digiquant company tracking)

EXA `category=company` returns inline `entities[{type: company,
properties{name, foundedYear, description, workforce, headquarters,
financials{fundingTotal, fundingLatestRound}, webTraffic}}]` with funding
history (live sample **vendored at T0** at
`tests/ds/fixtures/websets/s5_category_company.json` — NuCicer
$16M total / Series A 2025-07-01 $11.5M; Pollen Systems $3.45M; Orchard
$26.4M; provenance and sanitization notes in
`tests/ds/fixtures/websets/README.md`; the `/tmp/exa-review/` path is scratch
and MUST NOT be referenced by code or tests). The OSS path reproduces this as:

1. Candidate generation via `search_web(WebSearchRequest)` with company-domain
   bias (`include_domains` from the caller's enrichment config +
   funding-press domains) and query diversification to reach `count` (R3) — no
   EXA `category` param on the OSS path.
2. Fetch each candidate page with `fetch_markdown` only (non-indexing, R2);
   already-fetched pages are reused rather than refetched.
3. Structured extraction (Phase B) into `CompanyEntity` mirroring the EXA
   properties shape: `name, founded_year, description, workforce_total,
   hq_city, hq_country, funding_total, funding_rounds[{name, date,
   amount}]` — every scalar carries **per-scalar provenance**: `provenance:
   dict[str, list[Citation]]` keyed by field name (e.g.
   `provenance["funding_total"] = [...]`). A single flat `citations[]`
   wrapper is banned — it cannot attribute which citation supports which
   scalar. A scalar with zero citations is `unresolved` for that field
   (recorded in `provenance` as an empty list + reasoning on the entity).
4. FX normalization: all round amounts normalize to USD at extraction time
   using the **ECB euro foreign-exchange reference rates** vendored snapshot
   `tests/ds/fixtures/websets/fx_ecb_snapshot.json` (offline default;
   refreshed per live eval in Task 8). A non-USD amount with no rate in the
   snapshot → that round is `unresolved` with reasoning (never guessed).
5. Funding-history merge: round events extracted across pages are
   normalized (name lowercased, date to ISO month, amount to USD) and
   merged by `(name, date)`; `funding_total` is the sum of merged rounds.
   Reconciliation (no vacuous cases, no single-page veto): if ≥1 page
   claims an explicit total, the **median** of claimed totals must be
   within 1% of the summed rounds or `funding_total` is `unresolved` with
   reasoning; if NO page claims a total, the sum stands as `funding_total`
   (provenance = union of round citations). A round is admitted on
   **quorum**: ≥2 independent page citations, or 1 citation from the
   company's own domain (press release); single third-party mentions stay
   `unresolved`. This replaces any "any page vetoes" reading — one page's
   silence never blocks a quorum-admitted round.
6. Entity merge across candidates by normalized domain + name similarity;
   conflicting scalars keep the value with more independent citations and
   record the loser in `alternatives[]` (each alternative keeps its own
   `citations: list[Citation]` — no silent overwrite).
7. A `company_profile` enrichment type (member of the `EnrichmentDef.type`
   enum, § Architecture table) bundles the merged `CompanyEntity` onto
   the item so digiquant company tracking reads one field. The bundling symbol is
   named `company_profile_field` (flag I8 resolved — it is part of `enrich.py`'s
   public symbol list, § File Structure): `company_profile_field(entity:
   CompanyEntity) -> EnrichedField` returns the `resolved` field carrying the
   entity value plus the union of the entity's provenance citations, or
   `unresolved` with reasoning when the entity has no resolved scalars.

## Tech Stack

Python 3.12, pydantic v2 (strict typing), httpx only for webhooks/EXA shim
(no `exa-py`), webhook signing shared with Phase C
(`monitors/delivery.py:220-223`, `X-digi-signature` byte-identical),
asyncio lifespan worker, SQLite store (stdlib `sqlite3`, JSON columns, Phase C
connection discipline), polars for CSV export (never pandas), digillm structured
completion for `llm` verification/extraction, digifetch-backed Phase A
fetch path (composed, never reimplemented: `fetch_markdown`), ruff line-length 100.

## File Structure (exact paths)

```
digisearch/src/digisearch/websets/__init__.py        # public re-exports only
digisearch/src/digisearch/websets/models.py          # Webset, WebsetSearch,
                                                     # VerificationCriterion,
                                                     # CriterionResult,
                                                     # WebsetItem,
                                                     # EnrichmentDef (type enum
                                                     #  incl. company_profile),
                                                     # EnrichedField,
                                                     # CompanyEntity (+ provenance
                                                     #  dict[str, list[Citation]]),
                                                     # WebsetMonitor (bare Monitor
                                                     #  banned per R7e),
                                                     # WebhookConfig,
                                                     # WebsetEvent.
                                                     # Citation (+ normalize_url
                                                     #  where needed) is IMPORTED
                                                     #  from
                                                     #  digisearch.web_search.citation
                                                     #  (shared atom, R1) — never
                                                     #  redefined here
digisearch/src/digisearch/websets/store.py           # WebsetStore (SQLite CRUD)
                                                     # + get_store() env ctor
                                                     # (DIGISEARCH_WEBSETS_DB,
                                                     #  workspace default + cwd
                                                     #  fallback per R6)
digisearch/src/digisearch/websets/verify.py          # verify_item (+ rules mode)
digisearch/src/digisearch/websets/enrich.py          # enrich_item, merge_company_entities,
                                                     # reconcile_funding_history,
                                                     # company_profile_field
digisearch/src/digisearch/websets/runner.py          # Runner protocol + AsyncioRunner
                                                     # + lifespan task registry
                                                     # + resume_incomplete_websets
                                                     # + backfill_enrichment
digisearch/src/digisearch/websets/events.py          # append_event, list_events,
                                                     # deliver_webhook (HMAC-SHA256,
                                                     #  shared Phase C signing core)
                                                     # + webhook_deliveries ledger
                                                     #  keyed (webhook_id, event_id)
digisearch/src/digisearch/websets/export.py          # export_json, export_csv (polars)
digisearch/src/digisearch/websets/service.py         # facade: create_webset,
                                                     # get_webset, list_items,
                                                     # add_search,
                                                     # add_enrichment (+ backfill),
                                                     # remove_enrichment,
                                                     # create_monitor,
                                                     # list_monitors,
                                                     # trigger_monitor,
                                                     # add_webhook, rotate_webhook_secret,
                                                     # list_events,
                                                     # cancel_webset,
                                                     # export_webset
digisearch/src/digisearch/websets/providers/__init__.py
digisearch/src/digisearch/websets/providers/exa_websets.py  # dormant paid shim,
                                                     # ExaWebsetsProRequiredError(ExaError)
tests/ds/test_websets_models.py                      # @pytest.mark.unit (all files)
tests/ds/test_websets_store.py
tests/ds/test_websets_verify.py
tests/ds/test_websets_enrich.py
tests/ds/test_websets_runner.py
tests/ds/test_websets_export.py
tests/ds/test_websets_company.py
tests/ds/test_websets_api.py
tests/ds/fixtures/websets/README.md                  # fixture provenance (T0)
tests/ds/fixtures/websets/s5_category_company.json   # vendored EXA company sample (T0)
tests/ds/fixtures/websets/exa_401_pro_required.json  # vendored 401 body (T0)
tests/ds/fixtures/websets/fx_ecb_snapshot.json       # ECB FX snapshot (T0)
```

Modified (thin adapters only, existing auth patterns unchanged):

```
digisearch/src/digisearch/server.py                  # POST/GET webset routes +
                                                     # orchestrator dispatch branches (R12)
digisearch/src/digisearch/mcp_server.py              # websets_* tools (unprefixed, R10)
digisearch/src/digisearch/orchestrator_tools.py      # digisearch_websets_* constants +
                                                     # manifest entries (R10/R12)
digisearch/ARCHITECTURE.md                           # new § websets section
```

## Interfaces (exact signatures PRODUCED)

Import rule (R1/R2/R3 — no shape copies, landed owners only): `websets/models.py`
imports `Citation` (plus `normalize_url` where URL identity is needed) from
`digisearch.web_search.citation`; Phase B synthesis is called by direct import;
candidate recall calls `digisearch.web_search.service.search_web` and page
markdown calls `digisearch.web_search.fetch.fetch_markdown` by direct import
(same package) — never `ingest_url`, never `run_web_search`; HTTP (`POST
/v1/orchestrator_invoke`, `POST /v1/research_turn`) is used only at
process/component boundaries (digiclaw, digigraph, external callers) with
the caller's service JWT. Regression gate (R1 — replaces the unsatisfiable
pre-erratum gate; audit D21/I2); this command must return zero matches:

```
rg -n "web_providers|SearXNGBackend|SearXNGDegradedError|ingest_url|run_web_search|/tmp/exa-review|DIGIWEBSETS_DB_PATH|cadence_s|monitors\.sqlite3" \
  digisearch/src/digisearch/websets/ tests/ds/test_websets_*.py
```

(The gate bans phantom modules, out-of-scope corpus ingest, scratch paths, the
struck store env var/cadence name, and Phase C store bleed — it deliberately does
NOT ban the landed names this spec consumes: `search_web`, `fetch_markdown`,
`Citation`, `normalize_url`, `WebSearchRequest`, `max_results`, `recency_days`.)

All service functions live in `digisearch.websets.service` and are sync
(store I/O) except `run_webset_async`, which schedules background work and
returns immediately:

```python
def create_webset(
    *,
    query: str,
    count: int = 10,  # 1..100; target VERIFIED items (not a page size; cf. max_results)
    criteria: list[VerificationCriterion] | list[dict[str, str]],
    enrichments: list[EnrichmentDef] | list[dict[str, object]] | None = None,
    verification_mode: Literal["llm", "rules"] = "llm",
    workspace_id: str | None = None,  # tenant isolation; "datatap" rejected (§ Cross-phase)
    store: WebsetStore | None = None,
) -> Webset:
    """Create a webset + its initial search; schedule the run; return status=running.

    No provider/backend selector param (R4 — the `provider: Literal[...]` param is
    struck): the OSS path always uses `search_web`, and EXA-websets selection is the
    shim's concern (key presence) with the `backend: Literal["oss","exa"]` label
    recorded on the created object."""

def get_webset(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Return the webset or raise WebsetNotFoundError."""

def list_items(
    webset_id: str,
    *,
    verification: Literal["verified", "rejected", "pending"] | None = None,
    limit: int = 50,  # clamped 1..200
    cursor: str | None = None,  # last item id; None = from head (newest-first)
    store: WebsetStore | None = None,
) -> tuple[list[WebsetItem], str | None]:
    """List items NEWEST-first (R11 — UI pagination reads the newest first);
    verification filter defaults to all (audit reads rejected). Returns
    (page, next_cursor | None). Cursor semantics: `cursor` is the last item id of
    the previous page; the next page contains only items OLDER than that id
    (created_at-desc, id-desc tie-break); `next_cursor` is the last id of this
    page when more rows exist, else None. An unknown cursor raises
    `WebsetStoreError(code="cursor_not_found")` rather than silently restarting."""

def add_search(
    webset_id: str,
    *,
    query: str,
    count: int = 10,  # 1..100; target verified items for THIS search
    criteria: list[VerificationCriterion] | list[dict[str, str]] | None = None,
    store: WebsetStore | None = None,
) -> WebsetSearch:
    """Attach a follow-up search to a running/idle webset and schedule its
    run. Missing criteria inherits the webset's initial criteria."""

def add_enrichment(
    webset_id: str,
    enrichment: EnrichmentDef | dict[str, object],
    *,
    store: WebsetStore | None = None,
) -> EnrichmentDef:
    """Attach an enrichment (max 10 active) and backfill it onto verified
    items. Backfill execution path: the call itself only attaches the def
    (status running) and enqueues item ids lacking the field; the lifespan
    worker drains the queue via `runner.backfill_enrichment(webset_id,
    enrichment_id)` (same semaphore + per-item containment as the main
    run); each settled item emits `item.enriched` when § terminal-state
    conditions hold."""

def remove_enrichment(
    webset_id: str, enrichment_id: str, *, store: WebsetStore | None = None
) -> None:
    """Detach an enrichment; existing resolved values are retained on items."""

def export_webset(
    webset_id: str,
    *,
    fmt: Literal["csv", "json"] = "json",
    store: WebsetStore | None = None,
) -> tuple[str, str]:
    """Return (content, media_type). csv via polars; only verified items export."""

def create_monitor(
    webset_id: str,
    *,
    interval_seconds: int = 3600,  # >= 60; refresh-cadence METADATA, NOT a Phase C Watch
    webhook_url: str | None = None,  # https public URL; None = poll-only
    store: WebsetStore | None = None,
) -> WebsetMonitor:
    """Record a refresh cadence on a webset.

    POLL-ONLY v1 (R8): no scheduled tick driver executes `interval_seconds` in this
    phase — the value is stored schedule metadata for the deferred driver follow-up,
    and refreshes happen only via `trigger_monitor` (manual). Phase C watches are
    never created, addressed, or notified here."""

def list_monitors(webset_id: str, *, store: WebsetStore | None = None) -> list[WebsetMonitor]:
    """List a webset's monitors newest-created first (poll-only v1 operator surface)."""

def trigger_monitor(
    webset_id: str, monitor_id: str, *, store: WebsetStore | None = None
) -> Webset:
    """Manually refresh: start a new settling pass as a new `WebsetSearch`
    generation that re-runs the webset's searches against the current candidate
    set (the v1 substitute for the deferred tick driver). Webset status never
    goes backwards — after first completion it stays `idle`, and the refresh is
    observed via the new search's status + events, not via a webset status
    flip. Returns the webset. Unknown ids raise `WebsetStoreError` with code
    `webset_not_found` / `monitor_not_found`."""

def add_webhook(
    webset_id: str,
    *,
    url: str,  # https public URL (same SSRF/private-IP rejection as Phase C validate_delivery)
    events: list[str],  # subset of item.created|item.enriched|webset.idle|webset.failed
    store: WebsetStore | None = None,
) -> WebhookConfig:
    """Register a webhook; the secret is server-generated
    (`secrets.token_urlsafe(32)`), stored alongside the webhook record
    (never in logs), and returned ONCE in this response. Rotation via
    `rotate_webhook_secret` (24h overlap) below. Delivery signing is the shared
    Phase C core (`monitors/delivery.py:220-223`) so the header bytes are identical."""

def rotate_webhook_secret(webset_id: str, webhook_id: str, *, store: WebsetStore | None = None) -> WebhookConfig:
    """Generate a new secret with 24h overlap: the old secret stays valid
    until `previous_expires_at` (now+24h), then is dropped. Returns the
    record with the NEW secret in cleartext once."""

def list_events(
    webset_id: str,
    *,
    after: str | None = None,  # event id cursor (last seen); None = from the beginning
    limit: int = 50,  # clamped 1..200
    store: WebsetStore | None = None,
) -> tuple[list[WebsetEvent], str | None]:
    """Cursor-paged event read, OLDEST-FIRST (R11). Justification: the events table
    is an append-only log and the primary consumer is a tailing client that holds the
    last-seen event id and polls for strictly newer rows; oldest-first makes `after`
    a stable forward cursor (newest-first would force re-anchoring every poll and can
    skip rows appended between pages under concurrent writes). Cursor semantics:
    `after` is the last event id the caller has seen; the page returns events
    strictly newer than it, oldest-first; `next_cursor` is this page's last event id
    when more rows exist, else None; an unknown `after` raises
    `WebsetStoreError(code="cursor_not_found")`."""

def cancel_webset(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Set webset status=cancelled; the runner stops scheduling new items (in-flight
    item finishes its current field, then yields — no mid-LLM task.cancel);
    unattempted fields become `skipped`; every search not already `idle`/`failed`
    is settled `cancelled` (flag I6). Terminal: no further transitions."""

async def run_webset_async(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Drive one webset to idle: candidates -> verify -> enrich -> events. Never raises
    past WebsetNotFoundError; per-item failures mark items, webset-level failure emits
    webset.failed."""
```

HTTP (all behind existing `DigiAuthMiddleware`, `digisearch:query` scope —
same rule as `POST /v1/web_search`; no digikey change; errors use the
shared `digibase.errors.json_error_response` envelope with the stable
`code`s below; rate limiting follows the landed two-tier mechanism (audit D17):
static paths get a `_RATE_LIMITS` entry (`server.py:120-130`) **and** every
parameterized path gets an ordered `_RATE_LIMIT_PATTERNS` regex entry
(`server.py:137-142,145-157`) — exact statics are consulted first so
`/v1/websets/{webset_id}` cannot swallow more specific statics; the whole
surface stays on the existing per-IP `_rl_check` pattern):

```
POST /v1/websets                                        # 10/min (creation is a DoS surface)
  body: {query, count 1-100 default 10 (= target verified items),
         criteria[1-5], enrichments[0-10], verification_mode llm|rules,
         workspace_id?} -> 202 {webset} | 422 datatap_websets_disabled
GET /v1/websets/{webset_id}                             # 30/min
  -> 200 {webset} | 404 webset_not_found
POST /v1/websets/{webset_id}/searches                   # 10/min
  body: {query, count 1-100 default 10} -> 202 {search} (follow-up search)
GET /v1/websets/{webset_id}/items?verification=&limit=&cursor=   # 30/min
  -> 200 {items, next_cursor} (cursor = last item id, NEWEST-first; `offset` struck —
     aligned with Phase C)
POST /v1/websets/{webset_id}/enrichments                # 30/min
  -> 201 {enrichment} | 400 (>10) code enrichment_limit_exceeded
DELETE /v1/websets/{webset_id}/enrichments/{enrichment_id}  # 30/min -> 204
POST /v1/websets/{webset_id}/monitors                   # 10/min
  body: {interval_seconds >= 60 (metadata; poll-only v1), webhook_url https}
  -> 201 {webset_monitor}
GET /v1/websets/{webset_id}/monitors                    # 30/min
  -> 200 {monitors} (poll-only v1 operator surface)
POST /v1/websets/{webset_id}/monitors/{monitor_id}/trigger  # 10/min
  -> 202 {webset} (manual refresh; the v1 substitute for the deferred tick driver)
GET /v1/websets/{webset_id}/events?after=&limit=        # 30/min
  -> 200 {events, next_cursor} (cursor-paged, OLDEST-first after `after`; see § Interfaces)
POST /v1/websets/{webset_id}/webhooks                   # 10/min
  body: {url https, events[item.created,item.enriched,webset.idle,webset.failed]} -> 201 {webhook, secret-once}
POST /v1/websets/{webset_id}/webhooks/{webhook_id}/rotate  # 10/min -> 200 {webhook, secret-once}
POST /v1/websets/{webset_id}/cancel                     # 10/min -> 200 {webset} (status=cancelled)
GET /v1/websets/{webset_id}/export?format=csv|json      # 10/min (export is a DoS surface)
  -> file (verified items only)
```

Stable error codes (all in the `digibase.errors` envelope):
`webset_not_found`, `search_not_found`, `monitor_not_found`,
`enrichment_limit_exceeded`, `cursor_not_found` (unknown item/event cursor;
mirrors Phase C's `run_not_found` behavior at `monitors/store.py:310`),
`invalid_criteria` (0 or >5 rules), `invalid_verification_mode`,
`datatap_websets_disabled`, `webhook_url_required`,
`webhook_url_private` (same message text as Phase C so one client handler
covers both), `rate_limit_exceeded` (existing).

MCP tools (`mcp_server.py`, loopback-only unchanged). Names follow the landed
Phase C MCP convention — **unprefixed** (`monitors_create_watch`…,
`mcp_server.py:273-374`) — and mirror the callable ops this spec defines (R10):

```
websets_create(query, count, criteria_json, enrichments_json) -> webset id + status
websets_get(webset_id) -> status + counts (verified/pending/rejected)
websets_add_search(webset_id, query, count) -> search id + status
websets_list_items(webset_id, verification, limit, cursor) -> compact item text
websets_events(webset_id, after, limit) -> compact event tail (oldest-first)
websets_export(webset_id, format) -> CSV/JSON text (caps at 200 rows in chat)
```

Enrichment add/remove, webhook secrets, monitors, and cancel are HTTP-only v1
operator ops (not chat tools) — the six tools above are the deliberate MCP surface.

Orchestrator manifest (`orchestrator_tools.py`): the same six ops under the
**prefixed** `digisearch_websets_*` names, as OpenAI tool dicts, advertised
unconditionally (the OSS path has no key gate — unlike `digisearch_web_search`,
which stays EXA-gated). Wiring is three-part (R12; "manifest entries" alone is
insufficient — the landed dispatch is a hard-coded if-chain at `server.py:728-995`
ending in `HTTPException(400, "Unknown orchestrator tool")`):

1. `TOOL_DIGISEARCH_WEBSETS_*` constants added to `ORCHESTRATOR_TOOL_NAMES`
   (`orchestrator_tools.py:41-51`), mirroring the Phase C monitor constants.
2. Manifest entries added by `build_orchestrator_tool_manifest`
   (`orchestrator_tools.py:501-521`, Phase C monitor precedent `518-520`).
3. `if tool == "digisearch_websets_…"` dispatch branches added to
   `api_orchestrator_invoke` (`server.py:728-995`, Phase C monitor branches
   `958-993`), each returning the `OrchestratorInvokeResponse` envelope and
   raising no new error shape.

Webhook delivery: `POST {url}` with body `{event, webset_id, delivered_at}`
plus header `X-digi-signature: sha256=<hmac(secret, body)>`. The signing core is
**shared with Phase C**, not reimplemented (R7): reuse Phase C's exact signing
expression (`monitors/delivery.py:220-223` — `hmac.new(secret, payload,
sha256).hexdigest()`), factoring a tiny shared helper if cross-module reuse needs
it; never write a second HMAC implementation, so the header bytes are identical
across both webhook egresses. `WebhookConfig{url, events[], secret, previous_secret?,
previous_expires_at?, active, created_at}` — secret server-generated at create,
stored alongside the webhook record (never logged), rotated via
`rotate_webhook_secret` with 24h overlap. 3 attempts, linear backoff
5s/25s (explicit divergence from Phase C's 2 attempts, 0.5s linear —
`delivery.py:70-71,227-229`; recorded reason:
dataset webhooks carry billable enrichment work, worth one extra attempt;
see § Cross-phase alignment). Delivery state is a persistent failure row
in the `webhook_deliveries` ledger table keyed by `(webhook_id, event_id)`
(a UNIQUE/PK on the pair; INSERT-or-ignore on retry, so resumed delivery cannot
double-record) — the `events` table is append-only and event rows are NEVER
mutated, so "recorded on the event row" is struck. No retries past
ledger-recorded terminal failure. POLL-ONLY v1 (R8): there is no scheduled tick
to re-fire delivery — a re-run is the manual `trigger_monitor` call.

## Async lifecycle (no precedent — spec'd concretely here)

There is no `lifespan` / `asyncio.create_task` / `asyncio.to_thread` /
task-registry precedent in `server.py` (verified by grep — only the
`rate_limit` middleware is async), so this spec defines the full pattern;
implementers follow it verbatim:

- **Ownership:** `server.py` lifespan creates one `asyncio.TaskGroup` +
  an explicit registry `WEBSET_TASKS: dict[str, asyncio.Task]`
  (webset_id → task). Route handlers schedule via
  `tasks[webset_id] = task_group.create_task(run_webset_async(webset_id))`
  and return 202 immediately. Bare `asyncio.create_task` without a handle
  is banned — every task has a registry entry, a done-callback logging
  `(webset_id, ok|error)`, and removal on completion.
- **Observability:** task start/done/cancel log `webset_id` + counts only
  (never page bodies); `GET /v1/websets/{id}` surfaces `running` while a
  registry entry exists.
- **Startup resume:** on lifespan startup, `get_store()` opens the DB and
  `resume_incomplete_websets()` lists websets still in `running` (crashed
  worker — a clean shutdown cancels tasks first, so any `running` row at
  boot is orphaned) and re-schedules `run_webset_async` for each. The
  runner is idempotent: `verified` items and terminal enrichment fields
  are skipped, `pending` items/fields are re-driven, already-appended
  events are never duplicated. Event idempotency key scheme (flag I3
  resolved) — each event carries a deterministic `dedup_key` built from the
  tuple `(webset_id, kind, search_id, item_id or "", field or "")`, where
  `search_id` is the `WebsetSearch` generation that produced the event,
  enforced by a UNIQUE index on `events(webset_id, dedup_key)` with
  `INSERT OR IGNORE`:
  `item.created` → `(webset_id, "item.created", search_id, item_id, "")`;
  `item.enriched` → `(webset_id, "item.enriched", search_id, item_id, "")`
  (one event per item per generation once § terminal-state conditions hold,
  so no field slot is needed);
  `webset.idle` → `(webset_id, "webset.idle", search_id, "", "")`;
  `webset.failed` → `(webset_id, "webset.failed", search_id, "", "")`. The
  `field` slot is empty for item/webset-level events and reserved for
  field-scoped kinds (none in v1), so a resume WITHIN the same search cannot
  duplicate any event; each re-settling flow — `add_search`, the
  `add_enrichment` backfill run, `trigger_monitor` — creates a new
  `WebsetSearch` row (a new generation), so a completed pass can emit its
  terminal events again. Terminal `webset.*` events carry the generation of the
  pass that produced them. Unknown `kind` values are rejected by the
  insert path (no silent rows).
- **Refresh contract (status never backwards):** an `add_search`, the
  `add_enrichment` backfill run, and a manual `trigger_monitor` each start a new
  settling pass by creating a new `WebsetSearch` row — the new event generation
  above. `Webset.status` never goes backwards: after its first completion a
  webset stays `idle` while a refresh pass runs, and callers observe the refresh
  through the new search's status + events, never through a webset status flip.
- **Cancellation under the semaphore:** `cancel_webset` flips the row to
  `cancelled` and settles every search not already `idle`/`failed` as
  `cancelled` (flag I6). The runner checks the flag before each semaphore
  acquisition and between items; an in-flight item finishes its current
  field extraction, then yields without scheduling further work;
  unattempted fields are marked `skipped`. No `task.cancel()` mid-LLM call
  (avoids half-written enrichment rows); shutdown path cancels the
  TaskGroup and awaits it, then marks still-`running` rows `cancelled`.
- **SQLite concurrency:** exactly Phase C's discipline (R5;
  `monitors/store.py:20-25,159-166`) — each `WebsetStore` instance owns one
  `sqlite3` connection created in its constructor and bound to its thread
  (`check_same_thread` keeps its default), so a store is single-threaded;
  construct one per thread/request, which the module-level `get_store()` does.
  The file opens with `WAL` mode + `PRAGMA busy_timeout=5000` so the HTTP
  process and any second process can share it. **No module-level
  `threading.Lock`** (the pre-erratum claim is struck; a lock would serialize
  every webset and is not what Phase C does). The async runner reaches the sync
  store only via `await asyncio.to_thread(...)` at the async boundary.

## Cross-phase alignment (divergences recorded with reasons)

- **Tenant isolation:** `Webset` carries `workspace_id: str | None = None`
  (mirrors Phase C `Watch.workspace_id`). `create_webset` with a datatap
  `workspace_id` is rejected with `422 datatap_websets_disabled` (mirrors
  Phase C `datatap_monitors_disabled`); the runner never executes
  datatap-scoped websets. DataTap stays OFF end-to-end. If a later spec
  wants multi-tenant websets, it amends this section — no silent scoping.
- **Backend vocab (R4):** the webset `provider: Literal["auto","exa","searxng"]`
  parameter is struck — no such enum landed in Phase A (landed `WebSearchConfig.backend`
  is `auto|searxng|ddgs`, `web_search/service.py:24`; the EXA tool schema has no
  `provider` param, `orchestrator_tools.py:387-438`). Phase D uses Phase C's landed
  label on the object, and EXA-websets selection is the shim's concern (key presence):

  | Layer | Values | Meaning |
  |---|---|---|
  | Webset `backend` label (on `Webset`/`WebsetSearch`) | `oss` \| `exa` | mirrors Phase C `Watch.backend` (`monitors/models.py:107`); `oss` = the landed `search_web` recall path (`auto|searxng|ddgs` failover), `exa` = the paid shim answered |
  | Phase C `Watch.backend` | `oss` \| `exa` | turn-vs-shim label on `MonitorRun` |

  There is no caller-facing provider param in either layer; `ddgs`/`off` appear in
  neither (the `off` vocabulary never landed).
- **Recorded divergences from Phase C** (aligned where cheap, diverged
  with reason where the domain differs):

  | Area | Phase C | Phase D (this spec) | Reason |
  |---|---|---|---|
  | Cadence field | `interval_seconds` | `interval_seconds` | ALIGNED (`cadence_s` struck) |
  | List pagination | cursor (`run_id`) | cursor (`after` event id / item id) | ALIGNED (`offset` struck) |
  | Delivery retries | 2 attempts, 0.5s linear (`delivery.py:70-71`) | 3 attempts, 5s/25s backoff | DIVERGED: dataset webhooks carry billable enrichment work |
  | Delivery signing | HMAC-SHA256 `X-digi-signature` (`delivery.py:220-223`) | same — shared signing core, byte-identical header | ALIGNED (R7) |
  | Delivery state | receipts returned, not persisted (`delivery.py:28-31`) | `webhook_deliveries` ledger keyed `(webhook_id, event_id)` | DIVERGED: dataset events need recovery after a resumed runner (R7) |
  | Webhook secret / rotation | `secrets.token_hex(32)`, immediate rotate (`server.py:1261,1311`) | `secrets.token_urlsafe(32)`, 24h overlap window (`previous_expires_at`) | DIVERGED: D adds a rotation grace window; C rotates immediately (audit D15) |
  | Page truncation | n/a (recall path) | 6000 chars pre-LLM | DIVERGED: verification needs a fuller page than Phase B synthesis snippets |
  | Error shape | `digibase.errors` codes | same envelope + webset codes listed above | ALIGNED |
  | Store handle | `DIGISEARCH_MONITORS_DB` → `{DIGI_WORKSPACE}/…monitors.sqlite3` → `./.digisearch/monitors.sqlite3` | `DIGISEARCH_WEBSETS_DB` → `{DIGI_WORKSPACE}/…websets.sqlite3` → `./.digisearch/websets.sqlite3` | ALIGNED (convention + volume + cwd fallback, R6) |
  | Store concurrency | one connection per instance/thread, WAL + `busy_timeout=5000`, no in-process lock (`store.py:20-25,159-166`) | same (R5) | ALIGNED |
  | Monitor lifecycle | scheduled tick via `POST /v1/monitors/tick` (`server.py:1376-1382`, `digiclaw/monitors_tick.py:30`) | POLL-ONLY v1: manual `trigger_monitor`; tick driver deferred | DIVERGED (R8): no scheduled driver in this phase; follow-up named in § Tasks |

## Global Constraints

- Python 3.12, pydantic v2 everywhere, strict typing, ruff line-length 100,
  `ruff check + format --check` zero errors.
- Every test file lives at `tests/ds/test_websets_*.py` and carries
  `@pytest.mark.unit` (module `pytestmark` or per-test); every Task Run
  line invokes `pytest -m unit` (R3). `digisearch/tests/` **already exists**
  with the Phase A suite and is collected (`pytest.ini:2` testpaths;
  `digisearch/tests/test_web_search_*.py`, consumed cross-root via
  `sys.path.insert` at `tests/ds/test_web_eval_live.py:36-38`) — the
  pre-erratum "MUST NOT be created (non-existent)" claim is struck (audit D12);
  do not add websets tests there, and do not delete the existing files.
- Polars only for CSV export — never pandas, never `pandas-ta`.
- Digi product names always lowercase in prose/docs/commits (`digisearch`,
  `digigraph`, `digillm`, `digifetch`, `digiquant`, `digikey`).
- MCP-first: every capability is a discoverable tool; no pipeline logic
  directly in LangGraph nodes (the agent `plan → retrieve → aggregate`
  pipeline may *read* webset items as a retrieval source via `list_items`,
  never drive the runner). Phase D v1's discoverable surface is the six
  `websets_*` MCP tools / `digisearch_websets_*` orchestrator tools above;
  enrichment add/remove, webhook secrets, monitors, and cancel are deliberate
  HTTP-only operator routes in v1 (the same six-op split the MCP section
  states), not an accidental gap.
- digigraph must never `import digisearch` modules; all calls via
  `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke`.
- Auth fail-closed: all new routes inherit `DigiAuthMiddleware` +
  `digisearch:query` scope; MCP stays loopback-only `127.0.0.1:8765`.
- No full doc bodies in digismith spans (ids, counts, statuses only).
- Entity/model naming drops the `Digi` prefix (`Webset`, `WebsetItem`).
- #3420 invariant preserved: websets are an explicit, opt-in async job —
  never ambient on corpus RAG, never in the force-tool path.
- Every change traces to its implementation issue; update
  `digisearch/ARCHITECTURE.md` on interface change.
- Human gate (R13, unchanged): new external network exposure — webhook
  delivery to caller URLs is new egress — requires human review before merge.
  The gate sits on the **webhook-delivery task (T5b)**: do not merge T5b
  (or any commit that first enables outbound delivery) without it.

## Provider capability matrix (finding from live testing)

Recorded here so implementers and callers stop rediscovering it:

| Capability | OSS path (this spec) | EXA free-tier key | EXA Pro key |
|---|---|---|---|
| `/search` (+`category=company` entities w/ funding) | n/a (Phase A/B mirror) | works ($0.007/sample, s5) | works |
| Websets verify + enrich | **ships here, no key** | `401: Upgrade to a Pro plan` (live finding, this key tier) | works via `providers/exa_websets.py` shim |
| Company funding history | SearXNG → fetch → extract → merge (§ Architecture) | inline `entities` | inline `entities` |
| Async delivery (poll/webhook/events) | ships here | n/a (paywalled with Websets) | EXA webhooks |

The live 401 response body and the s5 company sample are **vendored at T0** under
`tests/ds/fixtures/websets/` (`exa_401_pro_required.json`,
`s5_category_company.json`; plus `fx_ecb_snapshot.json` and a provenance
`README.md`) and are referenced from the
`providers/exa_websets.py` module docstring by fixture path (request id
`97792aab…9ce7e`, s5 totals above) so the tier distinction is documented at
the code site, not just in this spec. Values are sanitized (no keys/tokens; the
s5 `image` fields are nulled because the source LinkedIn URLs carried signed
query tokens — see `tests/ds/fixtures/websets/README.md`). `/tmp` paths are
scratch and appear nowhere in code, tests, or docstrings.

## Tasks

**Re-scoped sequence (audit §5; T0 landed with this erratum):** T0 erratum +
fixture vendoring (this commit, no code) → T1 models → T2 store → T3 verify →
T4 enrich (needs T0 fixtures) → T5a runner + events → T5b webhook delivery +
ledger (**HUMAN GATE**, R13) → T6 service + export → T7 HTTP/MCP/orchestrator +
EXA shim → T8 live verification record. Deferred follow-ups (explicitly out of
v1): the scheduled webset tick driver (R8; Phase C's landed driver is
`digiclaw/monitors_tick.py:30` → `POST /v1/monitors/tick`, `server.py:1376-1382`
— a websets equivalent is a separate issue), recall paging (R3), and EXA-websets
shim live validation (Pro-key dependent; tracked by the #4123 live-pin
precedent). The `WebsetMonitor` `active|paused` lifecycle is deferred with the
driver (flag I4).

### Task 1: Models + per-field citation shapes

**Files:** create `websets/models.py`, `tests/ds/test_websets_models.py`.

- [ ] Step 1: write the failing test — construct a `Webset` with 2
  criteria + 2 enrichments (one `options`, one `company_profile`), a
  verified `WebsetItem` whose enrichment value carries 2 `Citation`s
  (imported from `digisearch.web_search.citation` — assert the import
  site is the shared atom, `assert EnrichedField.model_fields["citations"]`
  annotates that type), a `CompanyEntity` with 2 funding rounds
  plus `provenance` entries per scalar, and a `WebsetMonitor` (bare
  `Monitor` import must fail; no `status`/`paused` field exists);
  assert `model_dump(mode="json")` round-trips, `EnrichedField` with empty
  citations validates as `unresolved`, `count` outside 1..100 is rejected,
  the `backend` label defaults to `"oss"`, and ids match
  `^(ws|wss|wsi|wse|wsm)_<uuid4hex>$`. No `provider`/`auto` field exists
  (R4 — assert its absence so the struck param cannot creep back).
  Every test carries `@pytest.mark.unit`.
  Run: `pytest tests/ds/test_websets_models.py -m unit -v` → FAIL
  (`No module named 'digisearch.websets'`).
- [ ] Step 2: implement `models.py` exactly per § Interfaces object table
  (pydantic v2, `extra="forbid"` on request shapes, `extra="ignore"` on
  EXA-normalized reads; `Citation`/`normalize_url` imported from
  `digisearch.web_search.citation`, never redefined; `WebsetSearch.status`
  includes `cancelled`; `count: int = Field(default=10, ge=1, le=100)`;
  `Webset`/`WebsetSearch` carry `backend: Literal["oss","exa"] = "oss"`;
  id prefixes `ws_/wss_/wsi_/wse_/wsm_` + uuid4-hex validated by pattern).
  Note the recorded divergence: websets ids are `uuid4().hex`
  (`digibase/http.py:74` precedent) while Phase C entities are ULIDs
  (`monitors/store.py:122`) — deliberate, per the audit's T1 disposition.
- [ ] Step 3: run `pytest tests/ds/test_websets_models.py -m unit -v` →
  PASS; run
  `ruff check digisearch/src/digisearch/websets/ && ruff format --check digisearch/src/digisearch/websets/` →
  zero errors.

### Task 2: SQLite store

**Files:** create `websets/store.py`, `tests/ds/test_websets_store.py`.
Consumes Task 1.

- [ ] Step 1: write the failing test — create webset → add search → add 3
  items (verified/rejected/pending) → `list_items` filter per status →
  append/list 2 events → export-read round-trip. Assert ordering and cursor
  semantics (R11): items NEWEST-first with an unknown cursor raising
  `cursor_not_found`; events OLDEST-first after an explicit `after` cursor, also
  raising `cursor_not_found` for an unknown id; duplicate append of the same
  `dedup_key` (e.g. `webset.idle`) is INSERT-or-ignored, not duplicated.
  Use tmp file DB. `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_store.py -m unit -v` → FAIL.
- [ ] Step 2: implement `WebsetStore(path)` + a `WebsetStoreError` carrying the
  stable API-facing `code` (Phase C `MonitorStoreError` precedent,
  `monitors/store.py:110-119`) + module-level
  `get_store(db_path=None)` resolving explicit path → `DIGISEARCH_WEBSETS_DB` →
  `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3` → `./.digisearch/websets.sqlite3`
  (cwd fallback, R6) with tables
  `websets/searches/items/enrichments/webset_monitors/webhooks/webhook_deliveries/events`;
  connect exactly like Phase C (`monitors/store.py:159-166`): one connection per
  instance created in `__init__`, thread-bound, `WAL` + `busy_timeout=5000`, **no
  module `threading.Lock`** (R5); status transitions validated
  (`running → idle|failed|cancelled`, never backwards — `idle` is sticky after
  first completion, and refresh passes run as new search generations without
  flipping the webset back, § Async lifecycle); search statuses include
  `cancelled`; `set_webset_idle` refuses while any item has a `pending`
  verification or `pending` enrichment field; `events` is append-only (no
  UPDATE/DELETE path exists) with the `(webset_id, dedup_key)` UNIQUE index
  behind the per-generation INSERT-or-ignore idempotency key scheme (§ Async
  lifecycle).
- [ ] Step 3: run `pytest tests/ds/test_websets_store.py tests/ds/test_websets_models.py -m unit -v` →
  PASS + ruff clean.

### Task 3: Verification engine (llm + rules modes)

**Files:** create `websets/verify.py`, `tests/ds/test_websets_verify.py`.
Consumes Phase B extraction contract (mocked at the digillm boundary).

- [ ] Step 1: write the failing test — (a) rules mode: 2 criteria
  (domain allowlist + keyword presence) over a canned candidate → all-pass
  admits, keyword-miss rejects with reasoning referencing the rule; (b) llm
  mode with stubbed digillm completion returning per-rule verdicts →
  `CriterionResult` list carries `references: list[Citation]` (shared
  `Citation`, `title` defaulted, `excerpt` quoted); (c) empty criteria list
  raises `ValueError`; 6 criteria raise `ValueError`; (d) verification
  unavailable (stubbed digillm raises / candidate markdown empty) does NOT
  leave the item `pending` forever: the settlement path yields `rejected` with
  one synthetic `CriterionResult` per criterion (flag I9).
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_verify.py -m unit -v` → FAIL.
- [ ] Step 2: implement `verify_item(url, title, markdown, criteria, *,
  mode, llm_client=None) -> list[CriterionResult]` (the `markdown` argument is
  the candidate's `fetch_markdown` output, R2); markdown truncated to
  6000 chars before any LLM call; rules mode implements exactly
  `domain`, `keyword`, `recency` rule kinds (`recency` = published-date
  within N days — a rule-kind name, distinct from the landed
  `WebSearchRequest.recency_days` recall field at `web_search/models.py:29`,
  which maps to searxng `time_range`; the pre-erratum "struck field" rationale
  is false, audit D8; unknown kind raises `ValueError`, never silently passes).
- [ ] Step 3: run `pytest tests/ds/test_websets_verify.py -m unit -v` →
  PASS + ruff clean.

### Task 4: Enrichment engine + funding/entity merge

**Files:** create `websets/enrich.py`, `tests/ds/test_websets_enrich.py`,
`tests/ds/test_websets_company.py`. Consumes Tasks 1–3 + Phase B
(mocked digillm boundary).

- [ ] Step 1: write the failing tests — (a) all 8 enrichment types
  (incl. `company_profile`) validate (bad `number`/`date`/`options` →
  `unresolved`, never coerced); (b) every resolved field carries ≥1
  `Citation` or the test fails; (c) funding merge: two pages reporting
  the same Series A ($11.5M, 2025-07, NuCicer-style fixture from the
  T0-vendored `tests/ds/fixtures/websets/s5_category_company.json`) merge to
  one round, total reconciles against the median claimed total; conflicting
  median beyond 1% → `unresolved` with reasoning; zero claimed totals →
  sum stands (non-vacuous); single third-party mention without quorum →
  `unresolved`; (d) entity merge: same-domain candidates merge, loser
  value lands in `alternatives[]` with its own citations; (e) provenance:
  every `CompanyEntity` scalar has a `provenance[field]` entry;
  (f) `company_profile_field(entity)` bundles the entity into one
  `resolved` `EnrichedField` (union of provenance citations) and returns
  `unresolved` for a no-resolved-scalars entity (flag I8).
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_enrich.py tests/ds/test_websets_company.py -m unit -v` →
  FAIL.
- [ ] Step 2: implement `enrich_item`, `reconcile_funding_history`
  (ECB snapshot FX, median-quorum rule per § Architecture),
  `merge_company_entities`, `company_profile_field`; company fixtures
  loaded from `tests/ds/fixtures/websets/` (never `/tmp`; provenance in
  `tests/ds/fixtures/websets/README.md`); FX rates from
  `tests/ds/fixtures/websets/fx_ecb_snapshot.json`.
- [ ] Step 3: run both files with `-m unit` → PASS + ruff clean.

### Task 5a: Async runner + events

**Files:** create `websets/runner.py`, `websets/events.py`,
`tests/ds/test_websets_runner.py`. Consumes Tasks 1–4, Phase A landed recall
seams: `search_web` (`web_search/service.py:94`) and `fetch_markdown`
(`web_search/fetch.py:52`) — stubbed at those two seams, with `search_web` as
the single pinned provider boundary (R3; direct import per R1; never raw httpx
to the sidecar, never `ingest_url`, never `run_web_search`).

- [ ] Step 1: write the failing test — stubbed candidates (3) + stubbed
  verify (admit 2, reject 1) + stubbed enrich → after
  `await run_webset_async(id)`: webset is `idle`; assert the event log as
  a MULTISET `{item.created ×2, item.enriched ×2}` PLUS `webset.idle`
  strictly last (exact-sequence assertion banned — the semaphore-4
  concurrent runner does not guarantee inter-item order); `list_items`
  counts match; `list_events` re-read with `after=` returns only newer events
  (oldest-first, R11); a verification-unavailable candidate settles `rejected`
  (not `pending`) at candidate-pass end; forced enrich-failure item still emits
  `item.created` but no `item.enriched` for it, its fields are `unresolved`
  (terminal), webset still reaches `idle`; `cancel_webset` mid-run yields
  `cancelled` with searches settled `cancelled` and unattempted fields
  `skipped`; startup-resume test seeds a `running` webset row then calls
  `resume_incomplete_websets()` and asserts it is re-driven without
  duplicating existing events (the `(webset_id, dedup_key)` INSERT-or-ignore
  scheme, § Async lifecycle).
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_runner.py -m unit -v` → FAIL.
- [ ] Step 2: implement `AsyncioRunner` (semaphore 4 for fetch/verify,
  per-item errors contained, task registry + TaskGroup ownership +
  startup resume + semaphore-aware cancellation per § Async lifecycle;
  recall via `search_web` with query diversification since no paging exists —
  `max_results ≤ 10` per call, R3; page markdown via `fetch_markdown` only;
  store I/O via `asyncio.to_thread` — the store is thread-bound with one
  connection per instance and needs **no in-process lock**, R5);
  `backfill_enrichment(webset_id, enrichment_id)` for the
  `add_enrichment` path (§ Interfaces). Fan-out target is the webset itself:
  **poll-only v1** — no scheduled tick driver and no Phase C `Watch` is
  addressed here (R8; residual risk 6 closed by this sentence).
- [ ] Step 3: run `pytest tests/ds/test_websets_runner.py -m unit -v` →
  PASS + ruff clean.

### Task 5b: Webhook delivery + `webhook_deliveries` ledger — **HUMAN GATE (R13)**

**Files:** extend `websets/events.py`, add delivery tests to
`tests/ds/test_websets_runner.py` (same file as T5a's suite).
Consumes T5a. **Do not merge this task without human review: it is the first
outbound delivery to caller-controlled URLs (new external network exposure).**

- [ ] Step 1: write the failing test — `httpx.MockTransport` delivery asserts
  the `X-digi-signature` header verifies against the secret AND is
  byte-identical to the Phase C signing core's output for the same
  body/secret (`monitors/delivery.py:220-223` pattern); ledger rows appear in
  `webhook_deliveries` keyed `(webhook_id, event_id)` with INSERT-or-ignore on
  retry; 3 attempts with 5s/25s backoff (sleep seam, no real waits); a
  duplicate event delivery does not double-record; a terminal failure is
  recorded once and not retried further; event rows themselves are never
  mutated. `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_runner.py -m unit -v` → FAIL.
- [ ] Step 2: implement `deliver_webhook` sharing Phase C's signing helper
  (never a divergent HMAC implementation): 3 attempts, 5s/25s backoff,
  `X-digi-signature: sha256=<hmac(secret, body)>`, ledger rows in
  `webhook_deliveries` (`(webhook_id, event_id)` key; never event-row
  mutation). No scheduled re-fire exists in v1 — a refresh is the manual
  `trigger_monitor` call (R8).
- [ ] Step 3: run `pytest tests/ds/test_websets_runner.py -m unit -v` →
  PASS + ruff clean. Human gate satisfied before merge.

### Task 6: Service facade + export (polars CSV)

**Files:** create `websets/service.py`, `websets/export.py`,
`tests/ds/test_websets_export.py`. Consumes Tasks 1–5.

- [ ] Step 1: write the failing test — full local flow with stubbed
  runner boundaries: `create_webset` returns `running` (and a caller-supplied
  `count=0`/`count=101` is rejected); `get_webset`
  round-trips; `add_search` attaches a second search; `add_enrichment`
  11th raises; `remove_enrichment` retains resolved values;
  `create_monitor` returns a `WebsetMonitor` with no `status`/`paused` field
  (and `Monitor` is unimportable — I4/R8); `list_monitors` returns it;
  `trigger_monitor` re-runs the searches (manual refresh, poll-only v1);
  `add_webhook` returns a one-time secret;
  `rotate_webhook_secret` overlaps the old secret 24h; `list_events`
  cursor-pages OLDEST-first with `after=`;
  `cancel_webset` flips to `cancelled` and settles searches `cancelled`;
  `export_webset(fmt="json")` contains per-field citations;
  `export_webset(fmt="csv")` parses with polars, one row per verified
  item, rejected items excluded, citations column holds URLs.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_export.py -m unit -v` → FAIL.
- [ ] Step 2: implement `service.py` (exact § Interfaces signatures —
  `create_webset`, `get_webset`, `list_items`, `add_search`,
  `add_enrichment` + `backfill_enrichment` execution path,
  `remove_enrichment`, `create_monitor`, `list_monitors`, `trigger_monitor`,
  `add_webhook`,
  `rotate_webhook_secret`, `list_events`, `cancel_webset`,
  `export_webset`) + `export.py` (`export_json`, `export_csv` via
  `polars.DataFrame.write_csv`, flattened `enrichment__value` /
  `enrichment__citations` columns).
- [ ] Step 3: run `pytest tests/ds/test_websets_export.py -m unit -v` →
  PASS + ruff clean.

### Task 7: HTTP + MCP + orchestrator wiring + EXA shim

**Files:** create `websets/providers/exa_websets.py`; modify `server.py`,
`mcp_server.py`, `orchestrator_tools.py`; create
`tests/ds/test_websets_api.py`. Consumes Task 6.

- [ ] Step 1: write the failing test — `TestClient` against the app:
  `POST /v1/websets` → 202 with `status=running`; `GET` polls to `idle`
  (stub runner); `GET .../items`, `POST .../enrichments` (11th → 400
  `enrichment_limit_exceeded`), `POST .../monitors` + `GET .../monitors` +
  `POST .../monitors/{id}/trigger`, `GET .../export?format=csv` returns
  `text/csv`; an unknown item/event cursor → `cursor_not_found`; auth
  assertion copies the landed middleware-test pattern
  (`TestClient(app, headers=auth_headers())` — `tests/ds/test_web_exa.py:89-116`
  and `tests/ds/test_monitors_api.py:26-49`; the pre-erratum "no HTTP/auth tests
  in `test_web_exa.py`" claim is false, audit D13), unauthenticated
  `TestClient(app)` request → 401/403 from `DigiAuthMiddleware`; MCP tools
  register under the unprefixed `websets_*` names (assert the six names);
  orchestrator dispatch: `POST /v1/orchestrator_invoke` with each
  `digisearch_websets_*` name reaches its branch (not the unknown-tool 400);
  shim test: mocked 401 `Upgrade to a Pro plan` body (loaded from
  `tests/ds/fixtures/websets/exa_401_pro_required.json`) →
  `ExaWebsetsProRequiredError`, assert
  `issubclass(ExaWebsetsProRequiredError, ExaError)` and that
  `except ExaError` still catches it; datatap `workspace_id` create →
  422 `datatap_websets_disabled`.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_api.py -m unit -v` → FAIL.
- [ ] Step 2: implement routes (lifespan TaskGroup + `WEBSET_TASKS`
  registry per § Async lifecycle — bare `asyncio.create_task` without a
  handle is banned, never awaited inline), the six MCP tools (unprefixed
  `websets_*`, R10), and the three-part orchestrator wiring (R12): six
  `digisearch_websets_*` manifest entries (unconditional advertisement,
  Phase C monitor precedent `orchestrator_tools.py:518-520`), the
  corresponding `ORCHESTRATOR_TOOL_NAMES` constants (`orchestrator_tools.py:41-51`),
  and `if tool == …` dispatch branches in `api_orchestrator_invoke`
  (`server.py:728-995`). Shim with module docstring citing
  the vendored 401 fixture + s5 fixture paths. Add the `_RATE_LIMITS` statics
  AND `_RATE_LIMIT_PATTERNS` regex entries from § Interfaces (D17 — extend the
  ordered tuple at `server.py:137-142`; parameterized webset paths cannot be
  keyed by exact path). Re-validate the EXA Websets request
  translation against a Pro-tier key before merge (record request/response
  shapes in the shim docstring — the translation ships blind otherwise;
  key-less CI stays green via the mocked 401 test). Update
  `digisearch/ARCHITECTURE.md` websets section in the same change.
- [ ] Step 3: run `pytest tests/ds/test_websets_api.py tests/ds/test_web_exa.py -m unit -v` →
  PASS; `ruff check digisearch/ && ruff format --check digisearch/` →
  zero errors; `curl -s http://localhost:8002/health` unchanged.

### Task 8: Live verification record (no code)

- [ ] Step 1: stack up, create a 5-count company webset
  (`query="agtech robotics startups Series A 2024-2026"`, 2 criteria,
  3 enrichments incl. `company_profile`), poll to `idle` (poll-only v1 —
  refresh is the manual `trigger_monitor`, no tick driver), confirm the
  `item.created/item.enriched` multiset + `webset.idle`-last (never an
  exact sequence).
- [ ] Step 2: confirm funding totals against the vendored s5 EXA sample
  (`tests/ds/fixtures/websets/s5_category_company.json` — same companies
  should reconcile, not necessarily match; refresh
  `tests/ds/fixtures/websets/fx_ecb_snapshot.json` from the ECB daily feed and
  record both, updating the fixture `README.md` provenance date).
- [ ] Step 3: `GET .../export?format=csv`, open in a spreadsheet, confirm
  one-row-per-item + citation URLs present.
- [ ] Step 4: append measured timings + reconciliation notes to
  `digisearch/ARCHITECTURE.md` websets rollout paragraph.
