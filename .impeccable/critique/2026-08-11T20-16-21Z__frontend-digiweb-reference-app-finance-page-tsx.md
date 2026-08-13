---
target: olympus /finance reference surface (recheck after fixes)
total_score: 27
max_score: 32
na_heuristics: 5,9
p0_count: 0
p1_count: 1
timestamp: 2026-08-11T20-16-21Z
slug: frontend-digiweb-reference-app-finance-page-tsx
---
Method: dual-agent (A: design-review subagent · B: detector+browser-evidence subagent — isolated, run in parallel via Workflow). Re-check after 11 fixes landed from the original critique (merged via PR #2212).

#### Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Command bands carry an "as of" timestamp, but the ticker/blotter/perf-metrics blocks show none — inconsistent across widgets. |
| 2 | Match System / Real World | 4 | Domain-accurate throughout — reads like real trading software. |
| 3 | User Control and Freedom | 2 | **New finding**: Lightweight Charts' default scroll/zoom handlers capture mouse-wheel and touch-drag on all 6 chart panes instead of passing through to page scroll — reproduced live. |
| 4 | Consistency and Standards | 4 | Exceptionally disciplined — money-color-for-P&L-only followed with zero exceptions found. |
| 5 | Error Prevention | n/a | Pure display surface — no forms/inputs/destructive actions to guard against. |
| 6 | Recognition Rather Than Recall | 4 | Column headers and color meaning always visible in place. |
| 7 | Flexibility and Efficiency | 2 | Everything is static/read-only, no in-page jump navigation across 12 sections. |
| 8 | Aesthetic and Minimalist Design | 4 | Monochrome/flat/hairline discipline, high density never cluttered. |
| 9 | Error Recovery | n/a | No error/empty/failure states exist on this static page. |
| 10 | Help and Documentation | 4 | The numbered "charting rules" section is genuine on-page documentation of the pattern's own contract. |
| **Total** | | **27/32** | **Good** |

Two heuristics (Error Prevention, Error Recovery) were legitimately marked n/a this run — this is a pure static display surface with no forms or destructive actions, so those don't apply (per the critique's own mode-applicability rule, not scorer leniency). The original run scored them 1/1 despite the same non-applicability, which is arguably the less accurate reading.

**Trend for `frontend-digiweb-reference-app-finance-page-tsx` (2 runs): 20/40 → 27/32**
Different heuristic sets were scored (the first run scored all 10; this run marked 2 n/a as genuinely inapplicable), so this isn't a strict like-for-like number — but as percentages, that's 50% → 84%, a real jump from "Acceptable" to "Good."

#### Design Specificity Verdict

**LLM assessment**: Specific. Findings are anchored to exact source (chart-host.tsx's unmodified Lightweight Charts defaults, OrderBook.tsx/StockTicker.tsx markup, finance.css token usage), a verified computation (re-ran the DRAWDOWN_DEMO LCG walk in Node and confirmed the aria-label's "max −7.4%" is numerically correct — not just plausible-looking), and a reproduced runtime behavior (chart timescale visibly panned after a scroll gesture landed on a chart pane, on both desktop and mobile viewports).

**Deterministic scan**: `detect.mjs` ran clean — exit 0, zero findings — across all 5 target paths, same as both prior runs.

**Browser evidence**: All four targeted re-checks (position-count match, order-book ARIA semantics + accessible name, table `scope` attributes, mobile nav right-alignment) were independently confirmed fixed via direct DOM/computed-style queries, not inference from screenshots. Notably, the ResizeObserver flakiness that affected multiple prior sessions' browser tooling did not reproduce this run.

#### Overall Impression

Every one of the 11 fixes from the original critique holds up under independent re-verification — this is a real, durable improvement, not a regression waiting to happen. The surface has moved from "genuinely rough" to "disciplined, with one real interaction bug." That bug (chart panes eating scroll gestures) is a new finding from this fresh pass, not something the original critique or fix round touched — the page's growing density of full-width chart panes makes it more likely to bite as more sections get added.

#### What's Working

