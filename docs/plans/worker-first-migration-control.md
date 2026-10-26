# Container elimination — control plan

Status: **of record once merged**. Owner: Chris.

Decision: **full elimination**. Both containers (`DigiChatContainer`,
`DigiStackContainer`) are removed, and every program they run is replaced.
This supersedes the "stays" verdicts in
[`2026-10-26-digistackcontainer-replan.md`](./2026-10-26-digistackcontainer-replan.md);
that memo's sizing is kept because it is the price list for this decision.

## What was accepted, stated plainly

The replan rejected elimination because two ports are product changes, not
runtime swaps:

| Program | LOC | Why it is a product change |
|---|---:|---|
| `digisearch` | 29.0k | local ONNX embeddings, Chroma, parser stack, monitors/websets in thread-bound SQLite |
| `digigraph` | 23.9k | LangGraph execution, SSE, multi-minute runs, matplotlib/kaleido analytics |

Accepting full elimination means accepting that search retrieval and graph
execution are re-decided, not re-hosted. If either cannot be rebuilt to the
same product quality, the programme stops at that program rather than shipping
a worse product to hit a topology target. That is the one place where "full
elimination" yields to evidence.

## Rule zero: two spikes before any port

No port work starts until these two answer, because they can invalidate the
programme:

1. **Search spike** — embeddings on Workers AI (`@cf/baai/bge-m3`) and vector
   store on Vectorize, measured against the current Chroma index on a fixed
   query set: recall@10 and rank-1 agreement. Exit: a number, not an opinion.
   If recall drops materially, digisearch does not move as specified.
2. **Graph spike** — one real digigraph graph executed on Workflows + Durable
   Objects, with SSE to the client and a >5 minute run. Exit: it completes
   within the platform's CPU/duration limits, or it does not.

Both are time-boxed and produce a written finding. They are the only work that
runs in parallel with Phase A.

## Phases

Each phase is a set of steps; **one step in flight at a time**. Exit criteria
are production measurements, never merges.

### Phase A — surfaces that leave without a product decision
| Step | What | Exit | Reversible |
|---|---|---|---|
| A1 | `DIG-2915` runner → host launchd | digiquant jobs run from the host; container unused | yes |
| A2 | `redis`, `seed_chroma` delete | no consumer remains; digikey blocklist re-homed | yes |
| A3 | `searxng` → provider swap | search answers with no self-hosted dependency; per-query cost recorded | yes |
| A4 | langfuse retirement decision | decision recorded; images kept until Chris approves deletion | **no** at deletion |

### Phase B — MCP servers become Worker-native
| Step | What | Exit |
|---|---|---|
| B1 | `digivault-mcp` + `digisearch-mcp` as Worker MCP | every tool answers from the edge with no container in the path |
| B2 | `digigraph-mcp` as Worker MCP | same, once Phase E lands |

### Phase C — `digivault` service → Worker
D1 is already the production store. Exit: all vault routes and the four
baked-seed MCP tools read D1; the seed is deleted.

### Phase D — `digikey` cut
The Worker exists (`DIG-5548`, green, parked). Exit: tokens issued and verified
with no container in the path, and a token-compatibility test proves an
existing token issued by the container still verifies after the cut.

### Phase E — `digisearch` → Worker (gated by spike 1)
Embeddings and vectors move to Workers AI + Vectorize; parsers and monitors
move to Workers + Queues + D1. Exit: recall@10 within the agreed tolerance of
the baseline, measured on the same fixed query set.

### Phase F — `digigraph` → Workers (gated by spike 2)
Execution moves to Workflows/DO; SSE from the Worker. Exit: a full research
turn completes with the same tool trace shape, within platform limits.

### Phase G — chat container → Worker
Four verified blockers, each its own step:
| Blocker | Evidence | Replacement |
|---|---|---|
| listening socket | `trusted-proxy-server.mjs:277`, `:201` | proxy moves to the Worker edge |
| in-process Python MCP | `:233`, `server.py:414`, `Dockerfile.digichat-cloudflare:111` | Worker-native MCP (Phase B) |
| raw TCP Postgres | `src/db/index.ts:12` | Hyperdrive or an HTTP driver |
| boot-time filesystem | `license/state.ts:98`, `artifact-blobs.ts:127` | KV / R2 |

Exit: `/chat` p95 TTFB at the warm baseline, one full turn on **OCC** and on
the house surface, no cold start.

### Phase H — delete
`DigiChatContainer`, `DigiStackContainer`, their images. **Chris-only**, after a
verified week with no routing to either. Not reversible by redeploy.

## Control rules

1. One step in flight; the next does not begin until this one is measured in
   production.
2. Exit criteria are numbers. "Merged" is how the last incident happened.
3. Rollback written before the step starts, executable without a new commit.
4. Client surfaces named per step. OCC and every DataTap tenant are users.
5. Irreversible actions only with Chris, after the replacement has served alone.
6. A spike that fails stops its phase. It does not get argued past.

## What is already built (do not rebuild)

MCP JWT verification at the edge with a KV JWKS cache and loopback-Host
rewrite; config externalised to KV with a 30 s re-read; the 5.1 kB binding
limit hit and solved by splitting the corpus map; one tool expansion plus a
naming contract that fails CI on an id that does not exist; tenant-scoped
skills; a digikey Worker (`DIG-5548`) already green and parked.
