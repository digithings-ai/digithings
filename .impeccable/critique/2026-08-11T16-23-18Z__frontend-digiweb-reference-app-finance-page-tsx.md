---
target: olympus /finance reference surface
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-11T16-23-18Z
slug: frontend-digiweb-reference-app-finance-page-tsx
---
Method: dual-agent (A: design-review subagent · B: detector+browser-evidence subagent — isolated, run in parallel via Workflow)

#### Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | No live/stale signal anywhere — bare "as of" date stamps, plus an unused `.pw-live-dot` rule clearly meant for this and never wired up. |
| 2 | Match System / Real World | 4 | CAGR/Sharpe/Sortino/spread/exposure used exactly as a quant would; order-book ask/bid convention and tabular-nums throughout match desk-reading habits. |
| 3 | User Control and Freedom | 1 | Every position row's "dossier" drill-down is a dead `<span>` — no href, onClick, or button role. |
| 4 | Consistency and Standards | 2 | `ReturnsMatrix` has full ARIA table semantics; the blotter and workspace ledger use bare `<th>` with no `scope`. |
| 5 | Error Prevention | 1 | No empty-portfolio, failed-chart, or stale-data state modeled anywhere. |
| 6 | Recognition Rather Than Recall | 3 | Every value has an in-place mono label — but that label color computes under WCAG AA contrast. |
| 7 | Flexibility and Efficiency | 1 | None of the three tables sort/filter, despite a `SortableTable` component existing elsewhere in the same package. |
| 8 | Aesthetic and Minimalist Design | 3 | Flat/hairline/monochrome house style genuinely well executed; docked for developer-rationale prose sharing the same visual register as live data, 11 times over. |
| 9 | Error Recovery | 1 | Zero error/empty/degraded states demonstrated for any data-dependent surface. |
| 10 | Help and Documentation | 2 | Excellent as developer documentation; zero in-product help for an end user (no definition anywhere for Sortino, exposure, profit factor). |
| **Total** | | **20/40** | **Acceptable** |

This is a meaningfully lower score than the digichat `/chatbot` critique (33/40) — be honest about it: the visual/token layer here is genuinely strong, but the page-as-working-surface has real, structural gaps a trader would hit on day one.

#### Design Specificity Verdict

**LLM assessment**: Split verdict, and the split matters. The individual composites are genuinely authored for quant/trading — the order book's ask-descends-into-spread convention, the underwater drawdown plot that "only ever reads negative," the returns heatmap that tints by the grid's own max-abs, and above all the explicit, *followed* rule that `--up`/`--down` are reserved for P&L only and never chrome/identity (EquityCurve deliberately wears the accent instead). None of that falls out of a generic Tailwind admin kit. But judged as it actually renders, the page is structurally a component gallery — eleven near-identical kicker/heading/prose/demo blocks, several carrying developer-facing rationale a portfolio manager has no reason to read — and the interaction layer has real seams: the "dossier" drill-down is inert, and the command band's own position count doesn't match its own ledger. The visual grammar is specifically quant-authored and above the bar; the page as a working surface isn't yet the single coherent Operate page a trader would live in all day.

**Deterministic scan**: `detect.mjs` ran clean (exit 0, zero findings) across all 5 target paths. As with the chatbot critique, a clean detector run means "no known anti-pattern regex matched" — every real defect below was found by browser/DOM evidence or source reading, not the pattern scanner.

**Visual overlays**: Screenshot capture was intermittently flaky again this session (a known limitation already flagged twice). Assessment B worked around it via direct DOM/computed-style queries, confirming visual claims (mobile table overflow, tearsheet stacking) once screenshot capture recovered partway through.

#### Overall Impression

The token/visual discipline here is the best in the system so far — money-color quarantine is not just applied but *enforced end-to-end*, and it's explained in-product (EquityCurve's own docblock states "not the money colors — this is identity"). But the page hasn't crossed from "design-system showcase" into "a dashboard a trader would actually live in": a P0 trust break (position count doesn't match the visible ledger), a dead drill-down control styled as live, and zero error/empty states on a surface whose entire job is being an accurate ledger of what you hold.

#### What's Working

- **Money-color discipline is enforced, not just documented**: `--up`/`--down` never leak into chrome or identity anywhere on the page — confirmed independently by both assessments. The ticker, candles, order-book rows, and every P&L cell correctly claim the money hues; identity elements (EquityCurve) correctly don't.
- **`ReturnsMatrix`'s accessibility is unusually good**: every cell gets a full sentence ARIA label ("Jan 2023: 7.4%", "no data" for gaps) plus real `columnheader`/`rowheader` semantics — confirmed live in the accessibility tree, a noticeably higher bar than the plain-`<th>` tables elsewhere on the same page.
- **P&L is never color-only signaled**: Assessment B specifically checked this and cleared it — every P&L read carries an explicit +/− sign or ▲/▼ glyph alongside color, on the ticker and in the blotter alike.

