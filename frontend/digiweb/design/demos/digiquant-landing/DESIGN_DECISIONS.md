# Frontend Polish Loop — living punchlist

Goal: refine all frontend pages across **digithings.ai** and **digiquant.io** to
elite, production-grade quality (Hermès / Linear / Vercel / Anthropic tier).
Variable-first, shared components, intentional spacing, no AI-slop tells.

## Canonical sources (deployed)
- digithings.ai → `frontend/digithings-web` (Next.js static export)
- digiquant.io  → `frontend/digiquant-web` (+ `frontend/olympus` at `/olympus`)
- Shared design system → `frontend/digiweb/design` (tokens.css, site/site.css, components.css)
  and `frontend/digiweb/web` (`@digithings/web` — ThemeProvider, web-theme.css)
- LEGACY / not deployed: `frontend/digithings`, `frontend/digiquant` (old static HTML)

## Pages
- digithings-web: `/` (page.tsx), `/chat`, `/architecture`, `/modules/[id]`
- digiquant-web: `/` , `/pipeline`, `/strategies`, `/strategies/[id]`, `/subsystems/[id]`
- olympus: dashboard (separate audit later)

## Audit checklist (per user)
- [ ] favicon = actual QR code on BOTH sites — DONE for digiquant (was generic /favicon.svg)
- [ ] background gradient (.glow) extends to page edges, no clipping
- [ ] section spacing not excessive / inconsistent — audit shared `site.css` section padding
- [ ] standardized shared components used everywhere (no per-page reinvention)
- [ ] every element has purpose/intent — kill decorative filler
- [ ] responsive + light/dark parity
- [ ] create demo artifacts for visual review when unsure

## Done
- [x] digiquant-web favicon now uses real QR (`/favicon-qr.svg`) with light/dark
      variants via prefers-color-scheme (layout.tsx). digithings already correct.

## Dev server setup (IMPORTANT — do this before previewing)
- Worktree needs `npm install` once (no node_modules → @digithings/web, geist fail to resolve).
- launch.json configs added: `digiquant-web` (port 4011), `digithings-web` (port 4012).
- Use preview_start with those names — NOT the auto-detected Python backend.
- The "Failed to patch lockfile / pnpm" error in logs is non-fatal Next.js noise; ignore.

## Verified
- digiquant.io favicon QR mark now renders in nav (was generic). ✓ live on :4011

## Triage notes (to address)
- Homepage hero: large vertical gap between nav and the `$ open core` badge — check
  hero top padding / section rhythm (candidate for the "spacing too large" issue).

## DESIGN BRIEF (from user, 2026-06-26) — the real direction

**North-star references (2026-06-29):** Deep scans + evolution paths live in
[`frontend/digiweb/design/references/`](../references/README.md) and
[`frontend/digiweb/design/EVOLUTION.md`](../EVOLUTION.md) — Graphite (scroll/motion),
Cursor (utilitarian bento), x.ai (brutalist dashboard/API). Read before the next
landing or Olympus/twelve-x pass.

Sequencing decision: **system-first** (scroll-aware header, section primitives, motion
tokens applied globally) THEN per-page creative. Landing pages can "go crazy";
Olympus + 12x dashboard stay professional/utility-focused.

Concrete directives (current sites FAIL these):
1. Hero is generic AI cliché — "small headline + buttons + chart on the side", same on
   digiquant & digithings & every AI site. Make it ORIGINAL, themed to quant/quantitative
   finance. Facilitate VISUALIZING the tool (pipeline, strategies) — captivating.
2. Ticker of daily prices is simulated & useless → WIRE TO REAL DATA: the price-table
   pipeline + actual Olympus portfolio returns. (Verify data source: Supabase price tables
   + Olympus portfolio; see massive-market-data MCP / Supabase.)
3. Scroll-aware header (ALL pages): (a) gets solid bg when scrolled (currently unreadable),
   (b) auto-hides on scroll-down, reappears on scroll-up / near top.
4. Section rhythm: currently just bg tint + title + boxes. Add branded MOVING/interactive
   visual elements, real section transitions. Make it captivating, on-brand.
5. Creativity by surface: landing = creative/bold; Olympus + 12x dashboard = professional.

### In progress: 4 throwaway art-direction demos (parallel subagents) for digiquant.io landing
Output dir: frontend/digiweb/design/demos/digiquant-landing/
- 01-bloomberg-terminal.html  (data-dense terminal)
- 02-linear-vercel.html        (premium dev-tool)
- 03-generative-data-art.html  (live canvas viz hero)
- 04-editorial-brand-forward.html (editorial/Hermès restraint)
Next: screenshot each, present to user, user picks ONE → becomes the brand direction →
write design doc/spec → writing-plans → implement system-first, then propagate.

