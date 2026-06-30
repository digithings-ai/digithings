# Frontend design evolution — four-layer deep recommendations

**Date:** 2026-06-30  
**Status:** Draft for review  
**Parent epic:** [#1200](https://github.com/digithings-ai/digithings/issues/1200)  
**Strategy:** [`frontend/design/EVOLUTION.md`](../../../frontend/design/EVOLUTION.md)  
**References:** [`frontend/design/references/scans/`](../../../frontend/design/references/scans/INDEX.md)

This document extends epic #1200 with patterns from Graphite, Cursor, and x.ai that were identified in brainstorming but not yet filed as issues. It covers four layers: marketing landings (A), product surfaces (B), shared primitives & motion (C), copy & IA (D).

**Blend (unchanged):** Cursor page map · Graphite scroll craft · xAI mono on dashboards · our mesh/grain/module accents.

---

## Executive summary

| Layer | Top 3 additions to epic #1200 | Priority |
|-------|------------------------------|----------|
| **A — Marketing** | HorizontalScrollBand, FaqAccordion + PricingMatrix, ClosingCtaBand | P1–P2 |
| **B — Product** | Olympus status strip, DigiChat embed chrome, twelve-x filter density | P2 |
| **C — Primitives** | HorizontalScrollBand, HeroFeaturePicker, FaqAccordion | P1 |
| **D — Copy/IA** | `COPY_GUIDE.md`, per-surface section maps, literal CTA library | P1 (docs) |

**Recommended new issues (Phase E):** 11 issues — see §5.

---

## Synthesis from four-layer research (2026-06-30)

Cross-layer conclusions after auditing Graphite, Cursor, and x.ai against our v7 landings and dashboard surfaces.

### Implementation spine

1. **Tokens first (A1)** — `--ease-glide`, `--section-y`, `--product-frame-w` unblock every primitive.
2. **Frame + grid (B1–B2)** — `ProductFrame` and `BentoGrid` are the structural spine; all marketing proof lives inside frames, not decorative screenshots.
3. **One scroll story (C6 + bento demotion)** — digiquant keeps a single pinned Olympus section; everything else demotes to bento or enter-only reveals.
4. **Copy before chrome (E8)** — `COPY_GUIDE.md` locks literal CTAs and section maps so Phase C/E wiring does not re-debate voice per PR.
5. **Dashboard flattening (D1)** — Olympus/twelve-x stop glass; x.ai mono labels only. No marketing primitives on dashboards.

### Highest-impact gaps (ranked)

| Rank | Gap | Layer | Fix |
|------|-----|-------|-----|
| 1 | Hero lacks literal CTA + trust | A | #1210, #1213, E9 |
| 2 | No shared bento / product frame | C | #1202, #1203 |
| 3 | No closing CTA band | A/C | E2 → E7 |
| 4 | digiquant pricing/FAQ scannability | A | E3 → E6 |
| 5 | Changelog mobile horizontal scroll | C | E1 → #1212 |
| 6 | Copy/IA undocumented | D | E8 |
| 7 | Glass-heavy Olympus | B | #1216 |
| 8 | Hero feature picker (digiquant) | A/C | E4 (after #1213) |

### Phase E at a glance

| ID | Title | Layer | Priority |
|----|-------|-------|----------|
| E1 | HorizontalScrollBand | C | P1 |
| E2 | ClosingCtaBand | C | P1 |
| E3 | FaqAccordion + PricingMatrix | C | P2 |
| E4 | HeroFeaturePicker | C | P2 |
| E5 | AnnouncementBar (content-gated) | C | P3 |
| E6 | digiquant.io pricing FAQ + matrix | A | P2 |
| E7 | Both landings closing CTA wiring | A | P1 |
| E8 | COPY_GUIDE.md | D | P1 |
| E9 | TrustStrip integration logos | A/C | P2 |
| E10 | CaseStudyCard (content-gated) | C | P3 |
| E11 | Olympus status dot → DigiSmith | B | P3 |

Parent epic: [#1200](https://github.com/digithings-ai/digithings/issues/1200).

### Suggested order (after Phase B)

1. **E8** — COPY_GUIDE (no deps; unblocks copy in C/E)
2. **E2 → E7** — closing CTA primitive then both landings
3. **E1** — horizontal scroll (unblocks changelog mobile)
4. **E3 → E6** — pricing primitives then digiquant wiring
5. **E9** — integration logo trust strip (after #1204)
6. **E4** — hero picker (after #1202, #1213)
7. **E5** — announcement bar (primitive only; enable when news exists)
8. **E10, E11** — defer until real quotes / operator need

---

## Layer A — Marketing landings

### Current state

| Surface | Components today | Gap vs references |
|---------|------------------|-------------------|
| digithings.ai | `HeroMesh`, `HeroGraph`, `ModuleManifest`, `DigiNav` | No literal hero CTA, no trust strip, no bento, no changelog, no final CTA |
| digiquant.io | `OlympusScene`, `StrategySuite`, `ResearchPipeline`, `CloneRepoButton` | Strong scroll story; missing progress rail, bento demotion, FAQ/pricing polish |

### Patterns to add (beyond #1210–#1215)

#### 1. FAQ accordion (Graphite/Cursor pricing)

- **Reference:** Graphite pricing page — expandable Q&A below tier matrix; Cursor pricing FAQ with checkmark bullets.
- **Surface:** digiquant.io `/#pricing` primarily; digithings optional (self-host FAQ).
- **Approaches:**
  - **A (recommended):** Shared `FaqAccordion` primitive + JSON content file per site.
  - **B:** Inline HTML per landing — faster, no reuse.
  - **C:** Link out to docs FAQ — loses conversion on-page.
- **Open-core content angles:** self-host requirements, NautilusTrader license, BYOK, no fake "limited AI requests."

#### 2. PricingMatrix / tier cards

- **Reference:** Graphite 4-tier + comparison matrix; Cursor Hobby/Individual/Teams/Enterprise with ✓ rows.
- **Surface:** digiquant.io only (digithings is open-core, not commercial tiers).
- **Approaches:**
  - **A (recommended):** 3 tiers — `Self-hosted` (MIT) · `Managed` (future) · `Enterprise` (contact) — honest, no fake limits.
  - **B:** x.ai per-unit token table — wrong model for quant product.
  - **C:** Skip pricing section — loses Cursor scannability.
- **Dependency:** FaqAccordion below matrix.

#### 3. CaseStudyCard / testimonial carousel

- **Reference:** Cursor enterprise wall; Graphite `{Co} × Graphite` horizontal cards.
- **Surface:** digithings.ai only.
- **Rule:** **Real quotes only** — GitHub stars, named OSS adopters, or skip entirely (anti-pattern #2).
- **Approaches:**
  - **A (recommended):** Defer until real quotes exist; placeholder = logo strip only.
  - **B:** Horizontal scroll of GitHub contributor / star count as social proof (StatCounter + logos).
  - **C:** Fake enterprise quotes — **reject**.

#### 4. AnnouncementBar

- **Reference:** Graphite 48px full-width clickable bar above nav ("Cursor Cloud Agents are now in Graphite…").
- **Surface:** Both landings when real news exists.
- **Approaches:**
  - **A (recommended):** Build primitive + ship disabled; enable via `announcement.json` when merging integrations/releases.
  - **B:** Hardcode in layout — fast but requires deploy per news.
- **Dependency:** None; optional on all pages.

#### 5. Closing CTA band

- **Reference:** Graphite/Cursor — full-width section before footer repeats primary action.
- **Surface:** Both landings.
- **Approaches:**
  - **A (recommended):** Shared `ClosingCtaBand` — headline + literal CTA + optional secondary.
  - **B:** Duplicate hero CTA markup — DRY violation.
- **Copy:** digithings → `ask digichat`; digiquant → `open olympus`.

#### 6. Hero feature picker (Graphite)

- **Reference:** Icon row (~53×53) below hero switches video/demo context.
- **Surface:** digiquant.io hero — flip Olympus / tearsheet / pipeline previews inside `ProductFrame`.
- **Approaches:**
  - **A (recommended):** `HeroFeaturePicker` + 3 tabs, no video (static UI crops) — lighter weight.
  - **B:** Actual video swap — heavy assets, maintenance cost.
  - **C:** Skip — hero stays single static frame.
- **Dependency:** #1202 ProductFrame, #1213 digiquant hero.

#### 7. Horizontal scroll bands (Cursor mobile)

- **Reference:** Changelog articles 262px wide, x positions overflow viewport; same for blog/testimonials.
- **Surface:** digithings changelog (#1212), optional testimonial row.
- **Approaches:**
  - **A (recommended):** `HorizontalScrollBand` primitive with snap, fade edges, `prefers-reduced-motion` → stack vertically.
  - **B:** CSS overflow-x only — no snap, worse UX.
- **Dependency:** #1207 ChangelogBand content shape.

#### 8. Logo / integration trust strip

- **Beyond #1204 TrustStrip:** x.ai partner logos (Azure, OCI, GCP) → our equivalents: NautilusTrader, LangGraph, LiteLLM, Polars logos (real integrations only).

---

## Layer B — Product surfaces

### Olympus (`frontend/olympus/`)

**Existing issues:** #1216 glass→surface, #1220 subpage chrome docs.

| Pattern | Reference | Gap | Recommendation |
|---------|-----------|-----|----------------|
| Flat panels + hairline | x.ai | `glass-card`, blur, shadow | #1216 — migrate to `--surface` + 1px `--hair` |
| Mono uppercase labels | x.ai | Mixed case metrics | Add `.label-mono` utility; KPI headers only |
| One white pill CTA per view | x.ai | Multiple competing buttons | Audit panels; one filled primary per view |
| Literal tab labels | Cursor | Some abbreviated tabs | Document in #1220; no abbreviations |
| Enter-only motion | Graphite | — | `reveal-up` on panel mount; **no scroll pin** |
| Status indicator | Graphite footer | None | Optional: wire footer dot to DigiSmith `/v1/status` (new issue, P3) |

**Approaches for glass migration:**
- **A (recommended):** Incremental — new components flat only; migrate top 5 glass surfaces per PR.
- **B:** Big-bang CSS override — risky visual regression.
- **C:** Keep glass on charts only — inconsistent with xAI direction.

### DigiChat (`frontend/digichat/`)

**Existing issues:** #240 tokens, #1218 product-as-hero.

| Pattern | Reference | Gap | Recommendation |
|---------|-----------|-----|----------------|
| Product is the hero | Cursor | Marketing wrapper around chat | #1218 — unauthenticated `/` shows full terminal chrome |
| Code sample band | x.ai + Cursor curl | BYOK buried in settings | #1209 + #1218 — tabbed `curl` / Python / TS |
| Terminal identity | x.ai mono | Partial Inter legacy | Block on #240 |
| Embed route | — | #261 separate | Keep embed minimal; no marketing chrome in iframe |

**Approaches for marketing route:**
- **A (recommended):** `/` when logged out = chat UI + slim header with `sign in` + friction line.
- **B:** Separate `/welcome` marketing page — splits traffic, Cursor doesn't do this.
- **C:** Landing-only static page — loses product-as-hero.

### twelve-x (`frontend/olympus/components/twelve-x/`)

**Existing issue:** #1217 utility polish.

| Pattern | Reference | Gap | Recommendation |
|---------|-----------|-----|----------------|
| Outline filter pills | x.ai | Filled/glass chips possible | 1px border, transparent bg |
| Counter strip | x.ai | No headline metrics | 2–3 real FX metrics from Supabase |
| Table density | Cursor agents list | Adequate | Tighten row padding only if needed |
| Tab bar | Cursor | `SubpageStickyTabBar` exists | Align labels with #1220 doc |

**Explicit reject list for twelve-x:** mesh, Fraunces/serif, scroll pinning, hero sections, announcement bar.

---

## Layer C — Shared primitives & motion

### Already in epic (#1201–#1209)

ProductFrame, BentoGrid, TrustStrip, reveal-up, ScrollyFeatures, StatCounter, ChangelogBand, CapabilityCard, CodeSampleBand.

### New primitives to add (Phase E)

| Primitive | Reference | Location | API sketch |
|-----------|-----------|----------|------------|
| `HorizontalScrollBand` | Cursor | `site/site.css` + optional `horizontal-scroll.js` | `.h-scroll` > `.h-scroll__track` > `.h-scroll__card` (min-width 262px); snap; edge fade |
| `HeroFeaturePicker` | Graphite | `site/site.css` + small JS | `.hero-picker` > buttons `[aria-selected]` + panel region swapping `ProductFrame` children |
| `ClosingCtaBand` | Cursor/Graphite | `site/site.css` | `.closing-cta` — centered h2 + `.btn` primary |
| `AnnouncementBar` | Graphite | `site/site.css` | `.announcement` 48px; dismissible; `data-href` |
| `FaqAccordion` | Graphite/Cursor | `site/site.css` + JS or `<details>` | `.faq` > `.faq__item` with `summary` + panel |
| `PricingMatrix` | Graphite | `site/site.css` | `.pricing` grid + `.pricing__tier` cards + optional comparison table |
| `CaseStudyCard` | Graphite/Cursor | extends bento cell | `.case-study` — label `{x} × digithings`, quote, logo |

### Motion system extensions (#1201 follow-up)

```css
/* Add with A1 tokens */
--ease-glide: cubic-bezier(0.22, 1, 0.36, 1);
--duration-reveal: 0.6s;
--duration-hover: 0.18s;

/* Behavior contracts */
@media (prefers-reduced-motion: reduce) {
  .reveal-up, .stat-counter, .scrolly-features { /* instant final state */ }
}
```

| Motion type | Use | Avoid |
|-------------|-----|-------|
| `reveal-up` | Section enter, bento cells | Always-on mesh |
| `--ease-glide` | Reveals, scrolly slide transitions | Nav open/close (use snappier ease) |
| Hover lift | Bento/card hover only | Dashboard panels |
| Scroll pin | **One** section per page | Strategy + Olympus double-pin competing |
| Counter animate | StatCounter on enter | Fake live tickers |

### Integration lessons (#1198)

- Scrolly height must be measured from pin content, not fixed `100svh`.
- Library CTA must be sibling of stack clip, not absolute overlay inside chart.
- Contact/footer need explicit z-index above sticky pin.
- `ProductFrame` inside pin must not use `overflow: hidden` that clips at browser zoom.

### Implementation order (Phase E after B)

1. `ClosingCtaBand` (no deps, both landings)
2. `HorizontalScrollBand` (unblocks changelog mobile)
3. `FaqAccordion` + `PricingMatrix` (digiquant pricing)
4. `HeroFeaturePicker` (after ProductFrame + digiquant hero)
5. `AnnouncementBar` (primitive only; content later)
6. `CaseStudyCard` (when real quotes exist)

---

## Layer D — Copy & information architecture

### Voice guide (→ `frontend/design/COPY_GUIDE.md`)

| Principle | Rule |
|-----------|------|
| Tone | Technical, precise, ownership-oriented — closer to x.ai than Cursor warmth |
| Product names | lowercase: digithings, digiquant, digichat |
| Proper nouns | Olympus, Atlas, Hermes, NautilusTrader, LangGraph |
| CTAs | **Literal destinations** — never naked "Get started" |
| Proof | Real data only — stars, backtest counts, release dates |
| Serif | Marketing hero display only; dashboards sans + mono |

### Literal CTA library

| Pattern | digithings.ai | digiquant.io | DigiChat | Olympus |
|---------|---------------|--------------|----------|---------|
| Primary | `ask digichat` | `open olympus` | `sign in` / `new chat` | context action |
| Secondary | `read docs` → | `browse strategies` → | `view on github` → | `export` / `run` |
| Developer | `make stack-local` | `git clone …` | `copy api command` | — |
| Explore | `explore digigraph` → | `view tearsheets` → | — | tab label |
| Contact | `contact us` | `contact@digithings.ai` | — | — |

### Friction reducers (under primary CTA)

| Surface | Draft line |
|---------|------------|
| digithings.ai | `open core · self-hosted · MCP-first · BYOK` |
| digiquant.io | `MIT license · NautilusTrader · tearsheets from real backtests` |
| DigiChat | `bring your own key · audit log on by default` |

### Per-surface section maps

#### digithings.ai (Cursor IA + x.ai API band)

1. Hero — headline + sub + literal CTA + friction + `ProductFrame` (supervisor/chat)
2. Trust — logo/integration strip or GitHub stars
3. Modules — **bento grid** (not long scroll) — #1211
4. Architecture — optional **one** scrolly OR manifest interactivity (not both competing)
5. Developer — `CodeSampleBand` or stack-local command
6. Changelog — `ChangelogBand` + horizontal scroll on mobile — #1212
7. Closing CTA — `ClosingCtaBand`
8. Footer — 4 columns: Architecture · Docs · Contact · Connect

**Draft hero:**
- **h1:** "Build agents on infrastructure you own."
- **sub:** "LangGraph orchestration, MCP tools, and open-core modules — self-hosted or cloud."
- **primary:** `ask digichat` · **secondary:** `read docs` →

#### digiquant.io (Graphite outcomes + Cursor bento)

1. Hero — Fraunces h1 + modality sub + CTAs + stats — #1213
2. Optional hero picker — Olympus / strategies / pipeline — Phase E
3. **Olympus scrolly** (only pin) + progress rail — #1215
4. Bento — Pipeline · Strategies · Pricing — #1214
5. Strategy suite — existing scroll stack (second story, not second pin)
6. Pricing — `PricingMatrix` + `FaqAccordion` — Phase E
7. Closing CTA — `open olympus`
8. Footer

**Draft hero:**
- **h1:** "A quant hedge fund. *In a box you own.*"
- **sub:** "Backtest · optimize · paper · live — NautilusTrader under the hood."
- **primary:** `open olympus` · **secondary:** `browse strategies` →

#### DigiChat (Cursor product-as-hero)

1. Nav — minimal: brand · sign in · theme
2. **Chat chrome = hero** — no marketing h1 above terminal
3. Sample prompts in empty state
4. `CodeSampleBand` below fold for API/BYOK
5. Footer — minimal

#### Olympus / twelve-x (x.ai infrastructure)

1. Sticky tab bar — literal labels
2. Page title — Instrument Serif display, one line
3. KPI row — mono uppercase labels, tabular nums
4. Content panels — flat surface, hairline
5. No marketing sections, no mesh

### Headline formulas (per `copy-patterns.md`)

| Surface | Formula | Example |
|---------|---------|---------|
| digithings | [ownership outcome] | "Build agents on infrastructure you own." |
| digiquant | [category] + [twist] | "A quant hedge fund. In a box you own." |
| digichat | (product speaks) | — |
| Olympus | [page function] | "Atlas pipeline" / "Today's snapshot" |

### Deliverables

| Item | Type | Issue needed? |
|------|------|---------------|
| `frontend/design/COPY_GUIDE.md` | New doc | Yes — docs issue |
| Per-surface section maps | Section in COPY_GUIDE | No — part of above |
| Landing copy implementation | Code | Covered by #1210–#1213 |

---

## §5 — Proposed Phase E issues (extend #1200)

| # | Title | Layer | Priority | Blocked by |
|---|-------|-------|----------|------------|
| E1 | Shared HorizontalScrollBand primitive | C | P1 | #1201 |
| E2 | Shared ClosingCtaBand primitive | C | P1 | #1201 |
| E3 | Shared FaqAccordion + PricingMatrix primitives | C | P2 | #1201 |
| E4 | Shared HeroFeaturePicker primitive | C | P2 | #1202, #1213 |
| E5 | Shared AnnouncementBar primitive (content-gated) | C | P3 | #1201 |
| E6 | digiquant.io — pricing FAQ + tier matrix at `/#pricing` | A | P2 | E3, #1214 |
| E7 | digithings.ai + digiquant.io — closing CTA band wiring | A | P1 | E2, #1210, #1213 |
| E8 | `frontend/design/COPY_GUIDE.md` | D | P1 | none (docs) |
| E9 | TrustStrip integration logo variant | A/C | P2 | #1204 |
| E10 | Shared CaseStudyCard (content-gated) | C | P3 | #1203, E1 |
| E11 | Olympus footer status dot → DigiSmith | B | P3 | #1216 |

**Note:** Layer D originally listed integration logos under optional defer; renumbered to **E9** so **E8** stays the COPY_GUIDE docs deliverable.

---

## §6 — Anti-patterns (reaffirmed)

1. Generic AI hero — headline + two buttons + chart sidebar
2. Fake ticker / fake enterprise stats
3. Decorative eyebrow pills with no action
4. Five scroll-pinned sections on one page
5. Mesh on product screenshots inside frames
6. Multiple primary CTAs in nav bar
7. Glass on new dashboard components
8. Stock testimonials without real attribution

---

## §7 — Next steps

1. **User review** this spec.
2. File Phase E issues (E1–E11) under epic [#1200](https://github.com/digithings-ai/digithings/issues/1200).
3. ~~Write `frontend/design/COPY_GUIDE.md` from §Layer D (E8).~~ Done — see [`COPY_GUIDE.md`](../../../frontend/design/COPY_GUIDE.md).
4. Begin implementation per synthesis order: #1201 → #1202 → … → Phase E.

---

## Related

- [`docs/agent-backlog/design-evolution/INDEX.md`](../../agent-backlog/design-evolution/INDEX.md)
- Epic [#1200](https://github.com/digithings-ai/digithings/issues/1200)
- Parent design epic [#235](https://github.com/digithings-ai/digithings/issues/235)