#### Priority Issues

- **[P0] Command band claims 11 positions; the ledger beneath it shows 5, with no disclosure.** `PortfolioWorkspaceReference`'s command band reads "positions: 11," but the table directly beneath lists exactly 5 rows (XLE, XLF, UUP, XLRE, XLV) with no "showing 5 of 11" or "top holdings" label anywhere.
  **Why it matters**: on a financial dashboard, whether the numbers on screen are complete or a partial slice is a first-order trust question — a user can't tell if 6 positions are hidden or the headline figure is stale/wrong, and either reading undermines confidence in a surface whose entire job is being an accurate ledger of what you hold.
  **Fix**: either make the row count match the headline, or explicitly disclose the slice ("Positions · showing 5 of 11 · sorted by weight").
  **Suggested command**: `/impeccable clarify`

- **[P1] The "dossier" drill-down on every position row is dead.** `portfolio-workspace-reference.tsx`'s `<span className="pw-follow">dossier</span>` has no `href`, `onClick`, or button role — confirmed live in the accessibility tree as role "generic," not "link." `finance.css` still carries ~100 unused lines (`.pw-focus`, `.pw-rail`, `.pw-proposals`, `.pw-risk-track`, `.pw-call`, `.pw-live-dot`) that look like the cut drill-down panel this was meant to open.
  **Why it matters**: it's styled exactly like an available action (accent color, in a column literally labeled "follow") and actively invites a click that does nothing — a broken promise on the one interaction this composition exists to support.
  **Fix**: either wire "dossier" to a real destination/panel (the orphaned CSS suggests one was designed), or strip the affordance styling so it reads as static metadata.
  **Suggested command**: `/impeccable harden`

