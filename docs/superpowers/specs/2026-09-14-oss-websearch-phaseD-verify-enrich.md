# Phase D — OSS Verify + Enrich Graph (Websets-like async list building)

**Date:** 2026-09-14
**Owner:** digisearch
**Status:** implementation spec (write-only, no code in this doc)
**Program:** open-source EXA equivalent (EXA kept as paid alternative)

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

- **CONSUMES — Phase A (ingest/search):** candidate generation runs on the
  Phase A surfaces only: `SearXNGBackend.query()` (live candidates,
  `digisearch.web_providers.searxng`) + `ingest_url()`
  (`digisearch.pipeline.url_ingest`) and `extract_markdown(html, url) ->
  tuple[str, str]` for page markdown. Direct import within `digisearch`
  (same-package rule, R2); Phase D never shells out to raw SearXNG itself
  and never touches `digisearch.web_search`, `run_web_search`, `ddgs`, or
  `off` — none of those exist (Phase A provider enum is
  `["auto","exa","searxng"]`, Task 6 of Phase A). Domain bias uses the
  canonical `include_domains` / `exclude_domains` args; fail-closed behavior
  (sidecar down → `SearXNGDegradedError`, never silent EXA fallback) is
  inherited unchanged.
- **CONSUMES — Phase B (structured synthesis with grounding):** verification
  verdicts and enrichment extraction use the Phase B structured-output path
  (schema-pinned LLM extraction whose outputs carry citations, same contract
  as `WebSearchData.output` + `output_schema`). Enrichment field values are
  only admitted together with their citations.
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
candidate generation (Phase A SearXNGBackend.query(), paged to count;
  page markdown via ingest_url()/extract_markdown)
  │ per candidate
  ▼
verification gate (1-5 criteria; every rule must pass before admission)
  │ admitted only
  ▼
per-item enrichment (typed fields, each with citations)
  │
  ▼  events appended at each transition
status -> "idle" (terminal: all searches settled AND all items enriched)
  │
   ├── poll:   GET /v1/websets/{id} + GET .../items
   ├── push:   webhooks (HMAC-signed) + webset-cadence re-run ticks
   │           (Phase C `Watch`es are NOT a fan-out target — see § Interfaces;
   │           a C↔D bridge is a named follow-up, not this spec)
   └── export: GET .../export?format=csv|json
