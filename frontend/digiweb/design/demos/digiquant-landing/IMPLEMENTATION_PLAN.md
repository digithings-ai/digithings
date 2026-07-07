# Port the v7 design language into the real digiquant-web app

## Context
We iterated a self-contained HTML prototype (`frontend/digiweb/design/demos/digiquant-landing/07-scroll-driven.html`) into a locked design direction for **digiquant.io**: a centered editorial "A quant hedge fund. In a box you own." hero over a mouse-following mesh-gradient, a scroll-pinned **Olympus** pipeline (Atlas → Hermes → Kairos, real phases, one continuous horizontal track, Kairos "in development"), a **vertical tearsheet** strategy suite on the **real** BTC/ETH/SOL Slapper backtests, lowercase **digiquant** branding with the **QR** mark, and an open-source closing section. The real Next.js app (`frontend/digiquant-web`) still ships the old, rejected "headline-left + chart-right + marquee ticker + pricing" home. This change replaces the real app's design language with v7, across all pages.

Decisions (confirmed with user):
- **No live tape / no live market prices this round.** Ship the v7 design without any live data. (If revisited later, source = the project's Supabase `price_history` table — daily OHLCV, anon-readable, same client pattern as `frontend/olympus/lib/supabase.ts`. Out of scope now.)
- **Whole-site port** (home + pipeline + strategies + tearsheet + subsystems).
- **All changes stay inside `frontend/digiquant-web/`.** Do NOT edit `@digithings/web` or `@digithings/design` — they are shared with **digithings.ai** and must not change. The design tokens there already match v7 exactly (`--accent #3DD6C4`, `--up`, `--down`, `--bg #0B0C0E`, Geist sans/mono), so v7 is expressible without touching shared CSS.

Already done in prior steps (verify, don't redo): `public/favicon-qr.svg` + `-light.svg` now encode `https://digiquant.io`; the `Brand` component (`app/_nav.tsx`) already renders lowercase `digiquant` + the QR mark; `layout.tsx` already wires the QR favicon with light/dark variants.

## Approach
Build v7 as a set of **digiquant-local client components** (canvas + scroll effects need the browser; everything is `"use client"` with effects, safe under Next static export and `prefers-reduced-motion`). Reuse the existing tokens, `Reveal`/`MotionProvider`, `Brand`, the real strategies JSON, and `TearsheetView`. Rewrite the pages to compose the new components. Keep the shared `Footer`; replace the shared `Nav` usage with a digiquant-local scroll-aware nav (the shared `Nav` is not scroll-aware and is used by digithings, so we don't alter it).

### New components — `frontend/digiquant-web/components/landing/`
- `HeroMesh.tsx` — full-bleed `<canvas>` animated mesh gradient that eases toward the cursor and parallaxes/fades on scroll; static calm fallback under reduced motion. (Port of v7 mesh + mouse-follow.)
- `DqNav.tsx` — scroll-aware top nav: transparent at top, blurred bg once scrolled, auto-hide on scroll-down / reveal on scroll-up. Uses `Brand` (QR + lowercase digiquant), real links, GitHub + "Open Olympus" CTAs. No "Sign in". Used on every page.
- `PipelineScene.tsx` — scroll-pinned Olympus pipeline: one continuous lerp-smoothed horizontal track of the **real** phases (Atlas `atlas/phases/*`: preflight→triage→alt-data→institutional→macro→asset-class→equities→consolidate→synthesis→publish; Hermes `hermes/phases/*`: h1 thesis review → … → h6 deliberation → h7 PM direction/risk sizing → h9 commit), crossfading engine headings, an Olympus logo, dwell windows per engine, and Kairos marked **"In development."** rAF lerp + `IntersectionObserver`.
- `StrategySuite.tsx` — vertical scrollytelling: the real `public/strategies/index.json` entries (BTC/ETH/SOL Slapper) on the left, a sticky tearsheet card on the right that swaps on scroll/click (equity curve + trade markers + real KPIs via `components/tearsheet/format.ts`), each linking to `/strategies/<id>`.

### Pages — `frontend/digiquant-web/app/`
- `page.tsx` — rewrite to: `<DqNav/>` + `<HeroMesh/>`/centered hero + `<PipelineScene/>` (id `#pipeline`) + `<StrategySuite/>` (id `#strategies`) + open-source/pricing CTA + `<Footer/>`. Remove the old hardcoded `TICKER`, the `dq-tickerbar`, the headline-left/chart-right hero, and the mini-flow. Keep the real "Open core (free) / Managed Atlas" pricing content but restyle into the new closing section.
- `pipeline/page.tsx`, `strategies/page.tsx`, `subsystems/[id]/page.tsx` — swap shared `<Nav>` for `<DqNav>`, apply the new section/type styling. `strategies/[id]/page.tsx` keeps `TearsheetView` (real data) under `<DqNav>` with restyled chrome.
- `layout.tsx` — update metadata to lowercase brand ("digiquant — a quant hedge fund in a box, …"), OG title/description; keep ThemeProvider/MotionProvider/grain/glow and the QR favicon. Rename remaining "DigiQuant" copy → "digiquant".

### CSS — `frontend/digiquant-web/app/globals.css`
Replace the digiquant-specific blocks (old `.hero-*`, `.dq-tickerbar`, `.dq-ticker*`, `.dq-mini-flow`, hero `.panel`) with the v7 classes (mesh hero, `.ehead`/`.steps`/`.step` pipeline, `.ts-*` vertical suite, scroll-aware `.nav` states). Consume existing tokens only; do not redefine colors. Keep the existing `.ts-*` tearsheet classes used by `TearsheetView`.

## Reuse (do not rebuild)
- Tokens/theme: `@digithings/design/tokens.css` (already matches), `Reveal`/`MotionProvider`/`EASE` from `@digithings/web` for simple reveals.
- `Brand`, `DQ_NAV`, `DQ_FOOTER`, `DQ_FOOTER_META` in `app/_nav.tsx` (update link targets; brand already correct).
- Real data: `public/strategies/index.json` + `*_slapper.json`; `components/tearsheet/{format.ts,types.ts,tearsheet-view.tsx,charts.tsx}`.
- Real pipeline phase names from `digiquant/src/digiquant/olympus/{atlas,hermes}/phases/`.
- The working v7 reference: `frontend/digiweb/design/demos/digiquant-landing/07-scroll-driven.html` (port its CSS/JS into React).

## Out of scope
- No edits to `@digithings/web` / `@digithings/design` (would affect digithings.ai).
- No live prices / tape wiring; no new API routes or Supabase calls.

## Verification
1. `npm install` in the worktree if needed, then `npm --workspace frontend/digiquant-web run dev` via the existing `digiquant-web` launch config (port 4011); preview_screenshot the home, `/pipeline`, `/strategies`, a `/strategies/<id>` tearsheet, and a `/subsystems/<id>` page at desktop + mobile; verify scroll-pinned pipeline advances Atlas→Hermes→Kairos, the mesh follows the cursor, the strategy suite swaps tearsheets, and no console errors.
2. Confirm digithings.ai is untouched: `git status` shows no changes under `frontend/digiweb/web`, `frontend/digiweb/design`, or `frontend/digithings-web`.
3. `npm --workspace frontend/digiquant-web run build` (static export) succeeds; check `out/index.html`, `out/strategies/btc_slapper/index.html`, `out/subsystems/atlas/index.html` exist.
4. Per CLAUDE.md before PR: `ruff`/lint not relevant (frontend), run `make score` on staged changes (Security/Quality/Optimization/Accuracy gate) and update `frontend` docs if an interface changed. Work stays on the current worktree branch.
