# Reference scan: x.ai

- **URL:** https://x.ai
- **Product:** Grok — frontier models, API, voice, code, multi-modal
- **Stack (observed):** Next.js, Tailwind, dark-only marketing
- **Last audited:** 2026-06-29

---

## 1. First impression

xAI is **brutalist infrastructure marketing**: near-black void, white type,
almost no decoration. The site says “research lab” not “SaaS landing page.”
Typography does the heavy lifting — especially **monospace at display scale**.
Color appears only inside product capability demos or rare atmospheric moments.

---

## 2. Information architecture

Typical homepage flow:

| # | Section | Purpose |
|---|---------|---------|
| 1 | Hero | Massive headline + sub + capability teaser cards |
| 2 | Interactive demos | Chat, Code agent, Imagine, Voice — each with “Explore →” |
| 3 | Developer API | “One API. Every modality.” + code sample + stats |
| 4 | Scale metrics | Animated counters (API calls, GPUs, mission) |
| 5 | News | Latest posts grid |
| 6 | Pricing paths | Build on your own vs Contact sales |
| 7 | Footer | Minimal links |

**Lesson:** Capabilities are **named modalities** (Chat, Code, Voice) with live
UI previews — not abstract feature bullets.

---

## 3. Navigation

| Aspect | Behavior |
|--------|----------|
| Canvas | Near-black edge-to-edge |
| Links | Ghost pills, hairline white border |
| CTA | One filled white pill (Sign up); others outline |
| Density | Sparse — few nav items visible |
| Mobile | Same pill language, stacked |

**Lesson:** One filled CTA per viewport; everything else outline-on-dark.

---

## 4. Typography

| Role | Treatment |
|------|-----------|
| Display | **Geist Mono** at extreme scale (up to ~320px), weight 300 |
| Body / h2 | **Universal Sans** (Inter-class geometric), 16–30px, weight 400 |
| Eyebrows / labels | Geist Mono **uppercase**, +1.4px tracking, 14px |
| Buttons | Mono uppercase, tracked |
| Display tracking | Aggressive negative (-2px to -2.4px at large sizes) |

**Two-face system:** Mono = infrastructure voice · Sans = readable body

**Lesson:** Mono as display is the brand — aligns with DigiThings terminal identity.

---

## 5. Color & surfaces

| Role | ~Value |
|------|--------|
| Canvas | `#0a0a0a` or `#1f2228` |
| Card | `#191919` |
| Hairline | `#212327` / white @ ~10% |
| Text | `#ffffff` primary |
| Focus | Electric blue `#2563eb` (rare) |
| Accents in illustrations | sunset `#ff7a17`, dusk `#7c3aed` — **not in chrome** |

**Elevation:** Hairline borders only. **No shadows. No gradients** on core UI.

**Lesson:** Color is an event, not wallpaper. Matches our `--hair` token approach.

---

## 6. Spacing & layout

- 8px base grid; sparse scale (2px → 64px)
- Cards: 8px radius, 24px padding, 1px border
- Pills: `9999px` radius — only interactive shape besides rects
- Section vertical padding ~64px desktop
- Hero: type **is** the visual — optional bloom/light wash at footer only

---

## 7. Component inventory

| Component | Notes |
|-----------|-------|
| Outline pill button | 1px white border, transparent fill |
| Filled pill CTA | White bg, dark text — single primary |
| Capability card | Mini product UI + “Explore →” |
| Code block | Python/TS/cURL tabs; copy button |
| Stat counter | Large mono numerals, scroll-triggered count-up |
| News card | Date · category · title · read time |
| Pricing tier | Two-column: self-serve vs sales |
| Agent UI mock | File tree, grep output, “Thought for 4.1s” |

---

## 8. Motion & scroll

- Counter animations on stats
- Subtle capability card hovers
- Demo UIs may animate internally (agent thinking, streaming)
- Page-level scroll is conventional — **no** Graphite-style pinned carousel
- Footer optional warm gradient bloom — atmospheric exception

**Lesson:** Motion proves **scale and capability**, not page choreography.

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Mono eyebrows (`// section`, uppercase kicker) | Already have `.kicker` in `site.css` | 320px display on dashboard |
| Outline pill buttons on dark | Ghost `.btn` + hairline | Pill-only system (we need rects for tables) |
| Capability cards with real UI | Grok → DigiGraph workflow, DigiChat, Atlas | Pure black `#000` canvas |
| API section with copy-paste code | digikey token exchange, `make stack-local` | Dark-only (we ship light mode) |
| Stat counters | Module count, backtest runs, open issues | Fake scale metrics |
| No shadow elevation | Olympus glass → flatten over time | Removing all atmosphere from **landings** |
| One filled primary CTA | Per-page: download stack vs ask digichat | Multiple competing primaries |

---

## 10. Map to our surfaces

| Surface | xAI patterns to use |
|---------|---------------------|
| digithings.ai | API/docs band with code sample; mono kickers |
| digiquant.io | Stat strip (strategies, backtests, OSS); modality cards |
| digichat | Chat-as-capability-card; terminal mono buttons |
| Olympus | Flat panels, hairline borders, mono labels, no shadow stack |
| twelve-x | **Primary reference** — data density, mono metrics, outline chrome |

---

## 11. Further reading

- [shadcn xAI design kit](https://www.shadcn.io/design/xai) — token extraction
- [getdesign.md x.ai preview](https://getdesign.md/design-md/x.ai/preview)
- [Refero Styles — xAI](https://styles.refero.design/style/3b83dfe4-2f53-4a4d-819d-e6045ca5f7dc)