## DIRECTION CHOSEN: BLEND of all 4 (user, 2026-06-26) — "create a mix + keep iterating"
Not one direction — fuse Terminal + Generative + Editorial. Blend tags selected:
+Terminal ticker/data, +Generative canvas accent, +Editorial typography.

Synthesis spec (drives 05-blend.html and ultimately the real build):
- IDENTITY: terminal-grade information density + editorial refinement, dark tokens.
- HERO: NOT a single oversized headline (that's the generic AI tell — explicitly reject).
  Instead a composed, information-rich "cockpit" hero (concise statement + live data
  panels + moving chart lines). Editorial styling but SMALLER headers.
- TICKER: pinned at the VERY top, stays visible ("the life remains at top"); a bit wider.
- HEADER: scroll-aware; when it retracts it must collapse ALL THE WAY to top (no gap);
  bar a bit wider; reappear on scroll-up/near-top.
- MOTION (do MORE): chart lines animating across the page; scroll choreography so the
  site "comes alive and takes shape" — ASYMMETRIC (e.g. right column static/pinned while
  left animates in/out; elements translate/assemble on scroll). Generative canvas accent
  (equity curves/order flow), subtle + performant. Respect prefers-reduced-motion.
- PRODUCT EMBEDS (reuse Olympus — DO NOT duplicate code; demo simulates, real build wires):
  * Pipeline = the ACTUAL Olympus research pipeline (Atlas→Hermes→Kairos); clickable
    stages; selecting one shows LIVE RESEARCH to read.
  * Strategies: SHORTER; rows with ASSET LOGOS (Bitcoin/ETH/etc.); clicking opens a
    TEARSHEET SIDE PANEL (slides from right) with live price chart + last few trades marked
    (entries/exits, long/short) + KPIs.
  * Ticker wired to REAL data (price-table pipeline + Olympus portfolio returns).
- Olympus + 12x dashboard stay professional (creativity is for the landing).

Artifacts so far: frontend/digiweb/design/demos/digiquant-landing/01..04 (screenshotted, reviewed).
DONE: 05-blend.html built by me (subagent hit session limit) + verified (no console errors,
desktop 2-col cockpit hero + stacked mobile, all components mount). Awaiting user reaction.
Open items to push next per brief: harder ASYMMETRIC scroll motion (left moves / right pinned),
confirm header sizes, then lock direction → spec → implement.
Next: build 05-blend.html, screenshot, present, ITERATE. Then spec → writing-plans →
implement system-first (header/section/motion primitives) reusing Olympus components.

## ITERATION LOG / north star (2026-06-26)
- v5 (left headline + right graph) → REJECTED (the generic AI cliché).
- v6 (centered thesis over full-bleed market field + Linear showcase) → REJECTED ("still not it").
- KEY INSIGHT: user wants MOTION-FORWARD, SCROLL-DRIVEN, immersive (Awwwards-tier). The page
  must TRANSFORM as you scroll — not a static layout with fade-ins. Confirmed references to
  emulate (ALL aspects — layout, motion, hero visual, typography):
  Stripe (animated mesh gradient + scroll motion), Linear (scroll-pinned product scenes),
  Anthropic/Hermès (editorial restraint, craft), Awwwards generative (WebGL/scrollytelling).
- User consistently likes: the top live TAPE; disliked: oversized single headline, side-by-side
  hero, "title + boxes", anything that feels templated/static.
- v7 plan: scroll-driven concept — Stripe-style animated gradient hero that reacts to scroll;
  scroll-PINNED scene where Atlas→Hermes→Kairos assemble as you scroll through; smooth-scroll
  feel; editorial type; keep tape + strategies/tearsheet. Self-contained (no external libs).
- Build artifacts in frontend/digiweb/design/demos/digiquant-landing/ (06-frontier.html exists; next 07).

- v7 (07-scroll-driven.html) BUILT + verified: Stripe-style animated mesh-gradient hero that
  reacts to scroll (parallax/fade); scroll-PINNED scene where Atlas→Hermes→Kairos assemble as you
  scroll (rail fill + stage cross-fade, verified railFill 50%/stage1 at p=0.5); editorial type;
  tape + strategies/tearsheet kept. NOTE: preview_screenshot can't capture scrolled states (black
  frame desync) — verify scrolled sections via DOM eval, not screenshots. Follow-up if kept: boost lede
  contrast over bright gradient center. Awaiting user reaction to the scroll-driven register.