- **Token discipline is airtight and self-consistent**: every chart, pill, and table across all 12 sections reads `--up`/`--down`/`--hair`/`--accent` from the same source, with zero exceptions found to the money-color-for-P&L-only rule.
- **Table and chart semantics are properly built, not just visually styled**: the positions blotter uses real `<table>`/`<th scope="col">`/`<th scope="row">`, the order book's div-based grid carries `role=table/row/rowgroup/cell` with a computed accessible name, and every chart's aria-label is independently verifiable against its actual generated series (confirmed via direct recomputation, not just plausibility).
- **The page teaches its own contract**: the numbered "charting rules" section turns implementation constraints into literal on-page documentation — a rare, valuable move for a component reference.

#### Priority Issues

- **[P1] Chart panes capture scroll/pan gestures instead of passing them through to the page.** All 6 embedded Lightweight Charts panes run on the library's unmodified default `handleScroll`/`handleScale`. Confirmed live: a scroll gesture aimed at a chart shifted its visible timescale ("26 Mar 5" → "2026 Mar 9") while the page's own scroll position didn't advance. On mobile, where touch-drag is the only scroll mechanism, a vertical swipe starting on a chart pans it instead of continuing the scroll — and charts occupy a large share of this page's height.
  **Fix**: override `handleScroll` (and consider `handleScale`) in the shared chart scaffold — e.g. `vertTouchDrag: false` and possibly `mouseWheel: false` for these display-only demo panes — reserving pan/zoom capture for surfaces where it's an intended interaction.
  **Suggested command**: `/impeccable adapt`

- **[P2] 3 of 12 sections (perf-metrics, returns-matrix, order-book) have no `id` on their section wrapper**, unlike the other 9. Silently breaks deep-linking to exactly those three patterns — an inconsistency that stands out precisely because the rest of the page is disciplined about anchors.
  **Fix**: add matching `id`s (e.g. `id="performance-metrics"`) to the three section wrappers.
  **Suggested command**: `/impeccable polish`

- **[P2] No in-page table of contents** despite being one of the longest reference pages in the suite (12 distinct pattern sections). A reader wanting one specific pattern has to scroll past everything before it.
  **Fix**: add a lightweight sticky "on this page" anchor list, shared across the design-reference site rather than built one-off.
  **Suggested command**: `/impeccable shape` (to plan the shared component before building it site-wide)

#### Persona Red Flags

**Riley (Mobile-first, touch-only)**: A vertical swipe starting on a full-width chart pane pans the chart instead of scrolling past it — the only scroll mechanism available on a phone. No in-page section index to jump ahead once a swipe gets "caught."

**Alex (Efficiency-driven power user)**: No sort/filter/jump-to on any table — fine for a static demo, signals these primitives aren't yet ready to be a fast-scan operate surface in production. Scroll interrupted by chart pan/zoom breaks the fast top-to-bottom scan this persona relies on.

**Casey (Skeptical evaluator)**: The missing `id`s on exactly 3 of 12 sections reads as a small crack in an otherwise very disciplined system. No visible evidence the default chart scroll-capture behavior was ever checked on an actual touch device before being promoted as the canonical dashboard chart primitive.

#### Minor Observations

- The "dossier" label is confirmed correctly de-styled as plain text (no button/link affordance) — but the term itself is still unexplained jargon with no tooltip.
- Portfolio workspace and portfolio blotter both happen to display "invested 84.8%" — coincidental reuse of the same demo figure across independent example datasets could read as implied data-linkage where none exists.
- One accessibility-tree read didn't surface a name for the order book's "size" cell while the adjacent "price" cell in the same row did, despite structurally identical markup — flagged as possibly a tooling artifact (the DOM value is present either way via `get_page_text`), worth an independent manual screen-reader spot-check.
- Browser-based visual QA for scrolled states was unreliable this session (blank/partial screenshot captures after scroll actions) — conclusions lean on the accessibility tree, extracted text, and source review more than scrolled screenshots; a manual visual pass on the lower two-thirds of the page is worth doing independently.

#### Questions to Consider

- If Olympus ships these chart primitives with Lightweight Charts' default scroll/zoom handlers untouched, has anyone actually scroll-tested the production dashboard on a phone, where one chart can occupy most of the fold?
- Portfolio workspace and portfolio blotter are two different information architectures for the same underlying concept (a book of positions) — will a real Olympus surface ship both at once, and on what basis would a user know which one is "the" positions screen?
- The page teaches its own charting rules explicitly — should the same treatment exist for the table and order-book patterns, or is chart chrome considered uniquely fragile enough to need it?
