# OSS Web Search Integration Review — Phases A/B/C/D (2026-09-14)

**Role:** integration reviewer. **Scope:** read-only review + this file. No code, no other writes, no commits.
**Files read:**
- `digisearch/src/digisearch/web_exa.py` (257 lines — the in-code contract)
- `digisearch/src/digisearch/server.py` (§`WebSearchRequest`, `api_web_search`, `api_orchestrator_invoke`, route list)
- `digisearch/src/digisearch/orchestrator_tools.py` (`TOOL_DIGISEARCH_WEB_SEARCH`, `TOOL_DIGISEARCH_RESEARCH_DELEGATE`, `build_web_search_tool`)
- Spec A `2026-09-14-oss-websearch-phaseA-url-ingest.md` (281 lines)
- Spec B `2026-09-14-oss-websearch-phaseB-web-research-turn.md` (872 lines)
- Spec C `2026-09-14-oss-websearch-phaseC-monitors.md` (1073 lines)
- Spec D `2026-09-14-oss-websearch-phaseD-verify-enrich.md` (529 lines)
- Directory check: `tests/ds/` and `tests/dc/` exist; `digisearch/tests/` does **not** exist; none of
  `web_providers/`, `web_search/`, `web/`, `monitors/`, `websets/` exist yet under `digisearch/src/digisearch/`.

**In-code anchors (normative for every resolution below):**
- Interchange envelope: `WebSearchData{results: list[dict], output: dict|None, search_type: str|None,
  cost_dollars: dict|None}` (`web_exa.py:52-60`), `extra="ignore"`.
- Request shape: `ExaWebSearchRequest{query, search_type="auto", num_results=8 (1-100), category=None,
  contents_text=False, output_schema=None, system_prompt=None}` (`server.py:884-898`).
- Tool split: `digisearch_web_search` = shallow live search → `POST /v1/digisearch_web_search` (EXA-gated, 503 without key);
  `digisearch_research_delegate` = composite turn → `POST /v1/research_turn`. They are not the same tool.
- Test roots: `tests/ds/` (+ `tests/dc/`). There is no `digisearch/tests/` directory.

---

## 1. Verdict table

