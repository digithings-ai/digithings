-- 030_drop_duplicate_indexes_positions_events.sql
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor)
--
-- Performance advisor WARN (duplicate_index): `positions` and `position_events`
-- each carried two identical btree(ticker, date DESC) indexes:
--   positions:       idx_positions_ticker  ≡  idx_positions_ticker_date
--   position_events: idx_events_ticker     ≡  idx_events_ticker_date
-- Drop the redundant one in each (keep the *_date-named one). Idempotent.
--
-- Already applied to prod 2026-06-08 via MCP; this file captures it so a clean
-- `supabase db push` reproduces the schema. Refs #524.

DROP INDEX IF EXISTS public.idx_positions_ticker;
DROP INDEX IF EXISTS public.idx_events_ticker;
