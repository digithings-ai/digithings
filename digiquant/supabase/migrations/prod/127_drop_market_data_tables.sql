-- 127_drop_market_data_tables.sql
-- Requires: every market-data reader on R2/live sources (#4053 Tasks 1-4);
-- NEXT_PUBLIC_MARKET_DATA_URL live in prod (D5); and the stack Worker
-- redeployed with DIGIQUANT_MARKET_DATA_BACKEND="r2" in [vars] (83640e28c),
-- so the hosted digiquant-mcp container stops forwarding "" —
-- apps/digithings-stack-cloudflare/wrangler.toml. Rollback =
-- restore-from-generation + replay (no flag rollback; tables are gone).
-- macro_series_observations is NOT dropped (FEDPROB/* has no R2 home).
-- trading_calendar is NOT dropped (calendar sync still writes it).
DROP VIEW IF EXISTS public.price_history_tickers;
DROP VIEW IF EXISTS public.public_price_latest;
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS price_technicals;
