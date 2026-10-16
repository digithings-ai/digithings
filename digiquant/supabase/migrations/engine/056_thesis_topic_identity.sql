-- 056_thesis_topic_identity.sql — Stable identity for market research opinions.
--
-- A thesis_id identifies one evolving thesis; topic_key identifies the durable
-- market opinion behind it. H2 must update an active row with the same topic
-- rather than minting another thesis_id for revised wording or evidence.

BEGIN;

ALTER TABLE theses
  ADD COLUMN IF NOT EXISTS topic_key text;

CREATE TEMP TABLE thesis_topic_merge_map (
  duplicate_thesis_id text PRIMARY KEY,
  canonical_thesis_id text NOT NULL,
  topic_key text NOT NULL
) ON COMMIT DROP;

INSERT INTO thesis_topic_merge_map (
  duplicate_thesis_id,
  canonical_thesis_id,
  topic_key
)
VALUES
  ('cta-equity-volatility', 'cta-risk-management', 'cta-equity-positioning-risk'),
  ('cta-risk-management', 'cta-risk-management', 'cta-equity-positioning-risk'),
  ('advanced-mat-demand-2026', 'advanced-materials-growth-trend', 'advanced-materials-growth'),
  ('advanced-mat-growth-2026', 'advanced-materials-growth-trend', 'advanced-materials-growth'),
  ('advanced-mat-inflation', 'advanced-materials-growth-trend', 'advanced-materials-growth'),
  ('advanced-mat-inflation-2026', 'advanced-materials-growth-trend', 'advanced-materials-growth'),
  ('advanced-materials-demand-shift', 'advanced-materials-growth-trend', 'advanced-materials-growth'),
  ('advanced-materials-growth-trend', 'advanced-materials-growth-trend', 'advanced-materials-growth');

-- Ensure each affected date has its canonical thesis before child rows move.
-- Prefer an existing canonical row; otherwise preserve the highest-confidence
-- member of the cluster as that date's canonical snapshot.
WITH ranked AS (
  SELECT
    t.*,
    mapping.canonical_thesis_id,
    mapping.topic_key AS canonical_topic_key,
    row_number() OVER (
      PARTITION BY t.date, mapping.canonical_thesis_id
      ORDER BY
        (t.thesis_id = mapping.canonical_thesis_id) DESC,
        t.confidence DESC NULLS LAST,
        t.thesis_id
    ) AS preference_rank
  FROM theses AS t
  JOIN thesis_topic_merge_map AS mapping
    ON mapping.duplicate_thesis_id = t.thesis_id
)
INSERT INTO theses (
  date,
  thesis_id,
  topic_key,
  name,
  vehicle,
  invalidation,
  status,
  notes,
  confidence,
  validation_criteria,
  invalidation_criteria,
  horizon,
  thesis_kind,
  linked_market_thesis_id
)
SELECT
  date,
  canonical_thesis_id,
  canonical_topic_key,
  name,
  vehicle,
  invalidation,
  status,
  notes,
  confidence,
  validation_criteria,
  invalidation_criteria,
  horizon,
  'market',
  linked_market_thesis_id
FROM ranked
WHERE preference_rank = 1
ON CONFLICT (date, thesis_id) DO UPDATE
SET topic_key = EXCLUDED.topic_key,
    thesis_kind = 'market';

