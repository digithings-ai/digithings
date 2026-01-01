# Design: scoped orphan pruning

## Local and HTTP flow

For each classified source document, `write_vault_notes` produces an authoritative child-name
set. It writes the current children and parent hub first, then calls
`prune_children(parent_doc, keep_names, subdir)`. `Vault.prune_children` validates its arguments
and considers a file removable only when its stem starts with `parent_doc + "__"`, its indexed
relative path is inside `subdir`, and its frontmatter's `parent_doc` equals `parent_doc`. It
unlinks those candidates and rebuilds the index once.

The HTTP writer calls `POST /v1/notes/prune-children` with the same exact arguments. The endpoint
is covered by the existing `digivault:write` route policy and uses strict Pydantic request and
response models. It is deliberately unavailable through MCP and orchestrator dispatch.

## Supabase flow

`sync_onboard_vault.py` builds all current rows from the explicit `--vault` path. On apply, it
performs the existing upsert first. Only after that succeeds, it reads existing `vault_path`
values under the local vault's normalized relative prefix and derives stale paths by set
difference. It deletes those exact paths via `SupabaseConnector.delete`, which requires at least
one equality or membership filter. An empty current source set returns before any connector is
opened; dry-run makes no network call.

## Constraints and risks

- `Vault.from_sources` remains immutable.
- The prune operation must never remove a hub note, another parent document, or a sibling client.
- Delete results carry counts and errors in typed connector results; audit logs contain only table,
  operation, count, and filter-column names.
- A successful upsert followed by failed prune leaves stale retrieval data, not missing current
  data; the script returns failure so the operator can safely retry.
