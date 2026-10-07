# Review: DIG-1815 Supabase read-amplification spec — fresh-context second opinion

**Subject reviewed:** `docs/plans/DIG-1815-supabase-read-amplification.md` and
`docs/plans/review-DIG-1815-supabase-read-amplification.md`, branch
`DIG-1815-supabase-read-amplification` at commit `c5027ec9a697281512769de9e803899ae7b5036b`.

**Reviewer:** Consultant Manager (a5aebf62-2341-4abc-bfcb-363ee216d60f), fresh context,
separate agent from the authoring EM session (6f361355-e086-4a53-a913-b5811e099ab0).

**Policy:** `docs/agents/CODE_REVIEW_POLICY.md` — notably line 53, *"Could not verify never
lowers severity. State plainly what you could not exercise, and keep the grade the mechanism
supports."* Every finding below is graded on a mechanism I read in source; where a runtime
cost is unknowable from a review run, that is said in the finding and does not lower the grade.

**Lane:** big (Claude second opinion routed through the Consultant Manager).

**Date:** 2026-10-07.

## Scope of this review, and what it does not cover

This verdict is scoped to **the repository at commit `c5027ec9a`**.

I did not, and cannot, reach production egress figures, the Supabase usage dashboard, or the
Query Advisor. No statement here should be read as a measurement of what actually consumed the
6 GB. Where the spec asserts a byte-level conclusion, this review grades the *source-level
mechanism* behind that assertion, and says so. Which table dominated egress is UNKNOWN, and
W0 (L1, Platform) is still the only thing that can answer it.

## Verdict

**rework** — of §1.1's measurement, §2.2 Part C's scope, and the §4 W1/W2 leaf instructions.
The three decisions in §2 (client-side TTL cache rather than a BFF, keep the `postgres_changes`
table path rather than broadcast, fail-fast-on-restriction retry) are sound, grounded in
constraints I verified in code, and I would keep all three unchanged.

## Severity counts

| Severity | Count |
|----------|-------|
| Blocker | 1 |
| Major | 5 |
| Minor | 4 |
| Nit | 1 |

---

## BLOCKER — W4/L6 does not touch the read surface the spec itself names as the cause

**Evidence**

- `apps/digiquant-web/lib/live/strategies.ts:60` — `fetchStrategyIndex()` is
  `supabase.from(TABLE).select("strategy_id, metrics")` with **no `.limit()`**, returning the
  full `metrics` JSONB for every strategy row. It is called from **two** landing components:
  `components/landing/MetricsOdometer.tsx:20` and `components/landing/StrategySuite.tsx:526`,
  so the identical unbounded read fires **twice per landing-page load**.
- `apps/digiquant-web/lib/live/strategies.ts:48` — `fetchTearsheet(slug)` is
  `.from(TABLE).select("metrics").eq("strategy_id", slug).maybeSingle()`, and
  `components/landing/StrategySuite.tsx:141` runs
  `Promise.all(strategyIds.map((id) => fetchTearsheet(id)))` — one full-`metrics` read per
  strategy card, on the public page.
- `apps/digiquant-web/lib/live/useLivePortfolio.ts:83` —
  `client.from("public_portfolio_positions").select(POSITION_COLUMNS)`, **no `.limit()`**;
  `:88-90` then `client.from(ACCOUNTING_NAV_VIEW).select(NAV_COLUMNS).order("date", …)` with
  **no `.limit()`**, reading the full NAV history. Mounted by
  `components/landing/DashboardPortfolioPanel.tsx:210`.
- `apps/digiquant-web/lib/live/supabaseClient.ts:21` — a second, separate browser Supabase
  client on the landing page.
- Spec §2.2 Part C and §8 L6: the scope is `NEXT_PUBLIC_LIVE_PRICES_SOCKET=1` and
  `apps/digiquant-web/lib/live/useLivePrices.ts` only. `strategies.ts`,
  `useLivePortfolio.ts`, `MetricsOdometer.tsx`, `StrategySuite.tsx` and
  `DashboardPortfolioPanel.tsx` appear nowhere in §4 or §8.

