## Goal

Align **digichat** marketing/public route with Cursor "product is the hero" model — full chat chrome as pitch + `CodeSampleBand` for BYOK/API ([`EVOLUTION.md` §3 digichat](../../../../packages/design/EVOLUTION.md)).

## Component

- [x] `apps/digichat/`

## Acceptance Criteria

- [ ] Marketing route (e.g. `/` unauthenticated or dedicated `/welcome`) minimizes wrapper chrome — terminal/session UI is the visual hero
- [ ] `CodeSampleBand` section for API/BYOK with tabs (`curl`, Python, TypeScript)
- [ ] Shared tokens from #240 applied (no hand-maintained `.dark` hex blocks)
- [ ] Cyan/purple accent alignment with v2 tokens
- [ ] `npm run lint && npm run test` in digichat passes
- [ ] No regression to authenticated chat UX

## Test Requirements

```bash
cd apps/digichat && npm run lint && npm run test
```

Manual: `/login`, main chat route, marketing route

## Documentation to Update

- [ ] `apps/digichat/README.md`
- [ ] `packages/design/EVOLUTION.md`

## Out of Scope

- BYOK model selector (#201)
- SSO (#202)
- Conversation history (#205)
- Embed route (#261)

## Dependencies

- Blocked by: B8 (CodeSampleBand), #240 (token adoption)
- Unblocks: none

## Human Gate Required?

- [ ] No
