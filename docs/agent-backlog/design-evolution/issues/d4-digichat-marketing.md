## Goal

Align **DigiChat** marketing/public route with Cursor "product is the hero" model — full chat chrome as pitch + `CodeSampleBand` for BYOK/API ([`EVOLUTION.md` §3 DigiChat](../../../../frontend/digiweb/design/EVOLUTION.md)).

## Component

- [x] `frontend/digichat/`

## Acceptance Criteria

- [ ] Marketing route (e.g. `/` unauthenticated or dedicated `/welcome`) minimizes wrapper chrome — terminal/session UI is the visual hero
- [ ] `CodeSampleBand` section for API/BYOK with tabs (`curl`, Python, TypeScript)
- [ ] Shared tokens from #240 applied (no hand-maintained `.dark` hex blocks)
- [ ] Cyan/purple accent alignment with v2 tokens
- [ ] `npm run lint && npm run test` in digichat passes
- [ ] No regression to authenticated chat UX

## Test Requirements

```bash
cd frontend/digichat && npm run lint && npm run test
```

Manual: `/login`, main chat route, marketing route

## Documentation to Update

- [ ] `frontend/digichat/README.md`
- [ ] `frontend/digiweb/design/EVOLUTION.md`

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
