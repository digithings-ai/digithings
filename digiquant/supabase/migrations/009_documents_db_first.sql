-- ============================================================================
-- digiquant-atlas: Documents DB-first (Migration 009)
-- - Logical document keys (not repo paths) in column renamed from file_path.
-- - Optional JSON payload (digest snapshot) for structured Library rendering.
-- - Normalizes legacy rows whose document_key stored old filesystem path prefixes.
--   (UPDATE patterns below match historical DB values only — not an active repo path.)
-- ============================================================================

ALTER TABLE documents ADD COLUMN IF NOT EXISTS payload jsonb;

COMMENT ON COLUMN documents.payload IS 'Structured snapshot JSON for digest rows (mirrors daily_snapshots.snapshot); optional for markdown-only segments.';

-- Normalize legacy filesystem-style paths to logical keys (before rename).
UPDATE documents
SET file_path = regexp_replace(file_path, '^.*outputs/daily/[0-9]{4}-[0-9]{2}-[0-9]{2}/', '')
WHERE file_path ~ '^.*outputs/daily/[0-9]{4}-[0-9]{2}-[0-9]{2}/';

UPDATE documents
SET file_path = regexp_replace(file_path, '^.*outputs/weekly/', 'weekly/')
WHERE file_path LIKE '%outputs/weekly/%';

UPDATE documents
SET file_path = regexp_replace(file_path, '^.*outputs/monthly/', 'monthly/')
WHERE file_path LIKE '%outputs/monthly/%';

UPDATE documents
SET file_path = regexp_replace(file_path, '^.*outputs/deep-dives/', 'deep-dives/')
WHERE file_path LIKE '%outputs/deep-dives/%';

UPDATE documents SET file_path = 'digest' WHERE file_path IN ('DIGEST.md', 'digest');
UPDATE documents SET file_path = 'digest-delta' WHERE file_path IN ('DIGEST-DELTA.md', 'digest-delta');

-- Dedupe: one row per (run date, logical key); keep richest content.
DELETE FROM documents d
WHERE d.id IN (
  SELECT id FROM (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY date, file_path
             ORDER BY length(COALESCE(content, '')) DESC NULLS LAST, id::text
           ) AS rn
    FROM documents
  ) sub
  WHERE rn > 1
);

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_date_file_path_key;

ALTER TABLE documents RENAME COLUMN file_path TO document_key;

ALTER TABLE documents ADD CONSTRAINT documents_date_document_key_key UNIQUE (date, document_key);

COMMENT ON COLUMN documents.document_key IS
  'Stable key for this document within its run date (e.g. digest, digest-delta, sectors/energy, deltas/macro). Not a filesystem path.';

-- Backfill digest rows from canonical daily snapshot + rendered markdown.
UPDATE documents d
SET
  payload = ds.snapshot,
  content = COALESCE(NULLIF(BTRIM(COALESCE(d.content, '')), ''), ds.digest_markdown)
FROM daily_snapshots ds
WHERE d.date = ds.date
  AND d.document_key = 'digest'
  AND ds.snapshot IS NOT NULL;
