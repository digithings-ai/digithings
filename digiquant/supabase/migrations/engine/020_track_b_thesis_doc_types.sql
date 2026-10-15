-- Track B thesis-first pipeline: new document payload types (human labels for documents.doc_type CHECK).

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
  'Includes Track B thesis pipeline: market_thesis_exploration, thesis_vehicle_map, pm_allocation_memo, deliberation_session_index.';