**Why it matters**

§2.2 argues, correctly, that "`digiquant-web` is where unbounded anonymous traffic meets a
per-connection Supabase socket", that "per-connection cost against anonymous traffic is the
shape that produces 6 GB", and that "that is where the socket comes off". §4 then sizes W4 as
"Highest ceiling against anonymous traffic".

On that same public landing page there are at least **four** Supabase-costing lanes, and W4 as
written switches off exactly one of them — the cheapest, because `useLivePrices` already has
two cost-free alternatives in the build (the R2 seed via `NEXT_PUBLIC_MARKET_DATA_URL` in
`lib/live/market-data.ts`, which its own header says has no Supabase fallback, and the keyless
Coinbase websocket, verified present across `app/page.tsx`, `LiveTickerRow.tsx`,
`useLivePrices.ts`, `useLivePortfolio.ts`, `quote-transforms.ts`). Turning off a lane that
already had free alternatives, while leaving three unbounded browser-credential reads on the
same page untouched, does not address the shape the spec identifies as the cause.

If anonymous landing traffic is what exhausted the quota, W4 as scoped moves the number by a
small fraction of what the plan assumes, and the quota re-breaches on 22 October. That is the
"coherent and wrong" failure mode this review was commissioned to look for. I cannot confirm
that anonymous landing traffic *is* the dominant source — that is W0's job and it is UNKNOWN —
but the plan cannot simultaneously argue that this page is the cause and plan a fix that
covers a quarter of it.

**What I would change**

- Extend W4 to cover the landing page's reads, not just its socket. Add a leaf (L8) bounding
  `strategies.ts` and `useLivePortfolio.ts`: a `.limit()` and explicit `.order()` on
  `fetchStrategyIndex`, a single fetch in `StrategySuite` reused by `MetricsOdometer` (the
  same local-derivation / shared-result pattern the spec already uses for `netCarriedIdeas`),
  a per-slug cap or batched read for `fetchTearsheet`, and a date-bounded `.gte('date', …)` on
  the NAV view. All frontend TypeScript under `apps/digiquant-web/`; no new origin, no key, no
  broadcast, no write policy — it stays inside every hard constraint on the card.
- Correct §2.2's reasoning so it names the four lanes, not one, and restate §4's "highest
  ceiling" claim against the corrected scope.
- Note for the leaf: `lib/live/strategies.ts` has **no test file** today (the directory ships
  `market-data.test.ts`, `nav-seam.test.ts`, `quote-transforms.test.ts` only), so this leaf
  needs a harness built from scratch rather than extended.

---

## MAJOR — §4/W2's `getConsensusTimeSeries` limit would silently ship a stale Consensus tab

**Evidence**

- `apps/dashboard/lib/twelve-x/fetch.ts:166-183` — `getConsensusTimeSeries` reads
  `fx_consensus_snapshot`, `.eq('weighted', true)`, `.eq('timeframe', timeframe)`, 17 columns,
  **no `.limit()`**, ordered `.order('run_date', { ascending: true })` then
  `.order('currency', { ascending: true })`. Unbounded across every `run_date` in the table.
- Spec §4/W2: "consensus time series `500`" — no mention of changing the order.
- `apps/dashboard/lib/twelve-x/fetch.ts:191-215` — `computeConsensusDeltaSet` walks the array
  **backwards** (`for (let i = series.length - 1; i >= 0; i--)`) under the comment
  `// Distinct run_dates present, newest-first (series is oldest→newest)`. It is
  array-order dependent.
- `apps/dashboard/lib/twelve-x/consensus-derive.ts:20-45` — `selectLatestCompleteConsensus`
  groups by `run_date` into a Map and sorts `[...byDate.keys()].sort((a, b) => b.localeCompare(a))`,
  i.e. newest-first, and is therefore **order-insensitive** with respect to the input array.

**Why it matters**

