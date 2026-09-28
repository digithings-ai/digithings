## Goal

Wire **`PricingMatrix`** + **`FaqAccordion`** (E3) into digiquant.io `/#pricing` section with honest open-core tier copy ([COPY_GUIDE.md §10](../../../../packages/design/COPY_GUIDE.md)).

## Component

- [x] `apps/digiquant-web/`

## Acceptance Criteria

- [ ] `/#pricing` anchor section with 3 tiers: Self-hosted (MIT) · Managed (future) · Enterprise (contact)
- [ ] FAQ accordion below tier matrix — self-host requirements, NautilusTrader license, BYOK, no fake limits
- [ ] Content in JSON or TS module (document source of truth)
- [ ] Bento Pricing cell (#1214) links to this section
- [ ] Literal CTAs per COPY_GUIDE (`open olympus`, `contact@digithings.ai`)
- [ ] Build passes; no visual regression on StrategySuite / Olympus pin

## Test Requirements

```bash
cd apps/digiquant-web && npm run build
```

Manual: navigate to `/#pricing`; FAQ keyboard accessible.

## Documentation to Update

- [ ] `packages/design/demos/digiquant-landing/DESIGN_DECISIONS.md`
- [ ] `packages/design/COPY_GUIDE.md` if tier copy changes

## Out of Scope

- Commercial billing integration
- digithings self-host FAQ (optional)

## Dependencies

- Blocked by: E3, #1214
- Unblocks: none

## Human Gate Required?

- [ ] No
