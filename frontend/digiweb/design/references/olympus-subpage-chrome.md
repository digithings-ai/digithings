# Olympus subpage chrome

Reference for the shared navigation + layout chrome on Olympus dashboard subpages
(Portfolio, Research, Overview, twelve-x, …), so new subpages and twelve-x stay
aligned with the Cursor "literal navigation" pattern. Source of truth:
[`frontend/olympus/components/subpage-tab-bar.tsx`](../../olympus/components/subpage-tab-bar.tsx).

## Tab bar anatomy — `SubpageStickyTabBar`

A sticky, in-page section-nav bar that keeps a subpage's tabs visible as the main
column scrolls.

```
┌──────────────────────────────────────────────────────────┐ ← sticky, top:0 (md)
│  [ Overview ]  [ Portfolio ]  [ Research ]  [ Signals ]   │   border-b · --hair
└──────────────────────────────────────────────────────────┘   bg --surface/95 + blur
        ↑ literal labels (no icon-only); active tab = fin-blue tint
```

| Part | Classes / behaviour |
|------|---------------------|
| Bar | `sticky z-20 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md`; `md:top-0` (mobile `top-[72px]`, under the app bar). `role="navigation"` + `aria-label`. |
| Width | `SUBPAGE_MAX` = `max-w-[1600px] mx-auto w-full px-4 md:px-6` — the standard subpage content width. |
| Tab | `subpageTabButtonClass(active)`: `rounded-lg border px-3/4 py-1.5/2 text-xs/sm font-medium`. Active = `bg-fin-blue/15 text-fin-blue border-fin-blue/40`; idle = `text-text-secondary` + hover tint. |
| Mobile | Tabs collapse behind a "Sections" `Menu`/`X` trigger (`md:hidden`); the panel drops down (`bg-bg-glass/95`) and closes on route change, Escape, or outside click, with focus management. |

`backdrop-blur` lives **only** on the sticky bar (the mobile panel reuses the same
region) — never a second nested blur layer (that produces a double-blur artifact).

## Tabs vs sidebar

- **Sticky tab bar** — in-page sections of a *single* subject (Portfolio →
  Overview / Holdings / Signals; a twelve-x currency → Matrix / Consensus / Events).
  Literal word labels, never icon-only.
- **App sidebar** (`.app-sidebar`) — top-level destinations across the whole app
  (chat threads, primary areas). Not for within-subpage section nav.

## Typography roles

- **Display** — Instrument Serif (`--font-display`), used sparingly for a subpage's
  hero/section title only. Dashboards are not marketing — no serif on data.
- **Labels / data** — Geist Mono (`--font-mono`): `uppercase tracking-wider` for
  metric/column labels, `tabular-nums` for figures. Tab labels themselves are Geist
  Sans `font-medium` (literal words, not mono).

## Surface / border rules (post-#1216 flat migration)

- Flat `--surface` panels (`.glass-card` is a flat panel, *not* glass), 1px `--hair`
  (`--color-border-subtle`) borders, hover to `--hair-2`. No glass morphism on
  content (anti-pattern #8). See the surface-system note in
  `frontend/olympus/app/globals.css`.
- `backdrop-blur` is confined to sticky/overlay chrome (this tab bar, the app top
  bar, command palette, sidebar) — never content cards.
- Accent = Olympus cyan (`fin-blue` / `--accent`), used for the active tab + focus ring.

## Standard subpage layout

```
┌─────────────────────────────────────────────────┐
│ app top bar            (sticky, blurred)          │
├─────────────────────────────────────────────────┤
│ SubpageStickyTabBar    (sticky, blurred)          │
├─────────────────────────────────────────────────┤
│  ⟨ Instrument Serif section title ⟩               │
│                                                   │
│  ┌──── .glass-card (flat --surface, --hair) ───┐  │
│  │  // MONO LABEL                               │  │
│  │  tabular-nums metrics · charts · tables      │  │
│  └──────────────────────────────────────────────┘  │
│  (content width = SUBPAGE_MAX, max-w-[1600px])    │
└─────────────────────────────────────────────────┘
```

---

See also: [`../EVOLUTION.md`](../EVOLUTION.md) §3 (Olympus) and the surface-system
note in `frontend/olympus/app/globals.css` (#1216). Olympus has no `ARCHITECTURE.md`,
so this reference is the design home for subpage chrome.
