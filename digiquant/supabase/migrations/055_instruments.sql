-- 055_instruments.sql — canonical metadata for every tracked market instrument (#1615)

CREATE TABLE IF NOT EXISTS instruments (
  ticker            text PRIMARY KEY,
  official_name     text NOT NULL,
  instrument_type   text,
  asset_class       text,
  category          text,
  sector            text,
  industry          text,
  exchange          text,
  currency          text,
  country           text,
  provider          text NOT NULL,
  provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_updated_at timestamptz NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_instruments_ticker CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''),
  CONSTRAINT chk_instruments_official_name CHECK (btrim(official_name) <> ''),
  CONSTRAINT chk_instruments_asset_class CHECK (
    asset_class IS NULL OR asset_class IN (
      'EQUITY', 'INTERNATIONAL', 'FIXED_INCOME', 'COMMODITY',
      'CRYPTO', 'FX', 'CASH', 'UNKNOWN'
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_instruments_category ON instruments(category);
CREATE INDEX IF NOT EXISTS idx_instruments_asset_class ON instruments(asset_class);
CREATE INDEX IF NOT EXISTS idx_instruments_sector ON instruments(sector);

ALTER TABLE instruments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read" ON instruments;
CREATE POLICY "anon_read" ON instruments FOR SELECT TO anon USING (true);

COMMENT ON TABLE instruments IS
  'Canonical provider-sourced identity and classification for every tracked ticker.';
COMMENT ON COLUMN instruments.official_name IS
  'Best available provider name; never derived or expanded by frontend clients.';
COMMENT ON COLUMN instruments.category IS
  'Canonical fine-grained risk category from the Olympus sector map.';
COMMENT ON COLUMN instruments.provider_metadata IS
  'Extensible non-authoritative source payload retained for future metadata fields.';

-- Seed every symbol already tracked by the book or market-data history. Provider
-- refreshes replace these placeholders; the frontend never expands ticker names itself.
INSERT INTO instruments (
  ticker, official_name, instrument_type, asset_class, category,
  provider, provider_metadata, source_updated_at
)
SELECT
  ticker,
  CASE WHEN ticker = 'CASH' THEN 'Cash' ELSE ticker END,
  CASE WHEN ticker = 'CASH' THEN 'CASH' ELSE NULL END,
  CASE WHEN ticker = 'CASH' THEN 'CASH' ELSE 'UNKNOWN' END,
  CASE WHEN ticker = 'CASH' THEN 'cash' ELSE 'unknown' END,
  'migration',
  '{"resolution":"unresolved"}'::jsonb,
  now()
FROM (
  SELECT DISTINCT upper(btrim(ticker)) AS ticker FROM positions
  UNION
  SELECT DISTINCT upper(btrim(ticker)) AS ticker FROM price_history
) tracked
WHERE ticker <> ''
ON CONFLICT (ticker) DO NOTHING;

-- A newly booked position must always have an instrument identity row, even when
-- the external metadata provider is unavailable during that run.
CREATE OR REPLACE FUNCTION ensure_position_instrument()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO instruments (
    ticker, official_name, instrument_type, asset_class, category,
    provider, provider_metadata, source_updated_at
  ) VALUES (
    upper(btrim(NEW.ticker)),
    CASE WHEN upper(btrim(NEW.ticker)) = 'CASH' THEN 'Cash' ELSE upper(btrim(NEW.ticker)) END,
    CASE WHEN upper(btrim(NEW.ticker)) = 'CASH' THEN 'CASH' ELSE NULL END,
    CASE WHEN upper(btrim(NEW.ticker)) = 'CASH' THEN 'CASH' ELSE 'UNKNOWN' END,
    CASE WHEN upper(btrim(NEW.ticker)) = 'CASH' THEN 'cash' ELSE 'unknown' END,
    'position-trigger',
    '{"resolution":"unresolved"}'::jsonb,
    now()
  )
  ON CONFLICT (ticker) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_positions_ensure_instrument ON positions;
CREATE TRIGGER trg_positions_ensure_instrument
BEFORE INSERT OR UPDATE OF ticker ON positions
FOR EACH ROW EXECUTE FUNCTION ensure_position_instrument();

CREATE OR REPLACE FUNCTION set_instruments_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_instruments_updated_at ON instruments;
CREATE TRIGGER trg_instruments_updated_at
BEFORE UPDATE ON instruments
FOR EACH ROW EXECUTE FUNCTION set_instruments_updated_at();
