# DIG-5549 decision record: can `DigiStackContainer` ever be emptied?

**Status:** decision record, docs-only. No deploy, secret, route, DNS or image change is
made by this document.
**Date:** 2026-10-26
**Author:** Edge & Domains Engineer
**Goal:** G02 Cloudflare infra & leave Supabase (`657cd9ec-cba3-467e-9afb-e2b4df7f8c44`)
**Epic:** DIG-2904 Cloudflare cost minimum
**Parent:** DIG-2914 split digikey/digigraph/digisearch to Workers + D1/Vectorize

## 1. Answer

**No. `DigiStackContainer` cannot be emptied before the 56k-LOC port is funded — and the
56k is not enough to empty it either.**

Three findings decide the question:

1. **The box has 11 programs today, not 12.** `zammad-mcp` left the base stack on
   2026-10-19 in #5926 and now runs inside the digichat image. It is recorded as the
   twelfth program below, with its current home, rather than re-counted in
   `supervisord.conf`.
2. **The six "deciding" programs are not the expensive ones.** `redis`, `searxng`,
   `seed_chroma`, `litellm` and `zammad-mcp` are cheap to remove or already gone;
   `digivault` is a 4.9k-LOC port. None of those moves deletes the box, because
   `digigraph` (23.9k LOC) and `digisearch` (29.0k LOC) stay and keep the class alive.
   Partial removal saves **$0**.
3. **The funded 56k covers three services; the box needs four.** The 56k is
   `digikey` 3.2k + `digigraph` 23.9k + `digisearch` 29.0k. `digivault` (4.9k) is also in
   the box and is outside DIG-2914's three. Emptying the box therefore costs roughly
   **61k LOC, not 56k**: the 56k is necessary and still about 5k short.

The only cheaper route is a **product change**, not a port: give up digigraph's
LangGraph orchestration (and its analytics surface) and digisearch's ingestion, monitors
and websets, and buy replacements. That has not been specified, and it is not what
DIG-2914 is funded to do.

## 2. Scope and method

- Program list at ticket time: the 12 `[program:]` blocks named in the DIG-2914 comment
  of 2026-10-25 — `redis`, `searxng`, `digikey`, `digigraph`, `seed_chroma`, `digivault`,
  `digisearch`, `digisearch-mcp`, `digivault-mcp`, `digigraph-mcp`, `zammad-mcp`,
  `litellm`.
