-- 015_macro_series_observations.sql — Multi-source macro / FX / sentiment time series.
-- Populated by scripts/ingest_fred.py, ingest_fx_frankfurter.py, ingest_crypto_fng.py.

CREATE TABLE IF NOT EXISTS macro_series_observations (
  source      text        NOT NULL,
  series_id   text        NOT NULL,
  obs_date    date        NOT NULL,
  value       numeric,
  unit        text,
  meta        jsonb,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, series_id, obs_date)
);

CREATE INDEX IF NOT EXISTS idx_macro_series_obs_source_date
  ON macro_series_observations (source, obs_date DESC);

CREATE INDEX IF NOT EXISTS idx_macro_series_obs_series_date
  ON macro_series_observations (series_id, obs_date DESC);

ALTER TABLE macro_series_observations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "macro_series_observations_anon_select" ON macro_series_observations;
CREATE POLICY "macro_series_observations_anon_select"
  ON macro_series_observations FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE macro_series_observations IS
  'Daily (or slower-frequency) observations from FRED, Frankfurter FX, crypto Fear & Greed, etc. '
  'Ingest scripts upsert via service_role; anon may SELECT for MCP / agents.';

COMMENT ON COLUMN macro_series_observations.source IS
  'Provider namespace: fred, frankfurter, crypto_fear_greed, …';

COMMENT ON COLUMN macro_series_observations.series_id IS
  'Stable id within source, e.g. DGS10, FX/EUR, FNG/value.';
