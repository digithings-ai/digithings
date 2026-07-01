# Database Backfill — Apr 16–Apr 29, 2026

**Status:** Complete  
**Started:** 2026-04-29  
**Completed:** 2026-04-29  
**Executor:** Claude Code (autonomous session)

## Context

Pipeline migration paused live runs from Apr 15 → Apr 29. This plan fills the gap with:
- T1: Data quality fixes on existing rows (Apr 8, Apr 15, nav_history)
- T2: Mechanical portfolio forward-propagation (Apr 22–28) from price_history
- T3: Synthesized research snapshots for Apr 16–29 (tagged, brief)
- T4: DEFERRED — deliberation sessions, trade events, new thesis entries (user review required)

All synthesized rows are tagged:
```json
{"_backfill": true, "_backfill_method": "claude-synthesized", "_backfill_date": "2026-04-29"}
```

## Safety constraints

- No writes to aspirational tables: `deliberation_sessions`, `deliberation_rounds`, `analyst_coverage`, `deep_dive_triggers`, `thesis_vehicles`
- No `position_events` beyond HOLD
- No new thesis entries — existing 6 theses carry forward
- All upserts use existing idempotency keys: `daily_snapshots(date)`, `documents(date,document_key)`, `nav_history(date)`, `positions(date,ticker)`, `portfolio_metrics(date)`
- Portfolio composition unchanged: BIL 40%, SHY 15%, SPY 15%, IAU 15%, XLP 10%, EFA 5%

## Rollback

All T2/T3 rows are uniquely identifiable via `_backfill: true` in snapshot JSONB metadata. To rollback:
```sql
-- Filtered rollback (safe — only removes rows with _backfill marker):
DELETE FROM daily_snapshots WHERE snapshot->>'_backfill' = 'true' AND date >= '2026-04-16';
DELETE FROM documents WHERE payload->>'_backfill' = 'true' AND date >= '2026-04-16';

-- ⚠ DESTRUCTIVE: nav_history/portfolio_metrics/positions lack a _backfill column.
-- These deletes remove ALL rows in the window, including any legitimate live data.
-- Only run if you are certain no real data exists in this range.
DELETE FROM nav_history WHERE date >= '2026-04-22';
DELETE FROM portfolio_metrics WHERE date >= '2026-04-22';
DELETE FROM positions WHERE date >= '2026-04-22';
```

## T1 — Data quality fixes (existing rows)

| Fix | Table | Date | Action |
|-----|-------|------|--------|
| JSON string → JSONB object | daily_snapshots | Apr 8 | regime, segment_biases, market_data cols stored as JSON strings — recast |
| Missing digest_markdown | daily_snapshots | Apr 15 | Generate from snapshot content |
| NULL cash_pct / invested_pct | nav_history | All | Set 0.0 / 100.0 (0% cash, 100% invested) |

## T2 — Portfolio forward-propagation (Apr 22–28)

Prices available in price_history. Weights unchanged from Apr 8/13 positions.

**Base:** Apr 21 close (BIL=91.57, SHY=82.48, SPY=704.08, IAU=88.04, XLP=81.84, EFA=101.63), NAV=100.944717

| Date | BIL | SHY | SPY | IAU | XLP | EFA | NAV | pnl_pct |
|------|-----|-----|-----|-----|-----|-----|-----|---------|
| Apr 22 | 91.57 | 82.52 | 711.21 | 89.19 | 82.11 | 101.97 | 101.353417 | 1.353417 |
| Apr 23 | 91.59 | 82.48 | 708.45 | 88.34 | 83.48 | 101.24 | 101.283837 | 1.283837 |
| Apr 24 | 91.61 | 82.57 | 713.94 | 88.75 | 83.23 | 101.77 | 101.492614 | 1.492614 |
| Apr 25 | — | — | — | — | — | — | SKIP (no prices) | — |
| Apr 27 | 91.62 | 82.55 | 715.17 | 88.07 | 82.34 | 101.38 | 101.274873 | 1.274873 |
| Apr 28 | 91.63 | 82.50 | 711.69 | 86.46 | 83.08 | 100.96 | 100.988468 | 0.988468 |

## T3 — Research snapshot dates

| Date | Day | run_type | baseline_date | Has prices |
|------|-----|----------|--------------|-----------|
| Apr 16 | Wed | delta | 2026-04-12 | Yes |
| Apr 17 | Thu | delta | 2026-04-12 | Yes |
| Apr 18 | Fri | delta | 2026-04-12 | No (carry Apr 17) |
| Apr 19 | Sat | **baseline** | null | No (carry Apr 17) |
| Apr 21 | Mon | delta | 2026-04-19 | Yes |
| Apr 22 | Tue | delta | 2026-04-19 | Yes |
| Apr 23 | Wed | delta | 2026-04-19 | Yes |
| Apr 24 | Thu | delta | 2026-04-19 | Yes |
| Apr 25 | Fri | delta | 2026-04-19 | No (carry Apr 24) |
| Apr 26 | Sat | **baseline** | null | No (carry Apr 24) |
| Apr 28 | Mon | delta | 2026-04-26 | Yes |
| Apr 29 | Tue | delta | 2026-04-26 | No (in-flight at time of writing, 2026-04-29) |

## T4 — DEFERRED (user review required)

- `deliberation_sessions` and `deliberation_rounds` — aspirational table, no implementation
- New `position_events` (any trades Apr 22–29) — user must confirm
- New `theses` entries or XLP exit event — user must review T-003 decision
- Apr 29 portfolio prices — need today's market close
