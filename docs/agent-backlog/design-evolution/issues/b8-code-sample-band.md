## Goal

Build **`CodeSampleBand`** — x.ai tabbed SDK / Cursor curl row for API and BYOK marketing ([`xai-full.md`](../../../../frontend/design/references/scans/xai-full.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] CSS + minimal JS for `.code-sample-band`:
  - Tab list (e.g. `curl`, `Python`, `TypeScript`) switching visible code block
  - Copy-to-clipboard button on active block (reuse terminal patterns if available)
  - Geist Mono, dark code surface, 1px border
- [ ] Accessible tabs: keyboard nav, `aria-selected`, focus ring
- [ ] Demo with 3 tabs in smoke page
- [ ] Document in `site/README.md`

## Test Requirements

- Manual: tab switch + copy works
- No network calls in unit tests

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- DigiChat marketing route wiring (D4)
- Live API key generation

## Dependencies

- Blocked by: A1
- Unblocks: D4

## Human Gate Required?

- [ ] No
