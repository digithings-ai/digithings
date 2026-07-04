## Goal

Add **Graphite-style progress rail** to the digiquant.io Olympus scroll-pinned section via the shared `ScrollyFeatures` primitive ([`graphite-full.md`](../../../frontend/design/references/scans/graphite-full.md)).

## Component

- [x] `frontend/digiquant-web/`

## Acceptance Criteria

- [ ] Progress rail visible during `PipelineScene` (or unified scrolly) pin:
  - Shows slide/step index (dots or vertical tick marks)
  - Active step highlighted with `--accent` cyan
  - Updates synchronously with scroll position
- [ ] Rail hidden or simplified on mobile if space constrained (document breakpoint)
- [ ] `prefers-reduced-motion`: rail shows current step without scroll-driven animation
- [ ] No new pinned sections added
- [ ] Build passes; no overlap with StrategySuite or contact section (#1198 regressions)

## Test Requirements

- Manual scroll through full Olympus pin sequence
- Test at 390×844 and 1280×800

## Documentation to Update

- [ ] `frontend/digiquant-web` landing docs
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- Progress rail on StrategySuite (optional follow-up)
- digithings scrolly

## Dependencies

- Blocked by: B4 (ScrollyFeatures)
- Unblocks: none

## Human Gate Required?

- [ ] No
