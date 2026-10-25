# Design: split digikey / digigraph / digisearch off `DigiStackContainer` — DIG-2914

**Status:** proposal, docs-only. No service, secret, route, or DNS change is made by
this document. Everything under §7 marked *human-only* is gated.

**Goal:** G02 Cloudflare infra & leave Supabase (`657cd9ec-cba3-467e-9afb-e2b4df7f8c44`).
**Epic:** DIG-2904 Cloudflare cost minimum.
**Done when:** `DigiStackContainer` is gone from
`apps/digithings-stack-cloudflare/wrangler.toml`, the `stack` container image build is
deleted, and a 7-day container-billing read shows no `stack` instance time. A merged
PR is not the outcome.

## 1. Problem

DIG-2904 cuts the Cloudflare bill by deleting container apps. `DigiStackContainer`
(`standard-1`, 4 GiB, `max_instances = 1`, `sleepAfter = 15m`) is the largest of the
four. DIG-2914 was written as "split digikey/digigraph/digisearch to Workers +
D1/Vectorize" and states "Removes the Profile A container".

Neither service is a proxy. All three are Python FastAPI apps, so this is a rewrite,
not a port. Two findings below change what this issue can actually deliver.

## 2. What the container runs today (evidence)

Twelve supervisord programs
(`apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf`):

| # | Program | Kind | Public today |
|---|---|---|---|
| 1 | `redis` | state, loopback | no |
| 2 | `searxng` | web-search backend, loopback | no |
| 3 | `digikey` | FastAPI | `key.digithings.ai` |
| 4 | `digigraph` | FastAPI + MCP | `graph.digithings.ai` |
| 5 | `seed_chroma` | boot step | no |
| 6 | `digivault` | FastAPI | no (MCP via edge key) |
| 7 | `digisearch` | FastAPI | `search.digithings.ai` |
| 8 | `digisearch-mcp` | MCP, loopback | via `/_stack/mcp/digisearch/*` |
| 9 | `digivault-mcp` | MCP, loopback | via `/_stack/mcp/digivault/*` |
| 10 | `digigraph-mcp` | MCP, loopback | no public route |
| 11 | `zammad-mcp` | MCP, loopback | via `/_stack/mcp/zammad/*` (key-gated) |
| 12 | `litellm` | LLM proxy, loopback | no |

Container config: `apps/digithings-stack-cloudflare/wrangler.toml:113-126`.
Routes and hostnames: same file, `[[routes]]` block.

## 3. Finding 1 — removing the three does not remove the container

Nine programs that are not in this issue's title stay behind. The instance is already
at the cost floor (`standard-1`, one replica), so there is **no partial saving**:
until the last program leaves, container instance-time is unchanged.

Consequence: ordering must follow "what empties the box", not "what is cheapest to
port". A 56k-LOC rewrite of the three services, on its own, moves $0.

## 4. Finding 2 — per-service Worker viability

| Service | Python LOC | Routes | State | Worker verdict |
|---|---|---|---|---|
| digikey | 3,168 (24 files) | 9 | Postgres 4 tables, Redis blocklist/rate-limit, RS256 JWT, bcrypt admin keys | **green** |
| digisearch | 30,289 (171 files) | 40+ | Chroma (Vectorize backend already shipped), SQLite stores for websets/monitors, worker threads, Exa/monitor webhooks, ingest worker | **amber — split the surface** |
| digigraph | 23,045 (147 files) | ~16 | langgraph, polars, matplotlib + kaleido chart files, Postgres checkpoints, SSE streaming | **red as a whole** |

Routes: `digikey/src/digikey/server.py:110,116,127,177-611`;
`digisearch/src/digisearch/server.py`; `digigraph/src/digigraph/server.py:322-801`.

Why digigraph is red: `digigraph/src/digigraph/tools/analytics/visualization/*.py`
and `analysis/{regression,correlation}.py` render charts with matplotlib and
kaleido, and `/files/{path}` serves them. Workers cannot run matplotlib. Porting
would mean deleting chart and dataframe tools, which is a product change, not a
platform change.

Why digisearch is amber: the query / index / ingest API maps cleanly to Vectorize +
D1 + Queues, and `digisearch/src/digisearch/indexes/backends/vectorize.py` already
implements `DigiIndex` over the Vectorize v2 REST API. The webset and monitor
subsystems (`digisearch/src/digisearch/websets/`, `.../monitors/`) persist to
thread-bound SQLite and run background threads; they need D1 plus Workflows or
Queues, and they are the bulk of the effort.

## 5. Proposed sequencing

**Step 0 — parity harness (this issue, ~1 day).** Add
`scripts/check_digikey_route_parity.py`: import the digikey FastAPI app, dump
`{method, path, status, request_schema}` sorted, and diff it against the Worker's
route table. Fails CI on drift. This is the safety net every later step needs, and
it is the one artefact the interrupted runs kept reaching for.