Adding `.limit(500)` to a query ordered `run_date` **ascending** returns the **oldest** 500
rows and discards every recent run_date. `selectLatestCompleteConsensus` re-sorts and returns
the newest *complete* run present in the payload — so the tab does not crash, it renders the
newest run that survived truncation. At roughly ten G10 currencies per run_date, 500 rows is
about 50 run_dates; past that horizon the Consensus tab shows stale data presented as current,
and `computeConsensusDeltaSet` computes run-over-run deltas from a truncated set.

The spec **contradicts itself** here: §5's W2 acceptance bullet says "`getConsensusTimeSeries`
truncates to the newest N by `run_date desc`", which is correct, while §4/W2's number list
implies an unchanged order. A leaf implementer cutting L3 from §4's list ships the bug; only
the acceptance test stands between the plan and the defect.

Beyond this one query, it shows §4's twelve provisional numbers were chosen without reading
each query's order semantics. Per `CODE_REVIEW_POLICY.md` line 53 I cannot verify the row counts
that would tell me whether the *other* eleven limits truncate away rows a render needs — so I
keep the severity the mechanism supports and require each limit be justified against its
consumer, not against a round number.

**What I would change**

In §4/W2, replace the bare number with the order change: order `run_date` descending,
`.limit(500)`, and reverse client-side before `computeConsensusDeltaSet` — or, cleaner, filter
with `.gte('run_date', …)` on a date window and keep the ascending order both consumers already
assume. Whichever is chosen, §5 must pin the `// series is oldest→newest` contract in
`computeConsensusDeltaSet` as part of the same leaf, and add an acceptance bullet asserting the
newest run_date survives the bound. And make each of the remaining eleven numbers name the
consumer that constrains it.

---

## MAJOR — "21 failing requests per load" is low by roughly 3x; §1.1 omits most of the load

**Evidence** — the mount effect is `apps/dashboard/components/twelve-x/TwelveXClient.tsx:318`,
deps `[configured]`, and it issues three sequential waves, not one:

| Wave | Call site | Top-level fetches | Actual HTTP queries |
|------|-----------|------------------|---------------------|
| A | `TwelveXClient.tsx:330-343` | 9 | **10** |
| B | `TwelveXClient.tsx:348-351` | 2 | **4** |
| C | `TwelveXClient.tsx:353-361` | 5 | **7** |

- Wave A is 9 calls but **10 queries**: `getIntelligence()` (`fetch.ts:320`) calls
  `getLatestConfluenceDate()` (`fetch.ts:304`) first, so `fx_confluence_snapshot` is read twice.
- Wave B: `getEventOpinions` (`fetch.ts:499`) is 1 query; `getIntelligenceWhy` (`fetch.ts:1164`)
  is a `Promise.all` of `getIntelligence(date, limit)`, a direct `fx_consensus_snapshot` read
  (`fetch.ts:1178`), and `getLedger(date)` (`fetch.ts:1024`, one query because `runDate` is
  supplied) — 3 queries. The same `getIntelligence` confluence read therefore happens a
  **third** time on the load.
- Wave C: `getTradeIdeas` (`fetch.ts:662`) 1, `getTradeIdeaHistory` (`fetch.ts:701`) 1,
  `getTodayBriefs` (`fetch.ts:839`) 1, `getTodayEvents` (`fetch.ts:871`) 1, and
  `getConsensusDivergence` (`fetch.ts:1294`) is a `Promise.all` of **three** reads —
  `fx_consensus_snapshot` (`:1303`), `fx_smart_bias` (`:1313`), `fx_market_snapshots` (`:1320`).

Duplicates §1.1's table never lists:

- **`economic_calendar` read twice per load** — `getUpcomingEvents` (`fetch.ts:483`, wave A) and
  `getTodayEvents` (`fetch.ts:871`, wave C) both call `fetchCalendarWindow`
  (`fetch.ts:454`), which issues the *same* padded-window `economic_calendar` read at
  `fetch.ts:464`. §1.2 lists line 464 as one unbounded read; §1.1 counts zero.
- **`getTodayBriefs` as a fourth briefs-bearing read** — `fetch.ts:845` selects
  `BRIEF_COLUMNS`, which includes `brief_markdown` (`fetch.ts:521`). §1.2's audit table knows
  about line 845; §1.1's amplification table does not count it.