```

- No endpoint blocks on pipeline completion. MCP/orchestrator tools are
  split accordingly: a `create` tool (returns the webset id) plus `status`,
  `items`, and `export` tools for the follow-up turns.
- In-process asyncio worker (lifespan-managed task group) with a `Runner`
  protocol so a future out-of-process worker can replace it without changing
  the store, service, or HTTP shapes. No celery, no redis, no new infra.
- Persistence is a SQLite-backed `WebsetStore` (same precedent as
  `EmbeddingCache`): one file read from `DIGISEARCH_WEBSETS_DB`, default
  `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3` (same persistent volume as
  the Phase C monitors DB; never CWD — CWD breaks under service managers),
  constructed via `get_store(db_path=None)` exactly like Phase C
  `MonitorStore.get_store`. JSON columns for criteria/enrichments/events;
  `WAL` mode + `PRAGMA busy_timeout=5000` on every connect; all writes
  serialized by a module-level `threading.Lock` inside `WebsetStore`
  (single-writer discipline shared with Phase C); all blocking I/O from the
  async runner via `asyncio.to_thread` (concrete lifecycle in § Async
  lifecycle — there is no `asyncio.to_thread`/task-registry precedent in
  `server.py` to inherit). Unit tests run against a temp file; production
  path never touches `DIGISEARCH_ALLOW_STUB`.
- Verification modes: `llm` (default, via digillm structured completion,
  one verdict per criterion with reasoning + references) and `rules`
  (deterministic offline checks: domain allowlist, recency window, keyword
  presence). `rules` exists so unit tests and key-less installs stay green;
  production websets default to `llm` and fail closed (unverifiable items
  stay `pending`, never admitted silently).
- EXA compatibility shim: `providers/exa_websets.py` is dormant without
  `EXA_API_KEY` (same fail-closed pattern as `web_exa.py`) and maps the
  known `401 Upgrade to a Pro plan` response to a typed
  `ExaWebsetsProRequiredError`, declared explicitly as
  `class ExaWebsetsProRequiredError(ExaError)` in
  `providers/exa_websets.py` (subclass — never a sibling — so existing
  `except ExaError` handlers keep catching it with unchanged meaning), so
  callers can distinguish "key missing" (`ExaNotConfiguredError`) from
  "tier paywalled". When a Pro key exists, the shim translates the OSS
  webset request into EXA Websets calls and normalizes responses back into
  the OSS object shapes below — the HTTP/MCP surface does not change.

### EXA Websets semantic mirror (drop-in contract)

Object names, terminal state, and event names mirror EXA Websets API
semantics (shapes captured from EXA docs; field naming adapted to repo
conventions — lowercase, no `Digi` prefix):

| Concept | OSS object | Key fields |
|---|---|---|
| webset | `Webset` | `id` (`ws_` + uuid4-hex, no new dep — `uuid.uuid4().hex` per `digibase.http` precedent), `object="webset"`, `status`: `running` \| `idle` \| `failed` \| `cancelled`, `workspace_id: str \| None = None` (tenant isolation, § Cross-phase alignment), `searches`, `enrichments`, `created_at`, `updated_at` |
| search | `WebsetSearch` | `id` (`wss_` + uuid4-hex), `webset_id`, `query`, `count` (= target **verified** items for this search — NOT a result-page size; see `num_results` note below), `status`: `running` \| `idle` \| `failed`, `criteria` (1–5 rules) |
| item | `WebsetItem` | `id` (`wsi_` + uuid4-hex), `webset_id`, `url`, `title`, `verification`: `pending` \| `verified` \| `rejected`, `criteria_results[]` (verdict + reasoning + references per rule), `enrichments{field: EnrichedField}` (per-field value + citations + terminal status), `created_at` |
| enrichment | `EnrichmentDef` | `id` (`wse_` + uuid4-hex), `name`, `type`: `text` \| `number` \| `date` \| `url` \| `email` \| `phone` \| `options` \| `company_profile`, `description`, `options[]` (only for `options`), `status` |
| webset monitor | `WebsetMonitor` | `id` (`wsm_…`, prefix kept), `object="webset_monitor"`, `webset_id`, `interval_seconds >= 60` (aligned with Phase C `WatchSchedule.interval_seconds`; `cadence_s` struck), `webhook_url`, `status`: `active` \| `paused` — a webset-refresh cadence, explicitly NOT a Phase C `Watch` (R7e; bare `Monitor` is banned — it collides with the Phase C `Watch`/`MonitorRun` family) |
| event | `WebsetEvent` | `id`, `webset_id`, `type`: `item.created` \| `item.enriched` \| `webset.idle` \| `webset.failed`, `payload`, `created_at` (append-only log; delivery state lives in `webhook_deliveries`, never on event rows) |

- `Citation{url, title="", excerpt=""}` is owned by Phase A
  (`digisearch.web_providers.models.Citation`, `extra="forbid"`) and
  **imported** by `websets/models.py` — never redefined, never copied
  (R5). `CriterionResult.references` and `EnrichedField.citations` are both
  `list[Citation]`; Phase B joins on exact `url` match against the same
  type.
- `count` (webset/search target verified items) vs `num_results` (Phase A
  per-query result-page size passed to `SearXNGBackend.query`): different
  concepts, different names, never interchanged. The runner pages
  `SearXNGBackend.query(num_results=…)` until `count` verified items are
  admitted or candidates exhaust.

- `idle` is the only success-terminal state (webset and search level).
  A webset is `idle` when every search is `idle`/`failed` and no item has a
  `pending` enrichment field left. Enrichment-terminal per (item, field):
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
  audit). Tests assert the event log as a **multiset + `webset.idle`-last**
  (exact-sequence assertions are banned — the concurrent runner does not
  guarantee inter-item order).

### Verification gate

- Each `WebsetSearch` carries 1–5 `VerificationCriterion{name, rule,
  description}` entries (natural-language rules, e.g. "company is a
  photonics startup founded after 2018").
- `verify_item` evaluates every rule against the candidate's fetched
  markdown (Phase A extractor output, truncated to 6000 chars before the
  LLM call — truncation budget recorded as an explicit divergence from
  Phase B's `snippet ≤2000c` / `max_synthesis_chars=12000`: verification
  needs a fuller page than synthesis snippets; see § Cross-phase
  alignment) and returns one `CriterionResult{criterion, passed, reasoning,
  references: list[Citation]}` per rule (Phase A `Citation`, R5 — title
  defaults to `""`, excerpt carries the supporting quote). Item is admitted
  only if all rules pass; otherwise `rejected` with the failing reasons
  retained.
- digismith spans for verification carry only webset/item ids, rule names,
  and pass/fail counts — never page bodies or chunk content.

### Enrichment engine + per-field citations (auditable by construction)

- Each `EnrichmentDef` resolves to one `EnrichedField{value, citations:
  list[Citation], status: resolved | unresolved | skipped, error}` per
  item (Phase A `Citation`, R5). `citations` is mandatory on success: a
  field with an empty value or empty citations is `status="unresolved"`,
  never silently filled. See § terminal-state rule for when `unresolved` /
  `skipped` settle the item.
- Max 10 active enrichments per webset (11th create → HTTP 400).
- Extraction order per item: already-fetched page markdown first; if a
  field is still unresolved, one targeted Phase A fetch of the item URL (or
  a follow-up search for the field, e.g. "Acme Corp Series B amount") then
  a Phase B schema-pinned extraction limited to that field.
- Type validation is strict (pydantic v2): `number` must parse as float,
  `date` as ISO-8601 date, `url`/`email`/`phone` against format validators,
  `options` must equal one of `options[]`.

### Company/people enrichment (digiquant company tracking)

EXA `category=company` returns inline `entities[{type: company,
properties{name, foundedYear, description, workforce, headquarters,
financials{fundingTotal, fundingLatestRound}, webTraffic}}]` with funding
history (live sample vendored at
`tests/ds/fixtures/websets/s5_category_company.json` — NuCicer
$16M total / Series A 2025-07-01 $11.5M; Pollen Systems $3.45M; Orchard
$26.4M; the `/tmp/exa-review/` path is scratch and MUST NOT be referenced
by code or tests). The OSS path reproduces this as:

1. Candidate generation via `SearXNGBackend.query()` with company-domain
   bias (`include_domains` from the caller's enrichment config +
   funding-press domains) — no EXA `category` param on the OSS path.
2. Fetch each candidate page (`ingest_url()` markdown / `extract_markdown`
   fallback for already-fetched pages).
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
   the item so digiquant company tracking reads one field.

## Tech Stack

Python 3.12, pydantic v2 (strict typing), httpx only for webhooks/EXA shim
(no `exa-py`), asyncio lifespan worker, SQLite store (stdlib `sqlite3`,
JSON columns), polars for CSV export (never pandas), digillm structured
completion for `llm` verification/extraction, digifetch-backed Phase A
fetch path (composed, never reimplemented), ruff line-length 100.

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
                                                     # Citation is IMPORTED from
                                                     # digisearch.web_providers.models
                                                     # (Phase A-owned, R5) — never
                                                     # redefined here
digisearch/src/digisearch/websets/store.py           # WebsetStore (SQLite CRUD)
                                                     # + get_store() env ctor
                                                     # (DIGISEARCH_WEBSETS_DB)
digisearch/src/digisearch/websets/verify.py          # verify_item (+ rules mode)
digisearch/src/digisearch/websets/enrich.py          # enrich_item, merge_company_entities,
                                                     # reconcile_funding_history
digisearch/src/digisearch/websets/runner.py          # Runner protocol + AsyncioRunner
                                                     # + lifespan task registry
                                                     # + resume_incomplete_websets
                                                     # + backfill_enrichment
digisearch/src/digisearch/websets/events.py          # append_event, list_events,
                                                     # deliver_webhook (HMAC-SHA256)
                                                     # + webhook_deliveries ledger
digisearch/src/digisearch/websets/export.py          # export_json, export_csv (polars)
digisearch/src/digisearch/websets/service.py         # facade: create_webset,
                                                     # get_webset, list_items,
                                                     # add_search,
                                                     # add_enrichment (+ backfill),
                                                     # remove_enrichment,
                                                     # create_monitor,
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
tests/ds/fixtures/websets/s5_category_company.json   # vendored EXA company sample
tests/ds/fixtures/websets/exa_401_pro_required.json  # vendored 401 body
tests/ds/fixtures/websets/fx_ecb_snapshot.json       # ECB FX snapshot (Major 5)
```

