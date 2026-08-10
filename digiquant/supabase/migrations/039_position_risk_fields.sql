-- 039_position_risk_fields.sql — Per-position advisory risk fields (Pillar 2E, #726).
--
-- Adds display-only risk metadata to `positions`. These are ADVISORY — a stop / target /
-- horizon the dashboard can surface; they are NOT orders and nothing executes against them
-- (Olympus is paper-only). All nullable + idempotent so historical rows and the
-- feature-flagged writer (OLYMPUS_POSITION_RISK_FIELDS) stay backward-compatible: the
-- column add is inert until the flag is flipped on, and old rows simply read NULL.
--
-- entry_price / entry_date already exist (migrations 001/012); the writer begins populating
-- them under the same flag.

ALTER TABLE positions ADD COLUMN IF NOT EXISTS stop_loss_pct   numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS target_pct_gain numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS horizon_days    integer;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS conviction      numeric;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sector_bucket   text;

COMMENT ON COLUMN positions.stop_loss_pct IS
  'Advisory stop: % move below entry that would trip it (negative). ATR-derived. NOT an order.';
COMMENT ON COLUMN positions.target_pct_gain IS
  'Advisory target: % gain above entry. ATR-derived. NOT an order.';
COMMENT ON COLUMN positions.horizon_days IS
  'Advisory holding horizon in days.';
COMMENT ON COLUMN positions.conviction IS
  'Effective conviction at booking (analyst score + debate delta, -5..+5).';
COMMENT ON COLUMN positions.sector_bucket IS
  'Asset-class / sector bucket (sector_map.sector_bucket) for concentration roll-ups.';
