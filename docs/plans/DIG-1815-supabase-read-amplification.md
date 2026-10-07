# DIG-1815 — Stop Supabase read amplification on the public surfaces

**Lane:** big · **Author:** EM · **Status:** spec for approval · **Parent:** DIG-1806
**Repo file:** `docs/plans/DIG-1815-supabase-read-amplification.md`
**Review record:** `docs/plans/review-DIG-1815-supabase-read-amplification.md`

---

## 1. What actually leaked

The digithings Supabase org exceeded its free egress quota (6 GB against 5.5 GB) and
dropped requests until the 22 October refill. DIG-1806 traced it to an uncached
read-amplification pattern, not abuse. This spec is the fix.

The board declined the $25/month Pro upgrade (DIG-1806, 2026-10-07), so the org stays
restricted. That makes the failure mode *worse*, not better: under restriction every
read fails, and the read path retries each failure three times. The amplification is
at its worst exactly when the quota is exhausted, which is the state we are in now.

### 1.1 The measured-by-reading amplification factor

This is counted from source, not from the Query Advisor. It is a **floor**, not a total —
it counts duplicate queries, not bytes.

One dashboard FX Hub page load, from `TwelveXClient.tsx` mount plus the command palette
mount:

| # | Query | Unbounded? | Selects `brief_markdown`? | Fired by |
|---|-------|-----------|---------------------------|----------|
| 1 | `fx_research_history` (30-day window) | yes | **yes** | `TwelveXClient` → `getBriefs(30)` |
| 2 | `fx_research_history` (14-day window) | yes | **yes** | `TwelveXClient` → `getMatrix()` → `getBriefs(14)` |
| 3 | `fx_research_history` (30-day window) | yes | **yes** | `command-palette` → `getBriefs(30)` |
| 4 | `fx_trade_ideas_snapshot` (all history) | yes | no | `TwelveXClient` **and** `command-palette`, both → `getTradeIdeaArchive()` |
| 5 | `fx_consensus_snapshot` (all `run_date`s) | yes | no | `getConsensusTimeSeries()` |
| 6 | `fx_consensus_snapshot` | yes | no | `getIntelligenceWhy()` — second reader |
| 7 | `fx_consensus_snapshot` | yes | no | `getConsensusDivergence()` — third reader |

So a **single** page load issues **3 briefs queries and 2 identical trade-idea-archive
queries**, and three `brief_markdown` payloads arrive for the client to use one of. Under
restriction each of those seven becomes three attempts: **21 failing requests per load,
per tab, per refresh** — before the Realtime socket has delivered a single row.

Queries 1–4 are the same four statements firing two or three times. That is the whole
story of the 6 GB.

### 1.2 Row-limit audit

`apps/dashboard/lib/twelve-x/fetch.ts` has **23** `.from(` calls and **9** `.limit()`
calls. The issue recorded 8 limits; the current count is 9. **14 of 23 reads carry no
row limit at all.**

| Line | Table | Function | Bounded? |
|------|-------|----------|----------|
| 172 | `fx_consensus_snapshot` | `getConsensusTimeSeries` | **no** |
| 265 | `fx_daily_digest` | `getLatestDigest` | `limit(1)` |
| 294, 307, 329 | `fx_confluence_snapshot` | confluence series / ranks / latest | yes |
| 464 | `economic_calendar` | `fetchCalendarWindow` (±14d) | **no** |
| 504 | `fx_events_snapshot` | `getEventOpinions` | **no** |
| 556 | `fx_research_history` | `getBriefs` | **no** |
| 581 | `fx_research_history` | `getBrief` | `limit(1)` |
| 667 | `fx_trade_ideas_snapshot` | `getTradeIdeas` exact-date leg | **no** |
| 677 | `fx_trade_ideas_snapshot` | carried-episode fallback | `limit(50)` |
| 717 | `fx_trade_ideas_snapshot` | `getTradeIdeaHistory` | **no** |
| 736 | `fx_trade_ideas_snapshot` | `getTradeIdeaArchive` | **no** |
| 751 | `fx_idea_eval` | `getIdeaEval` | **no** |
| 771 | `fx_consensus_eval` | `getConsensusEval` | **no** |
| 818 | `macro_series_observations` | `getFxFixSeries` | `limit(10000)` |
| 845 | `fx_research_history` | `getTodayBriefs` | **no** |
| 1007 | `fx_relevance_ledger` | latest ledger row | `limit(1)` |
| 1031 | `fx_relevance_ledger` | `getLedger` | **no** |
| 1178 | `fx_consensus_snapshot` | `getIntelligenceWhy` | **no** |
| 1303 | `fx_consensus_snapshot` | `getConsensusDivergence` | **no** |
| 1313 | `fx_smart_bias` | `getConsensusDivergence` | **no** |
| 1320 | `fx_market_snapshots` | `getConsensusDivergence` | `limit(1)` |

