# Olympus Architecture Audit — Step 2 (Frontend / Dashboard)

> **Scope.** Page-by-page audit of the Olympus dashboard (`frontend/olympus/`, Next.js static
> export, reads prod Supabase via anon key): is every view rendering the right data, correctly,
> and optimally for a PM to review the research/deliberation/decisions and decide whether to
> follow the book? Cross-referenced against the Step-1 persistence map (`OLYMPUS_ARCHITECTURE_AUDIT.md`).
>
> **Method.** 6-agent Sonnet fan-out, one per route group, seeded with the backend persistence
> state; every CRITICAL claim re-verified against source. Date: 2026-06-17.

---

## 1. Verdict

The dashboard is **well-engineered and uniformly fail-soft** — every query degrades to an empty
state, lots of metrics are derived client-side, and the code quality is high. But in **pure-automated
prod**, the most decision-critical surfaces are broken or empty, and they trace to **four root causes**,
not scattered bugs:

- **"Expose the portfolio" half works:** held positions, NAV chart + drawdown/rolling, theses,
  activity ledger, the digest narrative (Morning Brief), the bull/bear Deliberations strip, and the
  Research/Library all render from populated tables.
- **"What should I do today" half is invisible:** the AI's actual recommendation (Today's Actions,
  target weights, rebalance) renders empty — **not because the data is missing** (it's in `pm-rebalance`
  + `positions`) but because the frontend reads a **stale digest shape** that the current pipeline
  no longer writes.
- **Performance metrics show fake zeros:** Sharpe/vol/drawdown/alpha/P&L display literal `0.00`
  because `portfolio_metrics` is unscheduled (Step-1 gap) and the UI doesn't null-guard.
- **The "under the hood" library renders the best artifacts in degraded form:** doc-key drift sends
  the automated `pm-rebalance` and `deliberation/{ticker}` docs to the plain-markdown fallback instead
  of their structured views.

Net: a PM can see *what is held* and *read the narrative*, but currently **cannot trust the headline
metrics, cannot see the recommended trades, and sees the richest research in a downgraded view.**

---

## 2. Root causes (fix these few → most symptoms clear)

### A. Stale `DigestSnapshot` contract — the dominant issue
`getFullDashboardData` (`lib/queries.ts`) reads:
- `snapshotJson.portfolio.proposed_positions` (line ~594) — **does not exist** in the live `DigestPayload`.
- `snapshot.regime` as an **object** (lines ~535, 861) — the live payload has no `regime` object.

The live `DigestPayload` (`lib/snapshot-types.ts`) has only **string** fields `market_regime_snapshot`
and `portfolio_recommendations` (+ `actionable_summary[]`, `risk_radar[]`). So on every automated run:
`proposedPositions = []` → cascades to **empty** `rebalance_actions`, `targetWeightByTicker`,
`effectiveCurrentPositions` (falls back to actual), and the regime label falls through to the full
narrative string.

**Cascade (all one bug):**
| Surface | Symptom |
|---------|---------|
| Overview → **Today's Actions** | always "No rebalance proposed" (even when `pm-rebalance` has live actions) |
| Portfolio → **Allocations** | no target-vs-actual; `AllocationsPositionsTable` doesn't even render a Target column |
| Overview/Portfolio → **rebalance_actions** | empty everywhere |
| `StrategyThesisPanel` | "Proposed positions" + "Rebalance actions" tables permanently empty |
| Overview → **Regime Hero `<h2>`** | renders a multi-sentence paragraph at 4xl-bold (no short regime token); colors fall to neutral |

**Fix:** rebind the decision surfaces to the data that *is* published — `pipeline_observability.pm_rebalance`
(`recommended_portfolio` + `actions`, already fetched from the `pm-rebalance` document) and/or the
`positions` table's target weights. Add a short regime label to the digest (or render `digest.headline`
as the hero title and keep `market_regime_snapshot` as the body). **Highest-value frontend fix.**

