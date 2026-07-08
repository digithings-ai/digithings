## Goal

Realign **digithings.ai** hero to Cursor pattern: literal primary CTA, trust strip, and `ProductFrame` product visual — per [`EVOLUTION.md` §3 digithings](../../../../frontend/digiweb/design/EVOLUTION.md).

## Component

- [x] `frontend/digithings-web/`

## Acceptance Criteria

- [ ] Hero includes:
  - Primary CTA: `Ask DigiChat` (or `Open docs` — pick one primary, one secondary ghost)
  - Secondary CTA with arrow suffix where appropriate
  - `TrustStrip` below CTAs: e.g. `open core · self-hosted · MCP-first`
  - `ProductFrame` showing supervisor diagram or static chat embed crop (no mesh on UI)
- [ ] Serif display (Fraunces) retained for h1 only; section headings sans per typography rules
- [ ] Mesh/grain atmosphere **hero only** — section below hero uses flat `--bg`
- [ ] `reveal-up` on hero text block (respects reduced motion)
- [ ] Mobile (390px): CTAs stack, frame scales via CQ, no horizontal overflow
- [ ] `npm run build` in `frontend/digithings-web` passes

## Test Requirements

**Manual smoke checklist:**
- [ ] Light + dark theme
- [ ] Primary CTA href correct (`/chat`, docs, or configured URL)
- [ ] No decorative eyebrow pill without action

## Documentation to Update

- [ ] `frontend/digithings-web/README.md` or landing component doc if exists
- [ ] `frontend/digiweb/design/EVOLUTION.md` Phase C digithings hero item

## Out of Scope

- Bento module grid (C2)
- Live DigiChat embed (#204)
- Changelog band (C3)

## Dependencies

- Blocked by: B1 (ProductFrame), B3 (TrustStrip + reveal-up)
- Unblocks: C2

## Human Gate Required?

- [ ] No
