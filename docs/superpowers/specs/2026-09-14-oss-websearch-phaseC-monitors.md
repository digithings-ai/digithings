# Phase C — Scheduled Web-Search Monitors (OSS EXA-monitors equivalent)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this spec task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship scheduled search watches owned by digisearch: a cron/interval-scheduled
query runs the SHALLOW recall path (`digisearch_web_search` → Phase A
`digisearch.web_providers.searxng.SearXNGBackend.query()` / `web_exa.exa_search`,
returning `WebSearchData` only — never the Phase B research turn
`digisearch_research_delegate`), semantic dedup surfaces only new content
versus previous runs, and delivery fans out to webhook/slack/email — with a run
envelope shaped so a paid EXA monitor can substitute for any OSS watch downstream.
Cost (`WebSearchData.cost_dollars`) is surfaced advisory-only, never enforced.

**Consumes:** Shallow recall entry points (`web_exa.exa_search` in
`digisearch/src/digisearch/web_exa.py` returning the `WebSearchData` contract;
Phase A `digisearch.web_providers.searxng.SearXNGBackend.query()` returning the
same `WebSearchData` shape) invoked by DIRECT IN-PROCESS CALL within the
`digisearch` process per R2 (no same-process loopback HTTP to self; loopback
`POST /v1/orchestrator_invoke {tool: digisearch_web_search}` survives only as an
integration-test path) + digiclaw agent scheduler
(`digiclaw/src/digiclaw/scheduler.py`, `schedule_schema.py`, `cron.py`) as the
dumb clock + a new `digibase.service_auth.get_service_jwt` helper created as an
explicit dependency inside Task 8 (it does NOT exist today — `digibase/` ships
no `service_auth.py`; see Task 8).

Landed-behavior note (not new work): `server.py` already passes
`include_domains`/`exclude_domains` through in BOTH dispatch arms
(`api_orchestrator_invoke` web-search arm at `server.py:817-844` +
`POST /v1/digisearch_web_search` at `server.py:916-944`) and the tool-schema
properties exist in `orchestrator_tools.py:397-406`. Monitors consume that
passthrough; no task re-specifies it.

**Produces:** Watch CRUD + schedule config + dedup rules + delivery config +
durable run history, over HTTP (`:8002`), MCP (`:8765`), and the orchestrator
manifest — orchestration + storage only, no new search internals.

**Spec context:** digithings-ai/digithings#3853 family; plans
`docs/superpowers/plans/2026-09-10-web-search-mcp-tool.md` (Phase A/B provider
+ service wiring), `2026-09-11-web-search-default-on-tool-only.md` (tool-only
fail-hard, service JWT, datatap OFF), `2026-09-12-web-search-followups.md`
(fail-closed hardening). This spec contradicts none of them; it calls only
their produced surfaces.

---

## 1. Architecture

```
digiclaw scheduler (clock only)            digisearch :8002 (owns everything else)
─────────────────────────────            ─────────────────────────────────────────
continuous agent, every 60s                POST /v1/monitors/tick
  │  run_due_monitors()  ───────────────▶  │ due evaluation (cron / interval)
  │  service JWT in header                  │ for each due watch:
  │                                         │   runner.run_watch(trigger=schedule)
   │                                         │     │ shallow recall (DIRECT call, same process)
  │                                         │     │ dedup vs previous runs
  │                                         │     │ persist MonitorRun (sqlite)
  │                                         │     ▼ fan-out delivery (webhook/slack/email)
```

Design rules:

- **digisearch owns schedule evaluation, execution, dedup, storage, delivery.**
  digiclaw contributes only the wake-up tick (`POST /v1/monitors/tick`) via the
  existing `Scheduler` + `AgentRunner` injection. No cron parsing is duplicated:
  watch schedules reuse the 5-field cron grammar by IMPORTING
  `parse_cron`/`CronExpression.matches` from `digiclaw/cron.py` (same grammar
  object, same rules — copying the grammar is forbidden, see §4.4), and
  `interval_seconds` means the same thing as digiclaw `continuous` mode.
- **Shallow recall is called directly, never over loopback HTTP (R2).**
  The runner calls `web_exa.exa_search(...)` / Phase A
  `SearXNGBackend.query(...)` in-process within `digisearch` (provider
  selection: EXA when `is_exa_configured()`, else the OSS SearXNG backend —
  same `WebSearchData` shape either way; never `import` the Phase B
  `digisearch_research_delegate` turn). Same-process loopback HTTP to self
  (`POST /v1/orchestrator_invoke {tool: digisearch_web_search}`) is NOT a
  runtime path; it survives only as an integration-test path. Tool-only
  fail-hard is inherited: an empty/failed recall raises, the run is persisted
  with `status: failed`, and delivery is skipped. No synthesis fallback is
  added here (plan 2026-09-11 deleted all synthesis paths). Cost passthrough
  (`cost_dollars`) is advisory-only display data, never a gate.
- **One canonical run envelope.** `MonitorRun` is the only shape downstream
  consumers (MCP, orchestrator, poll clients, EXA adapter) ever see. The EXA
  adapter translates remote EXA monitor runs into `MonitorRun`; OSS runs are
  born as `MonitorRun`. Backend is a label (`oss` | `exa`), never a shape fork.
- **Reference semantics extracted, not depended on.** changedetection.io
  (Apache-2.0) contributes: per-watch content fingerprint + "notify only on
  change" + recheck interval. Huginn (MIT) contributes: event-with-memory
  agents + seen-ID dedup + per-target delivery receipts. Both are cribbed as
  described behavior in `dedup.py` / `delivery.py` docstrings; neither is
  added as a dependency, sidecar, or vendored code.
- **Local-dev story is poll-first.** Default delivery `mode: poll` stores runs
  for `GET` retrieval with zero network exposure. `webhook`/`fanout` modes
  require public HTTPS targets and are rejected otherwise at create/update
  time with EXA-identical error codes (see §5 interop notes). Manual trigger
  + poll is a first-class path, not a fallback.

---

## 2. Tech Stack

Python 3.12, Pydantic v2 (`ConfigDict(extra="forbid")` on all HTTP bodies, per
`digisearch/ARCHITECTURE.md` §Input Validation Posture), `httpx` (delivery +
EXA adapter; already in base install), stdlib `sqlite3` (run storage; no new
dep), stdlib `smtplib` (email leg; no new dep), stdlib `difflib`
(similarity leg of dedup; no new dep), FastMCP (`mcp>=1.2,<2`), existing
`DigiAuthMiddleware` + `digisearch:query` scope (no digikey change), ruff
line-length 100.

No new dependencies. No new port. No new auth scope. No pandas. No embeddings
or search internals (dedup is URL identity + content hash + token-set
similarity only).

---

## 3. File Structure (exact paths)