### B. `portfolio_metrics` empty → fake zeros
`calculated.{sharpe,volatility,max_drawdown,alpha}` and `portfolio_pnl` default to **literal `0`**
when `portfolio_metrics` is empty (`queries.ts` ~909–921), which it always is in automated prod
(`refresh_performance_metrics.py` has no cron — Step-1 gap). The Performance tab, `server-metrics-strip`,
`advanced-stats-panel`, and the Overview P&L tile show `0.00` indistinguishable from a real flat day.
*(Overview Sharpe is safe — it's derived from `nav_history` via `computeRiskRatiosFromNavSnaps`.)*
**Fix:** schedule the refresh script (backend) **and** null-guard the UI (`server_portfolio_metrics === null` → render "—").

### C. Library / thesis doc-key drift
`resolveLibraryDocumentView` and `collectThesisRelatedDocLinks` match **old Track-B keys** that the
automated pipeline no longer writes:
- routes `rebalance-decision.json` → `RebalanceDocumentView`, but automated writes **`pm-rebalance`**
  (and `RebalanceDocumentView` reads `body.rebalance_table` while the automated payload has
  `actions`/`recommended_portfolio`) → falls back to plain markdown.
- routes `deliberation-transcript/{date}/{ticker}` → `DeliberationDocumentView`, but automated writes
  flat **`deliberation/{ticker}`** → falls back to markdown; and `collectThesisRelatedDocLinks` misses
  it entirely, so the thesis-detail "Related PM docs" never shows the bull/bear debate.

**Fix:** add the automated keys (`pm-rebalance`, `deliberation/{ticker}`) to the view resolver and the
thesis-related-doc matcher; make `RebalanceDocumentView` accept the `actions`/`recommended_portfolio` shape.

### D. Observability tabs gated/empty with no in-context explanation
Three of four tabs are bound to data that needs an operator/owner action (Step-1 gaps): **Attribution**
(`position_attribution`, no cron), **Run Health** (`atlas_run_health` view = migration 041, held),
**Position Risk** (`OLYMPUS_POSITION_RISK_FIELDS` off). All fail-soft to clean empty states — but the
nav gives no hint they're gated, so a PM reads them as "broken." **Fix:** schedule/apply the backend
pieces, and add a one-line "enabled after <X>" note to each gated EmptyState.

---

## 3. Confirmed bugs (ranked, beyond the root causes)

1. **Decision Scorecard conviction-range bug** — `decision_log.conviction` is `[-5,+5]` (backend
   `AnalystPayload.conviction_score`), but `lib/decision-scorecard.ts` documents `[0..5]` and buckets
   with `MED=2`. Sell-side calls (negative) get dumped into the "low" bucket → the conviction-calibration
   chart (the whole point of the scorecard) is wrong.
2. **No per-decision drill-down in Decision Scorecard** — `reflection` (the LLM post-mortem) and
   `thesis` are fetched (`observability-queries.ts:75`) but **never rendered**. The PM's primary tool
   to evaluate the agent's reasoning + what it learned is invisible.
3. **`documents` query hard-capped at `.limit(500)`** (`queries.ts:393`) — after ~3 months of daily
   runs, older research dates silently show "No files" while still clickable in the MiniCalendar.
4. **Regime color map covers 4 of 6 bias values** — `strong_bullish`/`strong_bearish`/`mixed` fall to
   neutral blue, so the highest-conviction days look neutral.
5. **`fetchThesisStaticParams` no dedup/limit** — as `theses` grows, `generateStaticParams` truncates
   at the PostgREST default → 404s on some `/portfolio/theses/{id}` pages in the static export.
6. **MacroSparklineRow fetched but never rendered** — `macro_series_preview` is queried on every
   Overview load (`queries.ts:803–836`) but the component isn't mounted → wasted round-trip.
7. **Portfolio → Analysis tab empty in automated prod** — it filters for Track-B artifacts
   (`market-thesis-exploration`, `thesis-vehicle-map`, `pm-allocation-memo`, `asset-recommendations`,
   `deliberation-transcript`) that the automated pipeline never writes; the automated `pm-rebalance` /
   `risk-debate` / `deliberation/{ticker}` docs (which *are* written) aren't surfaced here.
8. *(minor)* `PerformanceToPortfolioRedirectPage` lacks the Suspense boundary its siblings have;
   `NEXT_PUBLIC_OLYMPUS_VERSION` defaults to `"v0.1 · dev"` in chrome if unset; command-palette digest
   path filter checks `d.path === 'digest'`.

### ⚠️ Corrected false positive
One agent flagged **`components/library/DeltaRequestDocumentView.tsx` as a missing import (build-breaking)**.
**This is wrong — the file exists** (verified: 3,570 bytes, imported fine at `LibraryDocumentBody.tsx:6`).
Disregarded.

---

## 4. PM-UX assessment — "unravel what's under the hood"

The pipeline *does* publish the rich material (12 segment reports, the digest, per-ticker analyst docs,
`deliberation/{ticker}` bull/bear, `risk-debate`, `pm-rebalance`, evolution artifacts), and the
**Deliberations strip**, **Research**, and **Library** surfaces expose much of it. But the
"understand the system + decide" goal is only **~60% delivered** today:
- ✅ A PM can read the morning narrative, see held positions + NAV, browse research docs, and (via the
  Library) read segment reports and the bull/bear debate (in markdown).
- ❌ A PM **cannot see the recommended trades** (root cause A), **cannot trust the metrics** (B), sees
  the **best artifacts downgraded to markdown** (C), and **cannot read the agent's per-decision
  reflection/calibration** (bug #1–2). The **Analysis tab** is keyed to artifacts that don't exist (#7).

The fixes are concentrated: A + C + bugs #1–2 are pure frontend rebindings; B + D are the Step-1
backend scheduling/flag/migration items plus UI null-guards.

---

## 5. Recommended fixes (ranked)

| # | Fix | Type | Impact |
|---|-----|------|--------|
| 1 | Rebind Today's Actions / Allocations target / rebalance to `pipeline_observability.pm_rebalance` + add a short regime label | frontend | unblocks the entire decision spine |
| 2 | Null-guard metrics in the UI (show "—" not `0.00`) **and** schedule `refresh_performance_metrics` | FE + backend cron | honest performance surface |
| 3 | Add `pm-rebalance` + `deliberation/{ticker}` to `resolveLibraryDocumentView` + `collectThesisRelatedDocLinks`; widen `RebalanceDocumentView` to the `actions` shape | frontend | structured under-the-hood views |
| 4 | Fix Decision Scorecard conviction range to `[-5,+5]`; add a per-decision drill-down rendering `reflection` + `thesis` | frontend | working calibration + agent-reasoning review |
| 5 | Add "enabled after <operator action>" notes to the 3 gated observability tabs; schedule `refresh_attribution`, apply migration 041, flip `OLYMPUS_POSITION_RISK_FIELDS` | FE + backend (human gates) | observability tabs light up |
| 6 | Paginate the `documents` query past 500; init MiniCalendar to latest research month; mount or drop MacroSparklineRow; complete the regime color map | frontend | history + polish |

Items 2/5 overlap the Step-1 backend gaps — fixing the schedulers lights up both the backend tables
and the frontend tabs that read them.
