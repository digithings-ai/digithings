# DigiChat controls ledger (#1419)

State of `src/components/ui/*` after the E4 adoption: which wrappers became
thin re-exports of the shared `@digithings/web` controls layer, which stayed
local, and every known rendered-look delta for browser QA. Companion to the
E3 ledger pattern; the shared controls themselves live in
`frontend/digiweb/web/src/components/controls/` with dress CSS in
`frontend/digiweb/web/src/styles/controls-core.css` (static atoms) and
`controls-overlay.css` (behavioral controls).

## Swapped — thin re-exports of `@digithings/web`

| ui/ file | Shared control | Pin | Notes |
|---|---|---|---|
| `button.tsx` | `Button` | `dress="chat"` | digichat variant/size enums verbatim (`ButtonChatVariant`/`ButtonChatSize`). `buttonVariants` cva export dropped — zero importers (grep-verified). |
| `badge.tsx` | `Badge` | `dress="chat"` | useRender `render` prop + `{ slot, variant }` state preserved. `badgeVariants` export dropped — zero importers. |
| `card.tsx` | `Card` + parts | `dress="chat"` on root | Full 7-part shape, `size` `"default" \| "sm"`, `data-slot`/`data-size` hooks. |
| `input.tsx` | `Input` | `dress="chat"` | Same `@base-ui/react/input` primitive underneath. |
| `label.tsx` | `Label` | `dress="chat"` | `.group data-disabled` / `.peer:disabled` dimming kept (unlayered rules). |
| `avatar.tsx` | `Avatar` family | none (single dress) | Image/Fallback/Badge/Group/GroupCount; currently no digichat call sites (kept for surface compat). |
| `collapsible.tsx` | `Collapsible` family | none (unstyled passthrough) | Identical to the old wrapper. |
| `dropdown-menu.tsx` | `DropdownMenu` family (15 names) | none — default skin IS the chat dress | `skin="reference"` stays available on `DropdownMenuContent`. |
| `sheet.tsx` | `Sheet` family | none — single skin is the chat dress | Historical export surface kept: `SheetPortal`/`SheetOverlay` exist upstream but were never exported here. |
| `tooltip.tsx` | `Tooltip` family | none — default skin IS the chat dress | Provider `delay` defaults to 0; `skin="reference"` available on `TooltipContent`. |

Import sites: **zero changes** — every consumer still imports from
`@/components/ui/<x>`.

## Kept local — no shared counterpart yet

| ui/ file | Why |
|---|---|
| `scroll-area.tsx` | No shared ScrollArea control in `@digithings/web` yet. |
| `separator.tsx` | No shared Separator. |
| `sidebar.tsx` | shadcn sidebar system (cva + useRender + local Sheet/Tooltip/Button/Input/Separator/Skeleton composition). Not currently mounted by any digichat page. |
| `skeleton.tsx` | No shared Skeleton. |
| `textarea.tsx` | No shared Textarea (the reference `.ff-input` grammar has no multiline specimen promoted yet). |

Dependency outcome: `@base-ui/react` **stays** in `package.json` —
`scroll-area.tsx`, `separator.tsx`, and `sidebar.tsx` still import it
directly. `class-variance-authority` (sidebar), `tailwind-merge` (`cn`),
and `lucide-react` (app icons) also remain in use.

## Cascade contract (how parity is held without tailwind-merge)

The old wrappers resolved base-vs-call-site utility conflicts with
`cn()` = tailwind-merge (call site wins) while variant-ed base utilities
(`hover:`, `focus-visible:`, `aria-*`, `data-*`, `has-*`) compiled to
≥(0,2,0) selectors that beat plain call-site utilities. The shared CSS
reproduces exactly that split (see the `controls-core.css` header):
chat-dress defaults sit in `@layer components` (call-site utilities win),
state/structural rules are unlayered (they keep winning). Verified against
the compiled `next build` output:
`.ctl-*` defaults → `@layer components`, `.ctl-*:hover|:focus-visible|
[aria-*]|[data-size]|[data-theme=dark]` + `.ctl-sheet[data-side=*]`
geometry → unlayered, call-site `p-8`/`text-[9px]`/`h-6`/`sm:max-w-lg` →
`@layer utilities`.

Notably preserved (all verified against Tailwind v4.2.2 compiled
specificity/order of the OLD dress):

- Sheets stay **75% wide capped at 24rem** from the `sm` breakpoint — the
  call-site `w-full max-w-md` (BYOK panel) and `w-full sm:max-w-lg`
  (connections sheet) never actually won against the old
  `data-[side=right]:*` variants (0,2,0 beats 0,1,0), and still don't.
- Ghost-button hover still flips text to `--foreground` even where a call
  site pins a text color (`text-muted-foreground` on chat-panel copy/
  regenerate and byok-cli-flow close; `text-destructive
  hover:text-destructive` on byok-cli-flow "Clear key") — in the old build
  the base `hover:text-foreground` won those ties via compiled utility
  order, and the unlayered shared hover rule reproduces the same outcome.
- Delete item in the thread dropdown: idle `text-destructive`, focus keeps
  destructive text (call-site `focus:text-destructive` beats the
  components-layer `.ctl-menu-item:focus` color), icons flip to ink.

## Known deltas for browser QA (rendered-look risk, all transient states)

1. **chat-panel scroll-to-bottom button** (`variant="secondary"
   className="pointer-events-auto shadow-md"`): while `:focus-visible`,
   the old dress *composed* the ring with `shadow-md` (Tailwind ring/shadow
   var chain); the shared dress's unlayered `box-shadow` ring now
   *replaces* `shadow-md` for the duration of focus. Idle/hover unchanged.
2. **Inline SVG icons replace lucide** inside the shared Sheet close button
   (X) and DropdownMenu sub-trigger/check indicators (ChevronRight, Check).
   Same 24-viewBox geometry, `stroke-width` 2, `currentColor`, sized by the
   same `svg:not([class*='size-'])` rules — expected pixel-identical, worth
   one glance.
3. **ui/sidebar.tsx** (not mounted anywhere today): its mobile
   `SheetContent className="bg-sidebar …"` now beats the component-baked
   `bg-bg` via compiled utility order (`.bg-sidebar` sorts after `.bg-bg`)
   rather than tailwind-merge — same winner today, but order-dependent; if
   the sidebar is ever mounted, re-verify.

## Dropped exports

- `buttonVariants` (ui/button.tsx), `badgeVariants` (ui/badge.tsx) — cva
  artifacts with zero importers. Restore by wrapping the shared enums if a
  future call site needs class-string composition.
