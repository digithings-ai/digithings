# DigiQuant dashboard — Claude Code IMPLEMENT handoff

**Date:** 2026-10-01 (Europe/Rome)  
**Audience:** Chris’s Claude Code session (real app implement — **not** another HTML remock squeeze)  
**PR (visual SoT / HOLD hatch):** https://github.com/digithings-ai/digithings/pull/4911 (draft)  
**Branch:** `cursor/digiquant-dashboard-skeleton-mocks-67ef`  
**Visual aid on `:3920`:** tip `051f13ec` (lighter-gray headers) — Chris **APPROVED** for **layout / look-feel only** — **not** product SoT  
**Serve:** `http://127.0.0.1:3920/` from `docs/dashboard-mocks/canvas/`  
**HOLD:** do **not** hatch / Merge / undraft #4911. Chris runs implement here; Web does not merge.

**Addendum (2026-10-01 ~22:45 Rome):** DigiCon API = data SoT (view→API ground-up). Remock `051f13ec` / `:3920` = visual aid only — not SoT / be-all.

**Out of scope:** digiquant.io (Coder A / separate cloud); digithings.ai home #4916; rewriting the static canvas into another cramped one-page remock.

---

## What you are building

Implement the **DigiQuant dashboard** in the real app (`apps/dashboard` and related packages).

**Ground-up rule:** every data-showing block (chart, table, feed, pipeline, tearsheet, …) is wired to an existing **DigiCon API** function path. Build **view → DigiCon API** first; the UI is a visualization of those paths. DigiCon already exists — discover and wire each view to a real path; do not invent a parallel fake data layer.

**Remock role:** `:3920` tip **`051f13ec`** is a **visual aid only** (type, hairlines, section eyebrows, terminal density / look-feel). It is **not** the source of truth, not the be-all for IA or data, and not something to pixel-clone into another HTML remock.

Do **not** copy the rejected dense remock lineage (`29463fbf2`…`47734f912`). Product behaviors below = app shell requirements via modular components + DigiCon wiring.

---

## Implement brief (Chris APPROVED 2026-10-01)

### 1. One viewport — no page scroll
Every page fits **one viewport**. The document/window does not scroll. Panes/sections scroll **inside** their own frames if content overflows. If a page still cannot fit, split into **sidebar sub-routes / nested sections** — never lengthen the page.

### 2. Modular sections — rearrangeable
Every section/block is a **modular design element** (atom/molecule). Blocks are **rearrangeable / movable** on the page (drag reorder; resize where it helps). Persist layout preferences when practical.

### 3. Collapsible sidebar — all nav in the rail
**All navigation lives in the sidebar** (collapsible). Section click reveals nested subsections in the rail. **Kill** horizontal in-page section tab bars. Desk picker: compact **dropdown/popover** by default (wider than a narrow rail), with expand to **full-screen** overlay — not a cramped in-rail-only list.

### 4. Shortcuts + prior design comments
Fold in usability / a11y / canvas locks from Chris’s comments:

- Verbatim: desk notes `chris-dashboard-canvas-comments-verbatim-2026-10-01.md` (Message D is the main IA lock text).
- **Locks 1–7 (product):**
  1. One viewport; panes rearrange/resize/scroll inside; overflow → sidebar sub-tabs  
  2. Nested left sidebar (no horizontal section tabs)  
  3. Top chrome = **path only** (`house / portfolio / holdings`) — that path tree mirrors DigiCon API / component paths  
  4. Narrow panes: **column priority**; every pane **fullscreen + Esc**  
  5. Desk picker: dropdown + fullscreen  
  6. **DigiChat right rail**; DigiQuant left rail stays  
  7. HOLD hatch on remock PR until Chris says otherwise  

Also fold: slash-path = page; keyboard jump + arrow cycle pages; DigiChat right; portfolio subpages nest under Portfolio.

### 5. Layered build order (do this sequence)
1. **Atoms first** — individual components (e.g. shared **table** atom, then chart / feed / pipeline / tearsheet primitives).  
2. **Brief sections next** — compose atoms into Brief blocks (e.g. **book table**, **movers table**, decision, signals).  
3. **Terminal multi-pane layout last** — Bloomberg-like split-screen shell: rails + path top + rearrangeable panes filling one viewport.

Do not start with a full-page remock of every Brief block jammed into one HTML file.

### 6. Every data block → DigiCon API function path (ground-up)
Every dashboard block that shows data (chart / table / etc.) maps to a **DigiCon API function path**. Build **ground-up view → DigiCon**: find the existing DigiCon endpoint/function for that view and wire it. Examples of path-shaped UI chrome: `/book`, `/movers`, `/house/portfolio/holdings/...` — the top path mirrors the DigiCon/API tree. No orphan visualizations; no mock-only data SoT.

### 7. Process
- Remock `:3920` / `051f13ec` = **visual aid only** (not SoT / be-all).  
- Data + behavior SoT = **DigiCon API** + implement brief above.  
- **HOLD hatch** on remock PR #4911.  
- Chris runs implement in **his Claude Code session**.  
- Prefer OpenCode / local Claude for implement; do not burn unrelated cloud lanes without One/Chris.

---

## Visual aid only (not SoT)

| Item | Value |
|------|--------|
| Tip | `051f13ec` on `:3920` |
| Role | Layout / look-feel reference only — **not** source of truth, not be-all |
| Data SoT | Existing **DigiCon API** — wire every data block to a function path |
| Look cues | Lighter-gray section headers, open mock windows, lifted type |
| Rejected | Dense one-page remock after `29463fbf2`; treating the remock as product SoT |

Open `http://127.0.0.1:3920/brief.html` (hard-refresh) for craft cues while implementing against DigiCon.

---

## Suggested first PRs (real app)

1. Table atom + path-aware data hook stub for `/book` (or equivalent DigiQuant path).  
2. Movers table atom + `/movers`.  
3. Brief page composition using those atoms (still one viewport).  
4. Shell: collapsible nested sidebar + path-only top + DigiChat right rail.  
5. Pane rearrange / resize / fullscreen + Esc.  
6. Desk picker popover + fullscreen.

---

## Remotes

- GitHub: digithings-ai/digithings PR #4911 (draft, HOLD).  
- Cursor Origin may mirror the same branch for agentic tips.

— Web (handoff for Claude Code)