| # | Suspected conflict | Verdict | Decisive quotes (file + section) |
|---|---|---|---|
| 1 | Envelope war: `WebSearchResponse` vs `WebSearchData` | **CONFIRMED** — B and D program to shapes that do not exist; A and C are clean | A §"Relationship to existing drafts": "REJECTS its `WebSearchResult/WebSearchResponse` invention — all provider code returns `WebSearchData`" + A risk 1: "The 09-10 draft's `WebSearchResult/WebSearchResponse` shape does not exist in code and MUST NOT be revived — any later phase importing those names will fail at import". B §"Consumes": "`digisearch.web_search.models.WebSearchRequest{query,include_domains,exclude_domains,max_results,recency_days}` / `WebSearchResponse{query,results WebSearchResult{url,title,snippet,score,engine},provider}` / `SearXNGWebSearchProvider.search(req)`" + B Task 1 test: "`from digisearch.web_search.models import WebSearchResponse, WebSearchResult`" + B File Structure: retrieve.py "mapping Phase A `WebSearchResponse` / markdown pages to `web.retrieve.WebHit`". D §"Consumes — Phase A": "candidate generation runs on the Phase A OSS search surface (`digisearch.web_search` models, SearXNG primary / ddgs fallback providers, `run_web_search`, …)". C is clean: Consumes cites "`WebSearchData` contract in `digisearch/src/digisearch/web_exa.py`" and `results_all` = "`WebSearchData` result dicts, as returned". |
| 1b | Does EXA/OSS interchangeability actually break anywhere? | **CONFIRMED, two break sites** | B's sole adaptation seam imports a non-existent module (`digisearch.web_search.*` — only place allowed to touch Phase A), so `live_search`/`fetch_pages` raise `ImportError` and no `WebSearchData` is ever produced. D's candidate generation calls `run_web_search`, which A explicitly reserves: "Its `run_web_search` service name is reserved for a later phase; Phase A exposes only `SearXNGBackend.query()` + `ingest_url()`" (A §Relationship). C does not break: loopback `orchestrator_invoke {digisearch_web_search}` returns `WebSearchData` today. |
| 2 | Access pattern (direct import vs HTTP) | **CONFIRMED — no stated rule, three inconsistent choices** | C §1: "**Phase B is called over HTTP, never imported.** The runner calls `POST /v1/orchestrator_invoke {tool: digisearch_web_search…}` on its own server (loopback)". D Task 5: runner "stubbed at `run_web_search`, never raw SearXNG" = in-process direct call inside the same package. B `retrieve.py`: direct import of Phase A inside the same package (seam location is right, module name is wrong — see #1). So intra-`digisearch` callers use HTTP (C), direct import (B), and direct-call-to-missing-name (D) with no rule written anywhere. |
| 3 | Test paths `tests/ds/` vs `digisearch/tests/` | **CONFIRMED — B and D cite a non-existent path; A and C are clean** | A File Structure + all Task Verify blocks: `tests/ds/test_url_ingest.py`, `test_url_policy.py`, `test_readability_extract.py`, `test_searxng_backend.py`, `test_searxng_mapping.py` — exist as a root. C Tasks 1-8: `tests/ds/test_monitors_*.py` + `tests/dc/test_monitors_tick.py` — clean. B File Structure table + every Task Run line: `digisearch/tests/test_web_grounding_models.py`, `test_web_accounting.py`, `test_web_answer.py`, `test_web_structured.py`, `test_research_turn_web_branch.py`, `test_web_eval_live.py`, `web_eval_cases.py` — `digisearch/tests/` does not exist (verified by listing). D File Structure + every Task Run line: `digisearch/tests/test_websets_*.py` (8 files) — same non-existent root. |
| 4 | `WebSearchRequest` field names | **CONFIRMED — five divergent vocabularies** | Code (`server.py:770`): `{query, search_type, num_results, category, contents_text, output_schema, system_prompt}`. A `SearXNGBackend.query()`: `{query, num_results=8, include_domains, exclude_domains, category, timeout_s}` — no `search_type`. B Consumes: `{query, include_domains, exclude_domains, max_results, recency_days}` — `max_results` ≠ `num_results`, `recency_days` exists nowhere else. C `Watch`: `{query, search_type, num_results, include_domains, exclude_domains}` — no `category`. D Consumes: backend selection "`auto\|searxng\|ddgs\|off`" vs A's manifest enum "`["auto", "exa", "searxng"]` default `"auto"`" (A Task 6); D `POST /v1/websets` body uses `count` (target item count — a different concept wearing a similar name). |
| 5 | Shared `Citation{url, excerpt}` shape (B grounding vs D admissibility) | **CONFIRMED mismatch** | B Interfaces: "`class GroundingCitation(BaseModel): url: str; title: str = ''`" + "`FieldGrounding{field, citations min 1, confidence}`" (citations carry **title**, plus per-field **confidence**). D §Verification gate: "`CriterionResult{criterion, passed, reasoning, references[{url, excerpt}]}`"; D §Enrichment: "`citations` is mandatory on success: `[{url, excerpt}]` in EXA style". D's citations carry **excerpt, no title, no confidence**; B's carry **title, no excerpt**. Same word "citations", different structs — a B-grounded field cannot be fed to D admissibility without lossy translation. Neither spec names a shared owner; B puts its model in `web/grounding_models.py`, D lists a bare `Citation` in `websets/models.py` with no fields shown. |
| 6 | Cost semantics: OSS `total = 0.0`, "cheapest = OSS" hazard | **CONFIRMED real** | A §0: "`cost_dollars` for OSS backends: `{\"total\": 0.0, \"provider\": \"searxng\"}`". B Interfaces: "`class TurnCost… total: float = 0.0`"; B Task 2: "`total = 0.0` with `note: 'oss-synthesis; llm spend metered in digillm telemetry, not here'`" + "`TurnCost.total` stays numeric so budget comparisons (`total <= maxCostDollars`) keep working". Any router minimizing `total` (or any budget gate of the form `total <= max`) therefore always prefers OSS, including over a paid path that recalled better — while the dominant OSS cost driver (digillm synthesis tokens) is explicitly uncounted. B Task 5 test pins `"cost_dollars": {"total": 0.0, …}` as the expected value, cementing the hazard. |
| 7a | C runs "the Phase B web research turn" but invokes the shallow search tool | **CONFIRMED** | C Goal: "a cron/interval-scheduled query runs the Phase B web research turn". C §4.4: `run_watch` flow = "`POST /v1/orchestrator_invoke {tool: digisearch_web_search, arguments: {query, search_type, num_results, include/exclude domains}}`". In code, `digisearch_web_search` is the shallow EXA search (→ `POST /v1/digisearch_web_search`); the research turn is `digisearch_research_delegate` (→ `POST /v1/research_turn`). The Consumes line repeats it: "Phase B grounded web research turn (`POST /v1/digisearch_web_search` / `POST /v1/orchestrator_invoke {tool: digisearch_web_search}` …)" — `POST /v1/digisearch_web_search` is the shallow EXA route, not the turn. |
| 7b | Extractor signature + fallback choice | **CONFIRMED** | A Interfaces: "`def extract_markdown(html: str, url: str = '') -> tuple[str, str]` … Return (markdown, extractor_name)"; A Task 2: spike-then-decide trafilatura-vs-Crawl4AI, "trafilatura GPL-3.0 vs Crawl4AI Apache-2.0". B Consumes: "`extract_markdown(html, url) -> str` (trafilatura primary, readability fallback)" — returns `str` not tuple, pre-decides trafilatura-primary with a *different* fallback (readability, not Crawl4AI), no license note. |
| 7c | Provider method/module names | **CONFIRMED** | A produces `digisearch.web_providers.searxng.SearXNGBackend.query()`; B Consumes/Architecture cite `SearXNGWebSearchProvider.search(req)` and "`SearXNGBackend.search`". Neither `digisearch.web_search` nor `SearXNGWebSearchProvider` nor a `.search()` method exists in A or in the tree. |
| 7d | `ddgs` fallback / `off` backend as "Phase A surface" | **CONFIRMED fiction in D** | D Consumes: "SearXNG primary / ddgs fallback providers … backend selection (`auto\|searxng\|ddgs\|off`)". A §Relationship: "Its ddgs fallback … [is] explicitly later-phase work, not Phase A" and the only provider enum anywhere is A's `["auto", "exa", "searxng"]`. No spec defines ddgs semantics, `off` behavior, or who implements them. |
| 7e | Two different `Monitor` concepts | **CONFIRMED collision** | C: scheduled search watches (`Watch` + `MonitorRun` + `MonitorStore`; no class named `Monitor`). D object table: "`monitor` | `Monitor` | `id` (`wsm_…`), `webset_id`, `cadence_s`, `webhook_url`, `status: active\|paused`" — a webset-refresh cadence, unrelated to C watches. Same word, same service, disjoint meanings; `wsm_` ids will read as "watch…monitor" in joint logs. |
| 7f | SQLite store handles + default paths | **CONFIRMED drift** | C §3: "`DIGISEARCH_MONITORS_DB`, default `{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3`" (+ Docker volume note). D §Architecture: "(`DIGIWEBSETS_DB_PATH`, default `.digiwebsets.db` in CWD)". Different env prefix convention (`DIGISEARCH_` vs `DIGIWEBSETS_`), different default homes (workspace dot-dir vs process CWD — CWD breaks under service managers). |
| 7g | Human-gate asymmetry on identical egress | **CONFIRMED** | D Global Constraints: "Human gate: new external network exposure (webhook delivery to caller URLs is new egress) requires human review before merge". C §5: "Human gate: none triggered by this spec alone (no new external service dependency … no new network exposure — all listeners stay loopback …)" — yet C §4.5 `deliver()` POSTs run JSON to arbitrary webhook/slack URLs and sends email via operator SMTP relay: the same new egress D flags. ("Listeners stay loopback" is true of ingress and irrelevant to egress.) |
| 7h | Webhook auth convention | **CONFIRMED minor** | C §4.5: "`deliver` POSTs `run.model_dump(mode='json')`" — no signature. D §Interfaces: "`X-digi-signature: sha256=<hmac(secret, body)>`; 3 attempts, 5s/25s backoff". Two webhook-signing conventions in one service; C's EXA-ingress secret (`EXA_MONITOR_WEBHOOK_SECRET`) is spec'd but C's egress is unsigned. |
| 7i | B intra-spec accounting names | **CONFIRMED (inside B alone)** | B File Structure table: "`TurnClock` helpers: `start_clock()`, `record_stage()`, `to_usage()`, `estimate_cost()` … over a small `StageTimer` dataclass". B Task 2: "Produces: `StageTimer`, `start_clock()`, `record_stage()`, `finalize_usage()`, `estimate_cost()`" — `to_usage` vs `finalize_usage`, `TurnClock` vs `StageTimer` in the same spec. |
| 7j | `Watch.search_type` (EXA vocab) with no `category` | **CONFIRMED minor** | C `Watch`: "`search_type: str = 'auto'` … validated against `VALID_SEARCH_TYPES`" (EXA's instant/fast/auto/deep…), but no `category` field — while A's `query()` takes `category` (which drives `time_range='month'` for news) and no `search_type`. An OSS-backed watch cannot express what the OSS backend actually accepts, and carries a knob only the EXA path honors. |
| — | Ports / scopes / digikey | **DISMISSED (consistent)** | No new ports anywhere (A: loopback sidecar only; B: "no new MCP port"; C: "No new port", MCP stays `127.0.0.1:8765`; D: "MCP stays loopback-only `127.0.0.1:8765`"). No new scopes anywhere (A/B/C/D all reuse `digisearch:query` + `digisearch:ingest` via existing `DigiAuthMiddleware`, "no digikey change" stated in A Task 6, C §5, D HTTP section). |
| — | Cross-component rule (digigraph never imports digisearch) | **DISMISSED (consistent)** | B Architecture: "`digigraph` never imports `digisearch` … keeps calling `POST /v1/research_turn` / `POST /v1/orchestrator_invoke`". C §4.8: digiclaw tick POSTs `/v1/monitors/tick` over HTTP with service JWT. D Constraints: "digigraph must never `import digisearch` modules; all calls via `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke`" (`POST /v1/orchestrator_tools` is a real manifest route — `server.py:517`). All three agree. |
| — | Export formats | **DISMISSED (no conflict)** | Only D exports (CSV via polars + JSON); "polars … never pandas" matches the repo-wide Polars-only rule. Nothing else exports. |
| — | B `source` vs `include_web` naming | **DISMISSED (self-resolved)** | B Architecture: "`source='web'` (or `include_web=true` — Task 5 fixes one name)"; B Task 5 fixes it: "`source: Literal['corpus','web'] = 'corpus'`". One name chosen inside the spec. |

---

## 2. Canonical resolutions (one per confirmed conflict)

**R1 — Envelope: `WebSearchData` everywhere; the 09-10 names stay dead.**
`WebSearchData{results, output, search_type, cost_dollars}` (`web_exa.py:52-60`) is the only provider-neutral
interchange envelope at every surface (HTTP, MCP, orchestrator manifest, Phase B synthesis output, C `results_all`,
D candidate records). `WebSearchRequest/Response`, `WebSearchResult`, `SearXNGWebSearchProvider`,
`digisearch.web_search.*`, and `run_web_search` do not exist and MUST NOT be created under those names.
Concrete edits: B Consumes + File Structure + Task 1 test import `digisearch.web_providers.searxng.SearXNGBackend`
and type the seam as `WebSearchData → list[WebHit]`; B Architecture line "`SearXNGBackend.search`" → `.query()`;
D Consumes + Architecture + Task 5 re-point candidate generation at `SearXNGBackend.query()` /
`ingest_url()` (direct import, same package) until a later spec defines a unified router. A/C need no change.

**R2 — Access pattern rule (write it into A §"Produces" and B/C/D Constraints):**
*direct import within the `digisearch` package; HTTP (`POST /v1/orchestrator_invoke`, `POST /v1/research_turn`,
`POST /v1/monitors/tick`) only at process/component boundaries (digiclaw, digigraph, digichat, external callers),
always with the caller's service JWT.* Violations to fix: (a) C §4.4 `run_watch`/`_invoke_web_search_turn` —
same-process loopback HTTP to itself becomes a direct call into the Phase B entry point (fail-hard is preserved:
exceptions propagate instead of becoming HTTP 5xx, and the persisted `failed` run logic is unchanged);
the loopback-HTTP form may remain ONLY as an integration-test path. (b) D Task 5 stub boundary moves from the
fictional `run_web_search` to `SearXNGBackend.query` (+ `ingest_url` for page fetch). (c) B `retrieve.py` keeps its
seam position but imports `digisearch.web_providers.*`, never `digisearch.web_search.*`.

**R3 — Test roots: `tests/ds/` (+ `tests/dc/`), zero exceptions.**
Globally replace `digisearch/tests/` with `tests/ds/` in B (5 test files + `web_eval_cases.py` + all Task Run/ruff
lines + Task 6 `rg` line) and D (8 test files + all Task Run/ruff lines). Every occurrence is listed in verdict #3;
no `digisearch/tests/` directory is created. (D Task 7's `tests/ds/test_web_exa.py` reference stays `tests/ds/`
but implementers must check that file exists first — it was not in the visible listing.)

**R4 — Canonical request fields (code wins, phases extend additively):**
`{query*, search_type="auto" (EXA vocab, validated against `VALID_SEARCH_TYPES`), num_results=8 (1-100),
category=None, include_domains=[], exclude_domains=[], provider="auto"∈{auto,exa,searxng}, contents_text=False,
output_schema=None, system_prompt=None, timeout_s=None}`. Rejected: `max_results` → `num_results`;
`recency_days` → express via `category="news"` (+ A's `time_range=month`) until a spec adds real date-range fields;
`ddgs`/`off` → no such backends (see R7d); D's webset `count` is NOT `num_results` — it is "target verified items"
and MUST be documented as such wherever both appear. Concretes: add `provider` + `include/exclude_domains`
additively to code `WebSearchRequest` (A Task 6 already adds `provider`; fold the domain pair into the same change);
add optional `category` to C `Watch` (R7j); B Consumes field list rewritten to this list.

**R5 — Canonical citation: `Citation{url, title="", excerpt=""}` owned by Phase A.**
New `digisearch.web_providers.models.Citation` (`url*`, `title=""`, `excerpt=""`, `extra="forbid"`),
re-exported from `web_providers/__init__.py` (which already re-exports `WebSearchData`).
B `GroundingCitation` gains `excerpt: str = ""` (keeps `field`+`confidence` wrapper `FieldGrounding`);
D `Citation`/references gain `title: str = ""` (keeps `excerpt`, keeps per-field mandatory-citation admission).
Admissibility/verification joins key on exact `url` match; URL normalization (`normalize_url`) is shared from C
`dedup.py` by B and D rather than reimplemented. Rationale: A is the foundation phase and already owns the
EXA-shape mirror table (§0), so the citation atom lives with it.

**R6 — Cost rule: `total` is advisory-only; routing uses effort-normalized scoring.**
(a) No router, budget gate, or backend comparison may branch on `cost_dollars.total` alone while any backend
reports `0.0` — B Task 2's "`total <= maxCostDollars` keeps working" is struck and replaced with "budget gates
MUST include stage-ms and `breakdown.llm_calls > 0 ⇒ consult digillm telemetry`". (b) Unify the zero-cost shape to
`{total: 0.0, provider: <name>, breakdown: {searches, pages_fetched, llm_calls}, note: "oss-synthesis; llm spend
metered in digillm telemetry, not here"}` (merges A's provider stamp with B's breakdown). (c) Backend choice stays
explicit (`provider` param / per-watch `backend` label / effort preset), never cheapest-total-wins; B Task 5's
pinned `"cost_dollars": {"total": 0.0}` test gains an assertion that `provider` and `breakdown` are present.
When digillm telemetry exists, a follow-up spec may define effort-normalized scoring (cited fields per stage-second
per counted token-dollar); until then, comparison copy MUST say "OSS total excludes LLM spend".

**R7a — Monitors consume the shallow search, not the turn (fix the words, keep the design).**
C's dedup-over-recall design wants hits, not synthesized answers: keep §4.4 invoking `digisearch_web_search`
(renamed in code comments as "shallow recall path"), and rewrite C Goal + Consumes to "runs the live web-search
recall path (`digisearch_web_search` → `WebSearchData` results); the Phase B research turn
(`digisearch_research_delegate`) is NOT invoked". A turn-backed watch mode (for cited-answer digests) becomes a
named follow-up, not a silent substitution — otherwise the first implementer will wire the wrong tool.

**R7b — Extractor: A's signature wins; Apache-2.0 default; trafilatura gated.**
`extract_markdown(html, url) -> tuple[str, str]` (markdown, extractor_name) is canonical; B's `-> str` is fixed
and B adapts at its seam. Task 2 runs as written (trafilatura vs Crawl4AI eval) with the directed default:
**ship the Apache-2.0 option (Crawl4AI) unless the measured gap on the 5-fixture set is material, and trafilatura
(GPL-3.0) lands only with explicit legal sign-off for closed distributions** — already flagged in A Task 7 but now
a merge precondition, not a comment. B's "trafilatura primary, readability fallback" line is struck.

**R7c/d — Names that do not exist are struck everywhere:** `digisearch.web_search`, `SearXNGWebSearchProvider`,
`.search()`, `run_web_search`, `ddgs`, `off` (covered by R1/R2/R4; listed here so grep-verification has one place
to check: `rg -n "web_search\.models|SearXNGWebSearchProvider|run_web_search|ddgs|\"off\"|max_results|recency_days" docs/superpowers/specs/2026-09-14-oss-websearch-phase*.md` must return only this review file).

**R7e — Rename D's monitor:** D `Monitor` → `WebsetMonitor` (id prefix `wsm_` kept, object name `webset_monitor`);
D §Architecture "monitor fan-out" cross-reference must name Phase C watches explicitly if it means them, else say
"webset cadence". Phase C keeps `Watch`/`MonitorRun` unprefixed per the `Digi`-free entity rule.

**R7f — Store handles:** `DIGISEARCH_WEBSETS_DB`, default `{DIGI_WORKSPACE}/.digisearch/websets.sqlite3`
(same persistent volume as C's monitors DB; CWD default removed). Env naming, default home, and volume-mount docs
match C §3/Task 8. `WebsetStore` gains the same `get_store()` env-reading constructor shape as C's `get_store`.

**R7g — Human gate for C delivery:** C Task 5/6 (delivery + SMTP/webhook egress to caller URLs) gets the same
human-review-before-merge gate D carries. C §5 "Human gate: none" is struck and replaced with D's wording,
scoped to the delivery tasks (store/runner/dedup stay gateless).

**R7h — One webhook convention:** C egress adopts D's `X-digi-signature: sha256=<hmac(secret, body)>` signed
delivery (secret per watch, stored alongside `DeliveryConfig`); unsigned POST remains only for the `poll` mode
(which posts nothing). C's EXA-ingress `EXA_MONITOR_WEBHOOK_SECRET` check is unchanged.

**R7i — B accounting names:** `StageTimer` + `start_clock` / `record_stage` / `finalize_usage` / `estimate_cost`
(Task 2 wins); fix the File Structure table row (`TurnClock`/`to_usage` struck).

**R7j — C `Watch` gains `category`:** optional `category: str | None = None` (EXA company/news vocabulary),
passed through to the search call; `search_type` stays EXA-validated and is recorded-but-ignored on the OSS path
until/unless SearXNG gains a matching knob. Documents which knob belongs to which backend.

---

## 3. Residual risks (verified, unresolved by the above — carry into implementation issues)

1. **Single-IP SearXNG recall** (A risk 4): degraded-mode flagging is load-bearing; B/C/D must surface
   `output.degraded` to callers and must never blend degraded rows with owned-corpus hits. No spec defines the
   degraded-aware ranking rule — needs one before eval numbers are quoted.
2. **EXA tier paywall vs C's EXA adapter:** D proves live that Websets is `401: Upgrade to a Pro plan` on the
   current key tier; C's `exa_adapter`/`create_exa_monitor` assumes EXA monitor APIs work on the operator's key.
   C should adopt D's tier-aware pattern (`ExaWebsetsProRequiredError`-style typed error distinguishing
   key-missing from tier-paywalled) instead of only preserving verbatim `[webhook]` 4xx text.
3. **Citation identity across phases:** C dedups on normalized URLs; B/D join citations on exact strings.
   Until R5's shared `normalize_url` is actually imported by B and D, the same page will count as cited in one
   phase and uncited in another. Small, guaranteed confusion in joint evals.
4. **SQLite write concurrency:** C's tick loop (`tick_due_watches` + `run_watch` persists) and D's asyncio runner
   (semaphore-4 fetch/verify + event appends) are specified independently against two files; if ever co-located
   on one volume/host, WAL + busy-timeout settings should be specified once, not twice. Non-blocking for phase
   implementation, blocking for single-host ops.
5. **LLM spend stays invisible until digillm telemetry lands:** R6 stops bad routing but every "OSS costs $0"
   claim in operator docs remains false advertising until token spend is counted somewhere. The follow-up scoring
   spec (cited-fields per stage-second per token-dollar) has no owner — assign one with Phase B.
6. **D "monitor fan-out" (D line 72) has no target:** if it means Phase C watches, the C↔D delivery contract
   (envelope, auth, retry ownership) is unspecified; if it means webset cadence only, the words invite the wrong
   implementation. One sentence in D Task 5/7 must disambiguate.
7. **B live-eval anchors (`~$0.007` shallow / `~$0.26` deep, `/tmp/exa-review/` fixtures) are single-key,
   single-day samples** cited as design constants (effort presets, budget fields). Fine as scaffolding; pin a
   re-measurement task per environment before SLOs are written from them.
