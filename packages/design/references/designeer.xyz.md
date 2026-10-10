# Inspiration hub: designeer.xyz

- **URL:** https://designeer.xyz
- **What it is:** Curated directory of design galleries, component libraries, tools, reading, and people worth following — not a single product site to copy.
- **Role in digiweb:** Living **idea / tools dictionary**. Pull from here when exploring patterns for digiquant dashboard, FX Hub / twelve-x, digithings-web landings, digichat chrome, and shared digiweb kit work.
- **Last indexed:** 2026-09-28
- **Machine-readable:** [llms.txt](https://designeer.xyz/llms.txt) · [llms-full.txt](https://designeer.xyz/llms-full.txt) (full catalogue) · [mcp.json](https://designeer.xyz/mcp.json)

This is **not** a north-star site scan like Graphite / Cursor / xAI. Do not treat Designeer’s own chrome as a visual target. Use it to **find** galleries, kits, and essays, then adopt patterns through our tokens and `apps/reference` specimens.

---

## Why keep it

| Need | How Designeer helps |
|------|---------------------|
| Interface inspiration | Design Galleries section (Mobbin, Land-book, navbar.design, SaaSFrame, Shape of AI, …) |
| Build / ship tools | Component libraries, Figma/Framer, editors, agents & MCP |
| Motion & craft | Animations.dev, motion kits, reading (Refactoring UI, …) |
| Agent-friendly lookup | WebMCP + llms-full catalogue for keyword / section search |

Catalogue scale (as of index date): hundreds of tools across ~17 sections plus a “people worth following” list. Entries are curated (opened before listing); sponsor placements are labelled separately.

---

## High-signal starting points (digiweb)

Use these first when browsing from Designeer — then capture anything we adopt into `packages/design/references/` (site scan) or `apps/reference` (live specimen).

### Design galleries / product UI

| Source | URL | Pull for |
|--------|-----|----------|
| Mobbin | https://mobbin.com/ | Real mobile + web flows; dashboard density, nav, sheets |
| Land-book | https://land-book.com/ | Landing IA by industry; digithings / digiquant marketing |
| navbar.design | https://navbar.design/ | Nav / chrome patterns for digiweb shells |
| SaaSFrame | https://www.saasframe.io/ | SaaS marketing screenshots; section rhythm |
| The Shape of AI | https://www.shapeof.ai/ | AI product UI patterns; digichat / agent surfaces |

### Tools & canvases

| Source | URL | Pull for |
|--------|-----|----------|
| Figma | https://figma.com/ | Spec / handoff when we need a canvas, not tokens |
| Framer | https://framer.com/ | Motion / marketing prototypes (translate to React + tokens) |

### Reading / craft

| Source | URL | Pull for |
|--------|-----|----------|
| Refactoring UI | https://refactoringui.com/ | Practical spacing, hierarchy, restraint |
| Animations.dev | https://www.animations.dev/ | Motion that respects reduced-motion + one moment per surface |

Re-check Designeer’s Design Galleries / Reading / Motion / Interface Design sections for new entries; this table is a **seed**, not a closed list.

---

## How digiweb should use it

1. **Explore** — open https://designeer.xyz (or `search_tools` / section lists via WebMCP) for the problem class (nav, bento, blotter density, AI chat chrome).
2. **Shortlist** — 1–3 galleries or essays; note URLs here or in a follow-up site scan under `packages/design/references/`.
3. **Translate** — implement through `@digithings/design` tokens and live patterns in `apps/reference` — never paste foreign CSS/brand into digiquant / twelve-x / digithings-web.
4. **Promote** — if a source becomes a lasting north star, add a full scan page (same shape as `herdr.dev.md`) and a row in [`README.md`](README.md)’s north-star table.

---

## Adopt / Adapt / Avoid

| Stance | Guidance |
|--------|----------|
| **Adopt** | Designeer as the shared **index** of external inspiration + tools |
| **Adapt** | Individual gallery patterns into digiweb tokens / specimens |
| **Avoid** | Copying Designeer’s site UI, rankings, or sponsor chrome; treating any listed tool as mandatory stack |

---

## One-line lesson

> Designeer is the map. Our digiweb references and `apps/reference` are the territory we actually ship.
