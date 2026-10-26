# Re-plan: the fate of `DigiStackContainer`'s programs — DIG-2914

**Status:** decision memo, docs-only. No port, deploy, secret, route, DNS or image
change is made by this document. It supersedes the port plan in
`docs/plans/2026-10-26-dig2914-stack-split-to-workers.md` (§1–§9), which stays as
the record of how the port was sized and why it stopped.
**Date:** 2026-10-26
**Author:** Edge & Domains Engineer
**Goal:** G02 Cloudflare infra & leave Supabase (`657cd9ec-cba3-467e-9afb-e2b4df7f8c44`)
**Epic:** DIG-2904 Cloudflare cost minimum
**Trigger:** Chris answered the `[scope]` card on DIG-2914 with **C — stop and
re-plan the box before any port.**

## 1. What C decided, and what it stops

- The three-service port (digikey, digigraph, digisearch) is **stopped**. No port
  work starts, and none continues.
- The container is **not** deleted. `DigiStackContainer` stays in
  `apps/digithings-stack-cloudflare/wrangler.toml`.
- The digikey Worker built under DIG-5548 is **parked**: built, tested, unmerged,
  undeployed. `key.digithings.ai` is unchanged and no D1 database is created.
- This memo is the re-plan that C asked for: the fate of **every** program in the
  image, not only the three in the old title.

## 2. The box as it is today (confirmed)