Modified (thin adapters only, existing auth patterns unchanged):

```
digisearch/src/digisearch/server.py                  # POST/GET webset routes
digisearch/src/digisearch/mcp_server.py              # digisearch_webset_* tools
digisearch/src/digisearch/orchestrator_tools.py      # manifest entries
digisearch/ARCHITECTURE.md                           # new § websets section
```

## Interfaces (exact signatures PRODUCED)

Import rule (R1/R2/R5 — no shape copies): `websets/models.py` imports
`Citation` (and only `Citation` + `WebSearchData` where needed) from
`digisearch.web_providers.models`; candidate retrieval calls
`SearXNGBackend.query()` + `ingest_url()` by direct import (same package);
Phase B synthesis is called by direct import; HTTP (`POST
/v1/orchestrator_invoke`, `POST /v1/research_turn`) is used only at
process/component boundaries (digiclaw, digigraph, external callers) with
the caller's service JWT. `rg -n "web_search\.models|SearXNGWebSearchProvider|run_web_search|[^_]ddgs|\"off\"|max_results|recency_days|[^t]cadence_s|DIGIWEBSETS_DB_PATH|/tmp/exa-review" digisearch/src/digisearch/websets/ tests/ds/test_websets_*.py`
must return zero matches (the review-file exclusion does not apply here).

