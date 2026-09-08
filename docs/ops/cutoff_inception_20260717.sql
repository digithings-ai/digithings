-- AUDIT ARTIFACT ONLY — already applied to prod (Supabase `core`) on
-- 2026-09-08 for issue #3695 (inception cutoff at 2026-07-17).
--
-- WHAT IT DID (executed via supabase-py service-role, operator script):
--   1. Backed up 4 nav_history rows (2026-06-23/24/25/26) + 2
--      portfolio_metrics rows (2026-06-24/26) to JSON
--      (operator copy: /tmp/ntproto/cutoff_backup_20260908.json).
--   2. DELETE portfolio_metrics WHERE date < '2026-07-17' (house) → 2 rows.
--      DELETE nav_history WHERE date < '2026-07-17' (house) → 4 rows.
--   3. Rebased the 41 remaining nav_history rows: nav = round(100 * live_nav /
--      99.431364, 6), where 99.431364 was the live (pre-cutoff) 2026-07-17 NAV.
--      Result: 2026-07-17 = 100.0 … 2026-09-04 = 99.921539. Daily returns,
--      pnl_pct, and all metrics are scale-invariant and were NOT touched.
--      positions / position_events rows were kept as a paper trail.
--   4. Verified: 41 nav rows min date 2026-07-17, 32 metrics rows, 0 rows
--      remaining before the cutoff.
--
-- DO NOT re-run: the DELETEs are no-ops now (0 rows match) and the UPDATEs
-- would double-divide. ROLLBACK (if ever needed): re-insert the 6 backup rows
-- and multiply all 41 nav values back by 99.431364/100. No workflow or
-- migration references this file.
begin;
-- 4 nav_history rows deleted (pre-cutoff values shown for the record):
--   2026-06-23 nav=99.546640, 2026-06-24 nav=99.890309,
--   2026-06-25 nav=100.092953, 2026-06-26 nav=99.852949
delete from public.nav_history where workspace_id='6b753576-ced9-5319-9bfa-c5d0aacd9319' and date < '2026-07-17';
-- 2 portfolio_metrics rows deleted (pre-cutoff values shown for the record):
--   2026-06-24 pnl_pct=0.3452, 2026-06-26 pnl_pct=-0.2398
delete from public.portfolio_metrics where workspace_id='6b753576-ced9-5319-9bfa-c5d0aacd9319' and date < '2026-07-17';
-- 41 nav_history rows rebased: nav = round(100 * live_nav / 99.431364, 6)
-- (executed as 41 per-row PATCHes; recorded endpoints: 2026-07-17 100.0,
-- 2026-09-04 99.921539 — per-row values recoverable as 100 * <restatement
-- file NAV> / 99.431364 for dates >= 2026-07-17).
commit;
