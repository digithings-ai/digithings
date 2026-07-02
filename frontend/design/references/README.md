# External design references

Curated deep scans of frontends we treat as **north stars** for DigiThings
public surfaces. These are not copy targets — they are pattern libraries for
navigation, layout rhythm, typography roles, motion, and product framing.

| Site | URL | Primary lesson | Best for our… |
|------|-----|----------------|---------------|
| [Graphite](graphite.com.md) | https://graphite.com | Scroll-pinned features, motion as brand, product-in-context | digiquant.io landing, marketing motion |
| [Cursor](cursor.com.md) | https://cursor.com | Utilitarian bento layout, literal CTAs, product frames | digithings.ai, digichat, docs surfaces |
| [xAI](x.ai.md) | https://x.ai | Brutalist restraint, mono display, capability demos | Olympus, twelve-x, API/developer pages |

**Deep scans (page-by-page, components, mobile, copy):** [`scans/INDEX.md`](scans/INDEX.md)

**Synthesis and evolution paths:** [`../EVOLUTION.md`](../EVOLUTION.md)

**Canonical implementation (ours):** [`../tokens.css`](../tokens.css), [`../site/site.css`](../site/site.css), [`@digithings/web`](../../web/)

**Olympus subpage chrome (tab bar, tabs-vs-sidebar, typography, surfaces):** [`olympus-subpage-chrome.md`](olympus-subpage-chrome.md)

---

## How to use these docs

1. **Before a landing redesign** — read `EVOLUTION.md` § Surface matrix, then the
   relevant site scan for the pattern you need (bento vs scrolly vs brutalist).
2. **Before a new shared primitive** — check whether Graphite, Cursor, or xAI
   already solved it; note the “Adopt / Adapt / Avoid” table in each scan.
3. **Before Olympus / twelve-x UI work** — Cursor + xAI scans; landing scans are
   intentionally deprioritized for dashboard density.
4. **When debating fonts or spacing** — `EVOLUTION.md` § Typography & spacing
   locks the direction; individual scans are evidence, not law.

---

## Methodology

Each scan documents (where observable from live site + public design analyses):

- Information architecture and section order
- Navigation (desktop, mobile, sticky behavior)
- Typography scale and font roles
- Color, surfaces, elevation
- Spacing, grid, and container widths
- Component inventory (buttons, cards, hero, social proof, etc.)
- Motion and scroll behavior
- **Adopt / Adapt / Avoid** for DigiThings

Scans are **living notes**. Re-audit when a reference site ships a major redesign.
Last full pass: **2026-06-29** (deep layer in [`scans/`](scans/INDEX.md)).

---

## Surfaces in scope

| Surface | Path | Design mode |
|---------|------|-------------|
| digithings.ai | `frontend/digithings-web/` | Marketing + architecture story |
| digiquant.io | `frontend/digiquant-web/` | Marketing + quant product proof |
| DigiChat | `frontend/digichat/` | Product-as-landing (terminal chat) |
| Olympus | `frontend/olympus/` | Professional dashboard |
| twelve-x | `frontend/olympus/components/twelve-x/` | Data-dense research utility |
| Shared system | `frontend/design/`, `frontend/web/` | Tokens, primitives, motion |

Legacy static sites (`frontend/digithings/`, `frontend/digiquant/`) are not
deployment targets; do not extend them.
