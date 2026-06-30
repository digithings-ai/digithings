## Goal

Wire **`ClosingCtaBand`** (E2) on both **digithings.ai** and **digiquant.io** — final conversion section before footer with literal CTAs ([COPY_GUIDE.md §6–10](../../../frontend/design/COPY_GUIDE.md)).

## Component

- [x] `frontend/digithings-web/`, `frontend/digiquant-web/`

## Acceptance Criteria

- [ ] digithings.ai: closing band with headline + primary `ask digichat` + secondary `read docs` →
- [ ] digiquant.io: closing band with headline + primary `open olympus` + optional secondary
- [ ] Placed after changelog/features, immediately before footer on both sites
- [ ] Copy matches COPY_GUIDE draft lines
- [ ] `reveal-up` enter; reduced motion respected
- [ ] Build passes for both apps

## Test Requirements

```bash
cd frontend/digithings-web && npm run build
cd frontend/digiquant-web && npm run build
```

Manual: scroll to footer — closing CTA visible on both sites.

## Documentation to Update

- [ ] `frontend/design/EVOLUTION.md` — note Phase E wiring

## Out of Scope

- Hero CTA changes (#1210, #1213)
- A/B copy testing

## Dependencies

- Blocked by: E2, #1210 (digithings), #1213 (digiquant)
- Unblocks: none

## Human Gate Required?

- [ ] No