All service functions live in `digisearch.websets.service` and are sync
(store I/O) except `run_webset_async`, which schedules background work and
returns immediately:

```python
def create_webset(
    *,
    query: str,
    count: int = 10,  # target VERIFIED items (not a page size; cf. num_results)
    criteria: list[VerificationCriterion] | list[dict[str, str]],
    enrichments: list[EnrichmentDef] | list[dict[str, object]] | None = None,
    verification_mode: Literal["llm", "rules"] = "llm",
    provider: Literal["auto", "exa", "searxng"] = "auto",  # Phase A tool-schema enum (R1)
    workspace_id: str | None = None,  # tenant isolation; "datatap" rejected (§ Cross-phase)
    store: WebsetStore | None = None,
) -> Webset:
    """Create a webset + its initial search; schedule the run; return status=running."""

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
    """List items newest-first; verification filter defaults to all (audit
    reads rejected). Returns (page, next_cursor | None)."""

def add_search(
    webset_id: str,
    *,
    query: str,
    count: int = 10,  # target verified items for THIS search
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
    interval_seconds: int = 3600,  # >= 60; webset-refresh cadence, NOT a Phase C Watch
    webhook_url: str | None = None,  # https public URL; None = poll-only
    store: WebsetStore | None = None,
) -> WebsetMonitor:
    """Attach a refresh cadence to a webset. Fan-out target is the webset's
    own re-run tick only — Phase C watches are never created, addressed, or
    notified here."""

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
    `rotate_webhook_secret` (24h overlap) below."""

def rotate_webhook_secret(webset_id: str, webhook_id: str, *, store: WebsetStore | None = None) -> WebhookConfig:
    """Generate a new secret with 24h overlap: the old secret stays valid
    until `previous_expires_at` (now+24h), then is dropped. Returns the
    record with the NEW secret in cleartext once."""

def list_events(
    webset_id: str,
    *,
    after: str | None = None,  # event id cursor; None = from head
    limit: int = 50,  # clamped 1..200
    store: WebsetStore | None = None,
) -> tuple[list[WebsetEvent], str | None]:
    """Cursor-paged event read (oldest-first after `after`); returns
    (page, next_cursor | None). The events table is append-only."""

def cancel_webset(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Set status=cancelled; the runner stops scheduling new items (in-flight
    item finishes its current field, then yields — no mid-LLM task.cancel);
    unattempted fields become `skipped`. Terminal: no further transitions."""

async def run_webset_async(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Drive one webset to idle: candidates -> verify -> enrich -> events. Never raises
    past WebsetNotFoundError; per-item failures mark items, webset-level failure emits
    webset.failed."""
```

HTTP (all behind existing `DigiAuthMiddleware`, `digisearch:query` scope —
same rule as `POST /v1/web_search`; no digikey change; errors use the
shared `digibase.errors.json_error_response` envelope with the stable
`code`s below; every new path gets a `_RATE_LIMITS` entry in `server.py`
following the existing per-IP `_rl_check` pattern):

```
POST /v1/websets                                        # 10/min (creation is a DoS surface)
  body: {query, count 1-100 default 10 (= target verified items),
         criteria[1-5], enrichments[0-10], verification_mode llm|rules,
         workspace_id?} -> 202 {webset} | 422 datatap_websets_disabled
GET /v1/websets/{webset_id}                             # 30/min
  -> 200 {webset} | 404 webset_not_found
POST /v1/websets/{webset_id}/searches                   # 10/min
  body: {query, count} -> 202 {search} (adds a follow-up search to a running/idle webset)
GET /v1/websets/{webset_id}/items?verification=&limit=&cursor=   # 30/min
  -> 200 {items, next_cursor} (cursor = last item id, newest-first; `offset` struck — aligned with Phase C)
POST /v1/websets/{webset_id}/enrichments                # 30/min
  -> 201 {enrichment} | 400 (>10) code enrichment_limit_exceeded
DELETE /v1/websets/{webset_id}/enrichments/{enrichment_id}  # 30/min -> 204
POST /v1/websets/{webset_id}/monitors                   # 10/min
  body: {interval_seconds >= 60, webhook_url https} -> 201 {webset_monitor}
GET /v1/websets/{webset_id}/events?after=&limit=        # 30/min
  -> 200 {events, next_cursor} (cursor-paged, oldest-first after `after`)
POST /v1/websets/{webset_id}/webhooks                   # 10/min
  body: {url https, events[item.created,item.enriched,webset.idle,webset.failed]} -> 201 {webhook, secret-once}
POST /v1/websets/{webset_id}/webhooks/{webhook_id}/rotate  # 10/min -> 200 {webhook, secret-once}
POST /v1/websets/{webset_id}/cancel                     # 10/min -> 200 {webset} (status=cancelled)
GET /v1/websets/{webset_id}/export?format=csv|json      # 10/min (export is a DoS surface)
  -> file (verified items only)
```

