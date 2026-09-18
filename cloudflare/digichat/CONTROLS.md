# digichat controls ledger (#1419)

State of `src/components/ui/*` after the E4 adoption, the wave-3 kit
re-point, and the wave-4 dead-wrapper removal: which wrappers are thin
adapters over the canonical kit (`@digithings/web/ui`), which stayed local,
and every known rendered-look delta for browser QA. Companion to the E3
ledger pattern; the chat dress CSS
lives in `cloudflare/digiweb/web/src/styles/controls-core.css` (static atoms)
and `controls-overlay.css` (behavioral controls). The kit parts carry the
`dress="chat"` axis (wave-3 Important 1) that emits exactly those classes.

## Swapped — thin adapters over the kit (`@digithings/web/ui`)

| ui/ file | Kit part | Pin | Notes |
|---|---|---|---|
| `button.tsx` | `ui/button` | `dress="chat"` | digichat variant/size enums verbatim (`ButtonChatVariant`/`ButtonChatSize`) — identical to the kit's. `buttonVariants` cva export dropped — zero importers (grep-verified). |
| `card.tsx` | `ui/card` + parts | `dress="chat"` on root | Full 7-part shape, `size` `"default" \| "sm"`, `data-slot`/`data-size` hooks. Parts inherit the dress through the kit's Card context. |
| `collapsible.tsx` | `ui/collapsible` | none (unstyled passthrough) | Re-exports the kit `Collapsible` (re-pointed to `@digithings/web/ui` in wave 4); byte-identical to the deleted controls copy. |
| `dropdown-menu.tsx` | `DropdownMenu` family (15 names) | none — default skin IS the chat dress | `skin="reference"` stays available on `DropdownMenuContent`. |
| `tooltip.tsx` | `Tooltip` family | none — default skin IS the chat dress | Provider `delay` defaults to 0; `skin="reference"` available on `TooltipContent`. |

Import sites: **zero changes** — every consumer still imports from
`@/components/ui/<x>`.

## Removed in wave 4 — dead wrappers

`badge.tsx`, `input.tsx`, `label.tsx`, and `sheet.tsx` were deleted: every
call site had already moved to the kit (`@digithings/web/ui`), so the wrappers
had zero importers (grep-verified). `src/components/ui/` now holds only the
five thin adapters above — no local-only wrappers remain.

## Vendored trees (do not restyle)

`src/app/(baseline)/stock/ui/*` and `src/components/assistant-ui/skins/*` are
vendored assistant-ui trees kept verbatim (BLOCKED for restyle); they are not
part of this ledger.

Dependency outcome: `@base-ui/react` **stays** in `package.json` — the
vendored `app/(baseline)/stock/ui/*` and `components/assistant-ui/skins/*`
trees still import it directly. `class-variance-authority` (vendored skins),
`tailwind-merge` (`cn` in `lib/utils.ts`), and `lucide-react` (app icons) also
remain in use.

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
[aria-*]|[data-size]|[data-theme=dark]` state/structural rules → unlayered,
call-site `p-8`/`text-[9px]`/`h-6`/`sm:max-w-lg` → `@layer utilities`.

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

## Dropped exports

- `buttonVariants` (ui/button.tsx) — a cva artifact with zero importers.
  Restore by wrapping the shared enums if a future call site needs
  class-string composition. (`badgeVariants` no longer applies — `ui/badge.tsx`
  was deleted in wave 4; use the kit's `Badge`.)
