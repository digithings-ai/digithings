-- Persist explicit cumulative portfolio and benchmark return semantics (#1615).
-- The observation window spans the first through latest stored NAV record; the
-- benchmark uses closes available inside that same date range.

ALTER TABLE public.portfolio_metrics
    ADD COLUMN IF NOT EXISTS net_return_pct numeric,
    ADD COLUMN IF NOT EXISTS benchmark_return_pct numeric,
    ADD COLUMN IF NOT EXISTS relative_return_pct numeric,
    ADD COLUMN IF NOT EXISTS benchmark_ticker text NOT NULL DEFAULT 'SPY';

COMMENT ON COLUMN public.portfolio_metrics.net_return_pct IS
    'Cumulative simple return from first to latest stored NAV observation, in percent.';
COMMENT ON COLUMN public.portfolio_metrics.benchmark_return_pct IS
    'Cumulative simple return from first to latest benchmark close in the NAV date range, in percent.';
COMMENT ON COLUMN public.portfolio_metrics.relative_return_pct IS
    'Arithmetic excess return: net_return_pct minus benchmark_return_pct, in percentage points.';
COMMENT ON COLUMN public.portfolio_metrics.benchmark_ticker IS
    'Ticker used for benchmark_return_pct and relative_return_pct.';

CREATE INDEX IF NOT EXISTS position_attribution_ticker_date_idx
    ON public.position_attribution (ticker, date DESC);