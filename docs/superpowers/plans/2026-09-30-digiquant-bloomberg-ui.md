# digiquant Bloomberg UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild digiquant.io (`apps/digiquant-web`) and the digiquant dashboard (`apps/dashboard`) on the canonical kit with a Bloomberg-style terminal-finance presentation, after digithings.ai lands.

**Architecture:** Pages assemble kit parts from `packages/ui` and specimens from `apps/reference`. Shared chrome (nav, footer, vertical section rail) is promoted once, then dressed per surface. digiquant marketing is a wide, data-first document. The dashboard is a dense multi-pane terminal whose sidebar stays in the flex row and whose database gate never replaces a static route with a blank card. Visual slices stop for Chris to check locally in Cursor. Mechanical slices are OpenCode packages with a failing test first.

**Tech Stack:** Next.js static export (`next build --webpack`), `@digithings/ui`, design tokens in `packages/design/tokens.css`, Vitest, `scripts/check_frontend_canon.py`.

**Status:** plan only. Written 2026-09-30 against `origin/develop` @ `83ec167c7`. No page in `apps/digiquant-web` or `apps/dashboard` is rebuilt by this document.

**Supersedes, for digiquant only:** the gloom.sh visual target in [`2026-09-18-sites-rebuild-from-reference.md`](2026-09-18-sites-rebuild-from-reference.md) §1 and §6. That plan remains the source for digithings.ai (opencode) and for R0, which is done. Epic [#4424](https://github.com/digithings-ai/digithings/issues/4424) stays open.

## Global Constraints

- Polars only. Pydantic v2. These slices are frontend; they do not introduce pandas or untyped dict APIs.
- Canon: every new part lands in `packages/ui` with a specimen in `apps/reference` before a site imports it. `scripts/check_frontend_canon.py` stays green. No new app-local component-class family (`scripts/frontend_class_families.json`). No app-local `cursor-*` utilities (`apps/reference` excepted). No raw Tailwind palette utilities, no hex or `rgb()` literals in `.tsx` / `.ts`.
- Digi product names are lowercase in prose, docs, commits, and PR text (`digiquant`, `digithings`, `digichat`).
- Do not name private clients. Do not use Olympus, Atlas, Hermes, or Kairos in new copy. Leftover redirect paths in `apps/digiquant-web/public/_redirects` stay as paths.
- No live-trading claim. Performance figures that remain say in-sample or backtest. `Backtest only` and `Not OOS vs flat DCA` chips in `apps/digiquant-web/components/tearsheet/honesty.tsx` stay.
- Do not edit `apps/digichat`, `packages/digichat-ui`, `digikey/`, or `digiquant/brokers/`. Do not change the dashboard broker OAuth callback behavior in `apps/dashboard/app/settings/brokers/callback/page.tsx`.
- Print layouts on strategy tearsheets survive. `trailingSlash`, `basePath` `/dashboard`, `_redirects`, and the deploy scripts keep their current behavior.
- This plan does not invent Bloomberg screenshots or a sampled palette. Principles below are public terminal-UI patterns. New hex values are a Chris gate, added as tokens, never as component literals.

---

## 0. Where the epic stands

| Task | State on 2026-09-30 | Evidence |
|---|---|---|
| R0 reference IA | **Done** | 2026-09-18 plan §0. #4410. |
| D1 digithings.ai | **In flight** | PR [#4791](https://github.com/digithings-ai/digithings/pull/4791), branch `claude/digithings-web-ui-refactor`. Why-band polish still moving. Chris owns visual iteration. Branch was behind `develop` when the epic comment was written (2026-09-29). |
| R1 shared chrome | **Not started** | `NavShell` and `Footer` exist in `packages/ui`. digiquant.io still renders `apps/digiquant-web/components/landing/SiteNav.tsx`. The vertical rail is app-local on the digithings branch (`SectionRail.tsx`), not in the kit. |
| Q1 digiquant.io | **Not started** | `apps/digiquant-web/app/page.tsx` is still the mesh hero, scrolly pipeline, and `WordReveal`. |
| Q2 dashboard chrome + DB gate | **Not started** | Shell is `apps/dashboard/components/app-frame.tsx` + `sidebar.tsx`. Gate copy exists (`db-unavailable.tsx`) and is honest about retry. `/pipeline` is documented as exempt and tested as gated. |
| Q3 dashboard surfaces | **Not started** | 24 `page.tsx` files. Several are redirects. Two still nest `<main>`. |
| C1 / C2 | **Not started** | Claim list in the 2026-09-18 plan §7 is the starting inventory, re-dated at audit time. |

Owner sequence (2026-09-30): **digithings first, then digiquant marketing, then the dashboard.** Bloomberg replaces gloom.sh as the digiquant visual target. digithings stays opencode.

---

## 1. Design language

Three languages. They share the kit and the canon guard. They do not share a mood.

### 1.1 Bloomberg / terminal-finance (digiquant.io and the dashboard)

Public terminal-UI patterns this plan is allowed to use. No screenshot, no cloned asset, no "official Bloomberg hex."

- The page is a working surface. Information is the interface: figures, labels, hairline panels, a command or ticker strip. Decoration that does not carry a number or a wayfinding label comes out.
- Panels tile. Rules are 1px (`--hair`, `--term-hair`). Radius on data panels is 0, matching `.term` in `packages/design/site/site.css`. Gaps inside a panel are 8–12px. Section padding on the marketing site is 32–48px, not the gloom 96px rhythm.
- Type is small and mono for anything numeric. Dashboard panel titles sit at 13px mono. Marketing h1 is one line, mono, weight 600, at most 28px. Body copy on the marketing site may stay the kit sans at 15–16px for paragraphs only. Figures use `font-variant-numeric: tabular-nums`.
- Color is semantic. `--up` and `--down` are P&L only (already the house rule in `packages/design/tokens.css`). `--warn` is attention (pending, function highlight, stale). `--danger` is a fault, distinct from `--down`. Identity stays `--accent-digiquant` (the phosphor already ruled for digiquant). A classic amber-on-black function-key palette is **not** introduced in this plan. If Chris wants amber to replace the phosphor on digiquant surfaces, that is a token change in its own reviewed slice (open question 1).
- Chrome is a pinned top strip plus an optional left function rail. The top strip does not hide on scroll. `NavShell` today only allows `autoHide: "scroll" | "hover"` (`packages/ui/src/components/NavShell.tsx`). Q1 needs a third value, `"none"`, so the bar stays put.
- Dark is the working default for the dashboard (already `data-theme`). Light must still meet the AA pairs already pinned in `tokens.css`. The marketing site keeps both themes; it does not ship a mesh, a grain hero, or a scrolly word reveal.
- Motion is CSS-only and honor `prefers-reduced-motion`. No canvas mesh, no 480vh track, no ambient background.

Density tokens to consume, not reinvent:

| Role | Token / existing class | Use |
|---|---|---|
| Working ground | `--term-bg`, `--bg`, `--surface` | Panels and the dashboard canvas |
| Hairline | `--hair`, `--term-hair` | Panel rules |
| Figures | `--term-ink`, `--font-mono` (Geist Mono on the dashboard) | Numbers and labels |
| P&L | `--up`, `--down` | Signed returns only |
| Attention | `--warn` | Stale, pending, function highlight |
| Identity | `--accent-digiquant` | Wordmark and focus, not P&L |

### 1.2 digithings (opencode) — leave it

digithings.ai stays the opencode language from the 2026-09-18 plan §1: small mono type, flat nav, install command, dense module list, `Fig N` captions. PR #4791 is that work. This plan does not restyle it.

### 1.3 gloom.sh — what still applies

gloom.sh is no longer the model for digiquant. Keep only the overlaps that are already canon:

| gloom.sh note (2026-09-18) | Disposition |
|---|---|
| Geist + Geist Mono | Keep. Dashboard already loads Geist Mono in `apps/dashboard/app/layout.tsx`. |
| Semantic positive / negative / pending | Keep as `--up` / `--down` / `--warn`. |
| Flat, animation-light, bracketed mono labels | Keep. |
| 1024px measure, 36px/600 h1, −0.9px tracking, 96px section rhythm, 10px cards | Drop for digiquant. Too much marketing air. |
| Product screenshot as the hero | Drop. The hero artefact is a live ticker plus one claim line. A desk capture is allowed later only as a real `Figure` with a caption, after Chris asks for it. |
| Keycap chips as the organizing device for the pipeline | Drop on the marketing homepage. Keyboard hints stay inside the dashboard command palette, which already exists. |
| Install-channel triad (web / desktop / TUI) | Drop. digiquant's honest install remains the self-host clone, not a three-channel product launcher. |

### 1.4 What digiquant must not look like

digiquant must not inherit the opencode homepage: install tabs as the hero, the why-band three-app invoice, the mosaic, `~/digithings/...` path chrome, or a manifesto headline. The finance app on digithings is a product built on the stack. The digiquant site is the desk.

---

## 2. Learnings from digithings (#4791)

Read from branch `claude/digithings-web-ui-refactor` (PR #4791), not from memory of the live site.

### 2.1 Reuse

| Learning | Where it lives now | How digiquant uses it |
|---|---|---|
| Vertical section rail | `apps/digithings-web/components/landing/SectionRail.tsx` on the #4791 branch. Fixed left gutter, one tick per band, `aria-current="location"`, hash jump, hidden below 1400px. | Promote to `packages/ui` after #4791 merges (task R1). digiquant passes its own section list. The path text is a prop, defaulting empty. digiquant's label is the section name (`pipeline`, `book`), not `~/digithings/why`. |
| Scroll restoration | `HashScrollManager` already in `packages/ui`. | Marketing pages that use hash sections mount it. Already the kit; do not reimplement. |
| Kit promotion pattern | Module grid moved to `packages/ui` with a reference specimen and a settle gate. | Any new rail, pinned-nav mode, or ticker strip follows that path: kit + test + `apps/reference` specimen, then the site. |
| Short client pages | Security and about were cut hard on #4791. | digiquant prose pages (`/contact`, changelog lede, subsystem posters) stay short. One claim, the facts, the limit. |
| Honesty in the figure | Why-band copy deck says digiquant is the finance app's top box, not an infra layer. | Do not paste the why-band onto digiquant.io. Link to digithings.ai for the stack story. |
| Chris owns the look | PR #4791 body: visual iteration is Chris's; the PR is for review. | Same gate on every visual slice below. |

### 2.2 Do not copy

- The why band (`AppFirstSection`, three architectures, sticky invoice, mosaic, pipeline-on-tile). That is the digithings homepage argument.
- `SectionRail`'s hardcoded `SECTIONS` and the `~/digithings` prefix. Those are content, not the component.
- Opencode install chrome, FAQ morph, and `WordReveal` as a pinned claim. `WordReveal` may remain in the kit for digithings. digiquant home does not mount it.
- App-local landing components as the implementation style. `HeroMesh`, `HeroGraph`, `AmbientMesh`, `PipelineScene`, and `DashboardScene` are the "over the top" the 2026-09-20 direction already withdrew. Q1 deletes their use. Deleting the files is part of the home slice once nothing imports them.
- digichat embed, popup, or `/embed` protocol. The dashboard `DigichatPopup` stays mounted and unchanged.

### 2.3 Shared chrome, different dress

`NavShell` is already the shared top bar. digithings keeps `autoHide="scroll"`. digiquant marketing passes `autoHide="none"` once that value exists. Link arrays stay per site: `apps/digiquant-web/app/_nav.tsx` (`DQ_NAV_PRIMARY`, `DQ_FOOTER`) and the digithings nav module. One component, two link lists, two hide modes.

---

## 3. Q1 — digiquant.io page map

Package: `apps/digiquant-web`. Public origin `https://digiquant.io`. Plumbing that stays: `app/sitemap.ts`, `app/robots.ts`, `app/manifest.ts`, `public/_redirects`, static export, `lib/live/*` stale-vs-live contract, tearsheet print.

Home sections, in order, after the rebuild:

1. Pinned `NavShell` (`autoHide="none"`), brand from `_nav.tsx` (`TerminalMark` compact + wordmark `digiquant`).
2. One-line h1. Keep the factual claim already on the page: a quant research desk, open-source, self-hosted. Drop the three-line mesh hero and the "Scroll to explore" cue.
3. `StockTicker` via the existing `LiveTickerRow` (Coinbase plus equity majors). This is the hero artefact.
4. Four figures, single-sourced, as `Figure` + `StatCounter` / the existing `MetricsOdometer` data: subsystem count from `subsystems.length`, pipeline stage count from the `FLOW` array (7), published tearsheet trade count from the live index, live orders = 0. Caption states why live is zero: routing is off, venue tokens are refused.
5. Pipeline as a ruled list of those 7 stages (Research, Indicators, Strategy, Signals, Optimize, Backtest, Export). Export copy keeps "Live trading is not on yet." No keycap gallery. No scrolly scene.
6. Live book panel, existing `LivePortfolioPanel`, restyled as a hairline panel. Unavailable env renders the current "connects on deploy" empty state, not a fake book.
7. Strategy suite linking into `/strategies` and `/strategies/[id]`.
8. Pricing: the three tiers in `app/_pricing.ts` unchanged in facts (Self-hosted Free, Managed Coming soon, Enterprise Contact) rendered with `PricingTierCard`. FAQ accordion from `PRICING_FAQ`.
9. `ContactMailto` to `contact@digiquant.io`. `Footer` + `Colophon` with `DQ_FOOTER`.
10. `SectionRail` only if the page still has four or more bands after the cut. Short pages omit it.

| Route | Kit parts | Acceptance |
|---|---|---|
| `/` | `NavShell`, `StockTicker` (through `LiveTickerRow`), `Figure`, `StatCounter` or `MetricsOdometer`, `PricingTierCard`, `ContactMailto`, `Footer`, `Colophon`, optional `SectionRail`, `HashScrollManager` | No `HeroMesh`, `PipelineScene`, `AmbientMesh`, or `WordReveal`. h1 is one line. `FLOW` stage 07 still says live trading is not on. `python3 scripts/check_frontend_canon.py` exits 0. `next build --webpack` in `apps/digiquant-web` exits 0. |
| `/strategies` | `NavShell`, `Footer`, strategy cards already backed by `components/tearsheet/strategy-library.tsx` | Filter toggles keep working. Grid is a hairline table or card row, not a bento. |
| `/strategies/[id]` | `TearsheetView` and the finance family (`KpiStrip`, `ReturnsMatrix`, `LiveBadge`, print helpers in `packages/ui/src/components/finance-tearsheet`) | Print stylesheet still prints. `BacktestOnlyChip` and `OosHonestyChip` still render with the titles in `honesty.tsx`. "illustrative, in-sample" footer text stays. |
| `/subsystems/[id]` | `NavShell`, `Footer`, `StackRow`, `subsystems` from `@digithings/ui` | One poster per id `research`, `portfolio`, `execution`. Related links are chips to the other two. No Atlas / Hermes / Kairos strings in the rendered HTML. Redirects in `_redirects` still resolve. |
| `/changelog` | `NavShell`, `Footer`, release rows | Mono meta, no marketing hero. |
| `/contact` | `NavShell`, `Footer`, `ContactMailto`, pricing facts consistent with `_pricing.ts` | `/pricing` redirect to `/contact/` in `_redirects` still 301s. |
| `/pipeline` | unchanged redirect to `/#pipeline` | `public/_redirects` and the client fallback in `app/pipeline/page.tsx` both land on `/#pipeline`. |
| `not-found` | `NavShell`, `Footer`, two links (home, dashboard) | No orphaned mesh styles. |

Content width: data bands may run to 1200px. Prose blocks cap at 72ch. Do not introduce a new CSS file in the app for this; use kit utilities and, if a density wrapper is missing, add it under `packages/ui` and a specimen under `apps/reference/app/(gallery)/(finance)/`.

---

## 4. Q2 — dashboard chrome and the DB gate

Package: `apps/dashboard`. Served at `/dashboard/` (`basePath` in `apps/dashboard/next.config.mjs`). The shell is `AppFrame` (`apps/dashboard/components/app-frame.tsx`).

### 4.1 Explicit layout

`Sidebar` is `position: fixed` below the `md` breakpoint (off-canvas) and `md:relative` from 768px up, inside a `flex` row (`sidebar.tsx` class list: `fixed ... md:relative`). Width is 260px expanded and 72px collapsed (`md:w-[72px]` / `md:w-[260px]`).

The wave-3/4 critical regression was page content painting under that fixed sidebar. The contract to lock:

- At `≥ md`, the aside participates in the flex row (`md:relative`). The main column is the flex sibling (`flex-1 min-w-0`). There is no second offset (no `ml-[260px]` that drifts from the collapsed width).
- Below `md`, the aside is off-canvas until `mobileNavOpen`. Main is full width. The open sidebar overlays; it does not push content.
- `AppFrame` owns the only `<main>` landmark for the shell. Page bodies do not add another.

Bloomberg dress of this shell (panel rules, mono labels, pinned command strip) is the visual slice V-Q2. The contract above is mechanical and lands first so the restyle cannot reintroduce the overlap.

### 4.2 Honest unavailable panel

`DbUnavailable` (`apps/dashboard/components/db-unavailable.tsx`) already says "Live data is temporarily unavailable" and tells the owner to reload or check back. The Retry button calls `window.location.reload()`. Copy must stay that honest. The component must not say the dashboard reconnects by itself: `dbStatus` in `apps/dashboard/lib/dashboard-context.tsx` is one fetch on mount.

Gate rule in `AppFrame`:

```tsx
const gated = dbStatus !== 'ok' && !isDbExempt(pathname);
```

When `gated` is true, `DbUnavailable` replaces `children` **inside** `<main>`, after `MobileAppBar`. `Sidebar`, `CommandPalette`, and `DigichatPopup` stay mounted.

### 4.3 `/pipeline` exemption

`apps/dashboard/lib/nav.ts` documents `/pipeline` as an operator surface that stays live when the backend is down. `DB_EXEMPT_PREFIXES` does not include it. `apps/dashboard/lib/nav.test.ts` pins the opposite (`isDbExempt('/pipeline')` is `false`).

Q2 makes the comment true and updates the test in the same change. The pipeline page then renders its own empty or stale state for missing runs. The shell must not swap it for `DbUnavailable`. Run health has to stay reachable when the book database is down.

Prefixes that stay exempt (already, keep them): `/system`, `/settings`, `/twelve-x`, `/architecture`, `/library`, `/observability`, `/performance`, `/research`, `/strategy`, `/portfolio/theses`, `/house`.

Prefixes that stay gated, and therefore show the honest panel: `/` (Brief), `/portfolio` (the prefix match must not treat `/portfolio/theses` as gating the parent — existing test), `/why`, and the data subroutes `/portfolio/ledger`, `/portfolio/attribution`, `/portfolio/performance`, `/portfolio/tickers`, `/portfolio/period`.

`/portfolio/theses` stays exempt because the hub redirects and the `?thesis=` reader must not be swallowed. That is the existing #1760 static-export constraint.

Auth routes (`/login`, `/signup`, `/auth/callback`) are outside `AppFrame`'s data gate (`AuthGate`). Do not put the unavailable card on them.

### 4.4 Mechanical test (Q2-M)

File: `apps/dashboard/lib/nav.test.ts`. Change the gate assertion that currently expects pipeline to be gated:

```ts
it('keeps the pipeline operator surface live when the backend is down', () => {
  expect(isDbExempt('/pipeline')).toBe(true);
  expect(isDbExempt('/pipeline/anything')).toBe(true);
});

it('gates the data-backed surfaces', () => {
  expect(isDbExempt('/')).toBe(false);
  expect(isDbExempt('/portfolio')).toBe(false);
  expect(isDbExempt('/why')).toBe(false);
});
```

`DB_EXEMPT_PREFIXES` gains `'/pipeline'`. The comment and the array then agree.

File: `apps/dashboard/components/db-unavailable.test.tsx` (new). Render `DbUnavailable` and assert the title string `Live data is temporarily unavailable`, the body does not match `/reconnect automatically/i`, and the button text is `Retry`.

File: `apps/dashboard/components/app-frame.contract.test.tsx` (new). Read the sidebar and frame sources (same style as other dashboard source contracts) and assert the aside class string contains `md:relative`, the frame root contains `flex min-h-screen`, and `app-frame.tsx` contains exactly one `<main`.

Run: `cd apps/dashboard && npx vitest run lib/nav.test.ts components/db-unavailable.test.tsx components/app-frame.contract.test.tsx`

Expected before the prefix edit: the new pipeline test fails. Expected after: all three files pass.

---

## 5. Q3 — dashboard surfaces

Route inventory under `apps/dashboard/app`. Paths are app-relative; the browser path prefixes `/dashboard`.

### 5.1 Live surfaces (Bloomberg density, behavior unchanged)

| Route | What it is | Q3 note |
|---|---|---|
| `/` | Brief (`DailyBriefWorkspace`) | Gated. Dense KPI strip, tabular figures, provenance badges from `lib/live-valuation.ts` (`live` / `close` / `unavailable`). Never render 0 for an unavailable mark. |
| `/portfolio` | Portfolio shell | Gated. Tabs stay. |
| `/portfolio/ledger` | Ledger | Gated. |
| `/portfolio/theses` | `?thesis=` dossier, else redirect to `/portfolio?tab=theses` | Exempt. Keep the static-export single page (#1760). |
| `/portfolio/attribution` | Attribution | Gated. Remove the nested `<main>` in `app/portfolio/attribution/page.tsx`. |
| `/portfolio/performance` | Tearsheet | Gated. In-sample wording stays. |
| `/portfolio/tickers` | Ticker dossier | Gated. Remove the nested `<main>` in `components/portfolio/tickers/TickerDossierView.tsx`. |
| `/pipeline` | Decision graph | Exempt after Q2. Compact command band stays; h1 stays `sr-only` so the static export still has one (`check-static-export`). |
| `/why` | Reasoning surface (`WhyClient`) | Gated. Real page, not a redirect. Sidebar already treats `/why` as Pipeline-active (`routeActive` in `sidebar.tsx`). Do not delete the route in this epic. |
| `/settings` | Settings | Exempt. |
| `/house` | House identity chrome | Exempt. Corpus sample keys fail soft. |
| `/login`, `/signup`, `/auth/callback` | Auth | No data-gate card. No visual experiment on the OAuth callback. |
| `/settings/brokers/callback` | Alpaca OAuth return | **Out of visual scope.** Behavior stays. |

### 5.2 Redirects (must keep working, must stay exempt so the gate cannot swallow them)

| Route | Lands on | Source |
|---|---|---|
| `/system` | `/pipeline` | `app/system/page.tsx` |
| `/architecture` | Pipeline (via the system redirect chain) | `legacy-spa-redirect.tsx` `ArchitectureToSystemRedirectPage` |
| `/observability` | `/pipeline` (query preserved) | `ObservabilityToSystemRedirectPage` |
| `/library` | Pipeline node (date, docKey preserved) | `LibraryToWhyRedirectPage` |
| `/research` | Pipeline (date preserved) | `ResearchToWhyRedirectPage` |
| `/performance` | `/portfolio/performance` | `PerformanceToPortfolioRedirectPage` |
| `/portfolio/period` | `/portfolio/performance` | `PeriodToTearsheetRedirectPage` |
| `/strategy` | `/portfolio?tab=theses`, or thesis detail when `?thesis=` is set | `StrategyToAnalysisRedirectPage` |

The minor regression "nav destinations silently collapsing to `/pipeline`" is checked by reading these targets. `/portfolio`, `/why`, and `/twelve-x` must not join that list.

### 5.3 twelve-x

`/twelve-x` (sidebar label FX Hub) stays DB-exempt because it reads its own research feed (`isTwelveXConfigured`), per the comment in `nav.ts` (#1664). This epic does not restyle it. A later slice can apply the terminal dress after Q3. Product gate copy and invite behavior stay.

### 5.4 Regressions every Q3 slice re-checks

From the 2026-09-18 plan §8, still in force:

1. **Critical.** Content is not under the sidebar at 1280px expanded, 1280px collapsed, and 390px (drawer closed and open).
2. **Important.** With the backend unconfigured, Brief shows `DbUnavailable` inside main. `/pipeline`, `/settings`, `/house`, and `/twelve-x` still render their own pages. Redirect routes still redirect.
3. **Important (digithings, not this epic's code).** Do not reintroduce a `/openwiki` nav link on digiquant.
4. **Minor.** Control labels use the kit mono, not a second type stack. No tall empty footer band on digiquant marketing pages (Q1). Nested `<main>` count in dashboard pages is zero.

---

## 6. Parallelism

```
#4791 digithings (D1) ── must land first
        │
        ├─ R1 kit (rail promotion, NavShell autoHide="none", reference specimens)
        │     └─ Q1 visual pages (need R1)
        │
        ├─ M-claims  digiquant claim inventory (no UI)     ─┐
        └─ M-shell   Q2 layout + /pipeline exempt tests    ─┴─ may run once #4791
                                                              has merged, beside R1
Q1 Chris sign-off
        └─ V-Q2 dashboard terminal dress (needs M-shell)
              └─ Q3 live surfaces
                    └─ C1 audit on the rebuilt pages, then C2 export certification
```

After digithings lands, and not before:

| Work | Needs R1? | Why |
|---|---|---|
| M-claims | No | Reads `_pricing.ts`, `FLOW`, `honesty.tsx`, sitemap. Writes a checklist. No components. |
| M-shell | No | Dashboard shell is not the marketing nav. Locks the sidebar contract and the pipeline exemption before any visual pass. |
| R1 | It is R1 | Rail and pinned-nav mode must exist in the kit or Q1 will grow an app-local family and fail the canon guard. |
| Q1 pages | Yes | They import `NavShell` pinned mode and `SectionRail`. |
| V-Q2 / Q3 | No (they need M-shell, and they wait for the Q1 Chris gate because the owner sequence puts the dashboard after marketing) | Dashboard chrome is its own shell. It does not wait on the marketing rail. It does wait on the sequence. |

Do not start Q1 against the #4791 branch tip while that branch is still rebasing. Shared chrome extracted early will fork.

---

## 7. Slice breakdown

Two kinds of slice.

**OpenCode package (mechanical).** An agent session can finish it without a visual opinion. Each package has a failing test, the files listed, and the gates below. Commit style `test:` then `feat:` / `fix:` per the repo convention. Branch from current `origin/develop` (or the module base the routing file requires — these are `component:website` / dashboard frontend and route to `develop`).

**Chris visual gate.** One agent sets the branch up: kit or page composition, `next dev` for that app, a short note of what to look at (route, theme, width). Chris validates locally in Cursor. The slice is not merge-ready on CI green alone. Dark and light, desktop (≥1280) and narrow (390).

Order:

| # | ID | Kind | PR delivers | Depends on |
|---|---|---|---|---|
| 0 | DOC | docs | This plan. | — |
| 1 | D1 | already open | #4791 merges. Not this plan's PR. | Chris on digithings. |
| 2 | M-claims | OpenCode | `docs/superpowers/plans/2026-09-30-digiquant-claim-inventory.md` listing every numeric claim on the Q1 routes, the file that sources it, and the date checked. No app code. | D1 merged only so the worker is not editing a stale tree. The inventory can be drafted read-only before that. |
| 3 | M-shell | OpenCode | `/pipeline` in `DB_EXEMPT_PREFIXES`, nav test updated, `DbUnavailable` render test, frame/sidebar contract test. No class-name restyle. | D1 merged. Parallel with R1. |
| 4 | R1 | OpenCode + one Chris look at the reference gallery | `SectionRail` in `packages/ui` (props: `sections: {id, label}[]`, `pathPrefix?: string`). Specimen on `apps/reference` chrome route. `NavShell` `autoHide="none"`. digithings switched off the app-local rail in a follow-up only if #4791 did not already promote it. | D1 merged. |
| 5 | V-home | Chris gate | Q1 `/` composed per §3. Delete unused mesh imports. | R1. |
| 6 | V-strategies | Chris gate | `/strategies` and `/strategies/[id]` including print and honesty chips. | R1. Can follow V-home. |
| 7 | V-rest | Chris gate | `/subsystems/[id]`, `/changelog`, `/contact`, `not-found`, pipeline redirect check. | R1. |
| 8 | V-Q2 | Chris gate | Dashboard shell dress on top of M-shell. Sidebar, brief unavailable panel, pipeline still reachable with the backend unset. | M-shell, and Chris has accepted V-home (sequence). |
| 9 | V-Q3a | Chris gate | Brief, portfolio, performance, attribution, tickers. Nested mains removed. | V-Q2. |
| 10 | V-Q3b | Chris gate | Pipeline graph chrome, why, settings, house, login/signup. No broker callback edits. No twelve-x restyle. | V-Q2. |
| 11 | C1 | OpenCode | Dated checklist per public digiquant page. M-claims updated against the shipped copy. | V-home, V-strategies, V-rest. |
| 12 | C2 | OpenCode + Chris skim | Both exports build. Links resolve. Sitemap matches routes. No placeholder copy. | C1. |

Gates on every code slice:

```bash
python3 scripts/check_frontend_canon.py
cd apps/digiquant-web && npx tsc --noEmit
cd apps/dashboard && npx vitest run lib/nav.test.ts
```

Add the app's `next build --webpack` on slices that touch that app's `app/` tree. digiquant-web also runs its vitest project (`npm test` in that package) when tearsheet or landing modules change.

Review: each code PR gets a fresh-context review file beside this plan, `docs/superpowers/plans/review-2026-09-30-digiquant-<slice>.md`, then the `<!-- in-session-review -->` comment and `reviewed:agent` when the policy requires a hatch. Author session does not review its own slice.

UI workflow, repeated because it is the whole point of the visual rows:

1. One agent opens the branch, wires kit parts, and starts the dev server (`apps/digiquant-web` or `apps/dashboard`).
2. The PR description lists the routes and the two viewports.
3. Chris validates locally in Cursor.
4. Only then does the slice count as accepted. Mechanical packages skip step 3.

---

## 8. Content and honesty constraints (digiquant)

Single-sourced. If the source file changes, the page changes. Do not hardcode a second copy.

| Claim | Source | Rule |
|---|---|---|
| Subsystem count | `subsystems` in `@digithings/ui` (`research`, `portfolio`, `execution`) | Render `subsystems.length`. |
| Pipeline stages | `FLOW` in `apps/digiquant-web/components/landing/ResearchPipeline.tsx` | Seven stages. Stage 07 body keeps the sentence that live trading is not on and venues wait on a human gate. Optimize stage keeps "in-sample." |
| Live orders | Literal 0 | Routing off, venue tokens refused. Do not replace with a projection. |
| Tearsheet performance | Strategy series + `honesty.tsx` | `Backtest only` chip. `Not OOS vs flat DCA` when out-of-sample does not beat flat DCA. No badge that calls a full-sample backtest a win. |
| Pricing | `apps/digiquant-web/app/_pricing.ts` | Free / Coming soon / Contact. No invented caps. FAQ already says no artificial request caps on self-host. |
| Nautilus | FAQ entry in `_pricing.ts` | "builds on NautilusTrader (open source) for all backtest, optimize, and live paths" is the license pointer, not a claim that live trading is switched on. Keep both sentences. |
| Names | — | lowercase digi names. No Olympus, Atlas, Hermes, Kairos in rendered copy. Redirects in `public/_redirects` remain. No private client names on marketing or dashboard chrome. |
| Dashboard marks | `lib/live-valuation.ts` | `unavailable` renders an em dash, never 0. `close` is labeled close. Live badge only when `source === 'live'`. |

C1 re-checks the 2026-09-18 §7 numbers that appear on digiquant pages (strategy honesty, two-tier vs three-tier pricing — the live source is three tiers in `_pricing.ts`; the older two-card `/contact` copy must be reconciled in V-rest, not left contradicting the homepage). SDCA knees `25/70` stay only if a tearsheet still sources them from the strategy record. Do not retype them into marketing prose.

---

## 9. Defer list

- **digichat product.** `apps/digichat`, `packages/digichat-ui`, embed protocol, dashboard `DigichatPopup` behavior. Untouched.
- **twelve-x / FX Hub visual.** Route stays. Restyle is a later epic slice.
- **digithings.ai page tree.** Owned by #4791 and the 2026-09-18 plan's D1. This plan consumes its chrome lessons after merge.
- **Amber-for-phosphor token swap.** Not in R1. Open question 1.
- **Hero product screenshot.** Not in V-home.
- **Broker OAuth and `digiquant/brokers/`.** Human gate. Not in any slice here.
- **`digikey/`.** Human gate.
- **New external host, font CDN, or analytics.** No. Geist Mono stays self-hosted via `next/font`.
- **Gloomberb attribution in chat.** Separate plans. Do not fold `term.gloom.sh` into this UI epic.
- **Release-please.** Not this work.

---

## 10. Open questions for Chris

1. **Accent.** Keep `--accent-digiquant` (phosphor) as the digiquant identity and `--warn` as the function/attention amber, or replace the phosphor with a terminal amber in `tokens.css` for digiquant-scoped surfaces only? This plan keeps the phosphor until you say otherwise.
2. **Marketing theme default.** Dashboard stays dark-first. Should digiquant.io open in dark as well, or keep "follow the OS" the way the dashboard theme script does?
3. **`/why` on the dashboard.** It is still a real page, and the sidebar highlights Pipeline when you are on it. Leave the route (this plan) or fold it into `/pipeline` in a later issue?
4. **M-shell before Q1.** The plan lets the sidebar contract and the `/pipeline` exemption land beside R1, before the marketing visual gate, because they are bug contracts. Say if you want every dashboard diff to wait until Q1 is accepted.
5. **Section rail on digiquant.io.** Promote it and use it on the home page only when four bands remain, or skip the rail on the marketing site entirely and keep it a digithings-only pattern?
6. **#4791 merge bar.** Confirm digiquant waits for that PR to merge, not merely for a design freeze on the branch.

---

## 11. Definition of done (the epic, not this docs PR)

- digithings #4791 has merged.
- R1 is in the kit: pinned nav mode and a prop-driven section rail, with reference specimens and tests.
- digiquant.io routes in §3 render from kit parts, canon guard green, meshes gone, honesty copy intact.
- Dashboard content clears the sidebar at the widths in §5.4. `/pipeline` is exempt. Gated routes show the honest panel inside main.
- Q3 nested mains are gone. Redirects in §5.2 still redirect. twelve-x and digichat are visually untouched.
- C1 checklist is dated. C2 exports build.
- None of §5.4 regressions reproduce. Dark and light checked by Chris on the visual slices.
