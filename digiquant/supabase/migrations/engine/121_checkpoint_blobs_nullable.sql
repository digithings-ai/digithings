-- 121_checkpoint_blobs_nullable.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Relax the LangGraph-owned payload columns for the R2 checkpoint archive
-- phase (#3766): archive_thread NULLs each payload cell after its bytes are
-- verified in R2 and the archive_objects pointer row exists. The vendor DDL
-- declares both blob columns NOT NULL, so the NULL step dies with 23502 on
-- the first row. Dropping the constraint keeps the NULL design and the
-- UPDATE-based restore path; LangGraph setup uses CREATE TABLE IF NOT
-- EXISTS, so the constraint cannot come back on reconnect.
alter table checkpoint_blobs alter column blob drop not null;
alter table checkpoint_writes alter column blob drop not null;