- **[P1] Nav icon buttons have no visible focus indicator.** Confirmed two ways: computed style after `.focus()` shows `outline: none, box-shadow: none` on both `.site-nav-theme` and `.site-nav-burger`; and a full CSS grep across the reference app finds no `:focus`/`:focus-visible` rule for either class anywhere, while sibling component families (`.ff-input`, `.acct-*`, `.tt-trigger`, `.skip-link`) all define one. Since `SiteNav` is shared chrome, this affects every reference page, not just `/finance`.
  **Why it matters**: a keyboard user tabbing through the page gets no visible indicator on either control — a hard accessibility failure, not a stylistic gap.
  **Fix**: add a `:focus-visible` rule to `.site-nav-theme` and `.site-nav-burger` matching the ring already used elsewhere (`web-theme.css`'s global `:focus-visible` rule, or the component-specific ones on `.ff-input`/`.tt-trigger`).
  **Suggested command**: `/impeccable audit`

- **[P1] `--ink-mute` labels — and especially the blotter's loss percentage — likely fail WCAG AA contrast.** Per DESIGN.md's documented hex values, `--ink-mute` (#6B7177) against `--surface` (#121417) computes to roughly 3.7:1 — under AA's 4.5:1 for normal text — and it's the color used for every table header, metric label (SHARPE, SORTINO, EXPOSURE), and timestamp on the page. It gets worse exactly where it should be clearest: the loss-percentage suffix in the blotter renders at `opacity-75` on top of `--down`, dropping effective contrast to roughly 3.26:1 by the same math. *(Caveat: this is Assessment A's calculation from documented token values; Assessment B did not independently run a full contrast sweep, having scoped its browser pass to focus/labels/tables/mobile instead — worth a dedicated contrast-check pass to confirm the exact numbers before treating this as fully verified.)*
  **Why it matters**: these aren't decorative colors — they're the labels that tell a user what every number means, and the one figure hit hardest is a losing position's percent P&L, precisely the number a stressed user needs to read fastest.
  **Fix**: raise `--ink-mute`'s luminance (or reserve it for large/bold text only) until it clears 4.5:1 against `--surface`/`--bg-canvas`, and drop the `opacity-75` treatment on the blotter's loss percentage in favor of a token that holds full contrast at that size.
  **Suggested command**: `/impeccable audit`

- **[P2] Table semantics are inconsistent, and the order book has none at all.** The blotter and workspace ledger use real `<table><thead><th>` markup, but no `<th>` carries a `scope` attribute (confirmed via live DOM query — all `scope: null`) — while `ReturnsMatrix`, rendered further down the same page, gives every cell a full ARIA label and proper headers. The order-book ladder is worse: it's built entirely from `<div>`/`<span>` with no `<table>`, no `role="table"/"row"/"columnheader"` at all — a screen reader gets an unstructured stream of numbers per row with no column identity, with row grouping (asks/spread/bids) preserved only by DOM order.
  **Why it matters**: the inconsistency makes the gap look accidental — the newest, most sophisticated component in the system got table semantics right, and the two simpler, more load-bearing tables (the actual holdings) plus the order book didn't.
  **Fix**: add `scope="col"` to every `<th>` in the blotter and workspace ledger (`scope="row"` on the leading ticker cell), and give the order book at minimum a `role="table"` structure with `columnheader` labels for price/size.
  **Suggested command**: `/impeccable polish`

- **[P2] 4 of 5 chart embeds render `aria-hidden` with no accessible name.** `PriceChartReference`, the standalone `EquityCurveReference`, `DrawdownPlotReference`, and `SyncedTearsheetReference` all call their chart primitive without the optional `label` prop, so each falls to the primitive's own documented "omitted → decorative" fallback. Only the Performance section's embedded `EquityCurve` passes a label, and even that's generic ("Book equity curve — demo series," not a data summary).
  **Why it matters**: a screen-reader user gets the section heading and prose for four of five chart sections, but zero access to the chart itself — on a page whose entire content in those sections *is* the chart.
  **Fix**: pass a meaningful `label` (or a short text summary of the series' current value/trend) to every chart instance.
  **Suggested command**: `/impeccable harden`

- **[P3] Ticker pause is hover-only, no touch/keyboard equivalent.** `.tk:hover .tk-track { animation-play-state: paused; }` (`finance-composites.css:46`) is the only pause mechanism; `prefers-reduced-motion` is correctly wired as a kill-switch, but there's no `:focus-within` or tap-to-pause handler — confirmed live at 375px that touch users have no way to stop the tape to read one value.
  **Suggested command**: `/impeccable adapt`

- **[P3] A JSX whitespace bug renders "…the sanctioned --up / --downmoney colors" (missing space).** Confirmed live on both desktop and mobile screenshots — a `</code>` tag sits adjacent to a line-break before "money colors," and JSX strips that boundary whitespace entirely.
  **Suggested command**: `/impeccable polish`

#### Persona Red Flags

**Alex (Power User)**: Clicking "dossier" on any position does nothing. None of the three tables (blotter, workspace ledger, order book) sort or filter — `SortableTable` exists elsewhere in the same package but isn't used here. The command band claims 11 positions while the ledger shows 5, with no way to tell if the rest are simply not displayed.

**Sam (Accessibility / Screen Reader)**: 4 of 5 chart embeds are `aria-hidden` with no accessible name. `--ink-mute` labels/headers/timestamps compute to ~3.7–3.9:1 against surface/canvas — under AA's 4.5:1 — and the blotter's loss-percent suffix falls further to ~3.26:1. Two of three real data tables lack `scope="col"`, and the order book has no table semantics at all. Both nav icon buttons (theme toggle, hamburger — shared chrome across every reference page) have no visible keyboard focus indicator.

**Riley (Stress Tester)**: No empty-portfolio state is modeled anywhere — every composite ships pre-populated with 5–11 rows. Two max-drawdown reads (−54.1%, −18.4%) get pixel-identical flat styling to a −1% dip, with no escalation tier ever exercised to check whether calm-monochrome still communicates severity at a genuinely catastrophic number. Both the order book (fixed 5 asks/5 bids) and the blotter (fixed 5 rows) hardcode their row counts with no virtualization or scroll pattern coded anywhere — untested what a 50-position book or a deep 100-level order book actually does to this layout.

#### Minor Observations

- `DashboardWorkspaceReference.tsx` is a fully built, documented component (referenced in `ARCHITECTURE.md` and `MANIFEST.json`) that's never imported by `page.tsx` or any other reference page — an orphaned composition sitting beside the one (`PortfolioWorkspaceReference`) that actually ships.
- The two workspace composites hardcode two different "as of" dates (21 JUL 2026 vs. 19 JUL 2026) against the same 84.8%/11-positions headline figures — harmless as static demo data, but a reminder that no freshness/staleness indicator pattern exists anywhere on this page.
- Mobile touch targets on the two nav buttons measure 33×33 and 34×24 CSS px — inside WCAG 2.5.8's 24px AA floor, but under Apple HIG's 44pt / Material's 48dp guidance for a dense financial dashboard that will be thumb-driven.
- 5 of 7 `<table>` elements the naive detector query found are internal DOM structures generated by TradingView Lightweight Charts (`tv-lightweight-charts`, 0 rows) — not authored markup; only 2 are real data tables. Flagging so this doesn't get miscounted in a future pass.

#### Questions to Consider

- The CSS for a richer per-position drill-down (`.pw-focus`, `.pw-rail`, `.pw-proposals`) already exists, unused, in `finance.css` — was that panel cut for scope before promotion, or simply forgotten, and should "dossier" get wired to it or removed?
- Is the workspace ledger's "5 rows under an 11-positions headline" a deliberate "top holdings" pattern that just needs a "showing 5 of 11" label, or evidence the reference's own demo data hasn't been checked for internal consistency — and if the latter, what else on this page hasn't been?
- House style keeps every P&L read flat and identically weighted regardless of magnitude — is "no color-shouting, ever" a principle that should hold at a −54% drawdown too, or does an Operate surface need one reserved escalation tier (weight/size, not hue) for genuinely catastrophic states?