```
digisearch/src/digisearch/monitors/__init__.py      # package doc + lazy re-exports
digisearch/src/digisearch/monitors/models.py        # Watch, WatchSchedule, DedupRule,
                                                    # DeliveryConfig, MonitorRun, receipts
digisearch/src/digisearch/monitors/store.py         # sqlite CRUD + run history
digisearch/src/digisearch/monitors/dedup.py         # fingerprint + seen-ID + similarity
digisearch/src/digisearch/monitors/runner.py        # run_watch() + tick_due_watches()
digisearch/src/digisearch/monitors/delivery.py      # webhook/slack/email fan-out
digisearch/src/digisearch/monitors/exa_adapter.py   # EXA monitor <-> MonitorRun mapping
digisearch/src/digisearch/server.py                 # +10 routes (modify, §4)
digisearch/src/digisearch/mcp_server.py             # +4 tools (modify, §4)
digisearch/src/digisearch/orchestrator_tools.py     # +2 tool defs (modify, §4)
digiclaw/src/digiclaw/monitors_tick.py              # run_due_monitors() clock caller (new)
digiclaw/agents/web-watch-tick.yaml                 # continuous 60s tick agent (new)
digibase/src/digibase/service_auth.py               # get_service_jwt (new prerequisite, Task 8)
tests/digibase/test_service_auth.py                 # new (Task 8)
tests/ds/test_monitors_models.py                    # new
tests/ds/test_monitors_store.py                     # new
tests/ds/test_monitors_dedup.py                     # new
tests/ds/test_monitors_runner.py                    # new
tests/ds/test_monitors_delivery.py                  # new
tests/ds/test_monitors_api.py                       # new
tests/ds/test_monitors_exa_adapter.py               # new
tests/dc/test_monitors_tick.py                      # new
```

Storage: SQLite file at `DIGISEARCH_MONITORS_DB`, default
`{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3` (Docker: mount the same
persistent volume as Chroma data; document the mount in `Task 8`). Tables
`watches (watch_id PK, body JSON, updated_at)` + `runs (run_id PK, watch_id,
status, trigger, started_at, finished_at, body JSON)` with an index on
`(watch_id, started_at DESC)`. JSON bodies keep the schema evolvable without
migrations; queryable columns stay real columns.

---

## 4. Interfaces (exact signatures PRODUCED)

### 4.1 Models (`monitors/models.py`)

```python
class WatchSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["cron", "interval"]          # cron: 5-field, same grammar as digiclaw/cron.py
    cron: str | None = None                    # required when mode=cron
    interval_seconds: int | None = Field(default=None, ge=60)  # required when interval
    enabled: bool = True
    timezone: str = "UTC"                      # IANA name; invalid -> 422 code timezone_unknown

class DedupRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: Literal["url", "url_content"] = "url_content"
    similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)

class DeliveryTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["webhook", "slack", "email"]
    url: str | None = None                     # webhook + slack (https, public)
    email_to: list[str] | None = None          # email (max 10 addresses)

class DeliveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["poll", "webhook", "fanout"] = "poll"
    targets: list[DeliveryTarget] = Field(default_factory=list, max_length=5)

class Watch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    watch_id: str = ""                         # server-assigned ulid-hex on create
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=500)
    search_type: str = "auto"                  # validated against VALID_SEARCH_TYPES
    num_results: int = Field(default=8, ge=1, le=100)
    category: str | None = None                # passthrough to exa_search/SearXNGBackend.query (R7j)
    include_domains: list[str] = Field(default_factory=list, max_length=5)
    exclude_domains: list[str] = Field(default_factory=list, max_length=20)
    schedule: WatchSchedule
    dedup: DedupRule = Field(default_factory=DedupRule)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    backend: Literal["oss", "exa"] = "oss"
    exa_monitor_id: str | None = None          # required when backend=exa
    workspace_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class DeliveryReceipt(BaseModel):
    target_kind: str
    ok: bool
    status_code: int | None = None
    error: str | None = None

class MonitorRun(BaseModel):
    """Canonical envelope. OSS runs are born in this shape; EXA runs are
    translated into it by exa_adapter. Downstream code never branches on backend."""
    model_config = ConfigDict(extra="forbid")
    run_id: str
    watch_id: str
    backend: Literal["oss", "exa"] = "oss"
    status: Literal["ok", "no_change", "failed"]
    trigger: Literal["schedule", "manual", "poll", "exa_webhook"]
    started_at: datetime
    finished_at: datetime
    query_snapshot: dict[str, Any]             # query/search_type/num_results/domains
    results_all: list[dict[str, Any]]          # WebSearchData result dicts, as returned
    results_new: list[dict[str, Any]]          # dedup survivors only
    dedup_stats: dict[str, int]                # {seen, new, changed, unchanged}
    cost_dollars: dict[str, Any] | None = None # passthrough from WebSearchData
    delivery: list[DeliveryReceipt] = Field(default_factory=list)
    error: str | None = None
```

Status semantics: `ok` = new content found and stored/delivered; `no_change` =
turn succeeded but dedup removed everything (delivery skipped, run still
persisted); `failed` = turn raised or backend errored (delivery skipped,
`error` set, fail-hard preserved — never an empty `ok`).

### 4.2 Store (`monitors/store.py`)

```python
class MonitorStoreError(RuntimeError): ...

def get_store(db_path: str | None = None) -> MonitorStore: ...  # env DIGISEARCH_MONITORS_DB

class MonitorStore:
    def create_watch(self, watch: Watch) -> Watch: ...
    def list_watches(self, *, workspace_id: str | None = None) -> list[Watch]: ...
    def get_watch(self, watch_id: str) -> Watch: ...            # missing -> MonitorStoreError(code=watch_not_found)
    def update_watch(self, watch_id: str, patch: dict[str, Any]) -> Watch: ...
    def delete_watch(self, watch_id: str) -> None: ...
    def append_run(self, run: MonitorRun) -> MonitorRun: ...
    def list_runs(self, watch_id: str, *, limit: int = 20, cursor: str | None = None) -> tuple[list[MonitorRun], str | None]: ...
    def get_run(self, watch_id: str, run_id: str) -> MonitorRun: ...
    def seen_fingerprints(self, watch_id: str, *, limit_runs: int = 10) -> dict[str, str]: ...
```

`cursor` is the `run_id` to page after (newest-first); returns `(page,
next_cursor | None)`. `limit` clamped to 1..100.

### 4.3 Dedup (`monitors/dedup.py`)

```python
def normalize_url(url: str) -> str: ...        # lowercase host, strip fragment + trailing slash + utm_*
def fingerprint(title: str, text: str) -> str: ...  # sha256 of normalized title+text
def dedup_results(
    current: list[dict[str, Any]],
    seen: dict[str, str],                       # normalized_url -> fingerprint
    rule: DedupRule,
) -> tuple[list[dict[str, Any]], dict[str, int]]: ...
```

Semantics (changedetection.io + Huginn, extracted): identity key is
`normalize_url`; `match=url` reports unseen keys as new; `match=url_content`
additionally reports a seen key as new when its fingerprint changed (content
edit counts as new, mirroring "notify on change"); near-duplicate unseen URLs
whose `difflib.SequenceMatcher` title ratio >= `similarity_threshold` against
any seen title collapse to unchanged (mirroring de-duplication memory). Stats
keys are exactly `{seen, new, changed, unchanged}`.

### 4.4 Runner (`monitors/runner.py`)

```python
def run_watch(
    watch_id: str,
    *,
    trigger: Literal["schedule", "manual", "poll"] = "manual",
    store: MonitorStore | None = None,
) -> MonitorRun: ...
def tick_due_watches(
    *,
    now: datetime | None = None,
    store: MonitorStore | None = None,
) -> list[MonitorRun]: ...
def is_due(watch: Watch, now: datetime, last_run_at: datetime | None) -> bool: ...
def _invoke_shallow_recall(
    *, query: str, search_type: str, num_results: int,
    category: str | None, include_domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> WebSearchData: ...
```

