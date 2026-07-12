## Goal

Build **`CapabilityCard`** — x.ai-style mini UI preview + "Explore →" link, composable inside bento cells or standalone grid ([`components-catalog.md`](../../../../frontend/digiweb/design/references/scans/components-catalog.md)).

## Component

- [x] cross-cutting (`frontend/digiweb/design/`)

## Acceptance Criteria

- [ ] CSS `.capability-card`:
  - Optional `.capability-card__preview` slot (image, `ProductFrame` child, or terminal snippet)
  - `.capability-card__title`, `.capability-card__body`
  - `.capability-card__cta` — text link with arrow suffix (`Explore →`)
- [ ] Works as `.bento__cell` composition or standalone `.capability-grid`
- [ ] Flat surface, hairline border — no decorative eyebrow pills without action (anti-pattern #3)
- [ ] Demo: 2 cards with ProductFrame previews in smoke page

## Test Requirements

- Visual smoke at light/dark themes

## Documentation to Update

- [ ] `frontend/digiweb/design/site/README.md`
- [ ] `frontend/digiweb/design/EVOLUTION.md`

## Out of Scope

- Real module screenshots (Phase C content)

## Dependencies

- Blocked by: B1, B2
- Unblocks: C2

## Human Gate Required?

- [ ] No
