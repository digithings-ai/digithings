-- Allow Research Delta rows (Track A / research-delta.json) in documents.doc_type

ALTER TABLE documents DROP CONSTRAINT IF EXISTS chk_documents_doc_type;

ALTER TABLE documents ADD CONSTRAINT chk_documents_doc_type CHECK (
  doc_type IS NULL OR doc_type IN (
    'Daily Digest',
    'Daily Delta',
    'Weekly Rollup',
    'Monthly Summary',
    'Deep Dive',
    'Research Delta'
  )
);

COMMENT ON CONSTRAINT chk_documents_doc_type ON documents IS
  'Includes Research Delta for positioning-blind research payloads (document_key research-delta.json).';
