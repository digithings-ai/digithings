# DigiQuant dashboard canvas → Claude Code handoff

**Date:** 2026-10-01 (Europe/Rome)  
**PR:** https://github.com/digithings-ai/digithings/pull/4911 (draft)  
**Branch:** `cursor/digiquant-dashboard-skeleton-mocks-67ef`  
**Tip (visual-ready remock):** `d5e0193c6` — pane size drag  
**Local serve:** `http://127.0.0.1:3920/` from `docs/dashboard-mocks/canvas/` (launchd `com.chris.dq-3920` when present)  
**HOLD:** do **not** hatch / Merge / undraft until Chris says go.

This handoff is for **implementing the real DigiQuant dashboard** (React / `apps/dashboard`) from the locked canvas mocks. digiquant.io is a separate lane (Coder A / cloud) — out of scope here.

---

## What the canvas is

Static HTML/CSS/JS mocks under `docs/dashboard-mocks/canvas/`:

| File | Role |
|------|------|
| `mock.css` | Layout, rails, atoms, Vela DigiQuant chart tokens, pane resize handles |
| `mock-nav.js` | Left nav, DigiChat right rail, desk picker, palette, pane rearrange / fullscreen / **size drag**, chart wheel → page scroll |
| `*.html` | Page frames (brief, holdings, charts, luxalgo, pipeline, …) |

Open `http://127.0.0.1:3920/brief.html` first for layout + resize/reorder.

---

## Locked craft (implement these)

### Layout / IA
1. **One viewport per page** — never taller or shorter than the window; panes rearrange / resize / scroll *inside*; overflow → sidebar **sub-tabs**, not page length.
2. **Nested left sidebar** — section click reveals subsections in the rail; **kill** horizontal in-page section tabs.
3. **Top chrome = path only** (`house / portfolio / holdings`) — that path tree is the DigiQuant API / component map.
4. **Narrow panes:** column priority (drop low-priority columns); every pane has **fullscreen + Esc**.
5. **Desk picker:** compact dropdown/popover by default (wider than rail), expand to full-screen overlay; choosing a desk swaps the sidebar.
6. **Rails:** DigiQuant left rail stays; **DigiChat right rail**.
7. **HOLD hatch** until Chris visual-OKs and says ship.

### Polish dump
8. Brief **nest** into subpages if one viewport still overflows.
9. Sparse pages **stretch** to fill the viewport.
10. Shared **atoms:** table / chart / feed / pipeline / tearsheet — same primitives everywhere.
11. **Kill** the top KPI / metrics strip.
12. Panes **dynamically rearrangeable** (drag handle ⋮⋮).

### Later locks (already on tip `d5e0193c6`)
13. **Chart vertical wheel** → scroll the page/parent (`.main > .col`), not the chart; keep horizontal pan/zoom.
14. **Top navigator / `01` eyebrows behind DigiChat** when chat is open (chat rail covers top; path/eyebrows not competing with chat).
15. **Vela DigiQuant chart theme:** bull = DigiQuant teal, bear = DigiQuant red — **not** stock TradingView green/red; full pane color scale from DigiQuant tokens (canon ref: `apps/dashboard/lib/chart-colors.ts` DARK_FALLBACK — teal `#3dd6c4` / red `#e5533e` on canvas).
16. **Pane size drag:** right edge snaps 12-col width; bottom edge sets height; persist per page (sessionStorage on mocks). Rearrange only from ⋮⋮; hide resize handles in pane fullscreen.

### Visual SoT
- Header look: lighter-gray section eyebrows from polish tip `051f13ec` (folded into later remocks).
- Current tip for handoff: **`d5e0193c6`**.

---

## Tip lineage (newest last)

| Tip | What |
|-----|------|
| `051f13ec` | Visual SoT polish (lighter-gray section headers) |
| `d548ae650` | Nav tip — superseded for visual by remocks |
| `29463fbf2` | Seven-lock remock |
| `9b64a1bf4` | Polish dump (locks 8–12) |
| `1f12a925b` | Chart vertical wheel → page scroll |
| `f68195d99` | DigiChat covers top nav + Vela DigiQuant colors |
| **`d5e0193c6`** | **Pane size drag** ← current |

---

## What to implement next (real app)

1. Map canvas IA → `apps/dashboard` routes / path segments matching top path + sidebar tree.
2. Port layout shell: left DigiQuant rail, right DigiChat rail, path-only top, one-viewport main column.
3. Pane model: reorder + resize + fullscreen + persist (replace sessionStorage with real user prefs when ready).
4. Atoms: table / chart (Vela + DigiQuant theme) / feed / pipeline / tearsheet.
5. Desk picker: popover + fullscreen overlay.
6. Brief and other pages as one-viewport compositions; nest via sidebar sub-tabs when content overflows.
7. Do **not** treat digiquant-web (:3910 / #4900) or digithings.ai home (:3901 / #4916) as this PR’s scope unless Chris says otherwise.

---

## Remotes / forge

- GitHub PR #4911 tracks the canvas branch for review.
- Cursor Origin may also hold the same branch tip for agentic work.
- PRs into `develop`; Chris / One gate Merge — **Web does not hatch**.

---

## Out of scope tonight

- digiquant.io (Coder A / separate cloud)
- Hatch / Merge / undraft of #4911
- digivoice / digikey / other modules
