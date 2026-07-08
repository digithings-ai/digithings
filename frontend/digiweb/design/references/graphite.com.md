# Reference scan: graphite.com

- **URL:** https://graphite.com
- **Product:** AI code review — stacked PRs, merge queue, agentic review
- **Stack (observed):** Custom CSS, heavy motion, dark zinc palette
- **Last audited:** 2026-06-29

---

## 1. First impression

Graphite reads as a **dark, fast, cinematic dev tool**. The page communicates
velocity through movement before copy. Near-black zinc void, warm near-white text,
orange accent used sparingly. The hero is not decorative — it hands off to
**real product UI** (PR page, agent chat, merge queue) inside scroll-driven frames.

---

## 2. Information architecture

Typical homepage flow (top → bottom):

| # | Section | Purpose |
|---|---------|---------|
| 1 | Announcement bar | Product news (e.g. Cursor Cloud Agents integration) |
| 2 | Hero | One-line value prop + primary CTA + friction reducer |
| 3 | Logo strip | “Trusted by…” enterprise logos |
| 4 | **Scroll-pinned feature stack** | 5+ capabilities in one viewport (signature pattern) |
| 5 | Feature deep-dives | Chat reviewer, AI review, merge queue, stacked PRs, PR page |
| 6 | Social proof | Long-form customer quotes |
| 7 | Enterprise / platform | GitHub sync, Git-native, scale stats |
| 8 | Footer | Links + **bold color accent blocks** (orange, yellow, cyan, blue) |

**Lesson:** Many features, **short perceived page length** — achieved by pinning
one section and swapping content on scroll rather than stacking five full sections.

---

## 3. Navigation

| Aspect | Behavior |
|--------|----------|
| Layout | Logo left · inline links center/right · CTAs right |
| Background | Transparent at top → zinc-900 glass on scroll |
| Link style | White ~60% opacity → 100% on hover (no color change) |
| Mobile | Compact header; links collapse (hamburger or reduced set) |
| Primary CTA | High-contrast orange button, always visible |
| GitHub / secondary | Icon or ghost, never competes with primary |

**Breakpoints:** Nine tuned widths (554px → 1440px) — intermediate states are
first-class, not afterthoughts.

---

## 4. Typography

| Role | Treatment |
|------|-----------|
| Primary face | **Matter** — geometric sans, 400–500 weights |
| Code | DM Mono / JetBrains Mono |
| h1 | ~36px / 500 — confident, not shouty |
| Feature h3 | ~24px / 600 |
| Body | 16px / 400, line-height 1.5–1.5 |
| Nav / buttons | 14px |
| Ligatures | Disabled (`liga` off) — dev-tool readability |

**Lesson:** One sans for UI; mono only in product chrome. No all-caps nav labels.

---

## 5. Color & surfaces

**Surfaces (elevation by luminance, not shadow):**

| Token role | ~Hex | Use |
|------------|------|-----|
| Page | `#0a0a0a` | zinc-950 base |
| Panel | `#18181b` | zinc-900 |
| Card | `#27272a` | zinc-800 |
| Elevated | `#3f3f46` | zinc-700 |

**Text:** `#e8e8ed` primary · `#a1a1a6` secondary

**Accent:** `#ff8833` brand orange — CTAs and rare highlights only

**Borders:** white @ 10% opacity — universal hairline

**Shadows:** Minimal (`0 1px 3px`); depth comes from surface steps.

**Lesson:** No pure `#000`. No glassmorphism in core product UI. Footer is where
multi-color brand play lives — not the main chrome.

---

## 6. Spacing & layout

- Header horizontal padding ~16px; content max-width ~1216px
- Sections often `0` outer padding — inner components own rhythm
- Footer top padding ~80px — clear separation
- Product embeds: **800px fixed artboard**, scaled via container queries:
  `min(1, calc(100cqw - 2rem) / 800px)`

**Lesson:** Product screenshots stay pixel-faithful at desktop; scale down
proportionally instead of reflowing UI at every breakpoint.

---

## 7. Component inventory

| Component | Notes |
|-----------|-------|
| Primary button | Orange fill, 10px radius, subtle shadow |
| Ghost button | Zinc surface, hairline border |
| Feature cell | Headline + one-liner + “Learn more →” + **product visual** |
| Progress rail | Scroll-linked indicator during pinned feature section |
| Logo cloud | Grayscale logos, single row |
| Case study card | Logo × partner name, links to story |
| Video / UI frame | Autoplay or static PR UI in dark frame |
| Announcement pill | Top bar, dismissible |

---

## 8. Motion & scroll

**Signature:** Custom **glide easing** — spring-like `linear()` curve, ~0.6s baseline.

| Pattern | Use |
|---------|-----|
| Translate-up + fade | Content enter |
| Scroll-pinned section | Feature carousel |
| Clip-path reveal | Section transitions |
| Marquee | Footer accent blocks |
| Progress bar | Tied to scroll position in pinned block |

**Lesson:** Motion is **coherent** — same easing everywhere. Generic `ease-in-out`
would feel off-brand. Respect reduced motion for accessibility.

**Technical note:** Ideal candidate for CSS scroll-driven animations with JS
fallback (`frontend/digiweb/design/scroll-trigger.js`).

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Scroll-pinned **one** flagship section per landing | Use digiquant Olympus pipeline, not PR UI | Copying orange/zinc palette wholesale |
| Product UI in flat dark frames | Our tearsheets, DigiChat, Olympus clips | Glass + mesh **on top of** product mocks |
| Glide easing token in `tokens.css` | Map to `--ease-glide` alongside `--ease` | Five separate 400vh scroll sections |
| Container-query product scaling | `ProductFrame` primitive | Nine breakpoints — start with 3–4 |
| Nav link opacity hover | Already close in `site.css` nav | Category rainbow in main chrome |
| Logo trust strip | Open-core / Nautilus / GitHub stars | — |
| Footer as personality zone | Module accent blocks | — |

---

## 10. Map to our surfaces

| Surface | Graphite patterns to use |
|---------|--------------------------|
| digiquant.io | Scroll-pinned Olympus + pipeline; tearsheet in frame |
| digithings.ai | One scrolly “module stack”; architecture manifest in frame |
| digichat | Agent conversation UI as hero visual (like Graphite Chat section) |
| Olympus | Motion on enter only; flat zinc panels inside dashboard |
| twelve-x | Skip scroll theater; use flat panels + data density |

---

## 11. Further reading

- [Compact scrolling feature sections (markepear)](https://www.markepear.dev/example/compact-scrolling-feature-sections-from-graphite)
- [design-bites graphite.dev DESIGN.md](https://github.com/educlopez/design-bites/blob/main/design-mds/graphite.dev/DESIGN.md) — extracted CSS analysis
