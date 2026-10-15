# digiquant.io v2 design plan

## 1. Goal and what changed

Build digiquant.io as a terminal-dense, motion-rich instrument panel. It uses the digithings.ai refactor grammar: a pinned nav, hairline rails, and a stack of id-anchored bands with one idea and one interactive piece each. The rejected v1 applied the *document* grammar (PageTitle, Section, GlyphList) to a landing page. It had one static idea per screen, almost no motion, and none of the kit's motion or finance parts. v2 changes three things:
- **Grammar:** bands, not documents.
- **Real surfaces:** a scroll-driven pipeline, a scrolling tearsheet rail, a live book, a price bar and a simulated chat.
- **Process:** framework first, then one band per reviewable pass.

## 2. Design language

**Blend.** Gloomberg supplies the *static* layer: flat surfaces, mono type, a 0-radius hairline grid, tabular numbers, bracketed micro-labels (`[live]`, `$`, `>`, `▸`), and keycap chips. Motion supplies the *behaviour* layer: things enter, scrub and count as you scroll, but only inside that fixed grid. The result should read as a live terminal that reveals itself.

**Fixed:**
- Tokens only, with no raw hex/rgb.
- Geist Mono everywhere.
- Radius 0, with a hairline as the only depth cue.
- Dark default, phosphor-teal accent for identity, focus and "alive".
- `--up`/`--down` only for signed P&L, never for identity or decoration.
- One accent per view, and one loud ink/paper CTA per viewport.
- Denser than digithings.ai: a tighter `--page-step`, applied through a local token override, not a new class family.

**Motion budget (page-wide).** Every effect needs a reduced-motion state (the finished state) and a no-JS state (content readable, with `data-motion` on hidden-initial elements).

| Moment | Where | Mechanism |
|---|---|---|
| Price marquee and tick-flash | MarketBar | CSS marquee; opacity-only flash |
| Hero entrance and blinking cursor | Hero | CSS `animate-appear` stagger, not JS |
| Metric count-up | Hero | `StatCounter`/`OdometerStrip`, once in view |
| Band entrances | Every band | `Reveal`/`Stagger`, once |
| **The one pin** | Pipeline | `HorizontalScrollTrack` |
| Snap-scroll rail | Tearsheets | `CardRail`, native, no pin |
| Scripted playback | Strategy dev | `ChatPlayback`, starts in view |
| Closing sweep (optional) | Colophon | Zero-JS CSS scroll-driven; ship only if promoted in this branch |

**Rules:**
- Use `m.*` under `MotionProvider`, and only `useMotionSafe`.
- Animate transform, opacity and pathLength only.
- Use function transforms for any pinned mapping.
- Do no per-frame `setState`; write to refs.
- Gate rAF loops with IntersectionObserver.
- Auto-running motion over 5s needs a visible pause control.
- The pinned track is active only at 960px and wider with motion allowed. Otherwise it is a native snap strip.
- WordReveal, DeckStack, HeroMesh and glow effects are dropped, so nothing competes for the pin.

## 3. Page architecture

Chrome, on every route: **MarketBar** (fixed top strip), pinned **NavShell** below it, **LayoutLines** rails, **SectionRail** (`~/digiquant/<section> NN/07`, at 1400px and wider), then **FooterCells** at the end.

Status legend: F = foundation, in Phase 0. L = later refinement pass.

### 3.1 Price bar (chrome) — F, data in L
- **Purpose:** the terminal status line.
- **Takeaway:** "this is a live market tool".
- **Layout:**
  ```
  [● live] BTC 6x,xxx ▲0.4%  ETH … | SPY close · as of 09-29 ▼0.2% …   00:00Z [pause]
  ```
- **Kit parts:** new `MarketBar` wrapping `StockTicker` and `LiveBadge`.
- **Motion:** marquee, tick-flash, pause control.
- **Data:** live crypto via the Coinbase public websocket and equity daily closes, with per-cell "as of" stamps. The SSR/empty state is `connecting…`, never invented prices. Labelled **real**.
- **Not Gloomberb data,** so no Gloomberb attribution here.

### 3.2 Hero — F
- **Purpose:** state what it is.
- **Takeaway:** "an open, self-hosted quant research desk; nothing hidden".
- **Layout:**
  ```
  ~/digiquant · open source
  A quant research desk
  in a glass box you own▌
  one-line mission            [ Open dashboard ]
  $ git clone …               (copy)
  ┌subsystems┬stages┬backtested trades┬live orders┐
  │    N     │  6   │       N         │    0      │
  ```
