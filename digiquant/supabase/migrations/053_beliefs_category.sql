-- 053_beliefs_category.sql — register the "learning" documents.category (#1383)
--
-- Migration 043 (beliefs on-demand distillation, #930) added the "Beliefs"
-- doc_type to chk_documents_doc_type but never registered the matching
-- documents.category. The beliefs writer publishes with category="learning"
-- (learning/beliefs_distillation.py — publish_document(..., category="learning")),
-- a value absent from chk_documents_category, so every beliefs fold was rejected
-- with APIError 23514 (violates check constraint "chk_documents_category") and
-- crashed the Olympus daily pipeline (red 2026-07-04 → 2026-07-14, 11 runs).
--
-- Same class of incident as #628 (category="research") and #1005 (doc_type). This
-- extends the migration-011 allow-list — every prior value is preserved.

BEGIN;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS chk_documents_category;

ALTER TABLE documents ADD CONSTRAINT chk_documents_category CHECK (
  category IS NULL OR category IN (
    'synthesis',
    'macro',
    'asset-class',
    'equity',
    'sector',
    'alt-data',
    'institutional',
    'portfolio',
    'delta',
    'output',
    'rollup',
    'deep-dive',
    'learning'
  )
);

COMMENT ON CONSTRAINT chk_documents_category ON documents IS
  'Research segment + structural categories + "learning" for beliefs distillation (#1383).';

COMMIT;
