## Goal

Upgrade **digiquant.io** hero with Cursor literal CTAs, Graphite friction trust strip, and x.ai-style stat counters ([`EVOLUTION.md` §3 digiquant](../../../../frontend/digiweb/design/EVOLUTION.md)).

## Component

- [x] `frontend/digiquant-web/`

## Acceptance Criteria

- [ ] Hero primary CTA: `Open Olympus` (or equivalent product entry)
- [ ] Secondary CTA: `Browse strategies` → `/#strategies` or library route
- [ ] `TrustStrip`: e.g. `NautilusTrader · open core · Atlas + Hermes`
- [ ] `StatCounter` row with 2–4 metrics:
  - Use **real** values when available (strategy count, module count)
  - Placeholders clearly labeled in code comments if not wired
- [ ] Fraunces hero display retained
- [ ] No fake price ticker (anti-pattern #2)
- [ ] Build passes; mobile CTAs + stats stack cleanly

## Test Requirements

```bash
cd frontend/digiquant-web && npm run build
```

Manual: verify `/#strategies` hash scroll still works after #1198 fixes

## Documentation to Update

- [ ] `frontend/digiquant-web/README.md`
- [ ] `frontend/digiweb/design/EVOLUTION.md`

## Out of Scope

- Bento grid (C5)
- Olympus progress rail (C6)

## Dependencies

- Blocked by: B3, B5
- Unblocks: none

## Human Gate Required?

- [ ] No