- **`fx_confluence_snapshot` three times** (two inside `getIntelligence`, one inside
  `getIntelligenceWhy`), and `fx_smart_bias` / `fx_market_snapshots` once each.

**Why it matters**

§1.1 says seven queries, "21 failing requests per load, per tab, per refresh". Source gives
**21 queries per load from `TwelveXClient` alone**, before the command palette and before
Realtime. Under restriction — the state the spec opens by describing — that is roughly **63
failing requests per load**, not 21.

The count being ~3x low does not by itself break the plan; every wave's direction survives. It
does break the *attribution*: §4 orders waves by "moves the number", and §6 says W0 exists to
correct the provisional figures. A baseline that is 3x low will make W1's post-change reading
look like a larger win than it is, and will make any wave that underperforms look like it
failed when it merely did less than the table implied.

**What I would change**

Rewrite §1.1 as a per-load table built the way the above one is built: top-level call → internal
query count → duplicated statement where one exists. State 21 queries and ~63 failing requests
from `TwelveXClient` on its own, add the palette's two where the invitee gate is met (§ MAJOR
below), and drop the rhetorical claim in §1.1's closing sentence about queries 1–4 (see next
finding).

---

## MAJOR — "That is the whole story of the 6 GB" is unsupported, and misses the largest read on the load

**Evidence**

- Spec §1.1, closing: *"Queries 1–4 are the same four statements firing two or three times.
  That is the whole story of the 6 GB."*
- Spec §6, three paragraphs later: *"Row counts per table, and which table dominates egress,
  are **still UNKNOWN**."*
- `apps/dashboard/lib/twelve-x/fetch.ts:166` — `getConsensusTimeSeries` reads
  `fx_consensus_snapshot` with **no `.limit()`**, no date bound, 17 columns, spanning every
  `run_date` ever recorded. It has **no duplicate anywhere**: grep for callers returns only
  `TwelveXClient.tsx:335`. It does not appear in §1.1's amplification table at all.

**Why it matters**

A duplicate-*count* floor cannot establish which statements caused a byte total. §1.1 says it
is a floor, not a byte count — and then draws a byte-causal conclusion from it, which contradicts
§6's own admission that the dominant table is UNKNOWN.

My own source walk points the other way. The single largest unbounded read on a load is
`getConsensusTimeSeries`: unbounded by row count, unbounded by date, 17 columns, no duplicate to
remove. W2 is the only wave that touches it. The spec's §1.1 narrative assigns the entire
incident to duplicated markdown-bearing briefs queries and calls W1 "the single biggest lever",
which means the wave most likely to be the actual lever is sequenced second and labelled
"mechanical, low risk".

**What I would change**

Delete the causal sentence from §1.1 and replace it with the honest form: four statements are
duplicated across a load; one further statement is unbounded by row and date; row counts are
UNKNOWN and byte attribution waits on W0. Re-rank §4's "Moves the number?" column on that
basis, and make `getConsensusTimeSeries` a named first-class item in W2 rather than one number
in a list of thirteen.

---

## MAJOR — W1's `getMatrix` de-dup silently widens the Matrix window from 14 days to 30

**Evidence**

- `apps/dashboard/lib/twelve-x/fetch.ts:989-992` — `getMatrix(windowDays = 14)` is
  `assembleMatrix(await getBriefs(windowDays))`.
- `apps/dashboard/lib/twelve-x/fetch.ts:904` — `assembleMatrix(briefs)` applies **no window of
  its own**. It folds every brief's `currency_views` into a per-`(broker, column)` candidate
  list, dedupes by `(source_file, run_date)`, sorts newest-first, and splits primary + history.
  The window is applied solely by `getBriefs`' `.gte('run_date', start)` at `fetch.ts:557`.
- Spec §4/W1: *"Remove `getMatrix`'s internal fetch … drop `getMatrix()` from the client's
  parallel batch and call `assembleMatrix(briefList)` locally in `TwelveXClient`"*, where
  `briefList` is the payload already fetched as `getBriefs(30)` (`TwelveXClient.tsx:339`).