### 1.3 Retry amplification

Both wrappers default to `retries = 3, delayMs = 500`, with `[]`-means-empty semantics
(`fetch.ts:68` `querySupabase`, `fetch.ts:107` `queryMainSupabase`). Neither inspects the
error before retrying. Backoff is a fixed `500ms * 2^attempt` with **no jitter**, so N
tabs refreshing together stay in lockstep.

### 1.4 Realtime

`apps/dashboard/lib/hooks/use-live-prices.ts` subscribes to `postgres_changes` on
`prices_live` with `event: "*"` and **no server-side filter**, discarding non-wanted
tickers client-side. `apps/digiquant-web/lib/live/useLivePrices.ts` repeats the pattern on
a public Cloudflare Pages landing page.

---

## 2. The three decisions the issue asks us to make

### 2.1 Cache: client-side TTL, **not** a BFF

**Decision: a tiered client-side TTL cache in the fetch layer.** Not a BFF route.

Reasons, in order of weight:

1. **A BFF for twelve-x is new external network exposure, which this issue's own gate
   forbids without stopping to ask.** The obvious BFF is already in the repo:
   `apps/dashboard-api/`, a read-only Cloudflare Worker holding `SUPABASE_SERVICE_ROLE_KEY`
   in worker secrets. Its `CONTRACT.md` §7 allowlist covers 16 core tables and then says
   explicitly: *"Out of scope for this route: the twelve-x suite (separate Supabase
   project with its own session-RLS model — stays direct)."* No twelve-x table
   (`fx_research_history`, `fx_idea_eval`, `fx_consensus_eval`, `fx_trade_ideas_snapshot`)
   appears anywhere under `apps/dashboard-api/`. Extending it means the Worker holds a
   service-role connection to a **second** Supabase project with a **different RLS model**,
   and serves it publicly. That is a new service dependency and a new network exposure —
   both on the minimal gate in `AGENTS.md` and on the gate written into this issue. It also
   pushes right up against the issue's out-of-scope line on Service-role key work.
2. **The other candidate BFF is dead code.** `apps/dashboard/examples/bff-snapshots-route.example.ts`
   says so in its own header: *"REM-036 — BFF snapshot route for Node hosting (not
   compatible with `output: 'export'`)"*. Both frontends are `output: 'export'`. It cannot
   run and it is unwired. `lib/snapshot-fetch.ts` records the same fact: static export
   cannot ship App Router API routes.
3. **A client cache fixes the duplicate read for free.** Once `getBriefs(30)` and
   `getTradeIdeaArchive()` are cached, the command palette's independent copy of both
   becomes a cache hit instead of a query. Item 4 of the issue is solved as a *consequence*
   of item 6, not as a separate context refactor.

**The honest limit of this choice, stated up front:** a per-visitor client cache does
**not** reduce egress for *distinct* visitors. If anonymous traffic is mostly
first-time visitors, the cache contributes close to zero and only bounding and slimming
move the number. This is exactly why bounding and slimming are sequenced **first** (§4),
and why the Realtime wave is the one most likely to matter for anonymous traffic. The
cache is the cheap layer, not the load-bearing one.