## COPY / POSITIONING LOCKED (user, 2026-06-26): "quant hedge fund in a box"
Positioning: a PERSONAL, AI-run, self-hostable quant hedge fund — institutional-grade quant made
accessible/cheap to anyone, self-hosted, AI-driven. Tone: technical/precise.
Chosen hero (wired into v7):
  Headline: "A quant hedge fund. <em>In a box you own.</em>"
  Lede: "The research-to-execution stack an institutional desk would build — Atlas researches,
  Hermes sizes the risk, Kairos executes on NautilusTrader. AI-driven, open-core and self-hosted,
  so a fund that used to need a team now runs for one."
Carry this "fund in a box for one" framing across all sections + digithings.ai where relevant.
Also fixed v7 lede readability over the mesh gradient (darkened veil center + text-shadow).

## v7 REFINEMENT ROUND (user, 2026-06-26) — 4 items
DONE: (1) QR for digiquant.io — segno-generated scannable QR encoding https://digiquant.io,
  3 variants in demos/ (qr-digiquant{,-light,-teal}.svg); wired correct QR into
  frontend/digiquant-web/public/favicon-qr.svg + -light.svg (replaced old). Phone-scan before prod.
DONE: (2) Hero hue follows mouse — mesh blobs ease toward cursor (hero-normalized), gentle (.045
  ease + .20 bias), trails down on scroll. In 07-scroll-driven.html. Verified.
DONE (3) PIPELINE rebuilt: horizontal Olympus pipeline, Olympus logo, zoom-per-engine. Verified:
  Atlas steps light 2→7 across its segment, Hermes zooms at p0.5, Kairos "In development" at p0.7+.
  Real steps wired (atlas 10 / hermes 9). Rail fills with progress.
DONE (4) TEARSHEETS rebuilt: vertical scrollytelling — 5 long/short strategies left, sticky
  tearsheet right (chart + trade markers + KPIs + last fills), IO-driven active on scroll + click.
  Verified switching. Removed dead slide-in #sheet markup. No console errors.
ALL 4 REFINEMENT ITEMS COMPLETE in 07-scroll-driven.html. Awaiting user review.
--- superseded follow-ups below (kept for history) ---
Follow-ups (next pass — big scrollytelling rebuilds):
  (3) PIPELINE = real Olympus pipeline, HORIZONTAL: embed Olympus logo; draw the FULL pipeline with
      all research sub-steps per engine. Scroll-pinned: when on Atlas, ZOOM IN to show Atlas's
      sub-steps; transitioning to Hermes, Atlas COLLAPSES + Hermes zooms in with its steps; same for
      Kairos. Kairos = mark "in development / coming soon" (not fully built yet). Keep the animated
      rail between the 3. Need real Atlas/Hermes step lists (check Olympus source:
      digiquant/src/digiquant/olympus/{atlas,hermes}).
      REAL STEPS (from atlas/phases + hermes/phases):
      ATLAS (research): preflight → triage → 1 alt-data → 2 institutional → 3 macro →
        4 asset-class → 5 equities → 6 consolidate → 7 synthesis → publish.
      HERMES (deliberate): h1 thesis review → h2 market-thesis exploration → h3 thesis→vehicle map →
        h4 opportunity screener → h5 asset analyst → h6 deliberation → h7 PM direction
        (+7e risk sizing) → h9 commit run (+ evolution).
      KAIROS (execute): IN DEVELOPMENT — show "coming soon", no sub-steps yet.
  (4) TEARSHEETS = VERTICAL scrollytelling (contrast the horizontal pipeline): strategies are a suite
      of long/short strategies; as you scroll, go strategy→strategy, each tearsheet pops up on the
      RIGHT; keep scrolling → next strategy + its tearsheet; ALSO clickable to select. Show real
      tearsheets. Two-direction dynamic (pipeline horizontal, tearsheets vertical).
  (5) lede readability over gradient — DONE (darkened veil + text-shadow).

## v7 CLEANUP — ALL DONE & VERIFIED (2026-06-26)
Hero decluttered (no NautilusTrader/eyebrow/scrollcue), live tape removed, brand=lowercase
"digiquant" + QR logo (qr-digiquant.svg), nav real (Pipeline/Strategies/Olympus↗ + GitHub +
Open Olympus, no Sign in), buttons → real routes (/olympus, github). Pipeline = ONE continuous
lerp-smoothed horizontal track, crossfading heads, engine dwell windows (Atlas 0-.42 / Hermes
.42-.80 / Kairos .80-1 "In development"), mask fade reduced so edge cards aren't hidden, trailing
spacer so last card centres. Strategies = REAL btc/eth/sol_slapper from index.json (Net +27M%/PF
8.66/Win 75.9%/DD -30.5% etc), tearsheet KPIs match real card, "View full tearsheet" → /strategies/<id>.
Open-core section → "Open source · MIT" with real GitHub/Olympus CTAs. No console errors.
NOTE: headless preview throttles rAF when idle (nav transition + pan loop look stuck in
screenshots) — verify scrolled behavior via DOM eval, not screenshots; it's smooth in a real browser.

