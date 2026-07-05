## Goal

Build **`StatCounter`** — scroll-triggered animated metrics (x.ai API scale + Cursor enterprise %) for hero and feature bands ([`xai-full.md`](../../../../frontend/design/references/scans/xai-full.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] JS module `frontend/design/stat-counter.js` (or extend scroll-trigger):
  - Observes `.stat-counter` elements; animates from 0 → `data-target` on enter viewport
  - Supports `data-prefix`, `data-suffix`, `data-decimals`
  - Uses `tabular-nums` + Geist Mono styling via `.stat-counter__value`
- [ ] CSS for `.stat-counter` row — horizontal strip of 2–4 metrics with mono uppercase labels (xAI)
- [ ] **No fake data policy:** demo uses clearly labeled placeholders; real wiring optional via `data-target` from props
- [ ] `prefers-reduced-motion`: show final value immediately
- [ ] Demo in smoke page
- [ ] Document API in `site/README.md`

## Test Requirements

- Unit test optional (number formatting); manual scroll trigger sufficient for v1

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/EVOLUTION.md`
- [ ] Note in `EVOLUTION.md` §10 anti-patterns: fake tickers rejected

## Out of Scope

- Live API metrics fetch (Phase C may wire real counts when available)
- twelve-x integration (D2)

## Dependencies

- Blocked by: A1
- Unblocks: C4, D2

## Human Gate Required?

- [ ] No
