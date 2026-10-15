-- 045_pm_direction_commit_run_doc_types.sql — register #930 thesis-first doc_types (#1005)
--
-- #930 (Olympus daily thesis-first graph) added two `documents` artifacts published
-- in the H9 commit-run node whose doc_type was never registered in
-- chk_documents_doc_type:
--   - "PM Direction Memo"  (commit_io.publish_hermes_documents)
--   - "Commit Run"         (commit_io.save_commit_manifest)
-- The date-serialization crash (#993/#994) masked the violation by crashing before
-- the row reached Postgres; once that was fixed the upsert was rejected with
-- APIError 23514 (violates check constraint "chk_documents_doc_type").
--
-- Extends the migration-043 allow-list — every prior value is preserved, including
-- the legacy "PM Allocation Memo" kept for historical rows.

BEGIN;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS chk_documents_doc_type;

ALTER TABLE documents ADD CONSTRAINT chk_documents_doc_type CHECK (
  doc_type IS NULL OR doc_type IN (
    'Daily Digest',
    'Daily Delta',
    'Weekly Rollup',
    'Monthly Summary',
    'Deep Dive',
    'Research Delta',
    'Research Baseline Manifest',
    'Document Delta',
    'Research Changelog',
    'Rebalance Decision',
    'Asset Recommendation',
    'Deliberation Transcript',
    'Deliberation Session Index',
    'Market Thesis Exploration',
    'Thesis Vehicle Map',
    'PM Allocation Memo',
    'PM Direction Memo',
    'Commit Run',
    'Sector Report',
    'Evolution Sources',
    'Evolution Quality Log',
    'Evolution Proposals',
    'Pipeline Review',
    'Custom Research',
    'Beliefs'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Track A/B output + beliefs (#930) + thesis-first commit-run doc_types: PM Direction Memo, Commit Run (#1005).';

COMMIT;
