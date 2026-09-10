-- 122_drop_market_data_tables.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Point of no return for the R2 market-data cutover (#3780, spec §7.4).
-- Requires N retained R2 generations + green parity (Tasks 5–7b).
-- Post-cutover rollback = restore-from-generation + replay.
-- CARVE-OUT (ruling 2026-09-09): macro_series_observations is NOT dropped
-- here — it remains the sole store for fedprob/bitview series, which have
-- no R2 home yet (Task 7b review). R2 homes for those series are future
-- work outside this epic.
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS price_technicals;
