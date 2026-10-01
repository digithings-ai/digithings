# DigiQuant dashboard canvas → Claude Code handoff

**Date:** 2026-10-01 (Europe/Rome) — **REVERTED visual tip**  
**PR:** https://github.com/digithings-ai/digithings/pull/4911 (draft)  
**Branch:** `cursor/digiquant-dashboard-skeleton-mocks-67ef`  
**Tip (visual serve):** `051f13ec` — polish SoT Chris liked (lighter-gray headers; **not** the one-viewport / fit-everything remock)  
**Local serve:** `http://127.0.0.1:3920/` from `docs/dashboard-mocks/canvas/` (launchd `com.chris.dq-3920`)  
**HOLD:** do **not** hatch / Merge / undraft until Chris says go.

## Revert note (2026-10-01 ~22:40 Rome)

Chris rejected the cramped **one-viewport / fit-everything-in-one-page** remock lineage (`29463fbf2` → `47734f912`). `:3920` is restored to **`051f13ec`**. Later tips (dense remock, polish dump, chart wheel, nav-behind-chat, Vela colors, pane size drag) are **not** the served visual until he re-opens those locks.

digiquant.io is a separate lane (Coder A) — out of scope.

---

## What the canvas is (at 051f13ec)

Static HTML/CSS/JS under `docs/dashboard-mocks/canvas/`. Open `http://127.0.0.1:3920/` / `brief.html`.

---

## Locks still intended for product (do not force onto this tip’s layout)

These were spoken for the real dashboard; the **served mock** is the pre-squeeze polish, not the dense remock:

1. One viewport / rearrange / resize — **revisit after visual**; do not re-apply the cramped remock without Chris OK  
2. Nested left sidebar (kill horizontal section tabs)  
3. Top = path only  
4. Column priority + pane fullscreen + Esc  
5. Desk picker: compact dropdown + fullscreen  
6. DigiChat right rail; DigiQuant left rail  
7. HOLD hatch  

Polish dump / later craft (brief nest, atoms, kill KPI, chart wheel → page scroll, nav behind chat, Vela DigiQuant teal/red, pane size drag) — implement in app when Chris re-locks; **not** on `:3920` right now.

### Visual SoT
- **`051f13ec`** lighter-gray section headers — Chris preferred this over the one-page remock.

---

## Tip lineage (served = 051f13ec)

| Tip | What | Served? |
|-----|------|---------|
| **`051f13ec`** | Visual SoT polish | **YES** |
| `d548ae650` | Nav tip (side branch; not on this tip line) | no |
| `29463fbf2`…`47734f912` | One-page remock + follow-ons | **reverted off :3920** |

---

## What to implement next (real app)

Prefer matching **051f13ec** look/feel first. Re-introduce one-viewport density only if Chris asks again after visual.

---

## Out of scope

- Hatch / Merge / undraft of #4911  
- digiquant.io / digithings.ai #4916 (separate)  
