-- ============================================================================
-- digiquant-atlas: Positions / events / metrics refactor (Migration 012)
--
-- - positions: snapshot-only holdings (drop narrative "action"); add optional
--   performance columns filled after close from price_history + entry data.
-- - position_events: incremental weight change + optional return since event.
-- - portfolio_metrics: mark how/when computed.
-- - nav_history: optional as-of timestamp for the indexed series point.
-- ============================================================================

-- ---- positions: remove action; add performance snapshot fields ----
ALTER TABLE positions DROP COLUMN IF EXISTS action;

ALTER TABLE positions ADD COLUMN IF NOT EXISTS unrealized_pnl_pct numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS day_change_pct numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS since_entry_return_pct numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS contribution_pct numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS metrics_as_of date;

COMMENT ON COLUMN positions.unrealized_pnl_pct IS 'Unrealized % vs entry_price as of metrics_as_of (from price_history close).';
COMMENT ON COLUMN positions.day_change_pct IS 'Previous close → close on metrics_as_of.';
COMMENT ON COLUMN positions.since_entry_return_pct IS 'Return from entry_date close to metrics_as_of close.';
COMMENT ON COLUMN positions.contribution_pct IS 'Approx portfolio contribution: weight_pct * (since_entry_return_pct/100); optional cache.';
COMMENT ON COLUMN positions.metrics_as_of IS 'Date of close used for metrics (usually last trading day).';

-- ---- position_events: granularity for adds/trims ----
ALTER TABLE position_events ADD COLUMN IF NOT EXISTS weight_change_pct numeric;
ALTER TABLE position_events ADD COLUMN IF NOT EXISTS cumulative_return_since_event_pct numeric;

COMMENT ON TABLE position_events IS 'One row per (date,ticker) change vs prior digest: OPEN/EXIT/REBALANCE/HOLD; use weight_change_pct for add/trim size.';
COMMENT ON COLUMN position_events.weight_change_pct IS 'Current weight_pct minus prev_weight_pct.';
COMMENT ON COLUMN position_events.cumulative_return_since_event_pct IS 'Optional: total return from event date close to last refresh (batch script).';

UPDATE position_events
SET weight_change_pct = COALESCE(weight_pct, 0) - COALESCE(prev_weight_pct, 0)
WHERE weight_change_pct IS NULL;

-- ---- portfolio_metrics ----
ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS computed_from text DEFAULT 'tearsheet';
ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS as_of_date date;

COMMENT ON TABLE portfolio_metrics IS 'Portfolio-wide risk/return snapshot for a date; may be augmented by refresh_performance_metrics.py.';
COMMENT ON COLUMN portfolio_metrics.computed_from IS 'tearsheet | refresh_script | mixed';

-- ---- nav_history ----
ALTER TABLE nav_history ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

COMMENT ON TABLE nav_history IS 'Indexed portfolio value (base 100) from simulated path; refresh script can append after close.';