Stable error codes (all in the `digibase.errors` envelope):
`webset_not_found`, `search_not_found`, `enrichment_limit_exceeded`,
`invalid_criteria` (0 or >5 rules), `invalid_verification_mode`,
`datatap_websets_disabled`, `webhook_url_required`,
`webhook_url_private` (same message text as Phase C so one client handler
covers both), `rate_limit_exceeded` (existing).

MCP tools (`mcp_server.py`, loopback-only unchanged):

```
digisearch_webset_create(query, count, criteria_json, enrichments_json) -> webset id + status
digisearch_webset_status(webset_id) -> status + counts (verified/pending/rejected)
digisearch_webset_items(webset_id, verification, limit, cursor) -> compact item text
digisearch_webset_export(webset_id, format) -> CSV/JSON text (caps at 200 rows in chat)
```

Orchestrator manifest (`orchestrator_tools.py`): same four names, OpenAI
tool dicts, advertised unconditionally (OSS path has no key gate — unlike
`digisearch_web_search`, which stays EXA-gated). Dispatch via existing
`POST /v1/orchestrator_invoke`.

Webhook delivery: `POST {url}` with body `{event, webset_id, delivered_at}`
plus header `X-digi-signature: sha256=<hmac(secret, body)>` (the single
webhook convention shared with Phase C egress, R7h); `WebhookConfig{url,
events[], secret, previous_secret?, previous_expires_at?, active,
created_at}` — secret server-generated at create, stored alongside the
webhook record (never logged), rotated via
`rotate_webhook_secret` with 24h overlap. 3 attempts, linear backoff
5s/25s (explicit divergence from Phase C's 2 attempts — recorded reason:
dataset webhooks carry billable enrichment work, worth one extra attempt;
see § Cross-phase alignment). Delivery state is a persistent failure row
in the `webhook_deliveries` ledger table keyed by `(webhook_id, event_id)`
— the `events` table is append-only and event rows are NEVER mutated, so
"recorded on the event row" is struck. No retries past ledger-recorded
terminal failure (webset cadence re-fires on next tick).

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
  events are never duplicated (append is keyed by `(webset_id, kind,
  item_id, field)` with INSERT-or-ignore).
- **Cancellation under the semaphore:** `cancel_webset` flips the row to
  `cancelled`. The runner checks the flag before each semaphore
  acquisition and between items; an in-flight item finishes its current
  field extraction, then yields without scheduling further work;
  unattempted fields are marked `skipped`. No `task.cancel()` mid-LLM call
  (avoids half-written enrichment rows); shutdown path cancels the
  TaskGroup and awaits it, then marks still-`running` rows `cancelled`.
- **SQLite concurrency:** `WebsetStore` opens with `WAL` mode +
  `PRAGMA busy_timeout=5000` (same single-writer discipline as Phase C —
  residual risk 4 in the integration review); writes serialized by the
  module-level `threading.Lock`; the async runner reaches the sync store
  only via `await asyncio.to_thread(...)`.

## Cross-phase alignment (divergences recorded with reasons)

- **Tenant isolation:** `Webset` carries `workspace_id: str | None = None`
  (mirrors Phase C `Watch.workspace_id`). `create_webset` with a datatap
  `workspace_id` is rejected with `422 datatap_websets_disabled` (mirrors
  Phase C `datatap_monitors_disabled`); the runner never executes
  datatap-scoped websets. DataTap stays OFF end-to-end. If a later spec
  wants multi-tenant websets, it amends this section — no silent scoping.
- **Backend vocab map** (webset `provider` param vs Phase C `backend`
  label — different layers, both valid):

  | Layer | Values | Meaning |
  |---|---|---|
  | Webset candidate provider (`create_webset provider`, default `"auto"`) | `auto` \| `exa` \| `searxng` | Phase A tool-schema enum (Phase A Task 6); `auto` = searxng-first, EXA fallback only when configured |
  | Phase C `Watch.backend` | `oss` \| `exa` | turn-vs-shim label on `MonitorRun`; `oss` here ≈ websets `searxng` path |

  `ddgs` / `off` appear in neither layer (struck everywhere).