- Current tree: 11 blocks
  (`apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf:23-172`).
  `zammad-mcp` was removed by commit `61e807121f` (#5926); its block now asserts absence
  in `tests/scripts/test_zammad_mcp_stack.py:44`.
- Every verdict below cites a file in this tree. Platform claims cite Cloudflare's
  documentation, read 2026-10-26. Cost uses the epic's own 7-day measurement plus the
  published Containers rates.
- "Rough size" is Python LOC excluding tests, from `find … -name '*.py' | xargs wc -l`
  on the service directory. It is a porting estimate, not a quote.

## 3. Verdicts for all twelve programs

| # | Program | Verdict | Evidence | Rough size |
|---|---|---|---|---|
| 1 | `redis` | **Leaves** (delete; no replacement) | Only two consumers: digikey's JWT `jti` blocklist (`digikey/src/digikey/blocklist.py:1-4`) and the SearXNG limiter (`config/searxng/settings.yml:87-88`). | 0 LOC — delete the block after #3 and #2 |
| 2 | `searxng` | **Replaced by a paid service** (Exa or Tavily) | digisearch already ships six providers (`digisearch/src/digisearch/web_providers/registry.py:34-51`); an Exa key is live in a Worker/runtime env (`docs/ops/SECRETS_INVENTORY.md:40,397`); Tavily has 1,000 free credits/month (`digisearch/ARCHITECTURE.md:526`). | <100 LOC: switch the `auto` default, add the secret, delete the image bake |
| 3 | `digikey` | **Leaves on a Worker** (D1 + KV + WebCrypto RS256) | 9 HTTP routes (`digikey/src/digikey/server.py:110-611`); 4 tables incl. `JtiIssuedRow` (`db_schema.py:38-120`); Redis is only the blocklist (`blocklist.py`); RS256 keys already PKCS#8. | 3.2k LOC, 9 routes — green |
| 4 | `digigraph` | **Stays on a container** | LangGraph is the workflow engine, not a helper: `StateGraph`/`add_node` in `graph/graph.py:9,403-412`, `graph/research_subgraph.py:14-25`, `graph/product_graphs.py:183-189`; 145 modules; SSE at `server.py:698-726`; 2,110 LOC of analytics chart tools. | 23.9k LOC — red; a rewrite plus product change |
| 5 | `seed_chroma` | **Leaves** (delete) | Already a no-op in production: exits immediately when `DIGI_VECTORIZE_ACTIVE=1` (`container/seed_chroma.sh:22-29`), computed once in `container/entrypoint.sh:150-167`. | ~120 lines of shell; no port |
| 6 | `digivault` | **Leaves on a Worker** (D1 + Vectorize) | D1 is already the production store: `D1Store.search/get_note/search_tag/backlinks/list_notes` (`digivault/src/digivault/d1_store.py:510-676`), FTS5 schema (`d1_schema.sql`), production map (`apps/digithings-stack-cloudflare/wrangler.toml:209`, `docs/ops/SECRETS_INVENTORY.md:114`). | 4.9k LOC, 15 routes — green/amber; 4 tools still read local files |
| 7 | `digisearch` | **Stays on a container** | 40 route decorators (`digisearch/src/digisearch/server.py`); 29.0k LOC; Vectorize backend exists but embeds locally with ONNX MiniLM (`indexes/backends/vectorize.py:38-50`); Chroma/parser stack, monitors and websets persist to thread-bound SQLite. | 29.0k LOC — red |
| 8 | `digisearch-mcp` | **Leaves on a Worker, with digisearch** | 744 LOC, 17 tools (`digisearch/src/digisearch/mcp_server.py`). It cannot leave before its backend does. | Included in #7's effort |
| 9 | `digivault-mcp` | **Leaves on a Worker, with digivault** | 77-LOC transport shell over the shared dispatch table; 6 tools. `search_notes` already prefers D1, but `search_tag`, `backlinks`, `lint`, `create_note` still open `DIGIVAULT_ROOT` (`digivault/src/digivault/tool_dispatch.py:330-407`). | ~77 LOC shell + D1 rewire of 4 tools |
| 10 | `digigraph-mcp` | **Stays with digigraph** | 439 LOC, 6 tools; auth against the stack JWKS (`container/supervisor/supervisord.conf:159-170`). | Included in #4's effort |
| 11 | `litellm` | **Replaced by direct provider calls or Workers AI** | Alias router: 121 `model_name` entries plus a 66-entry Cheaper Inference overlay merged at boot, 1h local cache, 2 retries (`config/litellm.yaml`; `config/litellm.cheaperinference.yaml`; pinned `litellm[proxy]==1.83.14` in `infra/docker/Dockerfile.digithings-stack-cloudflare:110`). digigraph already defaults to a direct base URL when `OPENAI_API_BASE` is unset (`digigraph/src/digigraph/model_config.py:664-697`) and parses BYOK headers itself (`llm_auth.py:1-40`). Workers AI exposes OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings`. | low LOC, but not zero: move the alias map and cache/retry into digigraph or callers |
| 12 | `zammad-mcp` | **Already left the stack** (still container-hosted) | Moved to the digichat image on 2026-10-19, #5926 (`61e807121f`): spawned by `apps/digichat/scripts/trusted-proxy-server.mjs`, served at `digithings.ai/api/mcp/zammad/mcp` behind `ZAMMAD_EDGE_KEY`. Absence pinned in `tests/scripts/test_zammad_mcp_stack.py:44`. | 0 LOC on the stack; it is digichat's problem now |

**What the table means in aggregate.** Seven programs can leave without touching any of
the three services DIG-2914 names. Add the funded `digikey` port and the box still runs
four: `digigraph`, `digigraph-mcp`, `digisearch`, `digisearch-mcp` — 52.8k LOC of Python
that still needs the container. The box stays billed.

## 4. The six deciding questions

### 4.1 digigraph without matplotlib, kaleido, polars and langgraph

**`graph.digithings.ai` loses nothing.** The public chat profile is `research_rag` and
its allowlist is only `digisearch*`, `digivault*` and `web_search`
(`infra/digichat-release/config/digiproject.yaml:32-46`). No chart or dataframe tool is
reachable from the public chat.

The loss falls on the **analytics agent surface**, which is not exposed in Profile A:
2,110 LOC under `digigraph/src/digigraph/tools/analytics/`, used by the
`agents/{analysis,visualization,data_prep,data_manipulation,data_engineer}` runners.
- `matplotlib` renders the PNG charts (`tools/analytics/visualization/plot_*.py`);
- `kaleido` is used only by the Sankey renderer (`plot_sankey.py:88`, `fig.write_image`);
- `polars` is the dataframe engine across the analytics tools.

**`langgraph` cannot be dropped.** It is the orchestration engine itself — the
`research_rag` workflow is a `StateGraph` (`graph/research_subgraph.py:14-25`), as are the
product and pipeline graphs. Dropping it is a rewrite of the workflow engine, not the
removal of an optional dependency.

Platform note (Cloudflare docs and the Pyodide package list, read 2026-10-26): Cloudflare's
Python Workers page supports pure-Python and Pyodide packages and defers the package list
to Pyodide. That list includes `polars 1.33.1` and `matplotlib 3.10.8`. `kaleido`,
`chromadb` and `onnxruntime` are not on it; `kaleido` also needs a Chromium binary.
Workers' 128 MB memory limit and CPU-second limits make the analytics path a poor fit
regardless. So "without matplotlib/polars" is partly a choice, "without kaleido" is a hard
limit, and "without langgraph" is a product change.

### 4.2 digivault and digivault-mcp on D1 + Vectorize

**The data layer is already D1.** `D1Store` implements search, get-note, tag lookup,
backlinks and listing (`d1_store.py:510-676`); the schema is a `notes` table plus an FTS5
index (`d1_schema.sql`); production passes a per-tenant `D1_DATABASE_MAP`
(`wrangler.toml:209`). Vectorize is the semantic index populated by
`scripts/vectorize_sync.py`; digivault itself does not query Vectorize.

**But two seams are still filesystem-backed.** `search_notes` prefers D1; `search_tag`,
`backlinks`, `lint` and `create_note` open `DIGIVAULT_ROOT`
(`tool_dispatch.py:330-407`). In production the container's `/data/vault` is the baked
seed, so those four MCP tools read the seed, not the live D1 corpus. Porting digivault is
therefore also a correctness fix: move the four handlers onto D1 (the store already has
`search_tag`/`backlinks`; `lint`/`create_note` need new SQL or R2) and put the MCP surface
on a Worker.

Verdict: feasible at ~4.9k LOC + a 77-LOC MCP shell. It is the smallest real Worker port
in the box, and it is **not** in DIG-2914's 56k.

### 4.3 litellm replaced by direct provider calls or Workers AI

`litellm` is an alias router, not a model host — and a large catalog, not a thin shim:
`config/litellm.yaml` carries **121 `model_name` entries** (OpenAI, OpenRouter
house pins, Ollama Cloud, and the BYOK catalog), and the stack merges a **66-entry
Cheaper Inference overlay** at boot when `CHEAPERINFERENCE_API_KEY` is set
(`litellm.cheaperinference.yaml`; `scripts/merge_litellm_cheaperinference.py`). Router
settings are `simple-shuffle`, 1-hour local cache, 2 retries and a 120-second timeout.

digigraph already supports a direct provider base: `OPENAI_API_BASE` is used when set,
otherwise `model_config.py:664-697` points at CheaperInference or OpenRouter. It also
parses BYOK headers itself and pins the provider base URLs in `llm_auth.py`, so the proxy
is not the only enforcement point for BYOK. Workers AI exposes OpenAI-compatible
chat-completions and embeddings endpoints, so it can be another base URL without a
router.

Loss to accept or re-implement: the central alias map (121 entries, many of them duplicate
aliases of the same house pin), the Cheaper Inference merge, the local response cache, the
per-host BYOK `api_base` pinning that the proxy applies, and router-level
retry/fallback. That is configuration and a small amount of client code, not a Worker
port — and none of it requires digigraph to leave the container.

### 4.4 searxng replaced by an already-paid search API

digisearch already integrates `exa`, `tavily`, `parallel`, `firecrawl` and `tinyfish`
(`web_providers/registry.py:34-51`). An Exa key is live in a Worker/runtime environment
(`SECRETS_INVENTORY.md:40,397`); Tavily's free tier is 1,000 credits/month.

One deliberate obstacle: `auto` always means the in-house SearXNG→ddgs path and never
consults an external key (`registry.py:1-13`, `resolve_provider_name`). Removing SearXNG
therefore needs either an explicit `provider=exa|tavily` from callers or a change to the
default mapping — a small code change, not a config flip.

Loss: self-hosted metasearch, no per-query vendor cost, and one fewer outage dependency.
The embedded `ddgs` scrape remains as a fragile fallback.

### 4.5 What still needs redis

Exactly two consumers:
1. **digikey's `jti` blocklist** — TTL keys per revoked token
   (`digikey/src/digikey/blocklist.py:1-4`). KV with `expirationTtl` is the direct
   replacement.
2. **SearXNG's limiter** — `redis.url: redis://valkey:6379/0`
   (`config/searxng/settings.yml:87-88`).

Nothing else imports Redis. Once digikey is on KV and SearXNG is on a paid API, `redis`
has no consumer and the program can be deleted.

### 4.6 zammad-mcp on the OCC path

**It is no longer on the stack.** Since 2026-10-19 (#5926) it runs inside the digichat
image, spawned by `apps/digichat/scripts/trusted-proxy-server.mjs`, reached through
`apps/digichat/src/app/api/mcp/zammad/[[...path]]/route.ts`, and gated at
`digithings.ai/api/mcp/zammad/mcp` by `ZAMMAD_EDGE_KEY`.

So the OCC path does not depend on `DigiStackContainer`. It does still depend on a
container — digichat's — so this move reduces the stack's program count but not the
account's container count.

## 5. What the box costs while it stays

Container billing is per 10 ms of running time, with monthly included allowances on
Workers Paid (Cloudflare Containers pricing, read 2026-10-26): 25 GiB-hours memory,
375 vCPU-minutes, 200 GB-hours disk; then $0.0000025/GiB-second memory,
$0.000020/vCPU-second CPU, $0.00000007/GB-second disk.
`DigiStackContainer` is `standard-1` (0.5 vCPU, 4 GiB, 8 GB), `max_instances = 1`
(`wrangler.toml:94-108`), `sleepAfter = "5m"` (`src/index.ts:106`).

The epic's 7-day observation measured the stack awake for **87 h/week ≈ 377 h/month**.
At that duty cycle:

| Line | Calculation | Cost/month |
|---|---|---|
| Memory | (377 × 4 − 25) GiB-h × 3600 × $0.0000025 | **$13.35** |
| Disk | (377 × 8 − 200) GB-h × 3600 × $0.00000007 | **$0.71** |
| CPU | 0.5 vCPU × 377 h, less 375 vCPU-min, at 10–100% active | **$0.91–$13.12** |
| **Total** | | **≈ $15–27** |

This is the prize for emptying the box, and it is lumpy: it does not fall
proportionally as programs leave, because the remaining services keep the instance
awake. It goes to ~$0 only when **all four** remaining services are gone. Removing the six
cheap programs first therefore saves $0.

## 6. Ordered remaining moves (conditional on a decision to empty)

Sizes are the same estimates as §3. Steps 1–6 remove programs and dependencies but do
**not** delete the class or the bill. Step 9 is the only step that deletes the class.

**Stage 0 — remove programs, $0 saved (ordered by dependency, cheapest first):**

1. **digikey → Worker** — 3.2k LOC, 9 routes, D1 + KV + WebCrypto RS256. Also removes
   Redis consumer #1. (Already scoped as DIG-5548.)
2. **searxng → Exa or Tavily** — <100 LOC default switch + secret; delete the image bake
   and the Redis limiter. Removes Redis consumer #2.
3. **redis → delete** — 0 LOC once #1 and #2 land.
4. **litellm → delete** — configuration plus a small client change; point
   `OPENAI_API_BASE` at the provider or Workers AI, and move the alias map, the Cheaper
   Inference overlay and cache/retry into digigraph.
5. **seed_chroma → delete** — ~120 lines of shell; production already exits immediately
   on the Vectorize path.
6. **digivault + digivault-mcp → Worker** — 4.9k LOC + 77-LOC shell; D1 for
   note/tag/backlink/lint/write, Vectorize for semantic search.

After Stage 0: `digigraph`, `digigraph-mcp`, `digisearch`, `digisearch-mcp` remain —
52.8k LOC — and the container is still billed at ~$15–27/month.

**Stage 1 — the deletion:**

7. **digisearch + digisearch-mcp → Worker** — 29.0k LOC, 40 routes. Vectorize backend
   exists; replace local ONNX embeddings with Workers AI embeddings; move ingestion to
   Queues/Workflows and monitors/websets to D1 + Workflows; re-host the 17 MCP tools.
8. **digigraph + digigraph-mcp → Worker** — 23.9k LOC, 145 modules. Rewrite the LangGraph
   workflow/state layer for Workers, replace Postgres/SQLite checkpointing, keep SSE, and
   either drop the 2.1k-LOC analytics surface or move it to a separate job container.
   This is the product change, not a port.
9. **Delete the class** — remove `[[containers]] class_name = "DigiStackContainer"`, the
   `STACK` Durable Object binding and migration, the image build, the deploy step, and the
   custom-domain container routing. 0 LOC, but it is the only step that changes the bill.

**Total:** ~61k LOC of porting (56k of it the three DIG-2914 services, 4.9k digivault),
plus the small config deletions, in nine steps.

## 7. What would make the answer "yes" earlier

Two routes, neither of them a port:

- **Replace both product surfaces with paid services.** Accept losing digigraph's
  LangGraph orchestration and analytics, and digisearch's ingestion/monitors/websets;
  buy an agent runtime and a managed search/retrieval service. This needs a new spec and
  a product decision; it is not DIG-2914 as written.
- **Consolidate the last four programs into the digichat container.** This deletes
  `DigiStackContainer` but not container cost, and digichat is already awake 146 h/week
  (more than the stack's 87 h). It also mixes the client/OCC surface into the base
  platform, which the 2026-10-19 ruling deliberately separated
  (`apps/digithings-stack-cloudflare/wrangler.toml:78-92`). Not recommended.

## 8. Certainty and recommendation

**Confirmed (observed in this tree):** the 11 current programs; the `zammad-mcp` move and
its absence pin; route and module counts; the D1 store and its methods; the provider
registry and the `auto` rule; the litellm config and digigraph's direct-base fallback;
the container class, instance type, `max_instances` and `sleepAfter`; the SearXNG bake and
its Redis limiter.

**Inferred:** the ~$15–27/month figure (measured awake hours × published rates, CPU
active-time assumed); Python Workers package availability and limits (Cloudflare docs,
not tested in this repo); that Stage 0 leaves the instance awake (traffic keeps
digigraph/digisearch warm).

**Hypothesis:** that digigraph can be ported to Python Workers at all without a product
change. Nothing in this tree tests LangGraph-on-Workers, checkpointing, or the 128 MB
memory ceiling against the 145-module app.

**Recommendation: Re-scope.** Do not fund the "empty the box" outcome as a cost play.
The saving is ~$15–27/month and arrives only after ~61k LOC and nine steps, the last two
of which are a rewrite of the chat/search product. Fund Stage 0 separately because it is
independently valuable — digikey on a Worker, digivault on D1, SearXNG on a paid API,
litellm removed, seed_chroma deleted — and put the digigraph/digisearch port behind a
product decision, not a container-bill decision. `DigiStackContainer` stays until that
decision is made.

## 9. Evidence index

- Program list: `apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf:23-172`
- Container class: `apps/digithings-stack-cloudflare/wrangler.toml:94-108`;
  `apps/digithings-stack-cloudflare/src/index.ts:91-106`
- Vectorize boot path: `apps/digithings-stack-cloudflare/container/entrypoint.sh:150-167`;
  `container/seed_chroma.sh:22-29`; `container/start_digisearch.sh:13-18`
- digikey: `digikey/src/digikey/server.py:110-611`; `digikey/src/digikey/db_schema.py:38-120`;
  `digikey/src/digikey/blocklist.py:1-4`
- digigraph: `digigraph/pyproject.toml:14-26`; `digigraph/src/digigraph/graph/graph.py:9,403-412`;
  `graph/research_subgraph.py:14-25`; `server.py:698-726`; `model_config.py:667-697`;
  `infra/digichat-release/config/digiproject.yaml:32-46`
- digisearch: `digisearch/src/digisearch/server.py` (40 route decorators);
  `indexes/backends/vectorize.py:38-50`; `web_providers/registry.py:1-51`;
  `digisearch/ARCHITECTURE.md:505-555`
- digivault: `digivault/src/digivault/d1_store.py:510-676`;
  `digivault/src/digivault/d1_schema.sql`; `digivault/src/digivault/tool_dispatch.py:330-407`;
  `digivault/src/digivault/server.py:180-340`
- litellm: `config/litellm.yaml` (121 `model_name` entries);
  `config/litellm.cheaperinference.yaml` (66); `scripts/merge_litellm_cheaperinference.py`;
  `digigraph/src/digigraph/llm_auth.py`; `infra/docker/Dockerfile.digithings-stack-cloudflare:110`
- zammad: commit `61e807121f` (#5926); `tests/scripts/test_zammad_mcp_stack.py:44`
- Cost: [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/),
  read 2026-10-26; awake hours from the DIG-2904 7-day observation
- Python Workers: [Python Workers](https://developers.cloudflare.com/workers/languages/python/),
  [Packages](https://developers.cloudflare.com/workers/languages/python/packages/),
  [Pyodide package list](https://pyodide.org/en/stable/usage/packages-in-pyodide.html),
  [Workers AI OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/),
  read 2026-10-26
