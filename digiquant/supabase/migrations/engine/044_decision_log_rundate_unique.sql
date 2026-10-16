-- 044_decision_log_rundate_unique.sql — one decision per (run_date, ticker) (#947)
--
-- Migration 026 keyed decision_log idempotency on (run_id, ticker). But a daily
-- run can execute multiple times under DIFFERENT GITHUB_RUN_IDs — CI's outer
-- retry fires a fresh run_id on each attempt — so two same-day attempts each
-- INSERT a row per ticker. The Jun-19 prod run logged 20 rows for 10 tickers
-- from two run_ids, with conflicting convictions (XLK +3/buy vs -1/hold), which
-- would double-count lessons in the learning loop.
--
-- The correct grain is one decision per logical run DATE per ticker: a same-day
-- replay (retry or manual re-run) must UPSERT the same row, latest wins. This
-- migration de-dupes existing rows (keeping the most recent per (run_date,
-- ticker)) and re-keys the unique constraint to (run_date, ticker).

BEGIN;

-- 1. De-dupe: keep the most recent row per (run_date, ticker) by created_at,
--    breaking ties on id so the result is deterministic.
DELETE FROM decision_log a
USING decision_log b
WHERE a.run_date = b.run_date
  AND a.ticker = b.ticker
  AND (a.created_at < b.created_at
       OR (a.created_at = b.created_at AND a.id < b.id));

-- 2. Swap the unique key from (run_id, ticker) to (run_date, ticker).
ALTER TABLE decision_log DROP CONSTRAINT IF EXISTS decision_log_run_ticker_unique;
ALTER TABLE decision_log
  ADD CONSTRAINT decision_log_rundate_ticker_unique UNIQUE (run_date, ticker);

COMMENT ON CONSTRAINT decision_log_rundate_ticker_unique ON decision_log IS
  'One decision per (run_date, ticker). A same-day re-run (CI retry / manual '
  'replay, possibly a new run_id) upserts the same row instead of duplicating; '
  'the resolver''s status=''pending'' guard still protects a resolved reflection. '
  'Replaces the (run_id, ticker) key from migration 026 (see #947).';

-- ── Rollback (commented) ────────────────────────────────────────────────────
-- ALTER TABLE decision_log DROP CONSTRAINT IF EXISTS decision_log_rundate_ticker_unique;
-- ALTER TABLE decision_log ADD CONSTRAINT decision_log_run_ticker_unique UNIQUE (run_id, ticker);

COMMIT;
