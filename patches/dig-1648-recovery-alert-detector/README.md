# DIG-1648 — watchdog recovery-alert detector: keys on a metric that is never written

## The defect

`dt-it-watch` section 6 (`recovery_alert.breached_zero_resolution`) fired an IT incident when

```python
alert.breached and (resolvedTakeovers + handedBack + ownerCompleted + otherTakeover + selfRecovery) == 0
```

`resolution_sum` is still `0` **because the platform never writes those columns**, not because
nothing is being resolved. Measured on `GET /api/companies/{co}/recovery-observability`:

- `sum(byCause[].resolvedCount)` = 37,891 of 37,893 on `legacy_execution_requires_reconciliation`
- every `perCauseRouting` outcome column is `0` across all 7 causes except `cancelled`
- `handoff` = `resolvedTakeovers 0, handedBack 0, ownerCompleted 0, otherTakeover 0, selfRecovery 0`

This is the CTO's item 5 on DIG-1648: the "resolved" figure is not progress. So the detector measured
the metric rather than the condition, and was eligible to page IT on a queue whose *active* backlog
had already fallen from 16,738 to 41.

`watch-state.json` held `recovery_alert.breached_zero_resolution: 1791330412`
= `2026-10-06T23:46:52Z`, i.e. past the 7-day mark on **2026-10-09**. The page would have landed on
a stale premise the same day it was diagnosed.

## The fix

Key on what is actually stuck — board-owned actions that are **still active**, from the same
`byCause` breakdown the dashboard is built on — and require a material backlog (`>= 25` active)
before arming:

```python
active_board = sum((b.get("activeCount") or 0) for b in (ro.get("byCause") or []))
if breached and active_board >= 25:
```

`handoff.boardOwned` is a **cumulative lifetime count and never falls** (16,738 -> 29,432 ->
38,290), so using it would pin the rule on forever once it trips. The incident text now carries the
per-cause active breakdown and an explicit warning that the outcome counters are unwritten.

The `resolution_sum` computation is kept — the incident body quotes it — but it no longer gates.

## Verification

`fixture-live-2026-10-09T16Z.json` is a real captured payload. Replaying both predicates:

| case | old | new | active | res_sum |
|---|---|---|---|---|
| ARM — live 16:01Z | fire | fire | 41 | 0 |
| CONTAMINATED — disposition backlog back at pre-patch level | fire | fire | 149 | 0 |
| CONTROL — fully drained, alert still breached | **fire** | **silent** | 0 | 0 |

The control is the point: the old predicate pages on a drained queue. The ARM case is what stops
this being a no-op — the new predicate still detects a real backlog. The fixture's own active total
is asserted to be 41, so a mis-built fixture fails loudly instead of passing vacuously.

`ast.parse` on the patched file passes. Not applied to the live tool: `kit/bin/dt-it-watch` is dirty
in the shared checkout and was edited 30 minutes before this patch was written, so landing it here
would collide with another run's uncommitted work.

## Files

- `dig-1648-recovery-alert-detector.patch` — the diff (55 lines)
- `fixture-live-2026-10-09T16Z.json` — the captured payload the verification replays

Lands with `git apply dig-1648-recovery-alert-detector.patch` from `kit/`.
