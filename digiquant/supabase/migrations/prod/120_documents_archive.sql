-- 120_documents_archive.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Covering index for the R2 documents archive phase (#3766): archive_documents
-- groups rows by (workspace_id, document_key) and keeps the newest date live,
-- so the grouping query needs exactly this composite.
create index if not exists idx_documents_workspace_key_date
  on documents (workspace_id, document_key, date desc);
