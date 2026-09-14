---
type: behavior-guide
title: digivault Notes and Links
description: digivault note behavior — frontmatter round-trips, wikilink parsing and rewrites, backlinks, tags, lint, and maintenance ops.
tags: [digivault, notes, wikilinks, frontmatter]
sources:
  - id: openwiki-source-7bbef4a62375238afea229da
    resource: repo://digivault/src/digivault/frontmatter.py
  - id: openwiki-source-9145937572c6f2e127fe29e2
    resource: repo://digivault/src/digivault/vault.py
  - id: openwiki-source-618990bdda68881766759160
    resource: repo://digivault/src/digivault/wikilinks.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digivault Notes and Links

A vault is a directory of markdown notes plus derived indexes (link
graph, backlinks, tags). `Vault` loads sources, builds the indexes, and
serves reads and sandboxed writes; every mutation refreshes the affected
index entries.

## Frontmatter

`split_frontmatter` / `dump_frontmatter` / `set_keys` implement
round-trip-safe YAML handling: `split(dump(fm, body)) == (fm, body)`.
Tags and aliases normalize to tuples on load, so `search_by_tag` and
index builds see canonical forms regardless of author style (inline
list, block list, or scalar).

## Wikilinks

`parse_links` recognizes `[[note]]`, `[[note#heading|alias]]`, and
`![[embed]]` forms into `LinkRef` records. `rewrite_target` and
`map_targets` rewrite link targets while masking code spans and blocks
first — examples inside fenced code never rewrite. Standard inline
<!-- openwiki: broken internal link [target] file "target" does not exist. Fix the href or restore the target, then delete this comment. -->
`[label](target)` links are out of scope (owned by the doc-link checker).

## Reads

`list_notes()` returns `Note` records with backlinks attached;
`backlinks(name)` returns inbound referrers; `search_by_tag(tag)` filters
the tag index; `get_note` / `read_text` fetch by name. `Vault.from_sources`
reconstructs the same indexes over remote note rows (Supabase/D1)
instead of the filesystem.

## Maintenance

`create_note` (with frontmatter + body), `write_note(...,
overwrite=True)` for idempotent upserts, `rename` with inbound-link
rewrite across the vault, `set_frontmatter`, `prune_children` for scoped
docs convergence, `reindex`, and `lint()` returning a `LintReport` (ok,
note count, issues). Writes require a writable vault and resolve through
`_safe_path` — traversal and absolute escapes refused.
