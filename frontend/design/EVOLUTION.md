# DigiThings design evolution

**Status:** Living document · **Last updated:** 2026-07-02

> **⚠️ 2026-07-02 — landing wiring reverted (design review, #1308).** After review,
> the epic's live landing/redesign changes were reverted from digithings.ai and
> digiquant.io. **Kept:** the digiquant.io `/#pricing` + FAQ section (#1226) and the
> DqNav/DigiNav hydration fix (#1291/#1296). **Reverted:** digithings hero
> trust-strip + ProductFrame + 4-module bento (#1210/#1211), digiquant hero CTAs +
> trust-strip + stat row + feature bento (#1213/#1214), the closing-CTA wiring on
> both sites (#1227), the DigiChat `/welcome` route (#1218), and the Olympus status
> dot (#1231). The shared CSS/JS **primitives below still exist** in `frontend/design/`
> (unused except by `/#pricing`); the checklist marks reflect what was *built*, not
> what is currently wired live. See #1308.

This file synthesizes three external north stars — [Graphite](references/graphite.com.md),
[Cursor](references/cursor.com.md), [x.ai](references/x.ai.md) — with our current
implementation and sets **evolution paths** per surface. "Current implementation"
is two layers: `tokens.css` + `site/site.css` (shared CSS foundation — brand,
buttons, terminal block, sections, and the CSS-only primitives built here in
Phase B) consumed directly by the v7 landings (`frontend/digithings-web`,
`frontend/digiquant-web`), plus `@digithings/web` (the React component layer —
nav, hero layout, `Reveal` motion, connected graph) that those same apps import
for everything with real interaction/state. Vanilla-JS equivalents of the
latter (`site/theme.js`, `ui.js`, `reveal.js`, `terminal.js`, `graph.js`) were
removed as dead code in #1240 once an import-graph audit confirmed neither
landing referenced them.

**Deep audits:** [`references/scans/`](references/scans/INDEX.md) — page-by-page,
components, mobile nav (Playwright), copy patterns.

**Implementation backlog:** [GitHub epic #1200](https://github.com/digithings-ai/digithings/issues/1200) · [`docs/agent-backlog/design-evolution/INDEX.md`](../../docs/agent-backlog/design-evolution/INDEX.md)

**Copy & IA:** [`COPY_GUIDE.md`](COPY_GUIDE.md) — voice, literal CTAs, per-surface section maps.

It does not replace [`README.md`](README.md) (token API) or
[`demos/digiquant-landing/DESIGN_DECISIONS.md`](demos/digiquant-landing/DESIGN_DECISIONS.md)
(iteration log). It is the **strategic layer**: what we keep, what we borrow, what
we build next.

---

## 1. The three references in one sentence each

| Reference | Essence | Risk if copied literally |
|-----------|---------|--------------------------|
| **Graphite** | Motion-forward scroll storytelling with real product UI in dark frames | Page fatigue; orange/zinc is not our brand |
| **Cursor** | Light, scannable bento layout; product screenshots; literal CTAs | Loses our terminal/quant identity; too generic SaaS |
| **xAI** | Brutalist dark infrastructure; mono display; capability demos; no decoration | Too austere for digiquant storytelling; dark-only |

**Our blend:**

> **Cursor’s page map and section discipline.**  
> **Graphite’s one scroll story and motion craft.**  
> **xAI’s mono infrastructure voice on dashboards and API surfaces.**  
> **Our existing atmosphere** (mesh, grain, module accents, open-core honesty).

---

## 2. Current state (2026-06)

### What we already do well

| Pattern | Where | Reference overlap |
|---------|-------|-------------------|
| `[data-theme]` semantic tokens | `tokens.css` → all Next sites | Graphite surfaces, Cursor light |
| Scroll-pinned Olympus pipeline | `digiquant-web` PipelineScene | Graphite feature stack |
| Hero mesh + parallax | `HeroMesh.tsx` both landings | Stripe/Graphite atmosphere |
| Mono kickers `// section` | `site.css` `.kicker` | xAI eyebrows |
| Module accent palette | `tokens.css` `--accent-*` | Unique to us — keep |
| Terminal / CLI identity | DigiChat, manifests, `terminal.js` | xAI mono voice |
| Glass dashboard | Olympus | **Deprecate toward flat** (xAI) |
| Hamburger nav + persistent theme/GitHub | `DigiNav`, `DqNav` | Cursor mobile utilitarian |
| Shared primitives | `scroll-trigger`, `typography-motion`, `quant-native` | Graphite motion infra |

### Known gaps (vs references)

| Gap | Reference | Priority |
|-----|-----------|----------|
| No shared **bento feature grid** primitive | Cursor | High |
| No **ProductFrame** (CQ-scaled embed) | Graphite, Cursor | High |
| Hero lacks **literal primary CTA** + trust strip | Cursor | High |
| Multiple scroll sections without progress rail | Graphite | Medium |
| No unified **motion tokens** (`--ease-glide`) | Graphite | Medium |
| Inter still in legacy token docs | — | Medium → Geist everywhere |
| Olympus still glass-heavy | xAI | Medium |
| twelve-x not aligned to shared subpage chrome docs | Cursor tabs | Low |
| No changelog/news band on landings | Cursor | Low |

---

## 3. Surface matrix — which reference leads where

```
                    Graphite    Cursor    xAI
                    ────────    ──────    ───
digithings.ai         ◐          ●        ○
digiquant.io          ●          ◐        ○
digichat              ○          ●        ◐
Olympus dashboard     ○          ◐        ●
twelve-x              ○          ◐        ●
API / docs pages      ○          ◐        ●

● = primary influence   ◐ = secondary   ○ = light touch
```

### digithings.ai (`frontend/digithings-web/`)

**Mode:** Marketing + architecture story

| Keep | Borrow | Evolve toward |
|------|--------|---------------|
| Mesh hero atmosphere | Cursor hero layout (copy · CTA · trust · frame) | Bento module grid with UI crops |
| Module manifest interactivity | Graphite single scrolly for architecture | `ProductFrame` per module |
| Serif hero display (Fraunces) | xAI mono kickers only | Sans for all section h2+ body |
| Principles 4-up | Cursor testimonial band | Real quotes + GitHub stars |

**Evolution path (ordered):**

1. Hero: add primary CTA (`ask digichat` / `read docs`) + trust line; product frame with supervisor diagram or chat embed
2. Replace long architecture-only section with **bento** + one optional scrolly
3. Add changelog/releases band
4. Motion: `--ease-glide` on reveals only; reduce always-on mesh outside hero

### digiquant.io (`frontend/digiquant-web/`)

**Mode:** Marketing + quant product proof

| Keep | Borrow | Evolve toward |
|------|--------|---------------|
| Olympus scroll-pinned scene | Graphite progress rail on pin | **Only** pinned section on page |
| Tearsheets / real strategy data | Cursor bento for Pipeline · Strategies · Pricing | `ProductFrame` tearsheet crops |
| Fraunces hero | Cursor literal CTAs (`open olympus`) | Stat strip (xAI counters) |
| Teal/cyan accent | — | Module green only inside quant UI |

**Evolution path:**

1. Demote extra scroll sections → bento grid
2. Add Graphite-style progress indicator to Olympus pin
3. Hero CTA + “fund in a box” trust strip
4. Wire stat counters to real metrics when available

### DigiChat (`frontend/digichat/`)

**Mode:** Product-as-landing

| Keep | Borrow | Evolve toward |
|------|--------|---------------|
| Terminal session UI | Cursor “product is the hero” | Marketing route = full chat chrome |
| BYOK CLI flow | xAI code-sample band for API | — |
| Purple module accent | — | Cyan alignment with v2 tokens (#240) |

**Evolution path:** Minimize marketing wrapper; chat surface **is** the pitch (Cursor model).

### Olympus (`frontend/olympus/`)

**Mode:** Professional dashboard — **creativity stops here**

| Keep | Borrow | Evolve toward |
|------|--------|---------------|
| Geist + Instrument Serif display | xAI flat panels, hairline borders | Reduce glass/shadow |
| Tab subpage chrome | Cursor literal nav labels | Document in `references/` |
| MotionLayer reveals | Graphite glide on enter only | No scroll pinning |
| Cyan accent unification | — | — |

**Evolution path:** Flatten `glass-card` → `surface` + hairline; mono uppercase labels for metrics; align with `quant-native` utilities.

### twelve-x (`frontend/olympus/components/twelve-x/`)

**Mode:** Data-dense FX research utility

| Keep | Borrow | Evolve toward |
|------|--------|---------------|
| Tab bar (`SubpageStickyTabBar`) | Cursor agent-list density | xAI mono stat headers |
| Matrix / consensus views | — | Outline pills for filters |
| Real Supabase data | xAI counter strip for key metrics | — |

**Evolution path:** Treat as **xAI + Cursor utility** — no mesh, no serif, no scroll storytelling. Document patterns in Olympus ARCHITECTURE when subpage chrome changes.

---

## 4. Typography direction

### Target roles (all surfaces)

| Role | Font | Weight | Reference |
|------|------|--------|-----------|
| Marketing hero display | Fraunces *or* Instrument Serif | 400 | Editorial (us) + Cursor tight tracking |
| Dashboard display | Instrument Serif | 400 | Olympus today |
| Body | Geist Sans | 400–500 | Cursor, xAI Universal Sans |
| Labels / eyebrows | Geist Mono, uppercase, tracked | 400 | xAI |
| Data / metrics | Geist Mono, tabular nums | 400–600 | xAI, quant-native |
| Code | Geist Mono | 400 | All three |

**Deprecate:** Inter as documented default in `README.md` legacy table — Geist is loaded in Next apps.

**Rule:** Serif = display only on marketing. Dashboards and twelve-x = sans + mono.

---

## 5. Spacing & layout tokens (proposed additions)

Add to `tokens.css` when implementing primitives:

```css
/* Containers */
--wrap: 1180px;          /* existing */
--wrap-wide: 1280px;     /* Cursor/Graphite marketing */
--product-frame-w: 800px; /* Graphite artboard */

/* Section rhythm */
--section-y: clamp(4rem, 8vw, 7rem);
--section-y-tight: clamp(2.5rem, 5vw, 4rem);

/* Motion (Graphite-inspired) */
--ease-glide: cubic-bezier(0.22, 1, 0.36, 1); /* tune to linear() later */
--duration-reveal: 0.6s;
--duration-hover: 0.18s;
```

---

## 6. Primitives to build (shared `frontend/design/`)

| Primitive | Purpose | References |
|-----------|---------|------------|
| `BentoGrid` / `.bento` ✅ | 2×2 feature cells ([`site/README.md`](site/README.md#bentogrid-css-only-evolutionmd-phase-b)) | Cursor |
| `ProductFrame` ✅ | CQ-scaled 800px UI embed ([`site/README.md`](site/README.md#productframe-css-only-evolutionmd-phase-b)) | Graphite, Cursor |
| `ScrollyFeatures` ✅ | Pinned section + progress rail + N slides — React hook `useScrollyFeatures` in `@digithings/web` (`frontend/web/src/motion/scrolly.tsx`); live `PipelineScene` adoption deferred (see below) | Graphite |
| `TrustStrip` ✅ | Logo / proof row ([`site/README.md`](site/README.md#truststrip-css-only-evolutionmd-phase-b)) | Cursor, Graphite |
| `StatCounter` ✅ | Scroll-triggered metrics ([`site/README.md`](site/README.md#statcounter-css--stat-counterjs-evolutionmd-phase-b)) | xAI |
| `CapabilityCard` ✅ | Mini UI + “Explore →” ([`site/README.md`](site/README.md#capabilitycard-css-only-evolutionmd-phase-b)) | xAI |
| `ChangelogBand` ✅ | Dated release rows ([`site/README.md`](site/README.md#changelogband-css-only--data-shape-evolutionmd-phase-b)) | Cursor |
| `CodeSampleBand` ✅ | Tabbed SDK / curl snippets ([`site/README.md`](site/README.md#codesampleband-css--code-sample-bandjs-evolutionmd-phase-b)) | xAI, Cursor |
| `reveal-up` utility ✅ | Opacity + translate enter ([`site/README.md`](site/README.md#reveal-up-css-only-utility-evolutionmd-phase-b)) | Graphite |
| `HorizontalScrollBand` / `.h-scroll` ✅ | Cursor-style horizontal snap row ([`site/README.md`](site/README.md#horizontalscrollband-css-only-evolutionmd-phase-e)) | Cursor |

**Implementation order:** `ProductFrame` → `BentoGrid` → `TrustStrip` → `ScrollyFeatures` refactor → `StatCounter`.

> **ScrollyFeatures landed as a React hook, not vanilla `frontend/design/`.** #1205's
> original spec ("shared module JS+CSS under `frontend/design/`, built on
> `scroll-trigger.js`") predated the finding that the vanilla `frontend/design/site/*.js`
> layer + `scroll-trigger.js` are dead (removed in #1240; zero importers) and both live
> marketing sites are React. The only two hand-rolled scrollies —
> `ScrollyGraph` (`@digithings/web`) and digiquant-web's `PipelineScene` — are React, so
> the primitive is a React hook `useScrollyFeatures` (+ `ScrollyRail`, pure math in
> `scrolly-core.ts`) in `@digithings/web`. **Refactoring the live `PipelineScene` to consume
> it is deferred to a follow-up** — its acceptance criterion is "no visual regression" via
> manual scroll QA at 100%/125% zoom, which needs a working in-browser preview (unavailable
> when the primitive was built). See [#1205](https://github.com/digithings-ai/digithings/issues/1205).

---

## 7. Atmosphere rules (resolve Graphite vs xAI tension)

| Zone | Atmosphere | References |
|------|------------|------------|
| Hero background | Mesh, grain, glow OK | Graphite / Stripe lineage |
| Section bodies | Flat `--bg`, hairline dividers | xAI, Cursor |
| Product frames | Flat dark panel, 1px border, no mesh on UI | Graphite, Cursor |
| Dashboards | No mesh; `--surface` steps only | xAI |
| Footer | Personality allowed (accent blocks, module colors) | Graphite footer |

**Mantra:** *Atmospheric outside, surgical inside.*

---

## 8. Navigation patterns (locked)

| Viewport | Pattern | Source |
|----------|---------|--------|
| Desktop wide | Brand · inline links · theme + GitHub | Cursor + Graphite |
| Desktop | No primary product CTA in bar (in sheet or hero) | User decision 2026-06 |
| Mobile | Hamburger · brand · theme + GitHub always visible | Us + Cursor utilitarian |
| Sheet | Full-height links + primary CTA at bottom | Us |
| Dashboard | Sticky tab bar, literal labels | Cursor + twelve-x |

---

## 9. Evolution phases

### Phase A — Document & tokens (current)

- [x] Reference scans in `references/`
- [x] This evolution doc
- [x] Add `--ease-glide`, `--section-y`, `--product-frame-w` to `tokens.css`
- [x] Update `README.md` typography table (Geist, not Inter)

### Phase B — Shared primitives

- [x] `ProductFrame` component + CSS
- [x] `BentoGrid` layout CSS in `site/site.css`
- [x] `TrustStrip`, `reveal-up` utilities
- [x] `StatCounter` component + CSS
- [x] `ChangelogBand` component + CSS
- [x] `CodeSampleBand` component + CSS
- [x] `CapabilityCard` component + CSS
- [x] `ScrollyFeatures` primitive (`useScrollyFeatures` hook in `@digithings/web`); live `PipelineScene` adoption deferred to a browser-QA follow-up (#1205)

### Phase C — Landing realignment

- [x] digithings hero: trust-strip + ProductFrame (#1210); bento module grid — 4 primary modules, accent-coloured, real links, added *above* the retained interactive `digithings ps` manifest (hybrid, #1211)
- [~] digiquant hero: literal CTAs (Open Olympus / Browse strategies) + trust-strip + real-value stat row (#1213); additive Pipeline·Strategies·Pricing feature bento after the hero, teal accent, real links — kept **both** pinned scrollies (OlympusScene + StrategySuite) rather than the AC's "one pin" (avoids regressing the flagship + #1198; per sign-off) (#1214). Graphite progress rail on the Olympus pin (#1215) — **satisfied by the existing `PipelineScene`**: `.dqp-rail` already renders a scroll-synced fill + engine nodes in `--accent` cyan, reduced-motion-safe, mobile-simplified at 820px (verified live: 55% scroll → 54.99% fill). Refactoring onto the shared `ScrollyFeatures` primitive would be pure regression risk, so left as-is.
- [ ] Changelog band (both sites) — #1212 **deferred**: no real releases source (no CHANGELOG.md / GitHub releases / tags); needs a data source + product call before shipping a public band (won't fabricate).

### Phase D — Dashboard flattening

- [x] Olympus glass → surface migration (#1216) — **audit: already flat**. `.glass-card` is a legacy *name* for a flat `--surface` panel (1px `--hair` border, subtle intentional depth shadow, not glass); `backdrop-blur` is confined to sticky/overlay chrome (nav, mobile app bar, command palette, sidebar), never content. Surface system documented in `frontend/olympus/app/globals.css` (Olympus has no ARCHITECTURE.md/AGENTS.md to update). No visual change — anti-pattern #8 already satisfied.
- [x] twelve-x xAI utility polish (#1217) — **audit: already there**. Section/table headers use `uppercase tracking-wider` mono-style labels (`ConsensusDataTable`, `IntelligenceTab`, `MoversStrip`); metrics use `font-mono tabular-nums`; chips/panels are flat (`.glass-card` = flat panel, per #1216); `MoversStrip` is already a real-data headline FX metric strip. No mesh/serif/scrolly. Forcing the shared `StatCounter` over the working `MoversStrip` would be churn — left as-is.
- [x] DigiChat full token adoption (#240, closed) + product-as-hero `/welcome` marketing route with a BYOK/API `CodeSampleBand` (#1218). Public route (frozen chat-UI hero, cyan accent); shared `.code-sample-band` CSS scoped under `.welcome-codeband` with local dark `--term-*` values (digichat doesn't set `:root[data-theme]`). No purple in v2 tokens — cyan only (AC wording flagged).

### Phase E — Additional primitives & content-gated integration

- [x] `HorizontalScrollBand` primitive (`.h-scroll`) — #1221
- [x] `ClosingCtaBand` primitive (`.closing-cta`) — #1222. CSS-only centered pre-footer band (headline + primary `.btn` + optional mono secondary), `--section-y`/`--wrap-wide`, composes with `.reveal-up`. Copy slots + digithings/digiquant variants documented in `site/README.md`; smoke demo added. Landing wiring is #1227.
- [x] `FaqAccordion` + `PricingMatrix` primitives — #1223. FAQ = native `<details>`/`<summary>` (`.faq`/`.faq__item`/`.faq__q`/`.faq__a`), shared `name` → exclusive accordion, CSS chevron (reduced-motion safe). Pricing = `.pricing` grid + `.pricing__tier` (3 honest open-core tiers, featured variant) + optional `.pricing-table` (✓/— cells). Content shapes + smoke demo + `site/README.md` documented; honest-copy policy (no fake usage caps).
- [x] `HeroFeaturePicker` primitive (`.hero-picker` + `hero-picker.js`) — #1224. WAI-ARIA icon-tab row (53×53px) swapping `.hero-picker__panel` ProductFrame previews; roving tabindex (←/→/Home/End), `aria-controls`/`aria-selected`, static crops only. Smoke demo (Olympus · Strategies · Pipeline) + `site/README.md`. React hero wiring is a follow-up (#1213).
- [x] `AnnouncementBar` primitive (content-gated) — #1225. 48px full-width `.announcement` bar + `announcement.js`; renders only for enabled content (empty/`{enabled:false}` → nothing, so OFF by default), stretched-link when `href` set (scheme-guarded), dismiss persists per-`id` in localStorage, escaped text. No animation (reduced-motion safe). `announcement-example.json` shape + smoke demo + `site/README.md` (enable procedure). React landing wiring deferred (content-driven).
- [x] digiquant.io pricing FAQ + tier matrix — #1226. Converted the homepage `#contact` section into `#pricing`: `PricingMatrix` (3 honest tiers — Self-hosted MIT / Managed waitlist / Enterprise contact) + `FaqAccordion` (self-host reqs · NautilusTrader license · BYOK · no fake limits), content in `app/_pricing.ts`. Bento "// pricing" cell + nav/footer now point to `#pricing` ("Contact"→"Pricing"). Self-host CTA reuses `CloneRepoButton`; Managed/Enterprise use `contact@digiquant.io`. Standalone `/contact` route + `_contact.ts` left as-is (follow-up).
- [x] both landings closing CTA wiring — #1227. `ClosingCtaBand` wired before the footer on both sites via `<Reveal className="closing-cta">` (reveal-up + reduced-motion via the shared Reveal). digithings.ai: "Build your agent stack in the open." → **Ask digichat** (/chat) · Read the docs (/docs). digiquant.io: "One graph, research to execution." → **Open Olympus** (/#olympus) · Browse strategies (/strategies). Internal links use `next/link`.
- [x] `TrustStrip` integration logo variant (`.trust-strip--logos`) — #1229. x.ai-style integration-mark row (real stack: NautilusTrader · LangGraph · LiteLLM · Polars), grayscale/muted default → color on hover, composes on the base strip. Smoke demo (text wordmarks; production uses real logo `<img>` + `alt`) + `site/README.md`. No stock/fabricated logos.
- [x] `CaseStudyCard` primitive (P3, content-gated) — #1230. `.case-study` flat card (`{org} × digithings` label, quote, attribution + optional logo), composes in bento/capability-grid/`.h-scroll`. Content-gated — ships dormant, `.case-study--example` watermark for demos only, real attribution required in production. Smoke demo (watermarked example row) + `site/README.md` content shape.
- [x] Olympus status dot → DigiSmith (P3) — #1231. Sidebar-footer operator dot polling DigiSmith `GET /v1/status` every 60s (`lib/digismith-status.ts` + `components/status-dot.tsx`). Env-gated on `NEXT_PUBLIC_DIGISMITH_URL` (unset → not rendered, so local dev without the stack is unaffected); non-blocking client fetch; green (ok) / amber (degraded) / red (error) / grey (unreachable — graceful); no PII in the label. Documented in Olympus README (no ARCHITECTURE.md exists). Maintainer-approved the new Olympus→DigiSmith dependency; deploy needs CORS + CSP `connect-src`.

---

## 10. Anti-patterns (explicit reject list)

From user iteration log + reference analysis:

1. **Generic AI hero** — oversized headline + two buttons + chart on the side
2. **Fake ticker** — simulated prices (wire real data or remove)
3. **Decorative eyebrow pills** — “open core · self-hosted” with no action
4. **Five scroll-pinned sections** on one page
5. **Mesh gradient on product screenshots**
6. **Multiple primary CTAs** in the nav bar
7. **Inter / Space Grotesk** as brand fonts going forward
8. **Glass morphism** on new dashboard components

---

## 11. Related files

| File | Role |
|------|------|
| [`COPY_GUIDE.md`](COPY_GUIDE.md) | Voice, CTAs, section maps, IA templates |
| [`references/README.md`](references/README.md) | Index of external scans |
| [`demos/digiquant-landing/DESIGN_DECISIONS.md`](demos/digiquant-landing/DESIGN_DECISIONS.md) | v7 iteration punchlist |
| [`site/README.md`](site/README.md) | Theme contract + JS modules |
| [`references/olympus-subpage-chrome.md`](references/olympus-subpage-chrome.md) | Olympus subpage chrome — tab bar, tabs-vs-sidebar, typography, surfaces (#1220) |
| [`docs/adr/0009-frontend-umbrella.md`](../../docs/adr/0009-frontend-umbrella.md) | Monorepo layout |
| `frontend/digithings-web/components/landing/` | DigiThings landing components |
| `frontend/digiquant-web/components/landing/` | DigiQuant landing components |
| `frontend/olympus/components/twelve-x/` | twelve-x research UI |

---

## 12. Maintenance

Re-audit reference sites when:

- Any of the three ships a major homepage redesign
- We complete a Phase (update checkboxes)
- A new public surface launches (add row to §3 surface matrix)

Assign reference updates to the same PR that implements the matching primitive
when possible — keeps scans honest.
