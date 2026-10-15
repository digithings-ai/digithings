-- 078_attention_plan_category.sql
--
-- Track C glass-box (#2622 / #1945): register documents.category "planner" for
-- AttentionPlan shadow upserts (document_key = attention-plan). Same class of
-- incident as #628 / #1383 — doc_type alone is not enough; category must be on
-- chk_documents_category or every publish fails with 23514.
--
-- Extends migration-053 allow-list; every prior value is preserved.
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call.

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
    'learning',
    'planner'
  )
);

COMMENT ON CONSTRAINT chk_documents_category ON documents IS
  'Research segment + structural categories + learning (#1383) + planner (#2622).';