`run_watch` flow: load watch → DIRECT in-process call `_invoke_shallow_recall`
(`web_exa.exa_search` when `is_exa_configured()`, else Phase A
`SearXNGBackend.query()` — both returning `WebSearchData`; per R2 there is NO
same-process loopback HTTP to self, and NO bearer token is threaded through
the runner) → `dedup_results` against `seen_fingerprints` → persist run →
fan out delivery unless `status in (no_change, failed)` or `mode=poll` →
return run. Any recall exception → persist `status: failed` with
`error=str(exc)` and re-raise as `MonitorRunError` carrying the persisted
`run_id`. `tick_due_watches` runs all due + enabled watches, isolates
per-watch failures (one watch failing never aborts the tick), and returns one
`MonitorRun` per attempted watch. Tick-phase skew: the 60s digiclaw tick is a
wake-up only, so a watch whose cadence boundary falls between ticks fires on
the next tick (up to ~60s late); per-watch cadence stays exact relative to
`last_run_at`. Timezone: `is_due` converts — `now` (assumed UTC when naive)
and `last_run_at` are normalized to the watch's `schedule.timezone` inside
`is_due` (callers pass UTC; the runner owns conversion, never the clock
caller). Cron grammar: IMPORT, never copy — `is_due` cron evaluation imports
`parse_cron`/`CronExpression.matches` from `digiclaw.cron` (Task 4 adds
`digiclaw` as a dependency of the monitors runner or moves evaluation behind
a small injected predicate; duplicating the grammar is forbidden).

### 4.5 Delivery (`monitors/delivery.py`)

```python
def validate_delivery(config: DeliveryConfig) -> None: ...
def deliver(
    run: MonitorRun, watch: Watch, *,
    delivery_secret: str, timeout_s: float = 10.0,
) -> list[DeliveryReceipt]: ...
```

`validate_delivery` raises `DeliveryConfigError` with EXA-identical codes:
`webhook_url_required` (`[webhook]: Required` — mode needs targets but none
given) and `webhook_url_private`
(`[webhook.url]: Webhook URL cannot point to localhost or private IPs` —
non-https, localhost, loopback, or RFC-1918/ULA target). Called on every
watch create/update, never only at run time. `deliver` POSTs
`run.model_dump(mode="json")` to webhook/slack targets (httpx, 2 attempts,
linear backoff) and sends a text summary via stdlib `smtplib` using
`DIGISEARCH_SMTP_*` env for email targets; every target yields exactly one
receipt; transport exceptions become `ok=False` receipts (delivery is
best-effort per target, the run itself already persisted). Signing (R7h):
every webhook/slack POST carries `X-digi-signature: sha256=<hex>` where hex
is `HMAC-SHA256(key=per-watch delivery secret, msg=raw request body bytes)`.
The secret is server-generated per watch at create time
(`secrets.token_hex(32)`), stored alongside the watch body (never logged),
and returned once in the create response as `delivery_secret` (rotation via
`PATCH` with `{"rotate_delivery_secret": true}`). Receivers verify the HMAC
over the raw body before trusting the payload. Unsigned POSTs are never sent.

### 4.6 HTTP (`server.py`; all behind `digisearch:query` via existing `DigiAuthMiddleware` EXCEPT `exa_webhook`)

| Method + path | Rate limit | Body → response |
|---|---|---|
| `POST /v1/monitors` | 30/min | `Watch` (no `watch_id`) → `201 Watch` |
| `GET /v1/monitors` | 30/min | `?workspace_id=` → `{"watches": [...]}` |
| `GET /v1/monitors/{watch_id}` | 30/min | → `Watch` / 404 `watch_not_found` |
| `PATCH /v1/monitors/{watch_id}` | 30/min | partial dict → `Watch` (re-validates delivery) |
| `DELETE /v1/monitors/{watch_id}` | 30/min | → `{"deleted": watch_id}` (runs retained) |
| `POST /v1/monitors/{watch_id}/trigger` | 10/min | `{"mode": "manual" \| "poll"}` → `201 MonitorRun` |
| `GET /v1/monitors/{watch_id}/runs` | 30/min | `?limit=&cursor=` → `{"runs": [...], "next_cursor": ...}` |
| `GET /v1/monitors/{watch_id}/runs/{run_id}` | 30/min | → `MonitorRun` / 404 `run_not_found` |
| `POST /v1/monitors/tick` | 10/min | `{}` → `{"runs": [MonitorRun...]}` (due watches only) |
| `POST /v1/monitors/exa_webhook` | 10/min | AUTH-EXEMPT: EXA remote payload → translated `MonitorRun` persisted |

`exa_webhook` auth-exemption (mandatory): EXA holds no digikey JWT and presents
only the shared `EXA_MONITOR_WEBHOOK_SECRET`. `digisearch_path_scopes` MUST
return `None` for `POST /v1/monitors/exa_webhook` (explicit exemption alongside
`_PUBLIC_PATHS`), and the handler MUST reject with 401 `exa_bad_signature`
when the configured secret is missing on the server or the request header does
not match (`X-Exa-Signature` bearer-compare via `hmac.compare_digest`; never
log the presented value). All other monitor routes stay behind
`digisearch:query`.

Validation errors use the shared `digibase.errors` shape via explicit
`json_error_response(...)` calls (custom `code` values are NOT produced by the
default FastAPI validation handler, which emits `validation_error` — every
`§4.6` stable code below MUST be raised through `json_error_response` with the
shared `{"error": {"code", "message", ...}}` envelope per `digibase/errors.py`):
`watch_not_found`, `run_not_found`, `invalid_cron`,
`webhook_url_required`, `webhook_url_private`, `exa_not_configured`,
`exa_bad_signature`, `datatap_monitors_disabled`. Unknown `search_type` is
rejected with the same `invalid search_type: ...` message as
`POST /v1/orchestrator_invoke`.

### 4.7 MCP (`mcp_server.py`, loopback-only) + orchestrator manifest

MCP tools: `monitors_create_watch(query, schedule_cron?, interval_seconds?,
num_results?, category?, include_domains?, exclude_domains?, delivery_mode?) -> str`
(JSON `Watch`), `monitors_list_watches() -> str`,
`monitors_trigger_watch(watch_id, mode?) -> str` (JSON `MonitorRun`),
`monitors_get_runs(watch_id, limit?) -> str`. Fail-closed without a
reachable store or backend exactly like `digisearch_web_search` returns its
disabled string without `EXA_API_KEY`.

Orchestrator manifest additions (`orchestrator_tools.py`):
`TOOL_DIGISEARCH_MONITORS_TRIGGER = "digisearch_monitors_trigger"` and
`TOOL_DIGISEARCH_MONITORS_RUNS = "digisearch_monitors_runs"`, dispatched in
`api_orchestrator_invoke` to the same runner/store functions (same envelope,
`ok: False` + error string on failure — the established fail-hard shape).

### 4.8 digiclaw clock (`digiclaw/monitors_tick.py` + `digiclaw/agents/web-watch-tick.yaml`)

```python
def run_due_monitors(*, digisearch_url: str, bearer_token: str | None = None) -> dict: ...
```

Reads `DIGISEARCH_URL` (default `http://127.0.0.1:8002`), resolves the service
JWT via `digibase.service_auth.get_service_jwt` — the NEW module created in
Task 8 (explicit dependency; does not exist today) — when no bearer is passed
(imported lazily so the module never fails at import time), POSTs
`/v1/monitors/tick`, returns `{"runs": n, "failed": m}`. Transport/auth
failure raises (tick outcome visible in scheduler `last_error`, never
swallowed). The YAML agent runs it on `continuous` `interval_seconds: 60`,
`enabled: true`; per-watch cadence stays on the watch schedule, so the 60s
tick is only a wake-up (up to ~60s tick-phase skew is expected and owned by
`is_due`, see §4.4).

---

## 5. Global Constraints

