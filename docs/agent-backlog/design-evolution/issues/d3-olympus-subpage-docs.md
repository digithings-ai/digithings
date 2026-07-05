## Goal

Document **Olympus subpage chrome** (sticky tab bar, breadcrumbs, section headers) in design references so twelve-x and future subpages stay aligned with Cursor literal-nav pattern ([`EVOLUTION.md` §3](../../../../frontend/design/EVOLUTION.md)).

## Component

- [x] cross-cutting (docs)

## Acceptance Criteria

- [ ] New doc `frontend/design/references/olympus-subpage-chrome.md` covering:
  - Tab bar anatomy (`SubpageStickyTabBar`)
  - When to use tabs vs sidebar
  - Typography roles on dashboard (Instrument Serif display, mono labels)
  - Surface/border rules post-D1
  - Screenshot or ASCII wireframe of standard subpage layout
- [ ] Linked from `frontend/design/references/README.md` and `EVOLUTION.md` §11
- [ ] `frontend/olympus/ARCHITECTURE.md` cross-links to new doc
- [ ] Docs-only PR; `make doc-check` passes

## Test Requirements

- `make doc-check`

## Documentation to Update

- [ ] `frontend/design/references/olympus-subpage-chrome.md` (new)
- [ ] `frontend/design/references/README.md`
- [ ] `frontend/design/EVOLUTION.md` — twelve-x alignment gap closed

## Out of Scope

- Code changes to tab bar
- New subpages

## Dependencies

- Blocked by: D1 (document final surface system)
- Unblocks: none

## Human Gate Required?

- [ ] No
