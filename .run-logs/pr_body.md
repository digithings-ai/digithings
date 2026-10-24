## Linked issue

Fixes DIG-5122

---

## Component

- [x] digiquant

## Change Type

- [x] test — tests only

## Summary

Commit `0777d95c3d` split the flat directory `digiquant/supabase/migrations/` into the layers
`engine/`, `prod/` and `cutover/`. 59 test modules still read their migration through the old flat
path and failed with `FileNotFoundError`. This PR points every one of those path constants at the
layer that actually holds the file, and restores the pre-split file set for the sweeps that read the
applied chain (`engine/` + `prod/`, never the staged `cutover/`).

The same split left the production generator `scripts/gen_d1_authz_policies.py` globbing the flat
directory. It parsed no migration at all, so the generated policy table had gone stale. The
generator now reads `engine/` + `prod/`, exactly like its already-migrated sibling
`scripts/gen_d1_reject_guards.py`. The generated artifact is byte-identical.

---

## Modules / files / folders touched

- `tests/dq/research/` — 49 files
- `tests/dq/test_core_advisor_harden_139.py`
- `tests/dq/test_d1_authz_policies.py`
- `tests/dq/test_d1_functions.py`
- `tests/dq/test_d1_reject_guards.py`
- `tests/dq/test_drop_market_tables_127.py`
- `tests/dq/test_tighten_anon_read_129.py`
- `tests/dq/notify/test_cloudflare_email.py`
- `tests/dq/notify/test_migration_103.py`
- `tests/dq/portfolio/test_commit_run.py`
- `tests/scripts/test_gitignore_knowledge_policy.py`
- `tests/scripts/test_pipeline_digiquant_attempt.py`
- `tests/scripts/test_self_host_parity.py`
- `scripts/gen_d1_authz_policies.py`
- `scripts/rls_proof/run.sh`
- `scripts/rls_proof/README.md`

64 files changed, 291 insertions(+), 151 deletions(-).

---

## What this PR delivers

- Every test module that reads a Supabase migration resolves the migration in the layer that holds
  it. No test reads the flat path any more.
- The sweeps that census the applied chain read `engine/` + `prod/` — the same 138 files the flat
  `glob("*.sql")` matched before the split — so a staged `cutover/` file can no longer change the
  result of a census, a constraint winner or a negative grant sweep.
- The "only one `NNN` file" uniqueness assertions read the whole tree with `rglob()`, so a duplicate
  that lands in another layer is still caught.
- `scripts/gen_d1_authz_policies.py` reads the real migrations again, so `--check` verifies a table
  that was actually parsed. The generated `digiquant/src/digiquant/d1_authz_policies.py` is
  unchanged.

---

## Feature or epic it belongs to

[Fixes DIG-5122](/DIG/issues/DIG-5122), under the epic
[DIG-3392](/DIG/issues/DIG-3392) — bring the digithings codebase to popular-OSS standard.
Follows the pattern of PR #6204, which repaired the same defect in the S28 shard.

---

## How it fits the project vision

A test that cannot find the file it is about is not a test. Every module repaired here was either
crashing or, worse, silently sweeping an empty string and passing for the wrong reason. The repair
keeps the suite honest about the migration chain that actually ships, and it keeps the generated
D1 policy artifact tied to the SQL it is derived from instead of to an empty directory.

---

## Review

Agentic review pass over the branch. Findings and how each was handled:

- **Blocker** — `tests/dq/research/test_execute_at_open.py` was missed by the first commit and
  still read the flat path. Fixed; its three red tests are green.
- **Nit** — `tests/scripts/test_gitignore_knowledge_policy.py` pinned a path that no longer exists.
  Repointed at `engine/`.
- **Should-fix** — five applied-chain reads had been widened from `glob("*.sql")` to
  `rglob("*.sql")`, which pulled the staged `cutover/` layer into a census of the applied chain.
  All five now read `engine/` + `prod/` explicitly. The uniqueness check in
  `tests/dq/research/test_migration_024.py` keeps `rglob()`, because for uniqueness the whole tree
  is the correct set.
- **Nit** — the `scripts/rls_proof/` harness header and README still described a flat top-level
  glob that the harness stopped applying at the split. Both now name the layered chain.

A second, independent verification pass resolved every path expression in the repository by
evaluating it (AST plus runtime evaluation of module-level constants and inline expressions) and
running every glob for real. Its negative control against the pre-branch tree finds 133 flat-path
reads across 54 files and every root-level `glob("*.sql")` returning an empty set. At this head it
finds none: the only remaining reference to a flat migration path is the deliberate negative
assertion that `025_trading_calendar.sql` does not exist, and that file exists nowhere in the
tree.

---

## Testing Evidence

Every shard was measured twice on the same machine: once on `origin/develop` and once on this
branch, so the numbers below are a set diff, not an opinion.

```
# S30 — the 49 research modules this PR touches
# develop: 61 failed, 96 passed, 852 errors
# branch : 1009 passed                        (0 failed)

# S31 — tests/dq/*.py + tests/dq/portfolio/ + tests/dq/notify/
# branch : 2743 passed, 6 failed, 6 skipped, 1 xfailed
# the 6 failures are byte-identical on develop (none of those files mentions migrations)

# S33 — tests/scripts/
# develop: 52 failed, 4543 passed, 50 skipped
# branch : 42 failed, 4550 passed, 50 skipped
# 0 newly broken; 10 fixed (4 in test_pipeline_digiquant_attempt.py,
# 6 in test_self_host_parity.py); the 42 remaining are identical on both sides

# ruff check            -> All checks passed (all 64 changed files)
# ruff format --check   -> clean on tests/dq/research/ (the tree CI format-checks)
# dt-secret-scan        -> clean, exit 0
# gen_d1_authz_policies.py --check      -> OK: policy table is in sync (41 tables)
# gen_d1_reject_guards.py --check       -> OK: artefact is in sync (19 guards)
# verify-supabase-migrations.sh          -> 76 engine + 62 prod, prefixes globally unique
```

The two failures that remain in `tests/scripts/test_self_host_parity.py` are pre-existing and
unrelated to this change: the repo has 10 `apps/*/wrangler.toml` files while
`EXPECTED_WRANGLER_FILES` is 9, and the committed parity baseline is stale against the tree.

---

## Documentation Updated

- [ ] `{component}/ARCHITECTURE.md` updated (Module Map, Public API, or Configuration changed)
- [ ] `{component}/AGENTS.md` updated (new patterns or anti-patterns discovered)
- [ ] Root `AGENTS.md` updated (if a cross-cutting rule changed). Keep `CLAUDE.md` as a pointer to AGENTS.md.

---

## Human Gate

- [ ] Live-trading path modified (broker adapters, order submission, execution gates)
- [ ] Auth or crypto modified (digikey signing, JWT generation, scope enforcement)
- [ ] New JWT scope added to a protected route
- [ ] `DIGI_ALLOW_CODE_EXEC` gate modified
- [ ] New network exposure (`0.0.0.0` bind or new published port)
- [ ] New external service dependency introduced
- [ ] `SECURITY.md` changed
- [ ] Novel architecture pattern introduced (not described in any existing ARCHITECTURE.md)

**Is human review required?** No
