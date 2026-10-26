# Container reduction — control plan

Status: **of record once merged**. Executes
[`2026-10-26-digistackcontainer-replan.md`](./2026-10-26-digistackcontainer-replan.md)
(the merged memo for `DIG-2914`) as a step-controlled programme.

Owner: Chris. One step in flight at a time.

## Scope, corrected against the evidence

The ask was "turn off the containers and migrate all to the Workers". The
merged replan evaluated exactly that and **rejected the whole-box version on
size, not on taste**:

| Program | LOC | Verdict |
|---|---:|---|
| `digigraph` (LangGraph, SSE, matplotlib) | 23.9k | stays — porting is a product change |
| `digisearch` (ONNX embeddings, Chroma, thread-bound SQLite) | 29.0k | stays |
| `digisearch-mcp` | 0.7k | stays with its backend |
| `digivault` + `digivault-mcp` | 5.0k | **candidate for a Worker on its own merits** |
| `digikey` | 3.2k | Worker built, **parked** — the cut moves the JWT issuer and saves $0 while the box stays |
| `redis`, `seed_chroma`, `searxng` | ~0 | delete (searxng only with a product reason) |

So this programme is **container reduction**, not container elimination. It
removes what can leave without a product change, and it says plainly what
cannot. A full migration remains possible, but it is a re-scoping decision with
a multi-month price, and it is not smuggled in here.

## Why it is worth doing at all

Not the money: the whole bill is $77/mo and emptying the box is worth $15–27/mo
against ~61k LOC. The case is **latency and operability** — a container cold
start measured at **42.9 s** against a shell that waits 30 s, and a per-surface
blast radius that a Worker does not have for stateless work.

## Control rules

1. **One step in flight.** The next step does not begin until this one meets
   its exit criteria in production.
2. **Exit criteria are production numbers**, not merged PRs. "Merged" is how the
   last incident happened.
3. **Rollback is written before the step starts** and must not need a new
   commit.
4. **Client surfaces are named per step.** OCC and every DataTap tenant are
   users; a step that cannot be validated on them does not ship.
5. **Deletions last**, after a full week with the replacement serving alone.
6. **Nothing irreversible without Chris.** Deleting a Cloudflare container app
   or a registry image cannot be undone by a redeploy.

## Ledger

| # | Step | Entry | Exit (production) | Rollback | Reversible? |
|---|---|---|---|---|---|
| 0 | Baseline + this plan | — | numbers recorded; plan merged | n/a | yes |
| 1 | `DIG-2915` runner cutover | launchd job installed and running | digiquant jobs run from the host; container declared but unused | re-enable the container trigger | yes |
| 2 | Cheap deletions (`redis`, `seed_chroma`) | step 1 exit | names gone; digikey's JTI blocklist and the SearXNG limiter re-homed | redeploy previous image | yes |
| 3 | `digivault` → Worker | step 2 exit; the four baked-seed tools read D1 | vault tools answer from D1 with no container in the path | previous image, dispatched | yes |
| 4 | Chat container → Worker | step 3 exit; the four blockers below are retired | `/chat` p95 TTFB at the warm baseline, no cold start | dispatch the previous image tag | yes |
| 5 | `digikey` cut | step 4 exit **and** a stated reason to move it | tokens issued/verified with no container in the path | previous container stays warm one release | yes |
| 6 | Retire `DigiStackContainer` | steps 2–5 leave it with no programs | app deleted, bill reflects it | restore from the release ledger | **no — Chris only** |

> Step 6 may legitimately never happen. If `digigraph` and `digisearch` stay,
> the box stays, and the ledger ends at step 5.

## Step 4 is not a port — it is four blockers

Verified in code, not inferred from issue titles:

| Blocker | Evidence | Consequence |
|---|---|---|
| A listening socket | `trusted-proxy-server.mjs:277` `http.createServer`, `:201` `net.connect` | a request-scoped Worker cannot hold it; the proxy must move to the Worker edge or a Durable Object |
| An in-process Python MCP | `:233` spawns `python3 -m scripts.zammad_mcp.server`; `server.py:414` serves streamable-http on `127.0.0.1:8770`; `Dockerfile.digichat-cloudflare:111` installs Python | must become a Worker-native MCP or a remote service |
| Raw TCP Postgres | `src/db/index.ts:12` `postgres()` | needs Hyperdrive or an HTTP driver |
| Boot-time filesystem | `license/state.ts:98`, `artifact-blobs.ts:127` (`/var/tmp`) | needs KV/R2 |

Not blockers, despite the assumption: SSE streaming works on Workers
(`app/api/chat/route.ts:978`), the MCP client is plain `fetch` JSON-RPC
(`lib/mcp/schema-proxy.ts:321`), and there is **no** PDF, upload,
websocket, redis or SQLite code in the chat image at all.

## What is already done, so we do not rebuild it

- MCP auth at the edge: digikey JWTs verified by the Worker, JWKS cached in KV,
  loopback Host rewritten (`mcp-edge-auth.ts`, `mcp-edge-target.ts`).
- Config externalised to KV with a 30 s re-read.
- The 5.1 kB text-binding limit hit and solved by splitting the corpus map.
- One tool expansion and a naming contract that fails CI on an id that does not
  exist.

## Risks

| Risk | Why it is dangerous | Mitigation |
|---|---|---|
| `digikey` cut | moves the JWT issuer for digisearch, digigraph, digiquant and digivault; a wrong `kid`/JWKS invalidates every existing token, DataTap and OCC included | last cut, with a token-compatibility test before it |
| Chat cut | replaces the container behind invite-gated OCC with 1-minute `sleepAfter` proxy semantics | step 4 measures a full turn on OCC, not a health check |
| Deleting a container app or image | cannot be undone by redeploy | Chris-only, after a verified deploy and a week |
| Declaring a step done on "merged" | the failure mode already observed | exit criteria are production numbers |
