## Goal

Add shared **`TrustStrip`** (logo/proof row) and **`reveal-up`** enter-animation utilities — Cursor hero trust line + Graphite friction reducers + Graphite glide reveals ([`copy-patterns.md`](../../../../frontend/digiweb/design/references/scans/copy-patterns.md)).

## Component

- [x] cross-cutting (`frontend/digiweb/design/`)

## Acceptance Criteria

- [ ] `.trust-strip` — horizontal flex/grid of proof items (text or logo slots), muted `--text-secondary`, works centered below hero CTAs
- [ ] `.trust-strip__item` — supports text (`open core · self-hosted`) or `<img>` logo with consistent height (~24–32px)
- [ ] `.reveal-up` utility — initial `opacity: 0; translateY(1rem)`; `.reveal-up.is-visible` (or `[data-revealed]`) animates with `--ease-glide` + `--duration-reveal`
- [ ] Integrate with existing `frontend/digiweb/design/scroll-trigger.js` or `site/reveal.js` — document trigger contract
- [ ] Respect `prefers-reduced-motion: reduce` (instant visible state)
- [ ] Demo in smoke page
- [ ] Document in `site/README.md`

## Test Requirements

- Manual: toggle reduced motion in OS; elements appear without animation
- Build both landing apps

## Documentation to Update

- [ ] `frontend/digiweb/design/site/README.md`
- [ ] `frontend/digiweb/design/EVOLUTION.md`

## Out of Scope

- Real customer logos (use placeholders)
- Hero CTA wiring (Phase C)

## Dependencies

- Blocked by: A1
- Unblocks: C1, C4

## Human Gate Required?

- [ ] No