- **Recorded divergences from Phase C** (aligned where cheap, diverged
  with reason where the domain differs):

  | Area | Phase C | Phase D (this spec) | Reason |
  |---|---|---|---|
  | Cadence field | `interval_seconds` | `interval_seconds` | ALIGNED (`cadence_s` struck) |
  | List pagination | cursor (`run_id`) | cursor (`after` event id / item id) | ALIGNED (`offset` struck) |
  | Delivery retries | 2 attempts | 3 attempts, 5s/25s backoff | DIVERGED: dataset webhooks carry billable enrichment work |
  | Page truncation | n/a (recall path) | 6000 chars pre-LLM | DIVERGED: verification needs a fuller page than Phase B synthesis snippets |
  | Error shape | `digibase.errors` codes | same envelope + webset codes listed above | ALIGNED |
  | Store handle | `DIGISEARCH_MONITORS_DB` / `{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3` | `DIGISEARCH_WEBSETS_DB` / `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3` | ALIGNED (convention + volume) |

## Global Constraints

- Python 3.12, pydantic v2 everywhere, strict typing, ruff line-length 100,
  `ruff check + format --check` zero errors.
- Every test file lives at `tests/ds/test_websets_*.py` and carries
  `@pytest.mark.unit` (module `pytestmark` or per-test); every Task Run
  line invokes `pytest -m unit` (R3). `digisearch/tests/` MUST NOT be
  created (verified non-existent in the integration review).
- Polars only for CSV export — never pandas, never `pandas-ta`.
- Digi product names always lowercase in prose/docs/commits (`digisearch`,
  `digigraph`, `digillm`, `digifetch`, `digiquant`, `digikey`).
- MCP-first: every capability is a discoverable tool; no pipeline logic
  directly in LangGraph nodes (the agent `plan → retrieve → aggregate`
  pipeline may *read* webset items as a retrieval source via `list_items`,
  never drive the runner).
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
- Human gate: new external network exposure (webhook delivery to
  caller URLs is new egress) requires human review before merge — do not
  merge the events/webhook task without it.

## Provider capability matrix (finding from live testing)

Recorded here so implementers and callers stop rediscovering it:

| Capability | OSS path (this spec) | EXA free-tier key | EXA Pro key |
|---|---|---|---|
| `/search` (+`category=company` entities w/ funding) | n/a (Phase A/B mirror) | works ($0.007/sample, s5) | works |
| Websets verify + enrich | **ships here, no key** | `401: Upgrade to a Pro plan` (live finding, this key tier) | works via `providers/exa_websets.py` shim |
| Company funding history | SearXNG → fetch → extract → merge (§ Architecture) | inline `entities` | inline `entities` |
| Async delivery (poll/webhook/events) | ships here | n/a (paywalled with Websets) | EXA webhooks |

The live 401 response body and the s5 company sample are vendored under
`tests/ds/fixtures/websets/` (`exa_401_pro_required.json`,
`s5_category_company.json`) and referenced from the
`providers/exa_websets.py` module docstring by fixture path (request id
`97792aab…9ce7e`, s5 totals above) so the tier distinction is documented at
the code site, not just in this spec. `/tmp` paths are scratch and appear
nowhere in code, tests, or docstrings.

## Tasks

### Task 1: Models + per-field citation shapes

**Files:** create `websets/models.py`, `tests/ds/test_websets_models.py`.

- [ ] Step 1: write the failing test — construct a `Webset` with 2
  criteria + 2 enrichments (one `options`, one `company_profile`), a
  verified `WebsetItem` whose enrichment value carries 2 `Citation`s
  (imported from `digisearch.web_providers.models` — assert the import
  site is Phase A, `assert EnrichedField.model_fields["citations"]`
  annotates the Phase A type), a `CompanyEntity` with 2 funding rounds
  plus `provenance` entries per scalar, and a `WebsetMonitor` (bare
  `Monitor` import must fail); assert `model_dump(mode="json")`
  round-trips, `EnrichedField` with empty citations validates as
  `unresolved`, and ids match `^(ws|wss|wsi|wse|wsm)_<uuid4hex>$`.
  Every test carries `@pytest.mark.unit`.
  Run: `pytest tests/ds/test_websets_models.py -m unit -v` → FAIL
  (`No module named 'digisearch.websets'`).
- [ ] Step 2: implement `models.py` exactly per § Interfaces object table
  (pydantic v2, `extra="forbid"` on request shapes, `extra="ignore"` on
  EXA-normalized reads; `Citation` imported from
  `digisearch.web_providers.models`, never redefined; id prefixes
  `ws_/wss_/wsi_/wse_/wsm_` + uuid4-hex validated by pattern).
