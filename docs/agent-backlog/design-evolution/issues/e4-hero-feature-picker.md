## Goal

Build shared **`HeroFeaturePicker`** primitive — Graphite icon row below hero that switches `ProductFrame` preview context (Olympus / tearsheet / pipeline) on digiquant.io ([design spec §Layer A](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] CSS `.hero-picker` > buttons with `[aria-selected]` + panel region for swapping frame children
- [ ] Icon buttons ~53×53px (Graphite reference)
- [ ] Static UI crops only — no video swap (lighter weight per spec)
- [ ] Keyboard accessible: arrow keys or tab + enter; `aria-controls` on panels
- [ ] 3 tabs minimum in demo: Olympus · Strategies · Pipeline
- [ ] Integrates with `ProductFrame` (#1202) without clipping at browser zoom
- [ ] Document in `frontend/design/site/README.md`

## Test Requirements

- Manual: tab switch updates frame content; focus ring visible
- Build digiquant-web after wiring in follow-up

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- digiquant hero wiring (#1213 — can add picker in same PR or follow-up)
- Video assets

## Dependencies

- Blocked by: #1202 (ProductFrame), #1213 (digiquant hero)
- Unblocks: digiquant hero picker integration

## Human Gate Required?

- [ ] No