- Python 3.12, Pydantic v2 everywhere, strict typing, ruff line-length 100;
  `ruff check digisearch/src/digisearch/monitors/ && ruff format --check`
  same path — zero errors. Polars only — never pandas (no pandas import
  anywhere; dedup uses stdlib).
- Lowercase digi product names in prose/docs/commits (`digisearch`,
  `digiclaw`, `digifetch`, `digigraph`).
- Entity naming drops the `Digi` prefix: `Watch`, `MonitorRun`,
  `MonitorStore`, `DeliveryReceipt` — never `DigiWatch`.
- Every new HTTP route requires `digisearch:query` via the existing
  `DigiAuthMiddleware` (extend `digisearch_path_scopes`; no digikey change) —
  EXCEPT `POST /v1/monitors/exa_webhook`, which is explicitly auth-exempt
  with a mandatory `EXA_MONITOR_WEBHOOK_SECRET` check (see §4.6).
  MCP stays loopback-only `127.0.0.1:8765`.
- Fail-closed / fail-hard throughout: unknown search type, missing watch/run,
  delivery misconfig, and recall failures all raise or return `ok: False` —
  never an empty `ok` run. No `DIGISEARCH_ALLOW_STUB` reads in monitors code
  (SQLite store works identically in tests and production).
- No raw user query, result body, or webhook URL with credentials in INFO
  logs (metadata only: `watch_id`, `run_id`, counts, durations) — the
  digisearch privacy rule. Webhook URLs may carry no `userinfo`
  (`https://token@host` rejected as `webhook_url_private`).
- datatap tenant: watch create with a datatap `workspace_id` is rejected
  (`datatap_monitors_disabled`), and the tick skips datatap-scoped watches —
  DataTap stays OFF end-to-end per plans 2026-09-11/12.
- Every change traces to its implementation issue (`task/<N>-slug` branch or
  `Fixes #N`); update `digisearch/ARCHITECTURE.md` (§3 + §9) and
  `digiclaw/ARCHITECTURE.md` (§3) on interface change.
- Human gate (R7g): REQUIRED for Tasks 5 and 6 before merge. Webhook/SMTP
  delivery is new EGRESS to caller-controlled endpoints (arbitrary https URLs
  + operator SMTP relay), which trips the root `AGENTS.md` human gate for
  "new external network exposure" — the struck "Human gate: none" claim was
  wrong. Tasks 5 (`delivery.py`: webhook POST targets, `smtplib` relay env)
  and 6 (route wiring that enables that egress) MUST each be held for human
  review; the Task 5/6 acceptance steps explicitly include the review gate.
  EXA adapter reuses the existing `EXA_API_KEY` integration (no new inbound
  service); all listeners stay loopback. If implementation adds a non-stdlib
  mail/Slack SDK, that addition needs human review as well.

### EXA interop notes (observed live behavior, must be mirrored)

- EXA monitor creation without a webhook fails as `[webhook]: Required`.
  OSS `POST /v1/monitors` with `delivery.mode != poll` and zero targets
  fails with code `webhook_url_required` and the same message text, so one
  client error handler covers both backends.
- EXA rejects private webhook targets at create time as
  `[webhook.url]: Webhook URL cannot point to localhost or other private
  or reserved IP addresses`. OSS `validate_delivery` enforces the identical
  rule (https-only, no localhost/loopback/RFC-1918/ULA/link-local/reserved,
  resolved via `socket.getaddrinfo` at validation time) with the same
  message text. Local dev therefore uses `mode: poll` + `trigger` + `GET
  runs`, or exposes a public URL via Cloudflare Tunnel / Tailscale per
  `SECURITY.md` (loopback-only binding is never relaxed for monitors).
- Manual-trigger + poll works on EXA today and is the portable path: any
  client that only uses create → trigger → list/get runs works unchanged
  against `backend: oss` and `backend: exa`. Only `delivery.targets` of kind
  `webhook` with a public URL behaves remotely on EXA (delivery executed by
  EXA, receipts recorded as `target_kind: exa_webhook`).

---

## 6. Tasks

### Task 1: Monitor models + canonical envelope

**Files:**
- Create: `digisearch/src/digisearch/monitors/__init__.py`
- Create: `digisearch/src/digisearch/monitors/models.py`
- Test: `tests/ds/test_monitors_models.py`

**Interfaces:**
- Consumes: `VALID_SEARCH_TYPES` from `digisearch.web_exa` (validation only),
  `WebSearchData` result-dict shape (received, never imported for logic).
- Produces: `Watch`, `WatchSchedule`, `DedupRule`, `DeliveryConfig`,
  `MonitorRun`, `DeliveryReceipt` used by Tasks 2–8.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from digisearch.monitors.models import DeliveryConfig, Watch

@pytest.mark.unit
def test_watch_defaults_poll_no_targets():
    w = Watch.model_validate(
        {"name": "etf flows", "query": "bitcoin etf flows",
         "schedule": {"mode": "interval", "interval_seconds": 3600}}
    )
    assert w.delivery.mode == "poll"
    assert w.backend == "oss"
    assert w.dedup.match == "url_content"

def test_interval_minimum_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Watch.model_validate(
            {"name": "x", "query": "y",
             "schedule": {"mode": "interval", "interval_seconds": 5}}
        )