**Why it matters**

The matrix input silently changes from a 14-day window to a 30-day window. Because
`assembleMatrix` takes the newest view per `(broker, column)`, cells whose newest view is
between 15 and 30 days old start rendering where they previously did not. That is a visible
change to a rendered surface (the Matrix tab), introduced by a wave described as a pure
de-duplication, with no acceptance bullet that would catch it.

The de-dup itself is right, and the precedent the spec cites is real: `netCarriedIdeas(ideaEvalRaw)`
is already applied client-side at `TwelveXClient.tsx:345`, which is why `fx_idea_eval` is fetched
once today. Only the window needs preserving.

**What I would change**

In §4/W1, specify the window explicitly: either slice the 30-day payload to the last 14 days
before calling `assembleMatrix`, or pass `windowDays` through and filter on `run_date` locally.
Add a W1 acceptance bullet: *"the assembled matrix for a fixture containing a view 20 days old
is identical to today's `getMatrix(14)` output."* And correct the net-effect arithmetic in the
same paragraph — see the next finding.

---

## MAJOR — the command-palette duplicate is gated, so §1.1 over-counts for paying tiers

**Evidence**

- `apps/dashboard/components/command-palette.tsx:329-334` — the FX effect opens
  `if (!fxHubOnlyInvitee) return;` before `Promise.all([getBriefs(30), getTradeIdeaArchive()])`.
- `apps/dashboard/lib/fx-hub-only.ts:46-49` — `fxHubOnlyInvitee: canFxHub &&
  effectivePlanTier === 'free'`, i.e. an `fx_hub`-granted invitee on the **free** tier only.
- `apps/dashboard/components/app-frame.tsx:7,28,39` — `<CommandPalette />` "stays mounted in
  every case", on every dashboard route.
- Spec §1.1 row 3 and row 4 count the palette's `getBriefs(30)` and `getTradeIdeaArchive()`
  unconditionally as part of "one dashboard FX Hub page load".

**Why it matters**

Two errors in opposite directions. For paying tiers and for anyone without the `fx_hub` grant,
§1.1's rows 3 and 4 do not fire on `/twelve-x` at all — the table over-counts. For the free-tier
`fx_hub` invitees they do fire, but the palette is mounted on **every** dashboard route, not
only `/twelve-x`, so for that cohort the duplicate is a **per-navigation** cost across the whole
app rather than a per-`/twelve-x`-load cost. The spec's frame — "TwelveXClient mount plus the
command palette mount", as if both describe one page load — is wrong in both directions, and it
is the frame W3's "fixes the command palette as a side effect" and §8 L4's allowed-files list
are built on.

This also sharpens the MAJOR above on the wave count: §4/W1 claims "**3 briefs queries → 1**".
`getTodayBriefs(canonical)` at `fetch.ts:845` filters `.eq('run_date', canonical)`, a different
predicate from `getBriefs(30)`'s `.gte('run_date', start)`, so it cannot be folded into the
windowed list. The honest arithmetic is **3 → 2**.

**What I would change**

State §1.1's rows 3–4 as conditional on the invitee gate, with the file:line evidence, and add
a sentence that the palette's cost applies to every dashboard route for that cohort. Correct
W1's net effect to 3 → 2 and say why `getTodayBriefs` stays. In §8 L4, name
`command-palette.tsx` as touched to consume the cache, which the spec already does — but state
that the duplication it removes is cohort-limited, so W3's value is bounded accordingly.

---

## MINOR — `getTradeIdeas`'s fallback leg is the one that fires during the incident, and W2 does not bound it

**Evidence**

- `apps/dashboard/lib/twelve-x/fetch.ts:662-692` — `getTradeIdeas(runDate)` issues the
  exact-date leg (`fetch.ts:667`, **no `.limit()`**) and, **only if that returns empty**,
  immediately issues the carried-episode fallback (`fetch.ts:677`,
  `.lte('run_date', runDate).order('as_of', {ascending:false}).limit(CARRIED_BOARD_OVERFETCH)`).
