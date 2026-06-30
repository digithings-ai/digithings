## Goal

Build shared **`FaqAccordion`** and **`PricingMatrix`** primitives — Graphite/Cursor pricing page patterns for digiquant.io `/#pricing` ([design spec §Layer A](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] `.faq` > `.faq__item` with `<details>`/`<summary>` or JS accordion — one open at a time optional
- [ ] `.pricing` grid + `.pricing__tier` cards (3 tiers: Self-hosted MIT · Managed future · Enterprise contact)
- [ ] Optional comparison table rows with ✓ checkmarks
- [ ] Open-core honest copy — no fake "limited AI requests"
- [ ] JSON content shape documented for FAQ + tiers per site
- [ ] `prefers-reduced-motion` respected on expand/collapse
- [ ] Demo in smoke page
- [ ] Document in `frontend/design/site/README.md`

## Test Requirements

```bash
cd frontend/digiquant-web && npm run build
```

Manual: keyboard expand FAQ; tier cards responsive at mobile.

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/COPY_GUIDE.md` §8 pricing voice

## Out of Scope

- digiquant landing wiring (E6)
- digithings self-host FAQ (optional follow-up)

## Dependencies

- Blocked by: #1201
- Unblocks: E6

## Human Gate Required?

- [ ] No
