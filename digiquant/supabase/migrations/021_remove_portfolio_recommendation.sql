-- Drop Portfolio Recommendation documents and remove the type from the CHECK constraint.

DELETE FROM documents
WHERE doc_type = 'Portfolio Recommendation'
   OR LOWER(document_key) LIKE '%portfolio-recommendation%';

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
    'Evolution Proposals'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Track B thesis pipeline; portfolio_recommendation removed (2026).';
