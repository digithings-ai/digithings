## Goal

Polish **twelve-x** FX research UI toward x.ai + Cursor utility: mono uppercase stat headers, outline filter pills, key-metric counter strip ([`EVOLUTION.md` §3 twelve-x](../../../frontend/design/EVOLUTION.md)).

## Component

- [x] `frontend/olympus/components/twelve-x/`

## Acceptance Criteria

- [ ] Metric/chart section headers use Geist Mono uppercase + letter-spacing (xAI label role)
- [ ] Filter controls use outline pills (1px `--hair`, no filled glass chips)
- [ ] `StatCounter` strip for 2–3 headline FX metrics (real Supabase data where available)
- [ ] **No** mesh, serif, or scroll storytelling added
- [ ] Tab bar (`SubpageStickyTabBar`) unchanged functionally; labels remain literal (Cursor)
- [ ] Build passes; matrix/consensus views readable at 1280px

## Test Requirements

```bash
cd frontend/olympus && npm run build
```

Manual: twelve-x tab navigation + filter interaction

## Documentation to Update

- [ ] `frontend/olympus/ARCHITECTURE.md` — twelve-x UI conventions
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- New data sources
- Olympus global flatten (D1) — coordinate styles

## Dependencies

- Blocked by: B5, D1
- Unblocks: none

## Human Gate Required?

- [ ] No
