-- Per-document research delta pipeline: manifest, per-doc deltas, PM-facing changelog.

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
    'Portfolio Recommendation',
    'Deliberation Transcript',
    'Sector Report',
    'Evolution Sources',
    'Evolution Quality Log',
    'Evolution Proposals'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Includes research_baseline_manifest, document_delta, research_changelog (see templates/schemas/).';
