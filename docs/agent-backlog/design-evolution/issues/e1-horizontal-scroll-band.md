## Goal

Build shared **`HorizontalScrollBand`** primitive — Cursor-style horizontal snap scroll for changelog cards, testimonial rows, and mobile overflow bands ([`EVOLUTION.md` §6](../../../../cloudflare/digiweb/design/EVOLUTION.md), [design spec §Layer C](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`cloudflare/digiweb/design/`)

## Acceptance Criteria

- [ ] CSS `.h-scroll` > `.h-scroll__track` > `.h-scroll__card` with min-width ~262px (Cursor changelog card width)
- [ ] Scroll snap (`scroll-snap-type: x mandatory`) + optional edge fade masks
- [ ] `prefers-reduced-motion: reduce` → stack cards vertically (no horizontal scroll)
- [ ] Optional `horizontal-scroll.js` for keyboard nav / focus management (document if skipped)
- [ ] Demo in smoke page with 3+ cards
- [ ] Document in `cloudflare/digiweb/design/site/README.md`

## Test Requirements

```bash
cd cloudflare/digithings-web && npm run build
cd cloudflare/digiquant-web && npm run build
```

Manual: mobile viewport — cards snap; reduced motion — vertical stack.

## Documentation to Update

- [ ] `cloudflare/digiweb/design/site/README.md`
- [ ] `cloudflare/digiweb/design/EVOLUTION.md`

## Out of Scope

- ChangelogBand content wiring (C3)
- Real testimonial content

## Dependencies

- Blocked by: #1201 (motion tokens)
- Unblocks: C3 mobile changelog layout

## Human Gate Required?

- [ ] No