- [ ] Step 3: run `pytest tests/ds/test_websets_models.py -m unit -v` →
  PASS; run
  `ruff check digisearch/src/digisearch/websets/ && ruff format --check digisearch/src/digisearch/websets/` →
  zero errors.

### Task 2: SQLite store

**Files:** create `websets/store.py`, `tests/ds/test_websets_store.py`.
Consumes Task 1.

- [ ] Step 1: write the failing test — create webset → add search → add 3
  items (verified/rejected/pending) → `list_items` filter per status →
  append/​list 2 events → export-read round-trip. Use tmp file DB.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_store.py -m unit -v` → FAIL.
- [ ] Step 2: implement `WebsetStore(path)` + `get_store(db_path=None)`
  reading `DIGISEARCH_WEBSETS_DB` (default
  `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3`) with tables
  `websets/searches/items/enrichments/webset_monitors/webhooks/webhook_deliveries/events`;
  connect with `WAL` + `busy_timeout=5000`, writes under the module
  `threading.Lock`; status transitions validated
  (`running → idle|failed|cancelled`, never backwards);
  `set_webset_idle` refuses while any item has a `pending` field;
  `events` is append-only (no UPDATE/DELETE path exists).
- [ ] Step 3: run `pytest tests/ds/test_websets_store.py tests/ds/test_websets_models.py -m unit -v` →
  PASS + ruff clean.

### Task 3: Verification engine (llm + rules modes)

**Files:** create `websets/verify.py`, `tests/ds/test_websets_verify.py`.
Consumes Phase B extraction contract (mocked at the digillm boundary).

- [ ] Step 1: write the failing test — (a) rules mode: 2 criteria
  (domain allowlist + keyword presence) over a canned candidate → all-pass
  admits, keyword-miss rejects with reasoning referencing the rule; (b) llm
  mode with stubbed digillm completion returning per-rule verdicts →
  `CriterionResult` list carries `references: list[Citation]` (Phase A
  type, `title` defaulted, `excerpt` quoted); (c) empty criteria list
  raises `ValueError`; 6 criteria raise `ValueError`.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_verify.py -m unit -v` → FAIL.
- [ ] Step 2: implement `verify_item(url, title, markdown, criteria, *,
  mode, llm_client=None) -> list[CriterionResult]`; markdown truncated to
  6000 chars before any LLM call; rules mode implements exactly
  `domain`, `keyword`, `recency` rule kinds (`recency` = published-date
  within N days; named to avoid collision with the struck Phase A/B
  request field `recency_days` — R7c; unknown kind raises
  `ValueError`, never silently passes).
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
  the same Series A ($11.5M, 2025-07, NuCicer-style fixture from
  `tests/ds/fixtures/websets/s5_category_company.json`) merge to one
  round, total reconciles against the median claimed total; conflicting
  median beyond 1% → `unresolved` with reasoning; zero claimed totals →
  sum stands (non-vacuous); single third-party mention without quorum →
  `unresolved`; (d) entity merge: same-domain candidates merge, loser
  value lands in `alternatives[]` with its own citations; (e) provenance:
  every `CompanyEntity` scalar has a `provenance[field]` entry.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_enrich.py tests/ds/test_websets_company.py -m unit -v` →
  FAIL.
- [ ] Step 2: implement `enrich_item`, `reconcile_funding_history`
  (ECB snapshot FX, median-quorum rule per § Architecture),
  `merge_company_entities`, `company_profile_field`; company fixtures
  loaded from `tests/ds/fixtures/websets/` (never `/tmp`); FX rates from
  `tests/ds/fixtures/websets/fx_ecb_snapshot.json`.
- [ ] Step 3: run both files with `-m unit` → PASS + ruff clean.

### Task 5: Async runner + events + webhooks

**Files:** create `websets/runner.py`, `websets/events.py`,
`tests/ds/test_websets_runner.py`. Consumes Tasks 1–4, Phase A
`SearXNGBackend.query()` + `ingest_url()` (stubbed at those two methods —
direct-import boundary per R2; never raw httpx to the sidecar, never
`run_web_search`).

- [ ] Step 1: write the failing test — stubbed candidates (3) + stubbed
  verify (admit 2, reject 1) + stubbed enrich → after
  `await run_webset_async(id)`: webset is `idle`; assert the event log as
  a MULTISET `{item.created ×2, item.enriched ×2}` PLUS `webset.idle`
  strictly last (exact-sequence assertion banned — the semaphore-4
  concurrent runner does not guarantee inter-item order); `list_items`
  counts match; webhook delivery test uses `httpx.MockTransport` and
  asserts the `X-digi-signature` header verifies against the secret;
  forced enrich-failure item still emits `item.created` but no
  `item.enriched` for it, its fields are `unresolved` (terminal), webset
  still reaches `idle`; `cancel_webset` mid-run yields `cancelled` with
  unattempted fields `skipped`; startup-resume test seeds a `running`
  webset row then calls `resume_incomplete_websets()` and asserts it is
  re-driven without duplicating existing events.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_runner.py -m unit -v` → FAIL.
