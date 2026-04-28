-- 027_custom_research_doc_type.sql — extend documents.doc_type CHECK constraint
-- to allow 'Custom Research' for user-triggered one-off runs (#313).
--
-- Run with:  supabase db push  (from apps/digiquant-atlas/supabase/)
--
-- Custom Research rows live alongside the standard Daily Digest / Daily Delta
-- output but with document_key = 'custom-research/<run_id>' so they don't
-- collide with the day's canonical digest row. They are never written to
-- ``daily_snapshots`` — that table is reserved for the regular cadence.

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
    'Custom Research'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Track A/B output + #313 user-triggered Custom Research doc type.';
