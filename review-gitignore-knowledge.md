<!-- in-session-review -->
## In-session review — DIG-1522 `/knowledge/` ignore rule

Fresh-context reviewer, no prior knowledge of the diff. **Verdict: approve with
nits**, none blocking. All five findings addressed in `ea72db7b1`.

### Independently confirmed

- The leak is real and the fix closes it. The reviewer fetched all six public
  `refs/backup/chris/digithings/detached/*` refs **anonymously** (no credential
  helper, `GIT_TERMINAL_PROMPT=0`) into a throwaway bare repo: five carry
  `knowledge/data-policy.md`, and `git show refs/anon:knowledge/data-policy.md`
  returns 112,157 bytes of it. The sixth, `20261006-112520`, carries none.
- The pins bite. Mutation testing in a scratch repo: unmodified 4 passed;
  `/knowledge/` deleted → 2 failed; unanchored → anchoring test failed;
  over-broad `/*` → 2 failed; narrowed to one file → knowledge test failed.
- `--no-index` is load-bearing — without it `test_no_tracked_source_is_shadowed`
  passes vacuously.
- Blast radius empty: `git ls-files | grep -i knowledge` returns 5 entries, none
  under `knowledge/`; no tracked symlinks; nothing in workflows or the Makefile
  references a `knowledge/` path.
- New evidence that strengthens the anchoring argument:
  `scripts/seed_knowledge_vault.py:40` sets `DEFAULT_VAULT_DIR = "docs/knowledge"`.

### Findings and what I did

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | minor | No probe for the escape `--no-index` opens: a tracked path under `knowledge/` passes all four tests. | Added `test_nothing_under_knowledge_is_tracked`. Mutation-checked in a replica repo — force-adding the policy fails this test, passes the other four. |
| 2 | minor | The comment's "and any nested checkout's copy" is **false**. Git treats a nested repo as a gitlink, so the *anchored* rule is the one that stages it; neither rule leaks contents. | Rewritten to the argument that holds: `docs/knowledge/`, the vault directory `seed_knowledge_vault.py` writes to. Fixed in both `.gitignore` and the test docstring. |
| 3 | nit | `rsplit(":", 1)` is ambiguous if a rule contains a colon. | Assumption documented in `_check_ignore`. No rule in this repo contains one; the sibling `test_gitignore_build_artifacts.py:69` shares it. |
| 4 | nit | "shadowed by a nearer `.gitignore`" is unconstructible — git does not descend into an excluded directory. | Docstring corrected. The root-resolution test is kept; it catches the rule being *moved*, which is the real failure mode. |
| 5 | nit | PR body cited `.gitignore:78`; the rule is on line 80. | PR body updated. |

### One correction to finding 1

The reviewer asserted that a force-added path would still be swept by
`git add -A`. **That does not reproduce.** I ran dt-snapshot's exact sequence
(`read-tree HEAD` into a temp index, then `git add -A`) in a replica repo with
the file force-added: the temp index is reset to HEAD, where the path does not
exist, so from git's point of view it is untracked *and* ignored and is not
staged. The guard is still correct and worth keeping — its real mechanism is
that a **committed** path under `knowledge/` is inherited from
`git read-tree HEAD` with no rule consulted — so that is what the docstring now
says.

### Not findings

Pre-existing and byte-identical on `develop`: `I001` in
`digiquant/scripts/recover_ledger.py:16`, 127 files in `ruff format --check`,
and `tests/scripts/test_zammad_mcp.py::test_allowed_host_patterns_append_port_wildcard`
(fails on the branch base with the diff stashed — confirmed).

Durable record: `review-gitignore-knowledge.md` beside the worktree.