- **Kit parts:** `HeroEntrance`, `CopyCommand`, `CtaLink`, `OdometerStrip`.
- **Motion:** staggered CSS entrance, block cursor, count-up.
- **Data:** structural counts come from the registry, the stage count from the shared stage definition, backtested trades from the strategy index, and `0` is a literal. Labelled **real**.
- **Old copy** ("glass box you own", "0 live orders") is kept because it is honest.
- No HeroMesh.

### 3.3 Products and integrations — F shell, L content
- **Purpose:** show what digiquant serves and what it plugs into.
- **Takeaway:** "a curated set of subsystems, with honest status".
- **Layout:**
  ```
  ┌ digiquant ps ─────────────────────────┐   (selectable rows type detail)
  │ online   research pipeline …          │
  │ online   portfolio / tearsheets …     │
  │ roadmap  strategy development         │
  └───────────────────────────────────────┘
  integrations ledger: name | role | status badge | attribution
  ```
- **Kit parts:** `TerminalManifest` (online/roadmap rows), `Table` plus `Badge`, `Reveal`. No new parts.
- **Integrations, text only:**
  - Gloomberb (digifetch): "Sourced from Gloomberb · Data delayed up to 15 minutes".
  - LuxAlgo Library: research metadata only, badged "in development" until #4779 is merged.
  - Coinbase (prices).
  - NautilusTrader (backtest engine).
  - MCP.
- **No marquee and no logos:** the icon registry has no marks for these, and rights are unchecked.
- **Data:** real, from repo facts. Re-verify counts at build.

### 3.4 Pipeline — L, primitive in F
- **Purpose:** show how a run is made.
- **Takeaway:** "six stages, and you can open the latest run".
- **Layout:**
  ```
  pin (100svh): Inputs → Research → Synthesis → Selection → Decision → Learning → [Execution: in development]
                ━━━━━━━━━━━●───────────  progress rail
  then (unpinned, in ProductFrame): kit Pipeline, snapshot of run YYYY-MM-DD
                nodes ▸ click → detail panel (status, counts, title)
  ```