Shape: in-memory `Map` + `sessionStorage` persistence (survives a same-tab reload, which
is the common "repeat visit" on a marketing page), schema-versioned, LRU-capped at 50
entries. TTL tiered by volatility:

| Data | TTL | Why |
|------|-----|-----|
| `fx_research_history` list, `fx_trade_ideas_snapshot` archive | 15 min | daily producer |
| `fx_consensus_snapshot` series, `fx_daily_digest`, `fx_idea_eval`, `fx_consensus_eval` | 5 min | intraday |
| `economic_calendar` window | 30 min | weekly-fed |
| `prices_live` seed + subscription | **not cached** | live by definition |

### 2.2 Realtime: keep the table path, narrow what we open, and turn it off by default on the public landing page

**Decision — three parts.**

**Server-side filtering is not available to us, and that is a finding, not an oversight.**
The obvious fix is a `filter` on the subscription. supabase-js client-side
`postgres_changes` does not carry a server-side row filter. The two routes that would give
us one are both closed:

- **Broadcast channels** — excluded on security grounds. The code documents why: the
  `postgres_changes` path on `public.prices_live` is what makes quotes unforgeable. RLS
  there has exactly one `FOR SELECT` policy and **no write policy**, so `anon` cannot author
  a row and only `service_role` can. Broadcast would mean any client could publish a price.
- **Private channels** — excluded by the database. `use-live-prices.ts` records that
  `private: true` was tried and abandoned: RLS on `realtime.messages` is unimplementable
  because the table is owned by `supabase_realtime_admin` and `CREATE POLICY` returns
  `42501`.

So there is no server-side filter available without new server code — which is the gate
again. That is the honest answer to the issue's question, and it is why the fixes below are
all about **not opening what we discard**.

**Part A — one shared socket per page, not one per consumer.** `use-live-prices.ts`
currently allocates a **per-instance** channel topic (`CHANNEL_PREFIX` + `useId()` +
`channelSeq++`). That is a deliberate workaround for #1833: `RealtimeClient.channel()`
dedupes by topic, so two consumers sharing a topic silently killed each other, and the fix
was to give every instance its own topic. The consequence was never followed through: **N
mounted consumers now mean N identical live streams**, each receiving and discarding the
same unwanted rows. Invert it — one module-level singleton subscription per page, with a
fan-out subscriber list, so N consumers mean 1 stream. The #1833 regression is fixed
properly instead of being paid for downstream.

**Part B — do not open the socket for a visitor who is not watching it.** The seed query
already delivers prices. Subscribe only after the tab has been visible and idle for a few
seconds; tear the socket down when the tab is hidden and re-open on return. A marketing
page read for 20 seconds should cost one seed query, not a live stream.

**Part C — on `digiquant-web`, default the database socket OFF.** `digiquant-web` is a
public static landing page served to unbounded anonymous traffic. It already has two
Supabase-cost-free live lanes: the keyless Coinbase websocket and the R2 market-API seed
(`lib/live/market-data.ts`, R2 via `NEXT_PUBLIC_MARKET_DATA_URL`). The database
`postgres_changes` socket is the only lane on that page that costs egress, and it is the
lane exposed to the most unvetted callers. Default it off behind
`NEXT_PUBLIC_LIVE_PRICES_SOCKET=1`, which keeps it available to the authenticated app
surface.

**Reasoning for the record:** `digiquant-web` is where unbounded anonymous traffic meets a
per-connection Supabase socket, while `apps/dashboard` reads are bounded by however many
operators load the page. Per-connection cost against anonymous traffic is the shape that
produces 6 GB, so that is where the socket comes off. The dashboard keeps its socket
because its price tiles are the product, and Part A makes it one socket per page instead of
one per consumer. And because the table path is what makes prices unforgeable, **none of
this moves anything to a broadcast channel** — the forgeability guarantee is untouched.

### 2.3 Retry: fail fast on restriction, and jitter

