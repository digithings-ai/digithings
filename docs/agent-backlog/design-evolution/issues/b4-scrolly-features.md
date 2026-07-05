## Goal

Extract a reusable **`ScrollyFeatures`** primitive from digiquant's `PipelineScene` / strategy scroll patterns — Graphite-style pinned section + progress rail + N slides ([`graphite-full.md`](../../../frontend/design/references/scans/graphite-full.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] Shared module (JS + CSS) under `frontend/design/`:
  - Sticky pin container with configurable slide count
  - **Progress rail** — vertical or horizontal indicator showing active slide index (Graphite pattern)
  - Scroll-driven slide transitions using existing scroll-trigger patterns
  - Dynamic scrolly height from measured pin content (lesson from #1198)
- [ ] Refactor `frontend/digiquant-web` Olympus `PipelineScene` to consume primitive **without visual regression** (screenshot or manual checklist)
- [ ] API documented: `initScrollyFeatures(rootEl, { slides, onSlideChange? })` or React hook equivalent
- [ ] Anti-pattern enforced: primitive docs warn **max one pinned section per page**
- [ ] `prefers-reduced-motion`: show all slides in flow layout

## Test Requirements

- Manual scroll test on digiquant landing at 100% and 125% browser zoom
- `cd frontend/digiquant-web && npm run build`

## Documentation to Update

- [ ] `frontend/design/site/README.md` — ScrollyFeatures API
- [ ] `frontend/digiquant-web/ARCHITECTURE.md` if landing structure changes
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- Adding a second scrolly to digithings (optional future)
- Strategy suite card stack (separate component; may share scroll infra)

## Dependencies

- Blocked by: A1, B1 (product frames inside slides)
- Unblocks: C6

## Human Gate Required?

- [ ] No
