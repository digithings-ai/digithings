-- Replace legacy REBALANCE with TRIM / ADD (directional sizing changes).
-- Historical rows: infer from weight_change_pct, else prev vs current weight.

ALTER TABLE position_events DROP CONSTRAINT IF EXISTS position_events_event_check;

UPDATE position_events
SET event = CASE
  WHEN COALESCE(weight_change_pct, 0) < 0 THEN 'TRIM'
  WHEN COALESCE(weight_change_pct, 0) > 0 THEN 'ADD'
  WHEN prev_weight_pct IS NOT NULL
    AND weight_pct IS NOT NULL
    AND weight_pct::numeric < prev_weight_pct::numeric
    THEN 'TRIM'
  WHEN prev_weight_pct IS NOT NULL
    AND weight_pct IS NOT NULL
    AND weight_pct::numeric > prev_weight_pct::numeric
    THEN 'ADD'
  ELSE 'TRIM'
END
WHERE event = 'REBALANCE';

ALTER TABLE position_events ADD CONSTRAINT position_events_event_check
  CHECK (event IN ('OPEN', 'EXIT', 'HOLD', 'TRIM', 'ADD'));

COMMENT ON TABLE position_events IS 'One row per (date,ticker) execution: OPEN/EXIT/TRIM/ADD/HOLD; use weight_change_pct for add/trim size.';