**Decision.** Two changes to `querySupabase` and `queryMainSupabase`:

1. **Fail fast on restriction — no retry.** Detect at the HTTP/error level: `status`
   `402` or `429`, or a message matching `quota`, `egress`, `rate limit`, `too many
   requests`. These are stable HTTP signals, not guessed PostgREST enum values. On a match,
   throw immediately instead of spending three attempts against an endpoint that is
   refusing us for billing reasons, which retrying cannot fix.
2. **Default reads to `retries: 2` with full jitter.** `delayMs * 2^attempt` becomes
   `random() * delayMs * 2^attempt`, so a thundering herd of tabs stops aligning on the
   same retry schedule.

Detection is ordered before the retry loop and the restricted flag propagates out of the
loop, so the first failure short-circuits the remaining two attempts. This ships in
**wave 1**, not wave 5: without it, every wave-1 measurement is taken while the read path
is still tripling its own failures, and the number we record would understate the fix.

---

## 3. What we will not do

- **No Supabase plan or billing change.** Board decision, and DIG-1814.
- **No Service-role key work, anywhere.** Keys stay out of issues and logs. This plan adds
  no new secret and no new secret-bearing surface — that is a direct reason the BFF is out.
- **No broadcast channel for prices.** See §2.2; it would reopen the forgeable-quote hole.
- **No write policy on `prices_live`.** Same reason.
- **No `dashboard-api` §7 widening.** See §2.1.

### Gates

Every wave in §4 is client-side TypeScript on two `output: 'export'` frontends. **No wave
introduces new external network exposure or a new service dependency, so no wave trips a
gate and nothing in this plan stops for a human gate.** `apps/dashboard` and
`apps/digiquant-web` have no gate files requiring stop-and-ask, and `digikey/` auth and
`digiquant/brokers/` are untouched.

**If Chris wants the BFF path instead**, that is a different plan: it needs its own gate
card answered before any code, and it needs the `dashboard-api` §7 contract widened to a
second Supabase project with a different RLS model. It is not a variant of this one.

Human-lock list: there is no lock-list file in the repo (`docs/agents/` has none; the only
`human lock` hit is an unrelated Olympus plan). Every file this plan touches is
frontend-only, outside `digikey/` and `digiquant/brokers/`, so no known lock applies. This
is re-checked against the EA's list before each leaf is cut.

---

## 4. Sequencing — change one thing, measure, then decide

Fixing all six at once hides which change moved the number. Six waves, each merged
separately, each with its own egress reading recorded on this issue.

| Wave | Change | Why this order | Moves the number? |
|------|--------|---------------|-------------------|
| **W0** | Measurement only, no code | No baseline means no proof. | no |
| **W1** | Briefs: slim columns, bound, de-dup, plus fail-fast-on-restriction | Highest ratio per unit of risk. Fail-fast ships with it so the measurement is not polluted by 3× retries. | **yes, most likely** |
| **W2** | Bound the remaining 13 unbounded reads | Mechanical, low risk, needs the W1 harness. | yes |
| **W3** | Client-side TTL cache — also removes the command-palette re-query | Depends on W2's bounds being sane to cache. | only for repeat visits |
| **W4** | Realtime: singleton socket, idle-gated open, off by default on `digiquant-web` | Highest ceiling against anonymous traffic. | **yes if anonymous traffic dominates** |
| **W5** | Retry: `retries: 2`, full jitter | Partially shipped in W1; finish the tuning. | only under failure |

**W1 — briefs.** The single biggest lever.
- Add `BRIEF_SUMMARY_COLUMNS` = `BRIEF_COLUMNS` minus `brief_markdown` (fetch.ts:519).
- `getBriefs()` and `getTodayBriefs()` select the summary set. `getBrief(sourceFile, runDate)`
  — the slide-over detail fetch, already `.limit(1)` — keeps the full set, so the open item
  still renders its markdown.
- Change the signature to `getBriefs({ windowDays, limit, includeMarkdown })`, defaulting
  `includeMarkdown: false`. Existing callers pass the window only.
