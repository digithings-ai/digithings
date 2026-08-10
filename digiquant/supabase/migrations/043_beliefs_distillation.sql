-- 043_beliefs_distillation.sql — beliefs blob on-demand learning loop (#930, spec §11.1)
--
-- Tracks which resolved decision_log rows have been folded into the beliefs
-- document, and extends documents.doc_type for the Beliefs artifact.

BEGIN;

ALTER TABLE decision_log
  ADD COLUMN IF NOT EXISTS beliefs_folded_at timestamptz;

COMMENT ON COLUMN decision_log.beliefs_folded_at IS
  'Set when this resolved row was consumed by beliefs distillation (§11.1).';

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
  'Track A/B output + beliefs on-demand distillation (#930).';

COMMIT;
