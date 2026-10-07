# Review: DIG-1815 spec - Supabase read amplification on the public surfaces

**Subject reviewed:** `docs/plans/DIG-1815-supabase-read-amplification.md` (published to DIG-1815 as the `plan` document, revision `cd4b4340-c08c-4038-b1d0-038cabccb0e6`)
**Reviewer:** EM agent (6f361355-e086-4a53-a913-b5811e099ab0), in-session verification pass
**Policy:** `docs/agents/CODE_REVIEW_POLICY.md`
**Lane:** big
**Date:** 2026-10-07
**Date of record note:** the EM is also the spec author, so this pass is a *self-verification* of the load-bearing factual claims, not fresh-context review coverage. Fresh-context review is the Claude second opinion, routed to the Consultant Manager as a child issue (see "Outstanding review" below). `CODE_REVIEW_POLICY.md` requires a fresh-context reviewer for `reviewed:agent`; nothing is merged on this record alone.

## Verdict

**Pass, with one scoping correction folded into the spec before publication.**

The spec's central claim - that the egress leak is duplicate, unbounded, bulk-text-carrying reads amplified by retries - survives verification against source. The three decisions (client-side TTL cache, narrowed Realtime, fail-fast-on-restriction retry) are each traceable to a constraint found in the code rather than to preference.

## Severity counts

| Severity | Count |
|----------|-------|
| Blocker | 0 |
| Major | 0 |
| Minor | 1 (folded in before publication) |
| Nit | 0 |

## Findings

### MINOR (folded in before publication) - the cache does not help anonymous first-time visitors, and the spec initially read as if it did

**Evidence:** `apps/dashboard/lib/twelve-x/fetch.ts:68` (`querySupabase`) and `:107` (`queryMainSupabase`) are the only read paths, and both are invoked from the browser; `apps/dashboard/next.config.js` sets `output: 'export'`, so there is no server cache in front of them.

**Why it matters:** a per-visitor client-side cache reduces egress only for a visitor who returns inside the TTL. If the anonymous traffic that exhausted the quota is mostly first-time visitors, the cache wave moves the number by approximately zero. That is the difference between a plan that fixes the leak and one that partly fixes it.

**Resolution:** section 2.1 of the spec now states this limit explicitly and says why bounding and slimming are sequenced first, and why the Realtime wave is the one most likely to matter for anonymous traffic. Sequencing in section 4 reflects it (W1/W2/W4 are the load-bearing waves; W3 is called "only for repeat visits").

### No blocker or major findings

No finding rises above MINOR. Specifically checked and found sound:

- **Row-limit audit (§1.2).** 23 `.from(` and 9 `.limit(` calls in `apps/dashboard/lib/twelve-x/fetch.ts`; 14 reads unbounded. The issue recorded 8 limits; 9 is the current count and the spec says so rather than silently disagreeing. Verified limit lines: 268, 298, 310, 333, 583, 681, 823, 1010, 1325.
- **`brief_markdown` has exactly one production consumer.** 12 grep hits under `apps/dashboard`; 10 are test fixtures or the type declaration (`lib/twelve-x/types.ts:179`), one is `BRIEF_COLUMNS` at `fetch.ts:521`, and the single real read is `components/twelve-x/BriefPanel.tsx:72-74`.
- **The W1 column split cannot break a render.** `BriefPanel.tsx:152` runs its own `const b = await getBrief(sourceFile, runDate);`, and `TwelveXClient.tsx:552` passes only identifiers into `<BriefPanel>`. So markdown is needed only on `getBrief`, which is already `.limit(1)` at `fetch.ts:583`.
- **BFF exclusion is grounded in an existing contract, not in opinion.** `apps/dashboard-api/CONTRACT.md` §7 allowlists 16 core tables and states the twelve-x suite is out of scope because it is a separate Supabase project with its own session-RLS model. No twelve-x table appears under `apps/dashboard-api/`. The candidate BFF at `apps/dashboard/examples/bff-snapshots-route.example.ts` states in its own header that it is incompatible with `output: 'export'`.
- **Server-side Realtime filtering is unavailable, not overlooked.** `apps/dashboard/lib/hooks/use-live-prices.ts` documents that `private: true` was tried and abandoned (RLS on `realtime.messages` is unimplementable; the table is owned by `supabase_realtime_admin` and `CREATE POLICY` returns 42501), and `apps/digiquant-web/lib/live/useLivePrices.ts` documents that the `postgres_changes` path on `public.prices_live` is what keeps prices unforgeable (one `FOR SELECT` policy, no write policy, `anon` cannot author a row). The spec therefore excludes broadcast channels on security grounds and derives its Realtime fix from what is left.
- **Duplicate-`getBriefs` count.** `getMatrix()` is `assembleMatrix(await getBriefs(14))` at `fetch.ts:989`; `TwelveXClient.tsx` also calls `getBriefs(30)`; `command-palette.tsx:36` imports `getBriefs` and `getTradeIdeaArchive` and fires both in its mount effect. Three briefs queries and two archive queries per load is what the code shows.
- **Local-derivation precedent for the de-dup fix.** `netCarriedIdeas(ideaEvalRaw)` is already applied client-side in `TwelveXClient`, which is why `fx_idea_eval` is fetched once today. The briefs de-dup follows an existing pattern rather than inventing one.
- **Gates.** Every planned file is frontend TypeScript on two `output: 'export'` surfaces. No wave adds a service dependency or a new network origin, so no gate trips. Recorded explicitly, because the issue's own gate language (new external exposure) is the thing that eliminated the BFF option.
- **Human-lock list.** No lock-list file exists in `docs/agents/`; the only "human lock" match in the repo is an unrelated Olympus plan. All planned files are outside `digikey/` and `digiquant/brokers/`. Re-checked against the EA's list before each leaf is cut.

## Outstanding review

- **Fresh-context agent review:** pending. Route: child issue to Consultant Manager (a5aebf62-2341-4abc-bfcb-363ee216d60f) for the lane-big Claude second opinion. That routing requirement comes from the **L lane** in the `digithings-operating-rules` skill and from the EM's charter, not from `CODE_REVIEW_POLICY.md` — which governs review mechanics and names no lanes or consultants. Findings append here when it lands.
- **Chris approves the spec:** pending, via `request_confirmation` on plan revision `cd4b4340-c08c-4038-b1d0-038cabccb0e6`.
- **Open measurement gap (§6):** the Supabase usage dashboard and Query Advisor were not reachable from the CTO's run on DIG-1806, and no Supabase console connection is available to the EM. Row counts and which table dominates egress are still UNKNOWN; W0 (L1, Platform) owns closing that. The §1.1 amplification factor is counted from source and is a duplicate-query floor, not a byte count.