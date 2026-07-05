## Goal

Build shared **`AnnouncementBar`** primitive — Graphite 48px full-width clickable bar above nav, content-gated via JSON ([COPY_GUIDE.md §11](../../../../frontend/design/COPY_GUIDE.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] CSS `.announcement` — 48px height, full width, optional dismiss button
- [ ] `data-href` or config link target; entire bar clickable when href set
- [ ] Content gate: `announcement.json` (or equivalent) — when empty/disabled, bar not rendered
- [ ] Ship disabled by default in both landings; document enable procedure
- [ ] Respects `prefers-reduced-motion` (no slide animation required)
- [ ] Demo in smoke page with sample integration news copy
- [ ] Document in `frontend/design/site/README.md`

## Test Requirements

- Manual: with empty JSON — no bar; with content — bar visible, link works, dismiss persists (optional localStorage)
- Build both landing apps

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/COPY_GUIDE.md` §11

## Out of Scope
- Hardcoded per-deploy news copy
- Olympus/dashboard announcement bar (explicit reject)

## Dependencies

- Blocked by: #1201
- Unblocks: none (content-driven)

## Human Gate Required?

- [ ] No
