-- 025_thesis_daily_fields.sql — Spec §7.1 daily thesis columns on `theses`.
--
-- Adds confidence, validation/invalidation criteria, horizon, thesis_kind, and
-- optional linked_market_thesis_id for the thesis-first Hermes graph (H1–H9).
-- Criteria are stored on the row and mirrored in documents payloads for edit-mode.

BEGIN;

ALTER TABLE theses
  ADD COLUMN IF NOT EXISTS confidence numeric,
  ADD COLUMN IF NOT EXISTS validation_criteria jsonb,
  ADD COLUMN IF NOT EXISTS invalidation_criteria jsonb,
  ADD COLUMN IF NOT EXISTS horizon text,
  ADD COLUMN IF NOT EXISTS thesis_kind text,
  ADD COLUMN IF NOT EXISTS linked_market_thesis_id text;

DO $$ BEGIN
  ALTER TABLE theses ADD CONSTRAINT chk_theses_confidence
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE theses ADD CONSTRAINT chk_theses_kind
    CHECK (thesis_kind IS NULL OR thesis_kind IN ('market', 'vehicle'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN theses.confidence IS
  'Canonical thesis confidence in [0.0, 1.0]; refreshed on daily H1 pass.';
COMMENT ON COLUMN theses.validation_criteria IS
  'JSON array of observable conditions that keep the thesis alive.';
COMMENT ON COLUMN theses.invalidation_criteria IS
  'JSON array of observable conditions that nullify the thesis.';
COMMENT ON COLUMN theses.thesis_kind IS
  'market (H2 macro exploration) or vehicle (H5 bottom-up analyst thesis).';
COMMENT ON COLUMN theses.linked_market_thesis_id IS
  'Optional parent market thesis when thesis_kind=vehicle.';

COMMIT;

-- ─── Rollback (commented) ───────────────────────────────────────────────────
-- BEGIN;
-- ALTER TABLE theses DROP CONSTRAINT IF EXISTS chk_theses_kind;
-- ALTER TABLE theses DROP CONSTRAINT IF EXISTS chk_theses_confidence;
-- ALTER TABLE theses
--   DROP COLUMN IF EXISTS linked_market_thesis_id,
--   DROP COLUMN IF EXISTS thesis_kind,
--   DROP COLUMN IF EXISTS horizon,
--   DROP COLUMN IF EXISTS invalidation_criteria,
--   DROP COLUMN IF EXISTS validation_criteria,
--   DROP COLUMN IF EXISTS confidence;
-- COMMIT;
