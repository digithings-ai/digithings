-- 077_attention_plan_doc_type.sql
--
-- Track C glass-box (#1945): register documents.doc_type "Attention Plan" for
-- WP13-class AttentionPlan shadow artifacts (document_key = attention-plan).
-- Extends migration-045 allow-list; every prior value is preserved.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call.

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
    'Beliefs',
    'Attention Plan'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Track A/B/C output doc_types including Beliefs (#930) and Attention Plan (#1945).';