-- Merge every ticker mapping into the canonical thesis before deleting the old
-- FK parent. Existing canonical mappings win descriptive ties; rank keeps the
-- strongest available ordering.
INSERT INTO thesis_vehicles AS canonical (
  date,
  thesis_id,
  ticker,
  rationale,
  exclusion_reasons,
  candidate_rank,
  user_mandate_notes,
  source_exploration_key,
  created_at
)
-- DISTINCT ON: when several duplicate theses collapse into one canonical id,
-- their vehicle rows can propose the same (date, canonical, ticker) key twice
-- in this single statement, which ON CONFLICT rejects ("cannot affect row a
-- second time"). Keep one deterministic winner per key — strongest rank, then
-- earliest row — before the upsert merges it against any existing canonical.
SELECT DISTINCT ON (vehicles.date, mapping.canonical_thesis_id, vehicles.ticker)
  vehicles.date,
  mapping.canonical_thesis_id,
  vehicles.ticker,
  vehicles.rationale,
  vehicles.exclusion_reasons,
  vehicles.candidate_rank,
  vehicles.user_mandate_notes,
  vehicles.source_exploration_key,
  vehicles.created_at
FROM thesis_vehicles AS vehicles
JOIN thesis_topic_merge_map AS mapping
  ON mapping.duplicate_thesis_id = vehicles.thesis_id
WHERE mapping.duplicate_thesis_id <> mapping.canonical_thesis_id
ORDER BY vehicles.date,
         mapping.canonical_thesis_id,
         vehicles.ticker,
         vehicles.candidate_rank ASC NULLS LAST,
         vehicles.created_at ASC
ON CONFLICT (date, thesis_id, ticker) DO UPDATE
SET rationale = COALESCE(canonical.rationale, EXCLUDED.rationale),
    exclusion_reasons = COALESCE(canonical.exclusion_reasons, EXCLUDED.exclusion_reasons),
    candidate_rank = COALESCE(
      LEAST(canonical.candidate_rank, EXCLUDED.candidate_rank),
      canonical.candidate_rank,
      EXCLUDED.candidate_rank
    ),
    user_mandate_notes = COALESCE(
      canonical.user_mandate_notes,
      EXCLUDED.user_mandate_notes
    ),
    source_exploration_key = COALESCE(
      canonical.source_exploration_key,
      EXCLUDED.source_exploration_key
    );

DELETE FROM thesis_vehicles AS vehicles
USING thesis_topic_merge_map AS mapping
WHERE vehicles.thesis_id = mapping.duplicate_thesis_id
  AND mapping.duplicate_thesis_id <> mapping.canonical_thesis_id;

UPDATE theses
SET linked_market_thesis_id = mapping.canonical_thesis_id
FROM thesis_topic_merge_map AS mapping
WHERE theses.linked_market_thesis_id = mapping.duplicate_thesis_id
  AND mapping.duplicate_thesis_id <> mapping.canonical_thesis_id;

UPDATE positions
SET thesis_id = mapping.canonical_thesis_id
FROM thesis_topic_merge_map AS mapping
WHERE positions.thesis_id = mapping.duplicate_thesis_id
  AND mapping.duplicate_thesis_id <> mapping.canonical_thesis_id;

UPDATE position_events
SET thesis_id = mapping.canonical_thesis_id
FROM thesis_topic_merge_map AS mapping
WHERE position_events.thesis_id = mapping.duplicate_thesis_id
  AND mapping.duplicate_thesis_id <> mapping.canonical_thesis_id;

UPDATE analyst_coverage AS coverage
SET thesis_ids = (
  SELECT jsonb_agg(DISTINCT COALESCE(mapping.canonical_thesis_id, item.thesis_id))
  FROM jsonb_array_elements_text(coverage.thesis_ids) AS item(thesis_id)
  LEFT JOIN thesis_topic_merge_map AS mapping
    ON mapping.duplicate_thesis_id = item.thesis_id
)
WHERE jsonb_typeof(coverage.thesis_ids) = 'array'
  AND EXISTS (
    SELECT 1
    FROM jsonb_array_elements_text(coverage.thesis_ids) AS item(thesis_id)
    JOIN thesis_topic_merge_map AS mapping
      ON mapping.duplicate_thesis_id = item.thesis_id
    WHERE mapping.duplicate_thesis_id <> mapping.canonical_thesis_id
  );

DELETE FROM theses
USING thesis_topic_merge_map AS mapping
WHERE theses.thesis_id = mapping.duplicate_thesis_id
  AND mapping.duplicate_thesis_id <> mapping.canonical_thesis_id;

-- Existing unrelated market views become their own initial topics. H2 may
-- preserve that key on updates; deliberate future consolidation uses another
-- reviewed mapping rather than fuzzy matching in application code.
UPDATE theses
SET topic_key = COALESCE(
  NULLIF(
    trim(BOTH '-' FROM regexp_replace(lower(thesis_id), '[^a-z0-9]+', '-', 'g')),
    ''
  ),
  'legacy-' || substr(md5(thesis_id), 1, 16)
)
WHERE thesis_kind = 'market'
  AND topic_key IS NULL;

-- Residual duplicates: rows the enumerated clusters did not foresee can still
-- collide AFTER the backfill above (two live theses whose ids slugify to one
-- topic — e.g. (2026-07-04, advanced-materials-growth) in prod, which blocked
-- the unique index on 2026-07-23). Collapse them the same way, computed
-- instead of enumerated, per colliding date: strongest row wins, its vehicle
-- mappings move, the loser's row for that date deletes. The loser thesis_id
-- may remain canonical on other dates; vehicle→market links self-heal in H5
-- each run, so no cross-date link rewrite is attempted here.
CREATE TEMP TABLE thesis_topic_residual_map ON COMMIT DROP AS
WITH ranked AS (
  SELECT
    date,
    thesis_id,
    topic_key,
    row_number() OVER (
      PARTITION BY date, topic_key
      ORDER BY confidence DESC NULLS LAST, thesis_id
    ) AS preference_rank,
    first_value(thesis_id) OVER (
      PARTITION BY date, topic_key
      ORDER BY confidence DESC NULLS LAST, thesis_id
    ) AS canonical_thesis_id
  FROM theses
  WHERE thesis_kind = 'market'
    AND topic_key IS NOT NULL
    AND (status IS NULL OR status NOT IN ('CLOSED', 'INVALIDATED'))
)
SELECT
  date,
  thesis_id AS duplicate_thesis_id,
  canonical_thesis_id
FROM ranked
WHERE preference_rank > 1;

INSERT INTO thesis_vehicles AS canonical (
  date,
  thesis_id,
  ticker,
  rationale,
  exclusion_reasons,
  candidate_rank,
  user_mandate_notes,
  source_exploration_key,
  created_at
)
SELECT DISTINCT ON (vehicles.date, residual.canonical_thesis_id, vehicles.ticker)
  vehicles.date,
  residual.canonical_thesis_id,
  vehicles.ticker,
  vehicles.rationale,
  vehicles.exclusion_reasons,
  vehicles.candidate_rank,
  vehicles.user_mandate_notes,
  vehicles.source_exploration_key,
  vehicles.created_at
FROM thesis_vehicles AS vehicles
JOIN thesis_topic_residual_map AS residual
  ON residual.duplicate_thesis_id = vehicles.thesis_id
 AND residual.date = vehicles.date
ORDER BY vehicles.date,
         residual.canonical_thesis_id,
         vehicles.ticker,
         vehicles.candidate_rank ASC NULLS LAST,
         vehicles.created_at ASC
ON CONFLICT (date, thesis_id, ticker) DO UPDATE
SET rationale = COALESCE(canonical.rationale, EXCLUDED.rationale),
    exclusion_reasons = COALESCE(canonical.exclusion_reasons, EXCLUDED.exclusion_reasons),
    candidate_rank = COALESCE(
      LEAST(canonical.candidate_rank, EXCLUDED.candidate_rank),
      canonical.candidate_rank,
      EXCLUDED.candidate_rank
    ),
    user_mandate_notes = COALESCE(
      canonical.user_mandate_notes,
      EXCLUDED.user_mandate_notes
    ),
    source_exploration_key = COALESCE(
      canonical.source_exploration_key,
      EXCLUDED.source_exploration_key
    );

DELETE FROM thesis_vehicles AS vehicles
USING thesis_topic_residual_map AS residual
WHERE vehicles.thesis_id = residual.duplicate_thesis_id
  AND vehicles.date = residual.date;

DELETE FROM theses
USING thesis_topic_residual_map AS residual
WHERE theses.thesis_id = residual.duplicate_thesis_id
  AND theses.date = residual.date;

DO $$ BEGIN
  ALTER TABLE theses ADD CONSTRAINT chk_theses_topic_key
    CHECK (
      topic_key IS NULL
      OR (
        char_length(topic_key) BETWEEN 1 AND 64
        AND topic_key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
      )
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_theses_topic_key_date
  ON theses (topic_key, date DESC)
  WHERE topic_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_theses_active_market_topic_date
  ON theses (date, topic_key)
  WHERE thesis_kind = 'market'
    AND topic_key IS NOT NULL
    AND (status IS NULL OR status NOT IN ('CLOSED', 'INVALIDATED'));

COMMENT ON COLUMN theses.topic_key IS
  'Stable lowercase identity for one durable market opinion. H2 updates the '
  'existing active thesis_id for this topic instead of creating a duplicate.';

COMMIT;

-- ─── Rollback (commented) ───────────────────────────────────────────────────
-- Duplicate-row consolidation is intentionally not reversible.
-- BEGIN;
-- DROP INDEX IF EXISTS uq_theses_active_market_topic_date;
-- DROP INDEX IF EXISTS idx_theses_topic_key_date;
-- ALTER TABLE theses DROP CONSTRAINT IF EXISTS chk_theses_topic_key;
-- ALTER TABLE theses DROP COLUMN IF EXISTS topic_key;
-- COMMIT;
