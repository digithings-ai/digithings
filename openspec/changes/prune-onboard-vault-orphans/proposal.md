# Prune stale docs_onboard vault children

## Intent

Make repeated docs_onboard runs converge when a source document's segment structure changes.
Today the writer upserts current `{slug}__*` notes but leaves former child notes indexed locally
and in Supabase. This change provides a narrowly scoped prune operation for one re-ingested
document and mirrors the result in `architecture_notes`.

## Scope

- Extend digivault's filesystem and HTTP write surfaces with a parent-and-subdirectory-scoped
  child-note prune operation.
- Have `scripts/docs_onboard/write_vault_notes.py` prune stale children after a successful
  parent-document rewrite.
- Extend the service-role Supabase connector with a guarded filtered-delete primitive and use it
  in `scripts/sync_onboard_vault.py` to remove rows absent from the supplied onboard vault.

## Out of scope

- Global vault cleanup, recursive directory deletion, and a delete MCP/orchestrator tool.
- D1 or Vectorize synchronization.
- HTML-to-Markdown conversion (#2191).
- Changes to digikey or live-trading paths.

## Approach

Child-note deletion requires three independent matches: the exact parent-note prefix, matching
`parent_doc` frontmatter, and containment inside the requested vault subdirectory. The HTTP
surface mirrors that operation under the existing write scope. Supabase pruning computes the
authoritative local row set, upserts it, then deletes only stale rows under the supplied vault
prefix. All operations are idempotent.