- Eleven supervisord programs on `develop` (`5281ddd44f`):
  `redis`, `searxng`, `digikey`, `digigraph`, `seed_chroma`, `digivault`,
  `digisearch`, `digisearch-mcp`, `digivault-mcp`, `digigraph-mcp`, `litellm`
  (`apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf`).
  `zammad-mcp` is the twelfth in the old count; it left on 2026-10-19 (#5926) and
  now runs in the digichat image.
- Class `DigiStackContainer`: `standard-1` (0.5 vCPU, 4 GiB, 8 GB),
  `max_instances = 1` (`wrangler.toml:98-112`), `sleepAfter = "5m"`
  (`src/index.ts:118`).
- Cost while it stays: about **$15–27/month** at the epic's measured 87 h/week
  awake (gate record §5; *reported*, computed from published rates).
- The epic's whole bill is about **$77/month**. This box is one line of it.

## 3. Why the port is the wrong lever

Emptying the box needs all four remaining programs to leave: `digigraph`,
`digigraph-mcp`, `digisearch`, `digisearch-mcp` — **52.8k LOC**, plus digivault's
4.9k to finish the job. The gate record sizes the whole move at about **61k LOC in
nine steps**. The last two steps are a rewrite of the chat and search product, not
a port.

Removing the seven cheap programs first saves **$0**, because the four that stay
keep the one instance awake. The saving is only realised by the 61k-LOC step that
deletes the class.

So the economics are: ~61k LOC of rewrite against **$15–27/month**. That is not a
cost play under any reading. It only makes sense if the product wants to stop
running LangGraph and the search/ingestion stack in-house for a reason other than
the bill.

## 4. Fate of each program

The verdicts below are the gate record's, re-read for this memo. Sizes are rough
Python LOC excluding tests (*reported*, from
`docs/plans/2026-10-26-dig5549-can-digistackcontainer-be-emptied.md` §3).

| # | Program | Fate under this re-plan | Why | Size |
|---|---|---|---|---|
| 1 | `redis` | **Delete** (cheap cleanup) | Only consumers are digikey's JTI blocklist and the SearXNG limiter. Both go if #3 and #2 go. | 0 |
| 2 | `searxng` | **Delete only with a product reason** | digisearch already has Exa/Tavily/Parallel/Firecrawl/Tinyfish providers; `auto` never consults them today, so the swap is a small code change. It removes a self-hosted dependency but adds per-query vendor cost. | <100 |
| 3 | `digikey` | **Parked** — Worker built, do not cut | 3.2k LOC, 9 routes. The Worker is green (DIG-5548), but the cut moves the JWT issuer for four services and saves $0 while the box stays. | 3.2k, done |
| 4 | `digigraph` | **Stays on the box** | LangGraph is the workflow engine (`StateGraph` in `graph/graph.py`, `graph/research_subgraph.py`), 145 modules, SSE, 2.1k LOC of matplotlib/kaleido analytics. Porting is a product change. | 23.9k |
| 5 | `seed_chroma` | **Delete** (cheap cleanup) | Already a no-op in production: exits when `DIGI_VECTORIZE_ACTIVE=1`. | ~0 |
| 6 | `digivault` | **Candidate for a Worker on its own merits** | 4.9k LOC, 15 routes; D1 is already the production store. But four MCP tools still read the baked vault seed instead of D1 — a correctness bug that a port would fix. | 4.9k |
| 7 | `digisearch` | **Stays on the box** | 29.0k LOC, 40 routes; local ONNX embeddings, Chroma/parser stack, monitors and websets in thread-bound SQLite. | 29.0k |
| 8 | `digisearch-mcp` | **Stays with #7** | 744 LOC, 17 tools; cannot leave before its backend. | — |
| 9 | `digivault-mcp` | **Goes with #6 if #6 is funded** | 77-LOC shell, 6 tools. | — |
| 10 | `digigraph-mcp` | **Stays with #4** | 439 LOC, 6 tools. | — |
| 11 | `litellm` | **Remove if the alias map moves** | 121 aliases + a 66-entry overlay, cache, retries. Not a port, but not a config flip either. Removing it does not shrink the box's bill. | low |
| 12 | `zammad-mcp` | **Already gone** to the digichat image (#5926) | Not on the stack. | 0 |

## 5. Target state, in two tiers

**Tier 1 — keep the box, clean it (no port, no cost saving).**
Delete `seed_chroma` and, once #2 and #3 are decided, `redis`. Leave `litellm`
until the alias map has a home. The box keeps `digigraph`, `digigraph-mcp`,
`digisearch`, `digisearch-mcp`. Cost stays at $15–27/month. This removes dead
programs and two moving parts, not money.

**Tier 2 — product decision, not a platform one.**
Either keep `digigraph` and `digisearch` in-house indefinitely, or replace their
product surfaces with managed services (agent runtime, managed retrieval) and then
delete the box. The second route is the only one that removes the line, and it
needs a product spec and vendor cost, neither of which exists today.

**Explicitly not funded by this re-plan:**
- The three-service port (stopped by C).
- A digigraph/digisearch Workers rewrite (61k LOC for $15–27/month).
- Consolidating the last four programs into the digichat container. It deletes
  `DigiStackContainer` but not container cost, and digichat is already awake
  longer (146 h/week vs 87 h/week).

## 6. What this changes on the board

- **DIG-2914** — port outcome withdrawn by C. The issue becomes the re-plan
  tracker and closes when this memo is accepted.
- **DIG-5548** — digikey Worker stays parked on its branch. No cut, no deploy, no
  D1 database, no `wrangler secret put`. Revive only on a product or reliability
  reason, not for the bill.
- **DIG-5549** — gate record stands as the evidence for this memo (PR #6462).
- **DIG-2904** — the box is not a cost lever. If the epic still needs savings, the
  larger measured lines are digichat (146 h/week) and the digiquant runner
  (129 h/week); this memo does not re-open them.

## 7. What would change this recommendation

- A product decision to stop running LangGraph and the ingestion/monitors/websets
  stack in-house. Then the box empties by replacement, not by port.
- The box's awake hours rising well above 87 h/week, which would raise the cost
  line while the port cost stays the same.
- A reliability defect in the box that a Worker fixes anyway (digivault's
  seed-vs-D1 reads are the one known case).

## 8. Certainty and recommendation

**Confirmed (checked this run on `develop` `5281ddd44f`):** the 11 programs; the
class, `standard-1`, `max_instances = 1`, `sleepAfter = "5m"`; that
`DigiStackContainer` is still in `wrangler.toml`; that no digikey Worker is
deployed and `key.digithings.ai` is unchanged.

**Reported:** the per-program verdicts and sizes from the gate record; the
$15–27/month figure and the 87 h/week awake time; the 61k-LOC total.

**Inferred:** that Tier 1 saves $0 (fixed instance class, per-instance billing);
that the box stays awake because the remaining four programs serve live traffic.

**Hypothesis:** that a managed agent runtime plus managed retrieval could replace
digigraph and digisearch at a cost below the box's $15–27/month. Nothing prices
that today.

**Recommendation: keep the box, clean the dead programs, and close the port line.**
The container costs about $15–27/month and costs about 61k LOC to remove. The
re-plan therefore ends the port, parks the digikey Worker, and moves the
digigraph/digisearch fate to a product decision. If the epic needs money, take it
from the lines that are awake more, not from this one.
