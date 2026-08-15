-- 051_lock_strategy_store.sql — Revoke public reads on the live strategy store (#1462).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- User ruling 2026-07-10 (issue #1462, follow-up to the 3-day signal delay): live
-- Slapper state must not be publicly queryable. The audit behind the ruling found
-- three strategy-store tables anon-readable with unrestricted (`qual: true`) SELECT
-- policies, which would have bypassed the signal delay entirely:
--   * strategy_signals — current position, last_signal_date, last_price (the signal)
--   * strategy_trades  — the live executed trade log (entries/exits/prices/pnl)
--   * strategies       — per-strategy config jsonb (parameters)
-- No frontend references any of the three (verified repo-wide 2026-07-10); the only
-- writer/reader is the tearsheet pipeline on the service role, which bypasses RLS
-- and is unaffected. Public strategy data flows exclusively through the 3-day-delayed
-- static JSON and strategy_tearsheets (whose pipeline now writes the delayed view,
-- PR #1479) — strategy_tearsheets deliberately KEEPS its anon policy.
--
-- Belt and braces: the policy drop removes RLS permission and the REVOKE removes the
-- PostgREST table grant, so neither anon nor authenticated can read these tables even
-- if a future migration re-grants schema-wide privileges.
--
-- Idempotent (DROP POLICY IF EXISTS + re-runnable REVOKE).

DROP POLICY IF EXISTS strategies_anon_select ON public.strategies;
DROP POLICY IF EXISTS strategy_signals_anon_select ON public.strategy_signals;
DROP POLICY IF EXISTS strategy_trades_anon_select ON public.strategy_trades;

REVOKE ALL ON public.strategies      FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.strategy_signals FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.strategy_trades  FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.strategy_signals IS
  'Live Slapper signal state. Private by user ruling 2026-07-10 (issue #1462): public '
  'consumers get the 3-day-delayed tearsheet payloads instead (signal_delay_days, '
  'PR #1479). Service-role pipeline access only.';

COMMENT ON TABLE public.strategy_trades IS
  'Live Slapper trade log. Private by user ruling 2026-07-10 (issue #1462): the public '
  'trade log ships inside the 3-day-delayed tearsheet JSON. Service-role pipeline '
  'access only.';
