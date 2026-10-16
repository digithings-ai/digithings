-- 029_daily_snapshots_legacy_nullable.sql — make the deprecated flat
-- daily_snapshots columns (regime, market_data) NULLABLE.
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor)
--
-- Why:
-- The Atlas publish adapter (olympus/atlas/supabase_io.publish_daily_snapshot)
-- writes the full digest into the `snapshot` JSONB column and intentionally
-- leaves the original flat columns unset — see its docstring: "the legacy
-- column set (bias fields, etc.) is populated by downstream readers or a
-- follow-up schema migration — not this adapter." THIS is that follow-up
-- migration, which was never written.
--
-- `regime` and `market_data` were declared NOT NULL (migrations 001 / 011), so
-- after the adapter moved to the `snapshot` JSONB, every daily_snapshots upsert
-- failed with PostgREST 23502 — blocking all baseline/delta publishes. (The
-- Gemini rate-limit failures masked it by aborting runs before publish; the
-- xAI cutover (#627) surfaced it via a full local end-to-end run.)
--
-- Reader-safe: all consumers read the `snapshot` JSONB (snapshot.regime,
-- snapshot.market_data, snapshot.portfolio, …), not these flat top-level
-- columns. Making them nullable unblocks publish without touching any reader.
--
-- Refs #524 (schema anomaly cleanup), #628 / #627 (publish failures).

ALTER TABLE daily_snapshots ALTER COLUMN regime DROP NOT NULL;
ALTER TABLE daily_snapshots ALTER COLUMN market_data DROP NOT NULL;
