# Olympus dashboard — ground-up redesign

**Date:** 2026-06-23
**Status:** Design approved (Sections 1–3 confirmed by user; 4–6 delegated to author's judgment)
**Author:** Claude (with Chris Stefan)
**Supersedes:** the P0 token-unification pass (2026-06-22) — which this builds on, not replaces.

## Why

The Olympus dashboard sprawls across **12 routes and ~17 sub-tabs**, and the signal
is buried. Even the landing page stacks **eleven co-equal panels** (regime hero,
4-KPI strip, Today's Actions, Morning Brief, held prices, benchmark blurb,
positions+pulse, deliberations, decision trail, thesis table, footer). The data
underneath is rich and correct — the failure is information architecture and
visual hierarchy, not the pipeline or the data layer.

This redesign reconceives the **visible product** from first principles while
reusing the **invisible, tested plumbing** (Supabase data layer, snapshot
parsing, markdown rendering, NAV/risk math, conviction scorecard).

## Foundational decisions (locked)

1. **Primary viewer: the portfolio owner** — someone following this portfolio as
   if it were theirs. Wants *today's decision*, *how am I doing*, and *why*.
   Decision-as-instruction. Operator surfaces collapse into a single demoted
   "system health" footnote.
2. **Home anchor: lead with the move** — today's action is the hero; NAV +
   vs-benchmark ride underneath as a status line; the regime read frames it. On a
   no-action day the hero reads "Holding — no changes" with the one-line reason,
   so it is never empty.
3. **Build strategy: reconceive on the tested core** — new IA, app shell, home,
   and page hierarchies designed fresh; reuse the data/render layer and recompose
   the panels that already work. The visible product is 100% new; the plumbing is
   reused. Keeps the P0 token work.

## Governing principle: three levels of depth

*glance → why → full.* Today answers "what's happening and how am I doing" at a
glance; one tap reveals the reasoning inline; the deep surfaces hold the full
record. Nothing the owner needs daily is more than one tap from Today.

## Section 1 — Information architecture

**12 routes / ~17 tabs → 4 destinations + Settings.**

| Destination | Route | Absorbs | Sub-views |
|---|---|---|---|
| **Today** | `/` | `/strategy`, the 11-panel overview | (single page, move-led) |
| **Portfolio** ("the book") | `/portfolio` | `/portfolio`, `/portfolio/theses`, `/performance` (`/strategy` splits: regime→Today, theses→here) | Holdings · Theses · Performance |
| **Why** ("the reasoning") | `/why` | `/research`, `/library`, today's digest + deliberations | The read · Deliberations · Documents |
| **System** (demoted) | `/system` | `/observability`, `/architecture` | Run health · How Olympus works |
| Settings | `/settings` | — | (utility gear) |

- **Nav label "Why"** (the owner's literal question); "Research" is the
  conservative fallback.
- **Twelve-X** (`/twelve-x`, orphaned 6-tab FX suite): **cut from the owner nav.**
  It is a separate product surface, not part of the book.

## Section 2 — The Today page

One job: *the decision, and how I'm doing.* Strict hierarchy — **the move is the
only element at full visual weight; everything else is a quiet, scannable summary
that doubles as a doorway to depth.**

Top to bottom:

1. **Regime ribbon** (quiet) — regime label · as-of date · run-type badge.
   `strategy.regime_label`, `portfolio.meta.last_updated`, `latest_snapshot_run_type`.
2. **THE MOVE** (hero) — `TODAY · N changes`, each action a bold tappable row
   (`TRIM NVDA −2pp "reason"`). HOLD day → `TODAY · Holding` + one-line reason +
   "why we're standing pat →". Source: `rebalance_actions` + `rationaleByTicker`
   (from `pm_rebalance`).
3. **NAV status line** — `NAV 104.2 · +0.3% today · +4.2% vs SPY since {date}`.
   `portfolio.snapshots`, `metrics`, benchmark blurb fn.
4. **Why today** (disclosure level 2, inline) — net stance + conviction + PM memo
   summary; "full debate →" into Why. `deliberations`, `pm_allocation_memo`.
5. **How I'm doing** — compact NAV curve vs SPY + excess/Sharpe; "Performance →".
6. **The read** — regime one-liner + `actionable_summary` + `risk_radar`; "full →".
7. **Holdings** summary — top positions w/ weight+delta; "View all →".
8. **Theses** summary — status dots; "Tracker →".

**Disclosure ladder:** L1 = move + NAV (no interaction); L2 = tap action / "why
today" → reasoning expands inline on Today; L3 = "→" links into Why / Portfolio.

**Mobile:** single column, same order; two-up summary pairs stack; move stays
hero; 4 destinations in the bottom app bar.

Net: Today drops from ~11 competing cards to **one hero + four quiet summaries**.

## Section 3 — The two deep surfaces

Both ordered **synthesized → raw**; the owner drops only as deep as the question needs.

### Portfolio — *the book* (`/portfolio`): Holdings · Theses · Performance

- **Holdings** (default) — full positions table (ticker, weight, Δweight, the
  thesis it serves, contribution to NAV). Row → per-position drilldown: entry,
  weight history, contribution curve, thesis, research links, event log. Reuses
  `position-drilldown`, `position-events`, `position-contribution-series`,
  `position-first-entry`, `portfolio-research-links`.
- **Theses** — tracker (claim, vehicle, status: confirmed/monitor/invalid) with
  expressing positions. → `/portfolio/theses/[id]` (claim, evidence for/against,
  vehicles, status history). Reuses `[thesisId]` page + `thesis-pipeline-snapshot`.
- **Performance** — NAV curve (windows), vs benchmark, drawdown, Sharpe/vol
  (`performance-series`, `portfolio-risk-metrics`) **+ Decision quality**: the
  conviction scorecard (`decision-scorecard`) — "high-conviction calls returned
  +X% vs low +Y% — calibrated ✓". Moved here from Observability; it is the
  strongest trust signal and belongs where the owner asks "how am I doing".

### Why — *the reasoning* (`/why`): The read · Deliberations · Documents

- **The read** (default) — the full digest, structured not as 11 equal walls:
  lead with regime + actionable + risk radar, deeper sections expandable.
  `segment_freshness` badges mark today vs baseline. Reuses
  `render-digest-from-snapshot` + `SafeMarkdown`.
- **Deliberations** — bull/bear debates, risk debate, PM memo (net stance +
  conviction); today's decisions sort to top. Reuses `render-pipeline-payloads`.
- **Documents** — raw research library, categorized/filterable by segment/date/tier.
  Absorbs `/library`. `research-doc-categorize`, `library-doc-tier`,
  `research-manifest`.

### Connective tissue — theses are the join

```
Documents ──synthesized──▶ The read ──argued──▶ Deliberations
 (raw research)            (the digest)         (bull/bear)
                                                     │
                                                crystallized
                                                     ▼
Today's move ◀──adjusts── Holdings ◀──expressed── Theses
 (the decision)           (what I own)            (what I believe)
```

Every drill-down link respects this chain both directions: holding → thesis →
research+debate; today's move → its debate → evidence. "What I own → why → proof"
is one continuous path.

## Section 4 — System, Settings, nav shell

- **System (`/system`)** — quiet operator footnote. **Run health** (last run
  status/time, freshness; `atlas_run_diagnostics`, `snapshot-staleness`) + **How
  Olympus works** (P0-rewritten architecture explainer). Muted, bottom of nav.
  **Cut:** operator-only deep panels (per-phase costs, routing internals,
  run-by-run tables) → drop or hide behind a "diagnostics" expander.
- **Settings (`/settings`)** — unchanged scope; gear, not a primary tab. Reuses
  `settings-content`.
- **Nav shell** — desktop slim left sidebar (4 primaries; System pinned bottom +
  muted; Settings gear); mobile bottom app bar (4 destinations); ⌘K command
  palette kept as the power path (destination/ticker/thesis) with a subtle Today
  hint. Reuses `sidebar`, `mobile-app-bar`, `subpage-tab-bar`, `command-palette`.

## Section 5 — Visual language

Built on the digiquant.io tokens already wired in P0 (`[data-theme]` dark+light,
Instrument Serif display, Geist body/mono, cyan-phosphor accent). Spend boldness
in exactly one place:

- **The one bold thing is the move** — "TODAY" in Instrument Serif at display
  size; action verbs (TRIM/ADD/SELL/HOLD) in heavy mono; regime accent washes
  *only* this block. Everything else quiet: hairline cards, muted labels, space.
- **Color = meaning** — accent is the brand thread; `--up`/`--down` for
  direction; regime tint localized to the hero (remove the current full-page
  ambient wash). Verbs colored by direction; HOLD muted.
- **Type carries hierarchy** so we lean less on boxes: display serif for identity,
  tabular mono for all numbers, Geist sans for prose.
- **Motion: one orchestrated entrance** — move resolves first (staggered rows),
  summaries settle after; `prefers-reduced-motion` respected. Reuses `motion-layer`.
- **States first-class** — layout-shaped skeletons (not spinners); "No changes
  today" a *designed* empty state; plain in-voice errors with retry; "as of {last
  run}" freshness; segment freshness in Why.
- **Mobile parity at 375px** — hero stays hero; pairs stack; tables → card rows;
  bottom bar thumb-reachable.

## Section 6 — Reuse / recompose / build / cut

- **Keep (tested plumbing):** `dashboard-context`, `queries`, `supabase`,
  `snapshot-fetch`, `snapshot-types`, `render-pipeline-payloads`,
  `render-digest-from-snapshot`, `render-document-from-payload`,
  `decision-scorecard`, `portfolio-risk-metrics`, `performance-series`,
  `position-*`, `portfolio-aggregates`, `thesis-*`, `SafeMarkdown`, `ui.tsx`,
  `security-headers`.
- **Recompose:** `TodayActionsPanel`→hero move; NAV chart→Today summary +
  Performance; `MorningBriefPanel`→Today read + Why "The read";
  `DeliberationsStrip`→Today "why today" + Why "Deliberations"; positions & thesis
  tables→Today summaries + Portfolio tabs.
- **Build new:** 4-item shell; Today composition (hero + disclosure ladder + 4
  summaries); Portfolio (3-tab book); Why (3-tab reasoning); System footnote;
  thesis-join drill links.
- **Cut / remove routes:** `/strategy` (→Today), `/twelve-x` (out),
  `/performance` (→Portfolio tab), `/observability` (→System), `/library`
  (→Why/Documents); operator-only panels drop/hide.
- **Testing:** plumbing tests stay green; page-level tests updated to new
  content/structure; new tests for the disclosure ladder, HOLD-day hero, nav map,
  and join links. TDD for new logic; snapshot/render tests for new compositions.

## Success criteria

- Today answers "what happened, how am I doing, and why" above the fold, with the
  move as the unmistakable hero, on both action and HOLD days.
- Primary nav is 4 destinations + Settings; no owner-facing task needs more than
  one tap from Today.
- Operator/debug surfaces are demoted to System; none compete with the book.
- Dark + light both correct; mobile parity at 375px; `prefers-reduced-motion` honored.
- Design language is unmistakably digiquant.io (tokens, serif, accent).
- All retained plumbing tests green; new behavior covered by tests.

## Out of scope

- Changes to the Atlas/Hermes pipeline or any backend data shape.
- Twelve-X / FX product (cut from owner nav; lives elsewhere if revived).
- Auth/JWT/BYOK behavior (Settings scope unchanged).