- `apps/dashboard/lib/twelve-x/fetch.ts:618` — `CARRIED_BOARD_OVERFETCH = 50`.
- Spec §4/W2 bounds "trade-idea exact-date `100`" and does not mention the fallback leg.

**Why it matters**

Under quota restriction every query errors, so the first leg returns empty and the fallback
runs **on every load**. `fx_trade_ideas_snapshot` therefore costs 6 attempts per load from this
one caller (3 for each leg), not 3 — exactly when egress matters least and the incident is in
progress. W2 bounds the leg that does *not* run under restriction and leaves the one that does
outside its stated scope.

**What I would change**

Add the fallback leg to §4/W2's list explicitly (it already carries `limit(50)`, so the change
is to state that it is reviewed and kept, and to note that the two legs together are 6 attempts
under restriction). Worth a §5 bullet: *"a restricted `getTradeIdeas` throws after the
exact-date attempt without issuing the fallback."*

---

## MINOR — Part A's upside on the dashboard is one socket, not a per-page-load multiplier

**Evidence**

- `apps/dashboard/lib/hooks/use-live-prices.ts` — consumers are exactly two:
  `apps/dashboard/components/portfolio/AllocationsPositionsTable.tsx:69` and
  `apps/dashboard/lib/hooks/use-live-brief-kpis.ts:66` (plus a mock in
  `AllocationsPositionsTable.test.tsx:16`). The per-instance topic
  (`CHANNEL_PREFIX` + `useId()` + module `channelSeq++`) is documented in the file header as the
  deliberate #1833 workaround for `RealtimeClient.channel()` deduping by topic and silently
  unsubscribing both consumers.
- On `apps/digiquant-web` the N is real: `components/landing/LiveTickerRow.tsx:95` and
  `lib/live/useLivePortfolio.ts:138` both mount `useLivePrices`.
- Spec §2.2 Part A claims "**N mounted consumers now mean N identical live streams**" as a
  consequence worth inverting, and sizes W4 as "Highest ceiling against anonymous traffic".

**Why it matters**

On the dashboard N is currently 2, and the two consumers are on different surfaces, so at best
one socket is saved when both happen to mount together. Part A is still worth doing — it removes
a fragile workaround and fixes #1833 properly rather than paying for it downstream — but it is
not the per-page-load egress lever the wave table implies. On `digiquant-web`, where N is real,
Part A is worth more, and L6 does not include it.

**What I would change**

Keep Part A. Restate its expected effect as "one socket per page on the dashboard (N=2 today)
and one per page on the landing page (N=2 today)", and fold the `digiquant-web` half of Part A
into L6's file list alongside the flag change.

---

## MINOR — the broadcast-exclusion argument is a post-hoc rationale, not a forward-looking security finding

**Evidence**

- `apps/digiquant-web/lib/live/useLivePrices.ts` header — documents that a **retired** broadcast
  channel (`prices:live`) "was forgeable: broadcast messages are client-authored, delivery is a
  bare INSERT into…", that `public.prices_live` has RLS enabled with exactly one `FOR SELECT`
  policy and **no write policy**, that `anon` cannot author a row, and that
  `postgres_changes` events are replayed from the WAL. It also records `private: true` as
  unimplementable (RLS on `realtime.messages` owned by `supabase_realtime_admin`;
  `CREATE POLICY` returns 42501).
- Spec §2.2 presents these as the security grounds on which broadcast is excluded for *this
  plan*.

**Why it matters**

Every factual claim checks out — the RLS shape, the 42501, the WAL replay. But the comment
documents why the *previous* implementation was replaced, which is an argument for keeping the
current path, not proof that broadcast must be excluded from every future design. The spec
reframes a changelog entry as a standing security constraint.

Under this card's own hard constraint ("no broadcast channel and no write policy on
`prices_live`") the outcome is identical, so this is a framing correction, not a decision change.

**What I would change**

