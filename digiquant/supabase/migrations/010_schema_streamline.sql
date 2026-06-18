-- ============================================================================
-- digiquant-atlas: Schema streamline (Migration 010)
--
-- 1) Drop migration-004 backup tables — duplicate copies of daily_snapshots /
--    documents from before RANGE partitioning. Active data lives in the
--    partitioned parents; these are safe to remove for a cleaner database.
--
-- 2) Drop benchmark_history — OHLCV for benchmarks (SPY, QQQ, TLT, GLD) is
--    stored in price_history.close; duplicate upserts from update_tearsheet are
--    redundant. Dashboard reads benchmarks from price_history.
--
-- Note: daily_snapshots / documents remain RANGE-partitioned by year (004).
-- Collapsing to a single unpartitioned table is optional future work if row
-- counts stay small.
-- ============================================================================

DROP TABLE IF EXISTS daily_snapshots_legacy CASCADE;
DROP TABLE IF EXISTS documents_legacy CASCADE;

DROP TABLE IF EXISTS benchmark_history CASCADE;