- **Kit parts:** new `HorizontalScrollTrack` (the page's only pin), kit `Pipeline`, `ProductFrame`, `DatePager` (optional), `Badge`.
- **Motion:**
  - Vertical scroll drives translateX with dwell weights and a rail fill.
  - Below 860px or under reduced motion, it becomes a native snap strip with every card visible.
- **Data:**
  - The track shows the six dashboard stages plus their real phase names, generated from one shared registry so the copy cannot drift.
  - The detail is **recorded**: a committed `app/_latest-run.json` produced by a capture script (the `capture_mcp_transcript.py` pattern).
  - It holds titles, phases, status and counts only, with the real run date and type shown ("snapshot of run …", never "today").
- **Execution** is a dashed "in development" card.
- One pipeline story, not two.

### 3.5 Tearsheets — L
- **Purpose:** show the output.
- **Takeaway:** "real strategy tearsheets, browsable".
- **Layout:**
  ```
  ◀ [card][card][card][card] ▶   (snap, edge fades, arrows step one card)
  card: name · symbol · kind · 4 KPIs · [backtest · in-sample] chip → /strategies/<slug>
  ```
- **Kit parts:** `CardRail` (promote if absent from this branch), `TearsheetCard` and `TearsheetCardKpis`.
- **Motion:** native snap scroll, plus `Reveal`. No pin.
- **Data:** live from `strategy_tearsheets` through the existing app-local `strategy-library-live`, with skeleton, "unpublished" and empty states. Labelled **real**.
- **Chips:** reuse the approved phrases "backtest · illustrative, in-sample" and "Backtest only".
- **Decision:** the rail replaces the old sticky DeckStack, so the pin budget goes to the pipeline.

### 3.6 Dashboard — L
- **Purpose:** show the tool.
- **Takeaway:** "a real dashboard, with the book on it".
- **Layout:**
  ```
  ┌ MediaFrame 16:9 ───────────────┐  book · <as-of>   [1M 3M YTD]
  │  ▶ recording to come           │  [ portfolio vs benchmark chart ]
  └────────────────────────────────┘  net return · CAGR · alpha   (read rows)
  ```
- **Kit parts:** new `MediaFrame`, plus the existing `portfolio-island` (`MultiTimeSeries`, `SegToggle`, `KpiStrip`, `LiveBadge`).
- **Motion:** the video starts in view, and under reduced motion shows the poster with controls. The chart uses `Reveal`.
- **Data:** the book is **real, paper**, with an as-of date and an honest loading/empty state (paper NAV, not money). The video is a **placeholder** now. The dashboard cannot be framed.
- **Charts:** canvas charts get a definite host height, because the no-JS state is blank.

### 3.7 Strategy development — L
- **Purpose:** show where it is heading, honestly.
- **Takeaway:** "chat builds a strategy through MCP tools; not live yet".
- **Layout:**
  ```
  1 idea → 2 backtest & optimize → 3 export (human gate)     ┌ digichat — simulation ┐
  ledger: Backtest/Optimize/Export via local MCP: available   │ > What can I start from? │
          Chat-driven building: in development                │ ▸ digiquant_list_strategies() ok 41ms │
          Live trading: off                                   └ [chip][chip][chip] [replay][skip] ┘
  badge: Simulation · scripted · not live
  ```
- **Kit parts:** new `ChatPlayback` (built from `ChatTranscript`, `ChatMessage`, `ChatToolCall` and `ChatStreamCursor`), `Badge`, `NumberedStages`, `CopyCommand` (stdio run command).
- **Motion:** in-view playback, the finished state under reduced motion or no-JS, and an sr-only full copy.
- **Data:** **simulated**.
  - Tool names and args are real, including the `*_json` strings.
  - Result values are masked (`—`) with the caption "illustrative placeholders, not a real run".
  - Tools are attributed to the local full-scope stdio MCP.
  - Chips are canned, and the composer is disabled.

### 3.8 Get started — L
- **Purpose:** convert.
- **Takeaway:** "own it, or have it run for you".
- **Layout:**
  ```
  $ git clone …   $ python -m digiquant.mcp_server --stdio
  Self-hosted (free, MIT) | Managed (coming soon) | Enterprise (contact)
  ```
- **Kit parts:** `Pricing` cards or `Table`, `CopyCommand`, `CtaLink`.
- **Data:** approved copy from `app/_pricing.ts`, with no invented prices.
- FAQ is dropped from the home page.

## 4. Phase 0 framework (build, then stop for owner review)

**Contents:**
- `globals.css` wiring: `@import` plus a matching `@source` line for each family used (deck not needed). The families are marquee, data-layout, finance-composites, effects-chrome, terminal-manifest, pricing, chat-core and chat-widgets (plain imports), and the new families.
- Shell: `MarketBar` (with the empty state and pause control), `NavShell` pinned, `LayoutLines`, `SectionRail`, `FooterCells`, and `MotionProvider` and `HashScrollManager` kept.
- Nav and footer data in `app/_nav.tsx`.
- **Kit promotions with specimens**, with all exports, CSS entries, MANIFEST and specimen-inventory wiring landed now, so later passes touch only their own files. The five promotions are `HorizontalScrollTrack`, `MarketBar`, `MediaFrame`, `SectionRail` and `ChatPlayback`. `ChatPlayback` is a minimal working version.
- `CardRail` is verified present in this branch, or ported from the changelog-rail reference.
- `app/page.tsx`: a shell that renders eight band files in order. Each is a `<section id>` on the hairline frame, with a status badge (`placeholder`) and the `Reveal` scaffold.
- The hero is real. The pipeline shows the real six stage names on the pinned track with placeholder cards. The other bands hold labelled placeholders.

**Acceptance:**
- Static export builds, and `scripts/check_frontend_canon.py` and the specimen tests are green.
- There is exactly one pinned section.
- Reduced-motion and no-JS renders show all content.
- No horizontal overflow at 375px.
- No invented numbers, and every placeholder is labelled.
- SectionRail tracks the bands.
- Owner reviews the scroll feel before any band work.

## 5. Iteration plan

After Phase 0, each pass is one band, reviewed on its own. Passes run in parallel as sub-agents, each in its own worktree branched from the Phase 0 commit, and merge one by one after the owner's review.

**File ownership.** Phase 0 exclusively owns the shared files: `app/page.tsx`, `_nav.tsx`, `globals.css`, `packages/ui/src/index.ts`, the `package.json` exports, `MANIFEST.json` and `specimen-inventory.ts`. Pass agents edit only what is listed below. A change to a shared file goes through the Phase 0 owner.

| Order | Pass | Owns |
|---|---|---|
| 1 | Pipeline | `app/_bands/pipeline.tsx`, `app/_latest-run.json`, the capture script, the phase registry, the kit `horizontal-track` dir and its specimen |
| 2 | Tearsheets | `_bands/tearsheets.tsx`, `components/tearsheet/strategy-library-live`, `CardRail` (kit and specimen) if promoted |
| 3 | Strategy dev | `_bands/strategy-dev.tsx`, `app/_strategy-script.ts`, the kit `chat/ChatPlayback` and its specimen |
| 4 | Hero and price bar | `_bands/hero.tsx`, `lib/live/market-bar.ts`, the kit `MarketBar` and its specimen |
| 5 | Products and integrations | `_bands/products.tsx`, `app/_products.ts` |
| 6 | Dashboard and video | `_bands/dashboard.tsx`, `components/live/portfolio-island`, the kit `MediaFrame` and its specimen |
| 7 | Get started and footer | `_bands/get-started.tsx`, `_pricing.ts` |

**Deferred follow-ups:**
- Swap in the real video after the dashboard rebuild.
- Promote a `PipelineGraph` from `apps/dashboard/components/pipeline` after the shell rebuild lands. That move must be a separate PR.
- Add a live-refresh badge on the pipeline via dashboard-api.
- Add an optional "recorded" tab in the chat using the existing `_mcp-transcript.json`.

## 6. Kit promotions and canon implications

| Part | Specimen (apps/reference) |
|---|---|
| `HorizontalScrollTrack` (sticky pin, content-derived runway, function transform, stepper fallback) | `effects/horizontal-track` |
| `MarketBar` | finance gallery, next to the ticker specimen |
| `MediaFrame` (poster, placeholder state, controls) | `data-layout/media-frame` |
| `ChatPlayback` plus the simulation badge | `chat/chat-playback` |
| `SectionRail` (coordinate with the refactor branch, where it is app-local) | `layout-patterns/section-rail` |
| `CardRail`, only if missing | the existing changelog-rail specimen |

Each promotion follows this recipe:
1. Add the specimen.
2. Build the props-driven primitive in `@digithings/ui`.
3. Add the exports and the CSS entry.
4. Regenerate the MANIFEST.
5. Add the `SPECIMENS` entry.
6. Add `@import` plus `@source` in `globals.css`.

Canon rules for all of them:
- Tokens only, and no raw colour in mask-images (the old track used `#000`).
- No `cursor-*` in the app.
- Logical properties.
- No `motion.*`.
- No new app-local class families. The census is near its limit, and band files are compositions with no new CSS classes.
- The chat script and the pipeline snapshot are data, not components.
- Note: `.ts-card` has a mild gradient and a hover transform. Accept it, or fix it in the kit as a separate change.

## 7. Data and honesty rules

| Surface | Label | Rule |
|---|---|---|
| Price bar | live / as of | Real feeds only, with per-cell as-of stamps. No SSR prices. Attribute Gloomberb only where its data renders. |
| Book | real (paper) | As-of date, honest empty state. Up/down colours only on real signed results. |
| Tearsheets | real | Backtest and in-sample chips. Empty states for unpublished. |
| Pipeline snapshot | recorded | Real run date and type, and metadata only. Never "today". |
| Chat | simulated | "Simulation · scripted · not live". Real tool names and args, masked results. |
| Video | placeholder | "Recording to come". It shows nothing the recording does not show. |

**Must NOT claim:**
- That strategy development is live.
- That there is a public hosted MCP, a "try it live" or a connect button, or any MCP URL.
- Pine or TradingView output, or broker or QuantConnect deployment. The export writes JSON only.
- `nautilus_bundle` for anything except `ema_cross`.
- Live trading (live orders are `0`).
- Gloomberb Pro bundling, or partnership or endorsement wording. The two names are distinct: Gloomberg (gloom.sh) is the design reference, Gloomberb is the data partner.
- LuxAlgo signals or source code. Say "Library research, concepts and indicator metadata".

**Other rules:**
- No numbers from the reference fixtures (`trend_xsec`, Sharpe 1.18, PF 6.62 and similar).
- The dashboard chat is read-scope, so backtest, optimize and export belong to the local full-scope MCP.

## 8. Risks and open questions

**Risks:**
- Kit parts from the refactor branch (`CardRail`, `Pipeline`, `StockTicker`) may not be on this branch. Phase 0 verifies this first.
- Pin conflicts. The plan allows exactly one pin.
- gloom.sh and luxalgo.com were not fetched, so the density and colour cues are inferred. The owner should look at both before the hero and price bar pass.
- Static export with live data: every live surface needs a skeleton or empty state and must never show fabricated first paint.
- Hydration bug #2244 has been seen on the old deck, so test each island.
- Counts (34 digifetch tools and similar) drift, so re-verify before publishing.

**Open questions, each with a default so work is not blocked:**
1. **Refactor kit parts:** cherry-pick them or rebase? Default: cherry-pick what is missing in Phase 0, and port `CardRail` from the reference if it is absent.
2. **Tearsheets:** horizontal `CardRail` or the sticky deck? Default: `CardRail`, which frees the pin for the pipeline.
3. **Price bar source:** default is the Coinbase public live crypto feed plus equity closes with as-of stamps. No Gloomberb quotes on the marketing page.
4. **Pipeline snapshot depth:** default is titles, phases, status and counts only, regenerated manually by script. Full document text exceeds the Observer tier.
5. **Integrations:** default is text-only with status badges and no logos. LuxAlgo shows "in development" until #4779 merges.
6. **Pricing and FAQ:** default is compact pricing on the home page and no FAQ. The chat starts as the lightweight `ChatPlayback`, and the full Thread is deferred to a possible `/try` route.

## 9. Critic revisions (supersede sections above where they conflict)

Both critics returned "not approvable as written". Accepted changes:

**Sequencing**
- Phase 0 splits into **0a** (chrome only: globals.css wiring, NavShell, LayoutLines, FooterCells, MotionProvider, empty MarketBar shell, stub bands, no kit promotions) and **0b** (kit promotions, one owner each, then frozen).
- Add a **vertical slice** before the parallel passes: hero + price bar + one real tearsheet card + pipeline in the real look with real data density. The owner judges Gloomberg feel and scroll motion on that, not on placeholders.
- First task: inventory every named kit part against `packages/ui` exports with paths (CardRail, HeroEntrance, OdometerStrip may be missing on this branch); gate the plan on it.
- One ownership rule: each promotion belongs to Phase 0 or to a pass, never both. Shared data (stage registry, counts) lives in a Phase 0-owned file with a frozen shape.
- Fetch gloom.sh and luxalgo.com before the hero/price-bar work and record what was taken. Nothing from either site's wording, name or marks appears on digiquant.io. The teal accent is provisional until then.
- Add T-shirt sizes and a critical path; run `check_frontend_canon.py` on a stub with the density override before committing to it.

**Scope**
- Merge products + integrations into one compact band; price bar is chrome only; pricing becomes a compact CTA strip near the footer.
- Motion budget gets numbers: Lighthouse mobile target, INP < 200ms, no long task > 50ms during scroll, measured JS added by motion.
- A11y section: focus inside the pin scrolls the runway, marquee is aria-hidden with aria-live off, pause/replay/skip controls, every card a tab stop in DOM order.

**Honesty**
- Price bar: "live" badge only while the socket is open and has ticked within N seconds, else "stale"/"offline". Name the origin and CSP connect-src. Name the equity source and check its licence/CORS; fall back to date-stamped recorded closes, not an empty bar.
- Hero: no literal "live orders: 0" metric. Reword as a statement ("no live trading") or derive from config. Stage count comes from the shared registry.
- Pipeline snapshot: takeaway is "a recorded run, not live"; a visible `recorded · date · run type` badge sits inside the frame chrome; allowlist and redact the JSON.
- MCP ledger status reads "runs locally over stdio", not "available". Chat frame carries "Simulation · scripted · not connected to any MCP server". Remove any latency/timing from the script.
- Gloomberb's 15-minute delay stated only if it is in their terms (cite it); add NautilusTrader licence/"built on" attribution.
- Dashboard band: state plainly the live embed is impossible today (`X-Frame-Options: DENY`); unblock options are a `frame-ancestors` carve-out on a read-only pipeline route, or a promoted PipelineGraph. Name the live-book endpoint, confirm public paper-only allowlisted fields, no secrets in `NEXT_PUBLIC_*`, and scan the exported bundle.
- Return figures show benchmark, window and "paper, not money" on the same row; in-sample qualifier repeated next to each tearsheet KPI strip.
- No-JS goal restated: content readable, dynamic panels show a labelled empty state.