In §2.2, attribute the broadcast exclusion to its source — the retired-channel incident
recorded in `useLivePrices.ts`'s header — and state the standing invariant separately: the
`postgres_changes` table path is what makes quotes unforgeable, because `anon` holds no write
grant on `prices_live`. That is accurate, and it is a stronger argument than the current framing
because it says what must stay true rather than what was once tried.

---

## MINOR — `next.config.js` does not exist

**Evidence**

- Spec §2.1 and the EM self-verification record both cite `apps/dashboard/next.config.js` as
  evidence for `output: 'export'`.
- The file is `apps/dashboard/next.config.mjs`; `output: 'export'` is at line 5.

**Why it matters**

The claim is true and the file is one character away. It matters only because §2.1's *first*
reason for rejecting the BFF — the one that opens the decision — cites this file, and a leaf
implementer sent to read `next.config.js` will not find it and may conclude the evidence is
missing. `apps/dashboard/examples/bff-snapshots-route.example.ts:1-6` and
`apps/dashboard-api/CONTRACT.md` §7 both check out as quoted, so nothing else in that section
moves.

**What I would change**

Fix the path to `apps/dashboard/next.config.mjs` in the spec and the review record.

---

## NIT — `BRIEF_COLUMNS` line number

The spec §4/W1 and the EM record cite `BRIEF_COLUMNS` at `fetch.ts:519` and
`fetch.ts:521` respectively for the same thing. The declaration starts at line 519 and
`brief_markdown` appears on line 521. Both are defensible; W1 should cite the declaration line
(519) and note the column at 521.

---

## Answers to the five questions asked

**1. Does the client-side TTL cache actually reduce egress, and is the wave sequencing honest?**

Partly. §2.1 states the first-visit limit plainly, and §4 marks W3 "only for repeat visits" — that
part is honest. W1 and W2 are per-load reductions and *do* help first-time visitors, so the plan
is not quietly resting on the cache.

What it does rest on is the socket. §2.2 and §4 both argue that anonymous traffic on
`digiquant-web` is what produced the 6 GB, and then W4 — the only wave aimed at that surface —
covers one of that page's four Supabase-costing lanes, and covers the one that already had two
cost-free alternatives in the build. That is the BLOCKER. Once W4 is scoped to the landing
page's reads, the sequencing is honest.

**2. Is the "21 failed requests per load" claim right?**

No. Source gives 21 queries per load from `TwelveXClient` alone (wave A = 10, wave B = 4,
wave C = 7), plus the palette's two for eligible invitees. Under restriction that is roughly
**63 failing requests per load**, not 21 — a ~3x understatement. Detail in the MAJOR above.

**3. Is there a bigger leak outside `fetch.ts` that scales with traffic?**

Yes, three lanes, all verified in source, none in the wave list:

- `apps/digiquant-web/lib/live/strategies.ts:48,60` — `fetchStrategyIndex()` unbounded, full
  `metrics` JSONB, fired **twice** per landing load from two components; plus
  `fetchTearsheet()` once per strategy card.
- `apps/digiquant-web/lib/live/useLivePortfolio.ts:83,88` — `public_portfolio_positions`
  unbounded, plus a full-history NAV read, on the public landing page.
- `apps/dashboard/lib/queries.ts` — **40** `.from(` calls, mounted on every dashboard route
  (`lib/dashboard-context.tsx:50` → `lib/auth-gate.tsx:61` → `app/layout.tsx:64`). These execute
  through `apiDb`, a PostgREST-shaped builder that hits `GET /v1/tables/:table` on the
  `dashboard-api` Worker, which holds a service-role key — so they are **not** free, they are
  service-role reads of the core project rather than browser-credential reads. And
  `apps/dashboard-api/src` contains no `Cache-Control`, ETag or `caches.` usage anywhere, so
  that payload is re-read from Supabase on every dashboard session. §1.1 never mentions this
  lane at all.

Which of these actually dominated the 6 GB is UNKNOWN and is W0's job. I am reporting the
mechanism, not a byte attribution.

**4. Is the Realtime conclusion right, including the security argument for excluding broadcast?**

