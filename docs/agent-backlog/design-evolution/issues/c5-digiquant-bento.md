## Goal

Demote extra digiquant.io scroll sections into a **Cursor bento grid** for Pipeline · Strategies · Pricing — with `ProductFrame` tearsheet/UI crops ([`EVOLUTION.md` §3](../../../../frontend/design/EVOLUTION.md)).

## Component

- [x] `frontend/digiquant-web/`

## Acceptance Criteria

- [ ] Bento section with 3+ cells:
  - **Pipeline** — link to Olympus pin or `/olympus`; preview in ProductFrame
  - **Strategies** — link to `/#strategies` or library; tearsheet crop in frame
  - **Pricing** — link to `/#pricing` or pricing section
- [ ] **Only one** scroll-pinned section remains on page (Olympus `PipelineScene` + StrategySuite per current design — document which sections stay pinned)
- [ ] Demoted sections: content moves into bento cards, not duplicated
- [ ] Teal/cyan accent on marketing; module green only inside quant UI previews
- [ ] No visual regression on StrategySuite scroll animation (#1198 behavior preserved)
- [ ] Build passes

## Test Requirements

- Manual scroll: Olympus pin + strategy stack + contact section z-order correct at 100%/125% zoom
- `cd frontend/digiquant-web && npm run build`

## Documentation to Update

- [ ] `frontend/design/demos/digiquant-landing/DESIGN_DECISIONS.md` — note bento demotion
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- Progress rail (C6)
- Pricing table redesign

## Dependencies

- Blocked by: B1, B2
- Unblocks: none

## Human Gate Required?

- [ ] No