@pytest.mark.unit
def test_monitor_run_envelope_keys():
    from digisearch.monitors.models import MonitorRun
    run = MonitorRun.model_validate(
        {"run_id": "r1", "watch_id": "w1", "status": "ok",
         "trigger": "manual", "started_at": "2026-09-14T00:00:00Z",
         "finished_at": "2026-09-14T00:01:00Z",
         "query_snapshot": {"query": "q"}, "results_all": [], "results_new": [],
         "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}}
    )
    assert run.dedup_stats["new"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_models.py -v`
Expected: FAIL with "No module named 'digisearch.monitors'"

- [ ] **Step 3: Write minimal implementation**

Implement `models.py` exactly per §4.1 (all HTTP-facing models
`extra="forbid"`; `interval_seconds ge=60`; `WatchSchedule` model validator
requiring `cron` for `cron` mode / `interval_seconds` for `interval` mode;
`search_type` validated against `VALID_SEARCH_TYPES` in `Watch`; `category`
is a plain passthrough field consumed by the landed `exa_search`/`server.py`
domain+category plumbing — no new provider work).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/monitors/ && ruff format --check digisearch/src/digisearch/monitors/`
Expected: zero errors

---

### Task 2: SQLite watch/run store

**Files:**
- Create: `digisearch/src/digisearch/monitors/store.py`
- Test: `tests/ds/test_monitors_store.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `MonitorStore` / `get_store` used by Tasks 4, 6, 7.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from digisearch.monitors.models import MonitorRun, Watch
from digisearch.monitors.store import MonitorStore

@pytest.mark.unit
def test_crud_and_run_history_pagination(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        Watch.model_validate(
            {"name": "etf", "query": "etf flows",
             "schedule": {"mode": "interval", "interval_seconds": 3600}}
        )
    )
    assert w.watch_id
    assert store.get_watch(w.watch_id).query == "etf flows"
    for i in range(3):
        store.append_run(
            MonitorRun.model_validate(
                {"run_id": f"r{i}", "watch_id": w.watch_id, "status": "no_change",
                 "trigger": "schedule", "started_at": "2026-09-14T00:00:00Z",
                 "finished_at": "2026-09-14T00:01:00Z",
                 "query_snapshot": {"query": "etf flows"}, "results_all": [],
                 "results_new": [],
                 "dedup_stats": {"seen": 1, "new": 0, "changed": 0, "unchanged": 1}}
            )
        )
    page, cursor = store.list_runs(w.watch_id, limit=2)
    assert [r.run_id for r in page] == ["r2", "r1"]
    assert cursor == "r1"
    page2, cursor2 = store.list_runs(w.watch_id, limit=2, cursor=cursor)
    assert [r.run_id for r in page2] == ["r0"]
    assert cursor2 is None
    store.delete_watch(w.watch_id)
    assert store.list_runs(w.watch_id)[0] != []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_store.py -v`
Expected: FAIL with "No module named" / missing `MonitorStore`

- [ ] **Step 3: Write minimal implementation**

Stdlib `sqlite3` only; `WAL` mode; `watch_id` as 26-char ulid-hex generated
in `create_watch`; runs retained after watch delete; `seen_fingerprints`
merges newest-first up to `limit_runs`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_store.py tests/ds/test_monitors_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/monitors/store.py tests/ds/test_monitors_store.py && ruff format --check digisearch/src/digisearch/monitors/store.py tests/ds/test_monitors_store.py`
Expected: zero errors

---

### Task 3: Semantic dedup (changedetection.io + Huginn semantics)

**Files:**
- Create: `digisearch/src/digisearch/monitors/dedup.py`
- Test: `tests/ds/test_monitors_dedup.py`

**Interfaces:**
- Consumes: Task 1 `DedupRule`.
- Produces: `dedup_results` / `normalize_url` / `fingerprint` used by Task 4.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from digisearch.monitors.dedup import dedup_results, fingerprint, normalize_url
from digisearch.monitors.models import DedupRule

@pytest.mark.unit
def test_normalize_strips_tracking_and_fragment():
    assert normalize_url("https://A.com/x/?utm_source=n#frag") == "https://a.com/x"

@pytest.mark.unit
def test_unseen_url_is_new_changed_content_is_new():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "body one")}
    current = [
        {"url": "https://a.com/1", "title": "T1 EDITED substantially", "text": "body one v2"},
        {"url": "https://b.com/2", "title": "Brand new", "text": "hello"},
    ]
    new, stats = dedup_results(current, seen, rule)
    assert stats == {"seen": 1, "new": 1, "changed": 1, "unchanged": 0}
    assert {r["url"] for r in new} == {"https://a.com/1", "https://b.com/2"}

@pytest.mark.unit
def test_near_duplicate_title_collapses():
    rule = DedupRule(match="url_content", similarity_threshold=0.5)
    seen = {"https://a.com/1": fingerprint("Bitcoin ETF flows rise", "x")}
    current = [{"url": "https://a.com/2", "title": "Bitcoin ETF flows rise!", "text": "y"}]
    new, stats = dedup_results(current, seen, rule)
    assert new == [] and stats["unchanged"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_dedup.py -v`
Expected: FAIL with "No module named 'digisearch.monitors.dedup'"

- [ ] **Step 3: Write minimal implementation**

Implement §4.3 exactly: `normalize_url` (lowercase host, drop fragment,
trailing slash, `utm_*` params); `fingerprint` (sha256 over
`title.strip().lower() + "\n" + text collapsed-whitespace`); `dedup_results`
per the three rules with exact stats keys. No embeddings, no network.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_dedup.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/monitors/dedup.py && ruff format --check digisearch/src/digisearch/monitors/dedup.py`
Expected: zero errors

---

### Task 4: Watch runner (Phase B turn → dedup → persist)

**Files:**
- Create: `digisearch/src/digisearch/monitors/runner.py`
- Test: `tests/ds/test_monitors_runner.py`

**Interfaces:**
- Consumes: Tasks 1–3 + shallow recall `_invoke_shallow_recall`
  (`web_exa.exa_search` / Phase A `SearXNGBackend.query()`, direct in-process
  call per R2; the recall boundary is mocked in tests) + Task 5 `deliver`.
- Produces: `run_watch` / `tick_due_watches` used by Tasks 6–8.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from digisearch.monitors.models import Watch
from digisearch.monitors.store import MonitorStore
from digisearch.web_exa import WebSearchData

def _recall_data() -> WebSearchData:
    return WebSearchData.model_validate({"results": [
        {"url": "https://a.com/1", "title": "A", "text": "alpha"},
        {"url": "https://b.com/2", "title": "B", "text": "beta"},
    ]})

@pytest.mark.unit
def test_run_watch_persists_new_only(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        Watch.model_validate(
            {"name": "etf", "query": "etf flows",
             "schedule": {"mode": "interval", "interval_seconds": 3600}}
        )
    )
    monkeypatch.setattr(mod, "_invoke_shallow_recall", lambda **k: _recall_data())
    monkeypatch.setattr(mod, "deliver", lambda run, watch, **k: [])
    first = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert first.status == "ok" and len(first.results_new) == 2
    second = mod.run_watch(w.watch_id, trigger="schedule", store=store)
    assert second.status == "no_change" and second.results_new == []

@pytest.mark.unit
def test_run_watch_fail_hard_persists_failed(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        Watch.model_validate(
            {"name": "etf", "query": "etf flows",
             "schedule": {"mode": "interval", "interval_seconds": 3600}}
        )
    )
    def boom(**k):
        raise RuntimeError("turn down")
    monkeypatch.setattr(mod, "_invoke_shallow_recall", boom)
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="manual", store=store)
    runs, _ = store.list_runs(w.watch_id)
    assert runs[0].status == "failed" and runs[0].error == "turn down"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_runner.py -v`
Expected: FAIL with "No module named 'digisearch.monitors.runner'"

- [ ] **Step 3: Write minimal implementation**

Implement §4.4: `_invoke_shallow_recall` calls `web_exa.exa_search(...)`
when `is_exa_configured()` else Phase A `SearXNGBackend.query(...)` directly
in-process (no httpx, no bearer token, no loopback); `run_watch` snapshots
the query (including `category` + landed domain passthrough), dedups,
persists, delivers only on `ok` + non-poll mode (threading the watch's stored
`delivery_secret` into `deliver` for the `X-digi-signature` HMAC);
`tick_due_watches` isolates per-watch errors. `is_due` IMPORTS the cron grammar from `digiclaw.cron`
(`parse_cron` + `matches`; no copied grammar) for cron mode and uses
`last_run_at + interval <= now` for interval mode (missing `last_run_at`
means due); timezone conversion lives in `is_due` per §4.4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_runner.py tests/ds/test_monitors_dedup.py tests/ds/test_monitors_store.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/monitors/runner.py tests/ds/test_monitors_runner.py && ruff format --check digisearch/src/digisearch/monitors/runner.py tests/ds/test_monitors_runner.py`
Expected: zero errors

---

### Task 5: Delivery fan-out + webhook validation (EXA-identical errors)

**Files:**
- Create: `digisearch/src/digisearch/monitors/delivery.py`
- Test: `tests/ds/test_monitors_delivery.py`

**Interfaces:**
- Consumes: Tasks 1 (`DeliveryConfig`, `MonitorRun`, `Watch`).
- Produces: `validate_delivery` (called on watch create/update in Task 6 +
  EXA adapter in Task 8) and `deliver` (called by Task 4).

- [ ] **Step 1: Write the failing test**

```python
import hmac
import hashlib
import httpx
import pytest
from digisearch.monitors.delivery import DeliveryConfigError, validate_delivery
from digisearch.monitors import delivery as mod
from digisearch.monitors.models import DeliveryConfig, MonitorRun, Watch

@pytest.mark.unit
def test_poll_needs_no_targets():
    validate_delivery(DeliveryConfig(mode="poll"))

@pytest.mark.unit
def test_webhook_without_targets_is_required():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(DeliveryConfig(mode="webhook", targets=[]))
    assert ei.value.code == "webhook_url_required"
    assert "[webhook]: Required" in str(ei.value)

@pytest.mark.unit
def test_private_urls_rejected():
    for bad in ["http://127.0.0.1:3000/hook", "https://localhost/hook",
                "https://192.168.1.10/hook", "https://10.0.0.5/hook"]:
        with pytest.raises(DeliveryConfigError) as ei:
            validate_delivery(
                DeliveryConfig(mode="webhook", targets=[{"kind": "webhook", "url": bad}])
            )
        assert ei.value.code == "webhook_url_private"

@pytest.mark.unit
def test_deliver_posts_run_json(monkeypatch):
    seen: list[dict] = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode()[:50])
        return httpx.Response(200, json={"ok": True})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))
    watch = Watch.model_validate(
        {"name": "etf", "query": "etf flows",
         "schedule": {"mode": "interval", "interval_seconds": 3600},
         "delivery": {"mode": "webhook",
                      "targets": [{"kind": "webhook", "url": "https://hooks.example.com/x"}]}}
    )
    run = MonitorRun.model_validate(
        {"run_id": "r1", "watch_id": "w1", "status": "ok", "trigger": "manual",
         "started_at": "2026-09-14T00:00:00Z", "finished_at": "2026-09-14T00:01:00Z",
         "query_snapshot": {"query": "etf flows"}, "results_all": [], "results_new": [],
         "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}}
    )
    receipts = mod.deliver(run, watch, delivery_secret="s3cr3t")
    assert receipts[0].ok is True and receipts[0].status_code == 200
    assert seen and "r1" in seen[0]

@pytest.mark.unit
def test_deliver_signs_webhook_hmac(monkeypatch):
    seen_headers: list[dict] = []
    seen_body: list[bytes] = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        seen_body.append(request.read())
        return httpx.Response(200, json={"ok": True})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))
    watch = Watch.model_validate(
        {"name": "etf", "query": "etf flows",
         "schedule": {"mode": "interval", "interval_seconds": 3600},
         "delivery": {"mode": "webhook",
                      "targets": [{"kind": "webhook", "url": "https://hooks.example.com/x"}]}}
    )
    run = MonitorRun.model_validate(
        {"run_id": "r9", "watch_id": "w9", "status": "ok", "trigger": "manual",
         "started_at": "2026-09-14T00:00:00Z", "finished_at": "2026-09-14T00:01:00Z",
         "query_snapshot": {"query": "etf flows"}, "results_all": [], "results_new": [],
         "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}}
    )
    mod.deliver(run, watch, delivery_secret="s3cr3t")
    sig = seen_headers[0].get("x-digi-signature", "")
    assert sig.startswith("sha256=")
    expect = hmac.new(b"s3cr3t", seen_body[0], hashlib.sha256).hexdigest()
    assert sig == f"sha256={expect}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_delivery.py -v`
Expected: FAIL with "No module named 'digisearch.monitors.delivery'"

- [ ] **Step 3: Write minimal implementation**

Implement §4.5: https-only + `socket.getaddrinfo` private/reserved rejection
+ userinfo rejection; `deliver(run, watch, *, delivery_secret, timeout_s=...)`
POSTs `run.model_dump(mode="json")` with `X-digi-signature` HMAC per §4.5,
email via stdlib `smtplib` with `DIGISEARCH_SMTP_HOST/PORT/USER/PASS/FROM` env
(missing relay env → `ok=False` receipt, never raise). Human-review gate
(R7g): do NOT merge this task without human sign-off — webhook/SMTP egress
to caller-controlled endpoints is new external network exposure per root
`AGENTS.md`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_delivery.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/monitors/delivery.py tests/ds/test_monitors_delivery.py && ruff format --check digisearch/src/digisearch/monitors/delivery.py tests/ds/test_monitors_delivery.py`
Expected: zero errors

---

### Task 6: HTTP API (CRUD + trigger + runs + tick)

**Files:**
- Modify: `digisearch/src/digisearch/server.py` (10 routes per §4.6 + rate-limit
  entries + `digisearch_path_scopes` extension for the new paths)
- Test: `tests/ds/test_monitors_api.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: the §4.6 surface consumed by Tasks 7–8 and all external clients.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


@pytest.mark.unit
def test_create_trigger_poll_cycle(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    monkeypatch.setattr(srv, "get_monitor_store", lambda: store)
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post("/v1/monitors", json={
        "name": "etf", "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600}})
    assert r.status_code == 201, r.text
    wid = r.json()["watch_id"]
    assert c.get(f"/v1/monitors/{wid}").status_code == 200
    t = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"})
    assert t.status_code in (200, 201), t.text
    body = t.json()
    assert set(body) >= {"run_id", "watch_id", "status", "results_new", "dedup_stats"}
    h = c.get(f"/v1/monitors/{wid}/runs?limit=5")
    assert h.status_code == 200 and h.json()["runs"][0]["run_id"] == body["run_id"]

@pytest.mark.unit
def test_private_webhook_rejected_like_exa(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore
    monkeypatch.setattr(
        srv, "get_monitor_store",
        lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3")))
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post("/v1/monitors", json={
        "name": "etf", "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
        "delivery": {"mode": "webhook",
                     "targets": [{"kind": "webhook", "url": "http://127.0.0.1:3000/h"}]}})
    assert r.status_code == 422
    assert "cannot point to localhost" in r.text

@pytest.mark.unit
def test_datatap_watch_rejected(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore
    monkeypatch.setattr(
        srv, "get_monitor_store",
        lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3")))
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post("/v1/monitors", json={
        "name": "etf", "query": "etf flows", "workspace_id": "datatap",
        "schedule": {"mode": "interval", "interval_seconds": 3600}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "datatap_monitors_disabled"

@pytest.mark.unit
def test_exa_webhook_exempt_but_secret_gated(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore
    monkeypatch.setattr(
        srv, "get_monitor_store",
        lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3")))
    monkeypatch.setenv("EXA_MONITOR_WEBHOOK_SECRET", "shh")
    anon = TestClient(srv.app)  # no JWT: exemption lets it reach the handler
    r = anon.post("/v1/monitors/exa_webhook", json={"nope": True})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "exa_bad_signature"
```

Store seam: `server.py` MUST expose `def get_monitor_store() -> MonitorStore`
(module-level constructor reading `DIGISEARCH_MONITORS_DB`, default
`{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3`); there is no
`srv._monitor_store` attribute — all snippets/tests inject via
`monkeypatch.setattr(srv, "get_monitor_store", ...)`. Auth: protected routes
REQUIRE `TestClient(app, headers=auth_headers())` per the
`tests/ds/test_orchestrator_invoke.py` pattern — a bare client gets 401s, so
the old "TestClient bypasses JWT" claim was false and is struck. Error
envelope: custom codes surface as `body["error"]["code"]` (the shared
`{"error": {"code", ...}}` envelope in `digibase/errors.py`), never top-level
`body["code"]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_api.py -v`
Expected: FAIL (no such routes — 404s)

- [ ] **Step 3: Write minimal implementation**

Thin route handlers only (validate → `get_monitor_store()`/runner/delivery →
return) via explicit `json_error_response(...)` for every §4.6 stable code;
extend `_RATE_LIMITS` (`/v1/monitors*` CRUD 30/min, trigger/tick/exa_webhook
10/min); extend `digisearch_path_scopes` so every new path maps to
`digisearch:query` EXCEPT `POST /v1/monitors/exa_webhook`, which returns
`None` (auth-exempt) with the mandatory secret check from §4.6. Human-review
gate (R7g): do NOT merge this task without human sign-off (enables Task 5
egress). `get_monitor_store()` is created in this task if Tasks 1–5 did not
already need it. Route handlers call `run_watch`/`tick_due_watches` WITHOUT
forwarding the caller's JWT — the runner's direct in-process recall needs no
bearer (per R2); the JWT only authenticates the inbound HTTP request at the
middleware layer (and the digiclaw→digisearch tick hop, which carries the
Task 8 service JWT).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_api.py tests/ds/test_monitors_runner.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/server.py tests/ds/test_monitors_api.py && ruff format --check digisearch/src/digisearch/server.py tests/ds/test_monitors_api.py`
Expected: zero errors

---

### Task 7: MCP + orchestrator surfaces

**Files:**
- Modify: `digisearch/src/digisearch/mcp_server.py` (4 tools per §4.7)
- Modify: `digisearch/src/digisearch/orchestrator_tools.py`
  (`digisearch_monitors_trigger`, `digisearch_monitors_runs` tool defs)
- Modify: `digisearch/src/digisearch/server.py` (`api_orchestrator_invoke`
  dispatch for the 2 new tools)
- Test: extend `tests/ds/test_monitors_api.py` (orchestrator invoke round-trip)

**Interfaces:**
- Consumes: Tasks 1–5 (same runner/store functions as Task 6).
- Produces: hub-callable monitor capability for digigraph; MCP tools for
  digiclaw MCP clients.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

@pytest.mark.unit
def test_orchestrator_trigger_round_trip(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore
    monkeypatch.setattr(
        srv, "get_monitor_store",
        lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3")))
    c = TestClient(srv.app, headers=auth_headers())
    wid = c.post("/v1/monitors", json={
        "name": "etf", "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600}}).json()["watch_id"]
    r = c.post("/v1/orchestrator_invoke", json={
        "tool": "digisearch_monitors_trigger",
        "arguments": {"watch_id": wid, "mode": "poll"}})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["data"]["watch_id"] == wid
    r2 = c.post("/v1/orchestrator_invoke", json={
        "tool": "digisearch_monitors_runs",
        "arguments": {"watch_id": wid, "limit": 5}})
    assert r2.json()["ok"] is True
    assert r2.json()["data"]["runs"] != []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_monitors_api.py -v -k orchestrator_trigger`
Expected: FAIL with "Unknown orchestrator tool"

- [ ] **Step 3: Write minimal implementation**

Manifest entries follow the existing `build_*_tool` pattern; dispatch arms
return `OrchestratorInvokeResponse(ok=True, data=run-or-runs-payload)` or
`(ok=False, error=...)` — the established fail-hard shape. MCP tools return
the same JSON the HTTP routes return, formatted via the existing MCP text
convention.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ds/test_monitors_api.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/mcp_server.py digisearch/src/digisearch/orchestrator_tools.py digisearch/src/digisearch/server.py && ruff format --check digisearch/src/digisearch/mcp_server.py digisearch/src/digisearch/orchestrator_tools.py digisearch/src/digisearch/server.py`
Expected: zero errors

---

### Task 8: `service_auth` prerequisite + EXA adapter + digiclaw tick + ops record

**Files:**
- Create: `digibase/src/digibase/service_auth.py` (NEW prerequisite — see below;
  `digibase/` ships no `service_auth.py` today and the unlanded plan
  2026-09-11 proposal MUST NOT be consumed as landed)
- Create: `digisearch/src/digisearch/monitors/exa_adapter.py`
- Create: `digiclaw/src/digiclaw/monitors_tick.py`
- Create: `digiclaw/agents/web-watch-tick.yaml`
- Modify: `digisearch/ARCHITECTURE.md` (§3 + §9: monitors module + routes),
  `digiclaw/ARCHITECTURE.md` (§3: tick surface + env vars),
  `digibase/ARCHITECTURE.md` (§3: new `service_auth` API)
- Test: `tests/digibase/test_service_auth.py` (new),
  `tests/ds/test_monitors_exa_adapter.py`, `tests/dc/test_monitors_tick.py`

**Interfaces:**
- Consumes: Tasks 1–7 + `EXA_API_KEY` + Task 8a pin table (translation shapes
  MUST NOT be frozen before Task 8a lands) + the `service_auth` module created
  in Step 3a below.
- Produces: EXA↔OSS interchangeability + the scheduled clock + operator docs.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

def test_exa_run_translates_to_canonical_envelope():
    from digisearch.monitors.exa_adapter import exa_run_to_monitor_run
    run = exa_run_to_monitor_run(
        watch_id="w1",
        exa_payload={
            "id": "exa_run_9", "status": "completed", "trigger": "schedule",
            "createdAt": "2026-09-14T00:00:00Z", "completedAt": "2026-09-14T00:01:00Z",
            "query": "etf flows",
            "results": [{"url": "https://a.com/1", "title": "A"}],
            "newResults": [{"url": "https://a.com/1", "title": "A"}],
        },
    )
    assert run.backend == "exa"
    assert run.status == "ok"
    assert run.results_new == [{"url": "https://a.com/1", "title": "A"}]
    assert run.dedup_stats["new"] == 1

@pytest.mark.unit
def test_exa_create_without_public_webhook_rejected():
    from digisearch.monitors.exa_adapter import ExaAdapterError, create_exa_monitor
    with pytest.raises(ExaAdapterError) as ei:
        create_exa_monitor(
            query="etf flows", webhook_url="http://127.0.0.1:3000/h", api_key="k")
    assert "cannot point to localhost" in str(ei.value)
```

```python
import pytest

@pytest.mark.unit
def test_tick_posts_with_service_jwt(monkeypatch):
    import httpx
    import digibase.service_auth as svc
    from digiclaw import monitors_tick as mod
    monkeypatch.setenv("DIGISEARCH_URL", "http://127.0.0.1:8002")
    monkeypatch.setattr(svc, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        assert str(request.url) == "http://127.0.0.1:8002/v1/monitors/tick"
        return httpx.Response(200, json={"runs": []})
    monkeypatch.setattr(
        mod, "_post", lambda url, token: httpx.Client(
            transport=httpx.MockTransport(handler)).post(
                url, headers={"authorization": f"Bearer {token}"}).json())
    out = mod.run_due_monitors()
    assert seen["auth"] == "Bearer svc-jwt"
    assert out == {"runs": 0, "failed": 0}
```

(`monitors_tick.py` MUST resolve the JWT via the fully-qualified lazy import
`from digibase.service_auth import get_service_jwt` inside `run_due_monitors`
— never `from digibase import service_auth` at module top level, never a
`mod.get_service_jwt` local alias — so the patch target above
(`digibase.service_auth.get_service_jwt`) is stable.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ds/test_monitors_exa_adapter.py tests/dc/test_monitors_tick.py -v`
Expected: FAIL with "No module named" for both new modules

- [ ] **Step 3a: Land the `service_auth` prerequisite FIRST (new file)**

`digibase.service_auth` does not exist — create it in this step before any
consumer is wired (side-effect-free on import per `digibase/AGENTS.md`):

```python
# digibase/src/digibase/service_auth.py
def get_service_jwt(*, scopes: list[str], audience: str | None = None) -> str: ...
```

Reads the operator-provisioned service credential env (document the exact env
names in `digibase/ARCHITECTURE.md` §3 in this step), mints/exchanges a
short-lived digikey JWT for `scopes`, caches only until expiry, never logs
key material. Test: `tests/digibase/test_service_auth.py` (`@pytest.mark.unit`,
credential env stubbed via `monkeypatch.setenv`; asserts a non-empty token
string is returned and no secret leaks into logs/exceptions).

- [ ] **Step 3b: Write minimal implementation**

`exa_adapter.py` (translation table frozen ONLY from the Task 8a pin record —
do not invent field names beyond the pinned shapes):

```python
def exa_run_to_monitor_run(*, watch_id: str, exa_payload: dict) -> MonitorRun: ...
def create_exa_monitor(*, query: str, webhook_url: str, schedule: str,
                       api_key: str | None = None) -> dict: ...
def delete_exa_monitor(*, exa_monitor_id: str, api_key: str | None = None) -> None: ...
```

Translation rules (initial shapes from the Task 8a pin ONLY): EXA `completed`
with non-empty new content → `ok`; `completed` with empty new content →
`no_change`; `failed`/`error` → `failed` with `error` passthrough;
`dedup_stats` derived from `len(results)` vs `len(newResults)`;
`cost_dollars` passed through advisory-only when present, else `None`.
`create_exa_monitor` runs the same `validate_delivery` check first (fail
before spending an EXA call) and maps EXA 4xx bodies containing `[webhook]`
into `ExaAdapterError` preserving the verbatim message.
`POST /v1/monitors/exa_webhook` is auth-exempt per §4.6 and MANDATORILY
verifies `EXA_MONITOR_WEBHOOK_SECRET` (`hmac.compare_digest`; missing server
secret or mismatch → 401 `exa_bad_signature` via `json_error_response`),
then translates + persists.

`monitors_tick.py` per §4.8 (lazy `get_service_jwt` import, raise on
transport/auth failure). `web-watch-tick.yaml`:

```yaml
name: web-watch-tick
description: Wake-up clock for digisearch scheduled web watches (Phase C)
schedule:
  mode: continuous
  interval_seconds: 60
  enabled: true
```

Docs: ARCHITECTURE updates + ops record (SQLite path + volume mount,
`DIGISEARCH_MONITORS_DB`, `DIGISEARCH_SMTP_*`, `EXA_MONITOR_WEBHOOK_SECRET`,
tunnel-or-poll story: local dev = `poll` mode; public webhooks via
Cloudflare Tunnel / Tailscale per `SECURITY.md`; manual-trigger + poll is
the portable path that works on both backends).

- [ ] **Step 4: Run all gates to verify they pass**

```bash
pytest tests/digibase/test_service_auth.py tests/ds/test_monitors_models.py tests/ds/test_monitors_store.py tests/ds/test_monitors_dedup.py tests/ds/test_monitors_runner.py tests/ds/test_monitors_delivery.py tests/ds/test_monitors_api.py tests/ds/test_monitors_exa_adapter.py tests/dc/test_monitors_tick.py -v
pytest tests/ -m unit -k "digisearch or digiclaw or digibase" -v
ruff check digibase/src/digibase/service_auth.py digisearch/src/digisearch/monitors/ digiclaw/src/digiclaw/monitors_tick.py && ruff format --check digibase/src/digibase/service_auth.py digisearch/src/digisearch/monitors/ digiclaw/src/digiclaw/monitors_tick.py
```

(The `-k` filter MUST include `digiclaw` (and `digibase` for Step 3a):
`-k "digisearch"` alone deselects `tests/dc/test_monitors_tick.py` and the
tick clock would ship untested. Every new test file in this spec carries
`@pytest.mark.unit`; `tests/dc/` collection must not require the stack.)

Expected: PASS, zero ruff errors. Live smoke (requires stack up):
`curl -s http://localhost:8002/health`, create watch → trigger `poll` →
`GET runs` returns the canonical envelope.

---

### Task 8a: EXA API spike-and-pin (live validation BEFORE freezing the translation table)

**Why:** the current EXA create/list/delete/run shapes were reconstructed from
two observed error strings plus assumed field names — and a live 401 paywall
on this key tier already proved residual access risk. Freezing the Task 8
translation table on unverified shapes guarantees a broken adapter.

**Files:**
- Create (throwaway, NOT shipped): `scripts/exa_monitors_spike.py` (or a
  scratch dir outside the packages — never `digisearch/src/`)
- Modify: Task 8 `exa_adapter.py` docstring (record the pinned shapes + tier)

- [ ] **Step 1: Run the live spike** (requires `EXA_API_KEY`; human runs or
  explicitly approves — live external calls + key-tier discovery):

```bash
EXA_API_KEY=$EXA_API_KEY python scripts/exa_monitors_spike.py
```

The script exercises, against the LIVE API with the operator's key tier, and
prints raw status + body for each: monitor **create** (with public webhook
URL), monitor **list/get**, monitor **delete**, and one **run payload**
(trigger or webhook sample). It asserts nothing about OSS code — it only
records what EXA actually returns.

- [ ] **Step 2: Pin the record** — paste the observed shapes into the
  `exa_adapter.py` module docstring as the pin table:

```
# PIN (observed <date>, key tier <tier>): create req/res fields …;
# list/get fields …; delete status …; run payload fields …;
# tier gating observed: <e.g. monitors endpoints 401 on this tier> …
```

- [ ] **Step 3: Reconcile** — if live shapes contradict the Task 8 translation
  assumptions (`id`/`status`/`createdAt`/`results`/`newResults`/4xx `[webhook]`
  bodies), update the Task 8 tests + implementation to the pinned shapes
  BEFORE merging Task 8. If the key tier 401s monitors endpoints, record
  `backend: exa` as tier-gated (fail-closed `exa_not_configured`-family error,
  never a silent `oss` fallback) and keep OSS as the default path.

Gate: Task 8 MUST NOT merge before this pin record exists. If no live key is
available, Task 8 lands with the adapter marked experimental + tier-gated, and
the pin becomes a follow-up issue — it does not silently freeze assumed shapes.

---

## 7. Self-Review

1. **Scope kept:** watch CRUD, schedule config (cron + interval), dedup
   rules, delivery config, run history API/MCP — orchestration + storage
   only. No provider, extractor, embedding, or ranking code is added or
   modified; Phase B is called, never re-implemented.
2. **No contradictions:** tool-only fail-hard, service-JWT headless auth for
   the digiclaw→digisearch tick hop ONLY (runner recall is a direct
   in-process call with no bearer, per R2), `digisearch:query` scope with no
   digikey change (sole exception: auth-exempt `exa_webhook` with mandatory
   secret check), `extra="forbid"` bodies, lowercase digi naming,
   `Digi`-free entity names, datatap OFF, `WebSearchData`-only results with
   advisory-only cost, and the landed `include/exclude_domains` (+ `category`)
   passthrough consumed — not re-specified — are all inherited unchanged
   from the three consolidated plans and the live `server.py` / `web_exa.py`
   contracts. `digibase.service_auth` is specified as NEW work (Task 8),
   never as landed.
3. **Interchangeability is structural:** one `MonitorRun` envelope, one
   error-message vocabulary (`[webhook]: Required`,
   `[webhook.url]: ...localhost...`), one signed-delivery header
   (`X-digi-signature`), and one portable path (create → trigger → list/get
   runs) shared by `oss` and `exa` backends. EXA shapes freeze only on the
   Task 8a live pin, never on assumed field names.
4. **Placeholder scan:** no TBD/TODO markers; no `pass` stubs; no
   `=None` default-client fixtures; every task names exact files, exact
   signatures, exact test commands, and exact expected outputs. Every new
   test carries `@pytest.mark.unit`; the Task 8 gate filters
   `-k "digisearch or digiclaw or digibase"` so `tests/dc/` is collected.