- `.limit(200)` on every briefs read, ordered `run_date desc, broker_name asc`.
- **Remove `getMatrix`'s internal fetch.** `getMatrix()` is `assembleMatrix(await
  getBriefs(14))` (fetch.ts:989) — a second briefs fetch on a load that already calls
  `getBriefs(30)`. `assembleMatrix` is already pure and already exported, so the fix is to
  drop `getMatrix()` from the client's parallel batch and call `assembleMatrix(briefList)`
  locally in `TwelveXClient`. This is the same local-derivation pattern already used for
  `netCarriedIdeas(ideaEvalRaw)`, which is why `fx_idea_eval` is fetched once today.

Net effect on one load: **3 briefs queries → 1**, with no `brief_markdown` in it.

**W2 — bound the rest.** A `.limit()` and an explicit `.order()` on all 13 remaining
unbounded reads, from the §1.2 table. Provisional numbers, to be corrected against the
Query Advisor in W0: consensus time series `500`, calendar window `300`, event opinions
`200`, trade-idea exact-date `100`, trade-idea history `200`, trade-idea archive `500`,
idea eval `50`, consensus eval `50`, ledger `200`, and the three internal
`fx_consensus_snapshot` reads `200` each. `macro_series_observations` drops from
`limit(10000)` to `2000` — 10 000 is the outlier that looks like a placeholder.

**W3 — cache.** As §2.1. Fixes the command palette as a side effect.

**W4 — Realtime.** As §2.2.

**W5 — retry.** As §2.3.

---

## 5. Acceptance, per wave

Tests are vitest, in the existing `apps/dashboard` vitest project. There is a working
mock-and-assert pattern already in `lib/twelve-x/fetch.test.ts`: `tradeIdeasDb.limits`
records every `.limit()` and one test already asserts `expect(tradeIdeasDb.limits).toEqual([50])`.
New bound assertions extend that recorder rather than inventing a new harness.

**W1**
- Every briefs read issued by `getBriefs` and `getTodayBriefs` selects a column set that
  does **not** contain `brief_markdown`.
- `getBrief('f.pdf', '2026-10-06')` still returns a row **with** `brief_markdown` — the
  split must not empty the slide-over.
- Every briefs read carries `.limit(200)` and the two-column order.
- A restricted error (`429`, and a `quota` message) throws after **one** attempt, not three.
- A transient error still retries and still succeeds on attempt 2.
- Two backoff delays for the same failure are not always equal (jitter).

**W2**
- Each of the 13 previously-unbounded reads records a limit through the existing recorder.
- `getConsensusTimeSeries` truncates to the newest N by `run_date desc` and the assembled
  series is identical for a fixture that fits inside N.

**W3**
- A second call inside the TTL issues **zero** queries.
- A call past the TTL refetches.
- Two consumers calling `getBriefs(30)` — the twelve-x client and the command palette —
  produce **one** query, not two.
- `prices_live` is never served from cache.

**W4**
- Two mounted consumers produce **one** `channel()` call (the #1833 regression stays
  fixed, and the fan-out is one socket).
- Hidden tab closes the subscription; visible-and-idle tab opens it.
- On `digiquant-web` with the flag unset, no `prices_live` `postgres_changes` subscription
  is created, and the Coinbase lane still updates prices.
- Prices still arrive, filtered to the requested tickers.

**W5**
- A transient error retries twice then throws.
- Backoff delays are jittered.

Issue-level acceptance, on top of the waves: a reviewed spec exists before implementation
(§7); every twelve-x read has an explicit limit and brief markdown is out of list queries;
the duplicate brief fetch and the command-palette re-query are gone; Realtime is filtered
or removed from public surfaces with the reasoning recorded (§2.2); a cache sits in front
of the read path; and **the measured egress delta after W1 is recorded on this issue**.

---

## 6. Measurement — W0, and the honest gap

W0 records, before any code: the current egress figure from the Supabase usage dashboard,
and the top queries by call count and by bytes from the Query Advisor "most frequent
queries" view. The W2 limits are then corrected against the Advisor rather than against my
provisional numbers.

**Gap to state plainly:** the Query Advisor and the usage dashboard were **not reachable**
from the CTO's run on DIG-1806, and no Supabase console connection is available in the EM's
run environment either. So:

- The amplification factor in §1.1 is **counted from source** and is a duplicate-query
  count, not a byte count. It is a floor.
- Row counts per table, and which table dominates egress, are **still UNKNOWN**. W0 owns
  closing that.
- The provisional limits in §4/W2 are engineering defaults, chosen to be safe for the
  known consumer shapes (200 rows for a 30-day brief list is well above the number of
  brokers per day). W0 may lower them, and that is the expected outcome, not a surprise.

Owner for W0: **Platform**, who already hold the Supabase project relationship on DIG-1814
(the 80% usage alert). One deliverable: two screenshots and the numbers written on this
issue. If Platform cannot reach the console either, W0 becomes a question for Chris and the
W2 defaults ship as-is — the plan does not block on it.

---

## 7. Review coverage and gates on this plan

Per `docs/agents/CODE_REVIEW_POLICY.md`, lane **big** requires a Claude review through the
Consultant Manager **before** implementation, and Chris approves the spec.

- **Fresh-context agent review** of this spec — recorded in
  `docs/plans/review-DIG-1815-supabase-read-amplification.md` with reviewer, subject,
  verdict, severity counts, and file:line evidence, plus the
  `<!-- in-session-review -->` findings comment on this issue. Author session does not
  review its own diff.
- **Consultant Manager** — the lane-big Claude second opinion, routed as its own child
  issue so it runs in parallel with the spec approval rather than after it.
- **Chris approves this spec** via a `request_confirmation` on the plan document revision,
  before any implementation leaf is created.
- Every implementation leaf then needs a leaf-level review before its merge. The Code
  Reviewer agent is currently **paused**; when a leaf is ready to merge it goes to a
  reviewer who is running, or it waits. A gate is never merged past.

---

## 8. Proposed leaves — created only after spec approval

At most 5 open at a time. Every leaf: failing test committed first, explicit allowed-file
list, blockers named.

| Leaf | Wave | Owner | Allowed files | Blocked by |
|------|------|-------|---------------|------------|
| L1 Record the baseline: Query Advisor top queries + current egress | W0 | Platform | none (report on DIG-1815) | — |
| L2 Slim + bound + de-dup the briefs reads, and fail fast on restriction | W1 | AI Engineer | `apps/dashboard/lib/twelve-x/fetch.ts`, `fetch.test.ts`, `components/twelve-x/TwelveXClient.tsx` | — |
| L3 Bound the remaining 13 unbounded reads | W2 | AI Engineer | `fetch.ts`, `fetch.test.ts` | L2 |
| L4 Client-side TTL cache in the fetch layer | W3 | AI Engineer | new `lib/twelve-x/cache.ts` + test, `fetch.ts`, `command-palette.tsx` | L3 |
| L5 Realtime: singleton socket + idle gate (dashboard) | W4 | AI Engineer | `lib/hooks/use-live-prices.ts`, `.test.ts` | — |
| L6 Realtime: socket off by default on `digiquant-web` | W4 | AI Engineer | `apps/digiquant-web/lib/live/useLivePrices.ts` | — |
| L7 Retry `retries: 2` + full jitter | W5 | AI Engineer | `fetch.ts`, `fetch.test.ts` | L2 |

L1, L2, L5, L6 have no blockers and can open together — that is 4, inside the cap of 5.
L3, L4, L7 open as their blockers merge.

`command-palette.tsx` is touched only in L4, and only to drop its duplicate fetch in favour
of the cache. L2 does not restructure it, because the cache makes the duplicate disappear
on its own.

All leaves are frontend TypeScript, so they route one-hop to `develop` per
`scripts/project_routing.json` (`component:website`). `apps/dashboard-api` is not touched
by any leaf.