## v7 CLEANUP PUNCH LIST (user, 2026-06-26) — execute all
HERO / declutter:
- Remove "NautilusTrader" from hero lede (too much detail for landing stage).
- Remove the eyebrow "open core · self-hosted · human-gated" (AI slop).
- Remove the "the loop" scroll cue.
- Remove the live tape from the top (user wants it gone now).
BRAND:
- Nav logo → the digiquant.io QR code mark (not the generated square glyph).
- Brand name = "digiquant" — SINGLE word, lowercase. (Update nav + footer.)
NAV:
- Header links must be REAL sections that exist + map to anchors; include "Olympus"
  (opens the Olympus dashboard). No fake links. Remove "Sign in" (no auth yet).
- Audit buttons: "Start a backtest", "Read the architecture", "Deploy a node" — only keep
  ones that are actually usable / point somewhere real; otherwise remove/replace.
PIPELINE (smoothness — Apple-like continuous scroll, currently jittery):
- Jitter: step highlight/pan jumps in discrete floor() steps → make pan CONTINUOUS (lerp/
  proportional translateX), not stepped.
- Mask fade hides edge boxes (e.g. "preflight" looks hidden when reached) → fix mask so steps
  aren't clipped/hidden.
- UNIFY the horizontal track: Atlas→Hermes→Kairos should be ONE continuous horizontal scroll in
  the SAME on-screen location; only the heading/label text changes as you cross into each engine.
  Track stays put & pans continuously across all steps → stable, unified, no jump between engines.
STRATEGIES / tearsheet:
- Wire REAL strategies (not generic BTC/ETH/SOL fake values). Use real names + values.
- Tearsheet should look like the ACTUAL tearsheet (the PDF-export one in
  frontend/digiquant-web/components/tearsheet/). Model demo on real tearsheet-view layout.
- Add real data shape so wiring later is trivial; no legacy/fake data leaking.
OPEN CORE section: user unsure what it is → reconsider/repurpose or make it a real
  open-source/GitHub section (meaningful, not vague).
GENERAL: whole-page scrolling must be smooth/continuous (Apple-like), no pausing/jitter.

## Next iterations
1. Read shared `frontend/digiweb/design/site/site.css` + `frontend/digiweb/web/styles/web-theme.css`
   — find the `.glow` gradient + section padding tokens. Fix edge-clipping + spacing.
2. Run a dev server (preview_start) on each site, screenshot every page at desktop +
   mobile, diff against the Hermès/Linear bar. Capture concrete defects with shots.
3. Triage homepage hero of each site first (highest-impact surface).

## 2026-07-01 — feature bento (#1214): additive, not a demotion

#1214's AC framed this as *demoting* scroll sections into a bento and keeping "only
one pinned section." Against the live landing that was stale + risky: digiquant.io
runs **two** intentional pinned scrollies — `OlympusScene` (the #1205 flagship, which
#1215 then *enhances* with a progress rail) and `StrategySuite` (#1198). Demoting
either regresses a good element. Per sign-off we went **additive**: a
`Pipeline · Strategies · Pricing` `.bento` after the hero (teal marketing accent, real
links to `#olympus` / `/strategies` / `#contact`), with **both** scrollies untouched.
Two pins is not the anti-pattern (#4 targets *five*). ProductFrame tearsheet crops
inside the cells remain a possible follow-up.

## #1226 — `/#pricing` (PricingMatrix + FaqAccordion)

The homepage `#contact` section was an ad-hoc two-card price block. Per Phase E we
**converted it into `#pricing`** using the shared `PricingMatrix` (`.pricing`) +
`FaqAccordion` (`.faq`) primitives (#1223): three honest open-core tiers —
**Self-hosted** (Free · MIT, CTA = existing `CloneRepoButton`), **Managed**
(featured, "Coming soon", waitlist), **Enterprise** (contact) — plus a pricing FAQ
(self-host requirements · NautilusTrader license · BYOK · **no fake usage caps**).
Copy is maintainer-approved and lives in `app/_pricing.ts` (source of truth). The
bento "// pricing" cell and the nav/footer link now target `#pricing` ("Contact" →
"Pricing"); Managed/Enterprise CTAs use `contact@digiquant.io`. The standalone
`/contact` route (+ `_contact.ts` two-tier copy) is intentionally left unchanged —
reconciling it to the 3-tier copy is a follow-up.
