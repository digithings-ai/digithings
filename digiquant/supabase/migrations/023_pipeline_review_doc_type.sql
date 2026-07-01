-- Allow pipeline_review post-mortem documents (GitHub backlog sync).

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
    'Pipeline Review'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Track B thesis pipeline + pipeline_review post-mortem (2026).';
