-- 119_archive_objects.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Pointer registry + quota ledger for the R2 checkpoint/document offload
-- (#3766 / spec 2026-09-09-r2-checkpoint-document-archive-design.md):
-- every payload archived to R2 gets one row here. The `size` column holds
-- COMPRESSED bytes, so `sum(size)` is the quota meter the watermark
-- eviction reads (no live R2 listing on the hot path).
--
-- Pointer discipline: archiver NULLs the source payload only AFTER the R2
-- put-verify AND this registry insert both succeed. A row with
-- status = 'archived' whose source payload is still present means the
-- pointer write failed mid-flight — safe to re-archive, never delete.
create table if not exists archive_objects (
  id bigint generated always as identity primary key,
  source_table text not null,
  source_key jsonb not null,
  r2_key text not null unique,
  sha256 text not null,
  size bigint not null,
  owner text not null default 'house',
  archived_at timestamptz not null default now(),
  status text not null default 'archived'
);
create index if not exists archive_objects_owner_table_idx
  on archive_objects (owner, source_table);
