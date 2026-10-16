# R2 Checkpoint & Document Archive (v2) — Design Spec

Date: 2026-09-09
Status: draft, pending owner review
Decisions locked: R2 on connected Cloudflare account; phased checkpoints-then-documents,
shared pointer registry; transparent read-through helper; Approach A (stored ledger +
watermark eviction); Supabase keeps latest run per owner; quota-driven retention.

## 1. Problem

The digiquant Supabase database sits at ~588MB against the 500MB free-tier quota
(need: shed ≥88MB). Largest occupants: LangGraph checkpoint tables
(`checkpoint_blobs` ~130MB + `checkpoint_writes` ~71MB ≈ 200MB across 4 threads /
2 runs) and versioned `documents` history (~21MB, desired history). Checkpoint JSONs
are crash-recovery scaffolding with a ~24h useful life (resume window is per-run-id:
`thread_base = resume_run_id or run_id`, `chain.py:907`); nobody reads old threads
except operator forensics via digigraph debug endpoints.

v1 (`digiquant/src/digiquant/ops/checkpoint_archive.py`, daily workflow
`pipeline-checkpoint-archive.yml`) archives threads to R2 with `--retain-days` but
has no pointer registry, no read-through, no quota-driven eviction, and still uses
`CHECKPOINT_ARCHIVE_R2_*` env names.

## 2. Target state

- **Supabase keeps the latest run per owner only** (`(owner, pipeline)` key; single
  default owner today). Each daily run archives its predecessor to R2 *before*
  writing new threads: archive-previous → verify → delete-previous → run-new.
- **R2 holds compressed history** in bucket `digithings-archive` (exists, WEUR,
  Standard). zstd with trained dictionary (~100KB, versioned); read-through
  decompresses transparently. Expected ~5–10MB per daily run (10–20x on repetitive
  same-schema JSON).
- **Retention is quota-driven (Approach A).** Pointer-registry ledger tracks
  compressed bytes per archived run; high watermark 8.5GB → delete oldest-first
  down to low watermark 7GB. Retention becomes emergent (more users → faster
  turnover). Periodic reconciliation (bucket listing vs ledger) corrects drift.
- **Math:** checkpoints 200MB → ~100MB lands DB ≈488MB (thin margin — ordering
  constraint above is load-bearing); +documents pointer-per-row (~21MB+) → ≈465MB,
  comfortable. R2 free tier (10 GB-month/month, verified current) holds years of
  baseline runs before watermarks bite.

## 3. Architecture

- Single bucket `digithings-archive`, prefixes `checkpoints/<thread>/...` and
  `documents/<key>/...` (phased: checkpoints first, documents second).
- New `archive_objects` registry table (migration 119+): `source_table`,
  `source_key` JSONB, `r2_key`, `sha256`, compressed `size`, `archived_at`,
  `status`. This table is BOTH the Supabase↔R2 link (DB rows hold R2 pointers
  only — direct link) and the quota ledger (sum of `size` = usage meter).
- Pointer failure keeps the Supabase row (never NULL-then-lose: write pointer row
  alongside NULL-ing; pointer write failure aborts the delete).
- `resolve_payload()` read-through helper with typed errors (not-found,
  checksum-mismatch, backend-unavailable); consumers: pipeline MCP tools +
  dashboard trace display adapters.
- Credentials: GitHub secrets `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`; endpoint constructed as
  `https://<account>.r2.cloudflarestorage.com` via simple injection. Pipeline yaml
  moves off `CHECKPOINT_ARCHIVE_R2_*` names. Secrets never go into files.

## 4. Data flow

Archive path (per run): list previous-run threads for `(owner, pipeline)` →
compress (zstd-dict) → put to R2 → verify (GET + sha256) → insert pointer rows →
NULL/delete Supabase rows → update ledger total → if total > 8.5GB, evict
oldest-first to 7GB → emit manifest.
Read path: caller requests payload by `(source_table, source_key)` →
`resolve_payload()` looks up pointer → GET from R2 → verify sha256 → decompress →
return bytes. Missing pointer = row still in Supabase (read locally).
Reconciliation (periodic): list bucket prefix, compare against ledger, correct
drift, alert on orphans.

## 5. Error handling

Fail-closed on archive path: any put/verify/pointer failure keeps Supabase rows
and pages the operator (daily workflow fails loudly, never silently drops data).
Read-through degrades to explicit typed errors; dashboard adapters show
"archived — retrieval failed (reason)" rather than empty state. Deletes from R2
(eviction) are oldest-first, never the latest run per owner, and logged with
manifest entries.

## 6. Testing

TDD throughout: FakeStore/FakeClient doubles (v1 precedent in
`tests/dq/ops/test_checkpoint_archive.py`); RED-first tests for ledger
accounting, watermark eviction order (oldest-first, latest-per-owner exempt),
pointer-failure-keeps-row, sha256-mismatch on read, reconciliation drift
correction, zstd-dict round-trip incl. dictionary version mismatch. Live
verification: supervised dry-run then first real archive+delete on prod, with
resume-behavior check on the following run.

## 7. rollout

1. Bucket + secrets — DONE (bucket `digithings-archive`; 4 `R2_*` secrets set).
2. Migration for `archive_objects` + v2 archiver (registry, zstd-dict,
   watermark eviction, `resolve_payload`) + pipeline yaml secret rename — this spec.
3. Checkpoints phase → supervised prod dry-run → live.
4. Documents phase (pointer-per-row) → live.
5. Reconciliation job + RUNBOOK note + module docs for agent discovery.