- [ ] Step 2: implement `AsyncioRunner` (semaphore 4 for fetch/verify,
  per-item errors contained, task registry + TaskGroup ownership +
  startup resume + semaphore-aware cancellation per § Async lifecycle;
  store I/O via `asyncio.to_thread` under the store lock);
  `backfill_enrichment(webset_id, enrichment_id)` for the
  `add_enrichment` path (§ Interfaces); `deliver_webhook` with 3
  attempts, 5s/25s backoff, HMAC-SHA256 header, ledger rows in
  `webhook_deliveries` (never event-row mutation). Fan-out target is the
  webset's own cadence tick only — no Phase C `Watch` is addressed here
  (residual risk 6 closed by this sentence).
- [ ] Step 3: run `pytest tests/ds/test_websets_runner.py -m unit -v` →
  PASS + ruff clean.

### Task 6: Service facade + export (polars CSV)

**Files:** create `websets/service.py`, `websets/export.py`,
`tests/ds/test_websets_export.py`. Consumes Tasks 1–5.

- [ ] Step 1: write the failing test — full local flow with stubbed
  runner boundaries: `create_webset` returns `running`; `get_webset`
  round-trips; `add_search` attaches a second search; `add_enrichment`
  11th raises; `remove_enrichment` retains resolved values;
  `create_monitor` returns a `WebsetMonitor` (and `Monitor` is
  unimportable); `add_webhook` returns a one-time secret;
  `rotate_webhook_secret` overlaps the old secret 24h; `list_events`
  cursor-pages; `cancel_webset` flips to `cancelled`;
  `export_webset(fmt="json")` contains per-field citations;
  `export_webset(fmt="csv")` parses with polars, one row per verified
  item, rejected items excluded, citations column holds URLs.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_export.py -m unit -v` → FAIL.
- [ ] Step 2: implement `service.py` (exact § Interfaces signatures —
  `create_webset`, `get_webset`, `list_items`, `add_search`,
  `add_enrichment` + `backfill_enrichment` execution path,
  `remove_enrichment`, `create_monitor`, `add_webhook`,
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
  `enrichment_limit_exceeded`), `GET .../export?format=csv` returns
  `text/csv`; auth assertion follows the explicit middleware pattern
  (there are no HTTP/auth tests in `tests/ds/test_web_exa.py` to copy —
  so: authed client = `TestClient(app, headers=auth_headers())` from
  `tests.digi_test_jwt` per `tests/ds/test_server_query.py`, unauthenticated
  `TestClient(app)` request → 401/403 from `DigiAuthMiddleware`); shim
  test: mocked 401 `Upgrade to a Pro plan` body (loaded from
  `tests/ds/fixtures/websets/exa_401_pro_required.json`) →
  `ExaWebsetsProRequiredError`, assert
  `issubclass(ExaWebsetsProRequiredError, ExaError)` and that
  `except ExaError` still catches it; datatap `workspace_id` create →
  422 `datatap_websets_disabled`.
  `@pytest.mark.unit` on every test.
  Run: `pytest tests/ds/test_websets_api.py -m unit -v` → FAIL.
- [ ] Step 2: implement routes (lifespan TaskGroup + `WEBSET_TASKS`
  registry per § Async lifecycle — bare `asyncio.create_task` without a
  handle is banned, never awaited inline), 4 MCP tools, 4 manifest
  entries (unconditional advertisement), shim with module docstring citing
  the vendored 401 fixture + s5 fixture paths. Add the `_RATE_LIMITS`
  entries from § Interfaces. Re-validate the EXA Websets request
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
  3 enrichments incl. `company_profile`), poll to `idle`, confirm the
  `item.created/item.enriched` multiset + `webset.idle`-last (never an
  exact sequence).
- [ ] Step 2: confirm funding totals against the vendored s5 EXA sample
  (`tests/ds/fixtures/websets/s5_category_company.json` — same companies
  should reconcile, not necessarily match; refresh
  `tests/ds/fixtures/websets/fx_ecb_snapshot.json` and record both).
- [ ] Step 3: `GET .../export?format=csv`, open in a spreadsheet, confirm
  one-row-per-item + citation URLs present.
- [ ] Step 4: append measured timings + reconciliation notes to
  `digisearch/ARCHITECTURE.md` websets rollout paragraph.
