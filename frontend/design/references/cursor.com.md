# Reference scan: cursor.com

- **URL:** https://cursor.com
- **Product:** AI coding agent — Tab, Agent, Cloud Agents, IDE + terminal + GitHub
- **Stack (observed):** Next.js, Tailwind CSS, light-first marketing
- **Last audited:** 2026-06-29

---

## 1. First impression

Cursor optimizes for **utilitarian simplicity**: scan in five seconds, download
or get started immediately. Warm off-white canvas, restrained neutrals, product
UI as the hero visual. No scroll theater on the homepage — **bento grids** and
clear section boundaries. Feels like a tool, not a brand film.

---

## 2. Information architecture

Typical homepage flow:

| # | Section | Purpose |
|---|---------|---------|
| 1 | Hero | Headline + platform download CTA + “Get started” + optional demo |
| 2 | Logo strip | “Trusted every day by teams…” |
| 3 | Feature bento | 3–4 large cells: Agents, Cloud agents, Terminal, Tab |
| 4 | Product demos | Live UI mocks (agent task list, chat, install curl) |
| 5 | Testimonials | Quote carousel — name, title, company |
| 6 | “Stay on the frontier” | Model picker, codebase Q&A, enterprise |
| 7 | Changelog | Dated entries — signals active product |
| 8 | Careers / blog highlights | Company credibility |
| 9 | Final CTA | Repeat download / get started |

**Lesson:** Each section has **one job**. No mixed hero (headline + chart + three CTAs + ticker).

---

## 3. Navigation

| Aspect | Behavior |
|--------|----------|
| Layout | Logo · links · theme/sign-in · download |
| Style | Light, minimal border on scroll |
| Links | Short labels: Features, Enterprise, Pricing, Docs |
| CTA | **Literal** — “Download for macOS” (platform-detected) |
| Mobile | Collapsed nav; primary CTA remains |

**Lesson:** CTAs name the outcome (`Download`, `curl … | bash`), not “Get started”.

---

## 4. Typography

| Role | Treatment |
|------|-----------|
| Display | **Cursor Gothic** / custom display — tight tracking on hero |
| Body | **Lato** or geometric sans — 16–18px |
| Mono | Code blocks, terminal install line |
| Hero h1 | Large, `tracking-tight`, `leading-[1.1]` |
| Section h3 | Medium weight, one line |
| Descriptors | Short subcopy, max ~2 lines |

**Palette (light):** `#f7f8f3` bg · `#e3e2dd` borders · `#989ba4` muted · `#d3c9b9` warm accent touches

**Lesson:** Display font for hero only; body stays readable sans. Tight line-height on headlines.

---

## 5. Color & surfaces

- **Light-first** marketing — no dark mode toggle required on homepage
- Surfaces: white cards on warm gray page
- Borders: subtle, 1px, low contrast
- Accent: minimal in chrome; color lives inside **product screenshots**
- Shadows: soft on product frames (`rounded-xl shadow-2xl border`)

**Lesson:** Chrome is quiet; product UI carries color.

---

## 6. Spacing & layout

| Pattern | Use |
|---------|-----|
| Two-column hero | Copy left · product visual right (desktop); stack mobile |
| Bento grid | 2×2 or asymmetric feature grid |
| `max-w-lg` subheads | Prevent line length drift |
| Generous section padding | `py-24`–`py-32` between bands |
| Sticky CTA | Repeat download in nav + footer |

**Lesson:** Whitespace is structural — separates sections without decorative dividers.

---

## 7. Component inventory

| Component | Notes |
|-----------|-------|
| Platform download button | Primary, OS-specific label |
| Secondary CTA | “Get started” / “Request a demo” |
| Bento feature card | Title · 1 sentence · link · UI crop |
| Agent UI mock | Task list, timers, model badge — **looks real** |
| Terminal one-liner | `curl https://cursor.com/install -fsS \| bash` |
| Logo cloud | Grayscale, even spacing |
| Testimonial | Quote + avatar + role |
| Changelog row | Date · version · title |
| Model picker mock | Dropdown of model names — frontier positioning |

---

## 8. Motion & scroll

- **Minimal** compared to Graphite
- Subtle hover on cards and buttons
- Product mocks may have internal animation (agent progress) but page scroll is standard
- No pinned multi-section carousel on homepage

**Lesson:** Motion inside product frames, not on the page chrome.

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Hero contract: headline · sub · CTA · trust · product frame | `make stack-local`, `ask digichat`, `open olympus` | Generic “Scroll to explore” as only CTA |
| Bento feature grid | Module grid on digithings; capabilities on digiquant | Multiple scrolly sections per page |
| Literal CTAs + install commands | Docker compose / make targets in mono | Vague “Deploy a node” with no route |
| Changelog / news band | GitHub releases, digigraph changelog | — |
| Testimonial / quote strip | Builder quotes, OSS adopters | Fake metrics |
| Product frame with border + shadow | Tearsheet, DigiChat, Olympus embed | — |
| Two-column hero layout | Mesh **behind** frame, not over copy | Side-by-side “headline + random chart” cliché |

---

## 10. Map to our surfaces

| Surface | Cursor patterns to use |
|---------|------------------------|
| digithings.ai | Bento module grid; hero with stack diagram frame; principles as 4-cell grid |
| digiquant.io | Bento for Pipeline/Strategies/Pricing; **one** Graphite scrolly for Olympus only |
| digichat | Chat UI **is** the landing — Cursor’s “product as hero” |
| Olympus | Changelog-style activity feed; literal nav labels |
| twelve-x | Tab bar + dense tables — Cursor’s agent list density, not marketing bento |

---

## 11. Further reading

- [BestSaaSWebDesigns — Cursor breakdown](https://bestsaaswebdesigns.com/site/cursor) — section crops, palette hex
- [B2B Landing Page Examples — Cursor 1.0](https://b2blandingpage.com/examples/cursor-1-0) — bento, sticky CTA, logos