The conclusion is right; two supporting claims need narrowing. Server-side filtering genuinely
is unavailable — the `private: true` 42501 finding is documented in the code and I read it. Part
C (socket off by default on the landing page) is right in direction and wrongly scoped (BLOCKER).
Part A is sound but worth one socket on the dashboard, not N (MINOR). The broadcast-exclusion
security argument is accurately quoted but is post-hoc (MINOR) — the conclusion holds, the
framing should change.

**5. Will the wave 1 column split break a render?**

No. `brief_markdown` has exactly one production read — `BriefPanel.tsx:72,74` — and `BriefPanel`
resolves its own row with `getBrief(sourceFile, runDate)`, already `.limit(1)` at
`fetch.ts:583`. Every other consumer of the list payloads reads summary columns only:
`command-palette.tsx:200-233` (`broker_name`, `document_title`, `source_file`, `run_date`,
`title`, `pair`, `direction`), `BriefsIndex.tsx:11-25` with `sortTodayBriefs` (`fetch.ts:595`,
ranking on `trader_relevance` and `currency_views` breadth, both in the summary set), and
`CurrencyDrilldownPanel.tsx:161-172` (`broker_name`, `central_thesis`, `source_file`, opening
the panel by key).

Two things W1 must still get right: `getTodayBriefs` must move to the summary column set (it
reads `BRIEF_COLUMNS` at `fetch.ts:846` — the spec says so, and it is necessary), and the
de-dup's window must be preserved (MAJOR above).

---

## What I verified as sound, so the reader knows what I did not re-litigate

- **The BFF exclusion (§2.1) is correct on all three grounds.** `apps/dashboard-api/CONTRACT.md`
  §7 does state the twelve-x suite is out of scope; no twelve-x table appears under
  `apps/dashboard-api/`; and `apps/dashboard/examples/bff-snapshots-route.example.ts` does
  declare itself incompatible with `output: 'export'`. Extending the Worker to a second Supabase
  project with a different RLS model, served publicly, would genuinely be new external exposure
  and would press against the service-role gate. I would keep this decision exactly as it stands.
- **§1.2's row-limit audit is accurate.** 23 `.from(` and 9 `.limit(` in `fetch.ts`; limits at
  lines 268, 298, 310, 333, 583, 681, 823, 1010, 1325; 14 reads unbounded. The spec's own
  correction from 8 to 9 is honest.
- **§1.3's retry description is exact.** `querySupabase` (`fetch.ts:68`) and
  `queryMainSupabase` (`fetch.ts:107`) both default `retries = 3, delayMs = 500`, loop
  `attempt < retries`, `if (error) throw error`, inspect nothing before retrying, and back off
  `delayMs * Math.pow(2, attempt)` with no jitter before `throw lastError`.
- **§2.3's decision is right, and shipping it in W1 rather than W5 is the right call.** Detection
  at the HTTP/error level before the loop is stable and cheap; a plan that measures every wave
  through a 3× retry multiplier is measuring its own harness.
- **§5's test-harness claim is true.** `fetch.test.ts:47` declares `limits: []`, line 94 records
  every `.limit()`, line 223 resets it, and line 280 asserts
  `expect(tradeIdeasDb.limits).toEqual([50])` against `CARRIED_BOARD_OVERFETCH = 50`
  (`fetch.ts:618`). Extending that recorder is the right call.
- **§1.4 is accurate.** Both `use-live-prices.ts` and `digiquant-web/lib/live/useLivePrices.ts`
  subscribe with `event: "*"`, no server-side filter, and a per-instance `useId()` topic. The
  keyless Coinbase websocket lane is real, and the R2 seed lane is real and already in the build.
- **§7's review-mechanics claims hold.** `docs/agents/CODE_REVIEW_POLICY.md` is 68 lines and
  names no lanes and no consultants; the lane-big requirement comes from the operating-rules
  skill and the EM's charter, as §7 states after correcting an earlier draft of itself. That
  self-correction is the right one.
- **The three decisions in §2 are all traceable to constraints I verified in code**, which is
  the standard §2.1 says it is meeting. That is why this review is `rework` on sequencing and
  measurement, not on direction.