**Step 1 — digikey on Workers (independent of every decision).** New
`apps/digikey-worker` (TypeScript, pattern: `apps/digidata-api`). D1 for the four
tables, KV for JTI/blocklist/rate-limit, RS256 through WebCrypto. Dual-run, then cut
`key.digithings.ai`, then delete `[program:digikey]`. Details in §6.

**Step 2 — gate spike (cheap, decides the budget).** Answer: can `digigraph`,
`digivault`, `litellm`, `searxng`, `redis` and `zammad-mcp` leave this image? If the
answer is no for digigraph, the container never dies, and Steps 3-4 buy nothing.
One issue, half a day, no code.

**Step 3 — digisearch surface split (only if Step 2 says the box can empty).**
Worker for `/query`, `/indexes*`, `/ingest*` over Vectorize + D1; Queues for ingest;
Workflows for websets and monitors; drop Chroma and `seed_chroma`.

**Step 4 — digigraph decision.** Either feature-cut it onto Workers + Durable
Objects/Workflows (product change, needs owner sign-off), or keep one slim container
for digigraph only (no instance removal).

**Step 5 — deletion.** Remove `[[containers]]` `DigiStackContainer`, its routes, its
`envVars` block, `Dockerfile.digithings-stack-cloudflare`, the deploy workflow
container step, and the `/_stack/*` edge shims.

## 6. digikey port notes

Surface (`digikey/src/digikey/server.py`): `GET /health`, `GET /healthz`,
`GET /.well-known/jwks.json`, `POST /v1/admin/keys`,
`POST /v1/oauth/token`, `POST /v1/admin/keys/{key_id}/revoke`,
`POST /v1/admin/bff-sessions/revoke`, `POST /v1/licenses/heartbeat`,
`POST /v1/admin/licenses/{license_id}/revoke`.

- **Schema.** Four tables in `digikey/src/digikey/db_schema.py`:
  `digikey_api_keys`, `digikey_jti_issued`, `digikey_user_profile_pointers`,
  `digikey_licenses`. They map to D1 DDL without type loss; `db_migrate.py` becomes a
  D1 migration under `migrations/`.
- **JTI and rate limits.** Redis is used only for the blocklist
  (`digikey/src/digikey/blocklist.py`). D1 with an expiry index is enough at current
  volume; KV is the alternative but has no atomic counters, so keep counters in D1.
- **RS256.** `crypto_keys.py` generates 2048-bit RSA. WebCrypto
  `RSASSA-PKCS1-v1_5` + SHA-256 signs the same tokens from the same PKCS#8 PEM, so
  `kid` and JWKS output stay byte-identical. No key rotation is needed for the cut.
- **bcrypt.** Used only to verify admin/BFF secrets. Two options: ship a bcrypt WASM
  module, or move admin hashes to PBKDF2-SHA256 via WebCrypto and rehash on the next
  admin write. Recommend PBKDF2 with a `digikey_api_keys.hash_algo` column, because
  the admin surface is two write paths and WASM bcrypt costs bundle size on every
  cold start.
- **Parity evidence before cut.** Golden JWTs verified by both runtimes; JWKS byte
  comparison; the Step 0 harness green; a replay of the licence heartbeat and
  revoke fixtures.

## 7. Risks and gates

- *Human-only:* `key.digithings.ai` DNS/route cut, `wrangler secret put`, and the
  deletion of the container route. All are Chris-owned.
- **Blast radius.** `key.` issues and verifies JWTs for digisearch, digigraph,
  digiquant and digivault. A signing defect takes every bearer-token call down. The
  cut therefore keeps both issuers live and publishes both keys until token TTL has
  passed.
- **Rollback.** Keep the `DigiStackContainer` image tag and the supervisord program
  for one release after the cut; revert the route, not the database. D1 is written
  only after the dual-run read path is green, so a rollback loses no writes.
- **Secrets.** Worker secrets go in through `wrangler secret put` only; nothing is
  echoed to a run log or comment.

## 8. Decision taken, and the open work

The stated outcome ("removes the Profile A container") is not reachable by this
issue alone, because nine non-targeted programs share the image and digigraph cannot
run on Workers without a product change.

The scope question could not be raised as an interactive card (the run is
non-interactive), so **option A is assumed** and the board reflects it:

- **DIG-5548** — digikey onto a Worker (Step 1). Safe under every option.
- **DIG-5549** — the gate spike (Step 2): can the remaining six programs leave the
  image? Safe under every option, and it decides whether Steps 3-4 are funded.
- **DIG-2914** stays open as the tracker and is held at `todo` until DIG-5549
  answers.

If the owner prefers B or C, say so on DIG-2914: B adds digigraph scope with a
feature-cut sign-off, C cancels the two children before code starts.
