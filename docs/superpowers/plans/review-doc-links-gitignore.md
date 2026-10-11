# Review — check_doc_links.py skips gitignored paths (#5022, PR #5021)

- **Subject:** `task/5001-doc-links-gitignore` → `develop`, PR [#5021](https://github.com/digithings-ai/digithings/pull/5021), reviewed as `git diff refs/remotes/github/develop...HEAD`
- **Reviewer:** in-session review on a fresh-context subagent (`ses_efc8f5607ffe7Lz47lx625E4la`), read-only. The author session did **not** review its own work; it re-ran the verification command for each finding before acting.
- **Issue:** [#5022](https://github.com/digithings-ai/digithings/issues/5022)
- **Precedent:** [`review-unified-model-catalog.md`](review-unified-model-catalog.md), [`review-byok-pin-swap.md`](review-byok-pin-swap.md)
- **Date:** 2026-10-03
- **Verdict:** `approve-with-nits` → **approve** after the fixes below

## Summary

The reviewer's own words: *"The production change is correct and does fix the real bug."* What held it back from a clean approve was one test that could not fail by construction, plus honesty and traceability problems in the commit message and PR body.

| Severity | Count | Fixed |
|---|---|---|
| major | 1 | 1 |
| minor | 4 | 4 |
| nit | 4 | 4 |

## F1 — major — `test_collect_skips_paths_git_ignores` was vacuous

**Claim.** It monkeypatched `mod._gitignore_paths`, so by construction it could not observe the real filter, and it asserted on `apps/digichat/.next/standalone/AGENTS.md` — a path that does not exist in a clean tree. (The commit message reproduced the failure at a *different* path, `.../standalone/apps/digichat/AGENTS.md`.)

**Verification.** The reviewer copied the assertion into a probe whose filter was the identity (i.e. the filter fully disabled). On a clean tree the probe reported `1 passed` and printed `artifact present on disk: False`; only after fabricating the file did the probe fail. In that same tree the shipped test still passed, because its monkeypatch supplied the very path it asserts is absent. The real filter does drop the copy (`real filter drops the .next copy: True`) — so **the production code was right; only the test was empty.**

**Fix.** Replaced with a real fixture: a `tmp_path` git repo (`git init`), `.gitignore` = `build/`, `docs/generated/*`, `!docs/generated/kept.md`, four files written, `monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)`, then `_collect_markdown_files()` with the real subprocess. It asserts the ignored files are absent and — the reason for shelling out to git at all — that the `!`-negated file **is** still collected. A module-scope `_git_repo()` helper carries the rationale: every other test stubs the subprocess, so this is the only place the production path runs end to end.

Four real failures surfaced while building that fixture, none of them test-massaging:

1. Both `subprocess.run` stubs still returned `str` stdout after the production switch to `text=False` + manual `surrogateescape` decoding → `TypeError: must be str or None, not bytes`. Fixed to bytes.
2. The first fixture put the negated file where no collect rule matched (`build/kept.md`), so the negation assertion was testing nothing. Restructured so every file sits under a rule that would collect it.
3. `!docs/generated/kept.md` was inert — **git cannot re-include a file whose parent directory is excluded**, so `docs/generated/` being excluded makes the negation a no-op. Changed to the idiomatic `docs/generated/*` + `!docs/generated/kept.md`.
4. An assertion that the stdin payload ended with a trailing NUL failed; the payload is NUL-**joined** with no trailing NUL because git reads to EOF. That is correct behaviour, so the assertion became set membership.

**Revert-detection now works behaviourally.** Re-pointing the test at `git show refs/remotes/github/develop:scripts/check_doc_links.py` gives **5 failed, 1 passed**, and the 5 include this test. Before the fix the suite only pinned symbol existence.

## F2 — minor — no test ever ran the real `git check-ignore` against a real ignored path

Tests 1–3 replaced `subprocess.run`, test 4 replaced `_gitignore_paths`, tests 5–6 ran against a clean tree where git reports nothing. Closed by the F1 fixture.

## F3 — minor — pathspec magic silently disabled the whole filter

**Claim.** A candidate whose name reads as pathspec magic (`:(glob)…`) makes `check-ignore` abort, and the fatal was swallowed.

**Verification.** `git check-ignore --stdin -v` with `':(glob)odd/x.md'` → `fatal: :(glob)odd/x.md: pathspec magic not supported by this command: 'glob'`, **rc 128** → the old `return frozenset()` fallback, so every other path silently lost its filter too.

**Resolution — and a correction to the finding.** The diagnosis was right; **the proposed remedy does not exist.** `--literal-pathspecs` is not supported by `check-ignore`:

```
$ git check-ignore --literal-pathspecs --stdin
error: unknown option 'literal-pathspecs'                       rc 129
$ git --literal-pathspecs check-ignore --stdin
fatal: … pathspec magic not supported by this command: 'literal' rc 128
```

The usage block lists only `-q/--quiet`, `-v/--verbose`, `--stdin`, `-z`, `-n/--non-matching`, `--no-index`, `--index`. So the query cannot be made literal, and the flag was **not** shipped. The other half of the finding is the real fix: an unexpected return code now writes the reason and git's own stderr to `sys.stderr` instead of dropping the filter in silence, and the comment says why the flag cannot help. Observed live: `check_doc_links: git check-ignore exited 129; treating every path as tracked.` followed by git's usage text, then the normal `OK (459 markdown files scanned)` and exit 0 — loud, not silent, and not a false failure.

## F4 — minor — a developer's global `core.excludesFile` could silently under-scan

**Claim.** In a standalone scratch repo the reviewer showed an untracked doc reported as rc 1 normally, but rc 0 (ignored) once `GIT_CONFIG_GLOBAL` pointed at a config whose `core.excludesFile` covered it — so a personal global gitignore containing `*.md` would drop every doc and `make doc-check` would pass vacuously.

**Fix.** `-c core.excludesFile=/dev/null` in the argv.

**Attribution.** The reviewer proved the claim; the author session's own attempt to reproduce it failed on harness setup (`GIT_CONFIG_GLOBAL` pointed at a file inside the digithings worktree → `fatal: bad config line` → rc 128 for every case, so both arms matched). The mitigation is shipped on the reviewer's evidence, not on a local reproduction, and is recorded as such.

## F5 — nit — no `-z`, so quoted / non-ASCII filenames never matched

Without `-z`, git C-quotes any path that is not plain ASCII, so set membership against the input fails. Reproduced in a scratch repo with `.gitignore` containing `build/` and `uni/`:

```
with -z:            uni/café.md
                    uni/quote".md
without -z:         "uni/caf\303\251.md"
                    "uni/quote\".md"
```

**Fix.** `-z` on both stdin and stdout, with manual `surrogateescape` decoding (`text=True` dropped, since `-z` is a byte protocol).

## F6 — minor — nothing traced this work to an issue

**Claim.** The branch was `task/5001-doc-links-gitignore` (5001 is the *merged PR* "land the unified model catalog's /review fixes"), the commit trailer read `Refs: #5000` (the closed BYOK-pins issue), and the test docstring read `(#5001)`. `gh issue list --search "check_doc_links OR doc-check in:title"` found only #4431 and #95, both unrelated doc-content issues.

**Fix.** Filed [#5022](https://github.com/digithings-ai/digithings/issues/5022) ("check_doc_links.py walks gitignored paths") and cited it in the PR body and the commit trailer. The branch name still carries the wrong number; renaming mid-review would churn the open PR, so the mismatch is stated in the PR body instead.

## F7–F9 — honesty corrections in the PR body

- **F7** — "the second of the two follow-ups from the #4994/#5000 work" was wrong on both counts: those are the catalog and pins issues, and `gh pr list --search "check_doc_links"` shows no sibling "first follow-up". Reworded to say what it actually is, a defect surfaced while working on #4994 and tracked as #5022.
- **F8** — the code comment claimed "a copy of every component's AGENTS.md" and "`make doc-check` fail on three links". The repro yields exactly **one** error line, and the reviewer could not verify the build claim (no `node_modules` in the worktree; `apps/digichat/next.config.ts` sets only `output: "standalone"` and `outputFileTracingRoot`). Softened to "a copy of component docs (AGENTS.md among them)" and "can make". Corroboration that phantom `.next` content is a real prior problem: `scripts/check_architecture_drift.py:56` already hardcodes `.next` in `_SKIP_DIR_PARTS`.
- **F9** — `scripts/check_architecture_drift.py:54-57,137-143` has the same class of gap on a hardcoded `_SKIP_DIR_PARTS`. The other scanners were checked and are not affected: `check_adr_numbering.py:66` uses `iterdir()` (no recursion); `digivault/src/digivault/vault.py:129` and `scripts/d1_sync.py:291` rglob a caller-supplied vault root, not the repo tree; `sync_architecture_vault.py` has no repo-tree walk. Left out of scope, noted in the PR body.

## What the reviewer independently verified as correct

- **`check-ignore` rc contract** — 0 = at least one ignored, 1 = none, stdout = the ignored subset, 128 = fatal — so the `not in (0, 1)` guard is right in shape.
- **No over-exclusion of tracked docs.** Git consults the index by default, so a `git add -f`'d file matching an ignore rule is *not* reported (scratch repo: `build/tracked.md` force-added under `.gitignore: build/` → only the genuinely-ignored path reported).
- **Before/after scan sets on the real tree are identical** — `old 459, new 459, dropped: [], added: [], new & gitignored: []`.
- **The bug reproduces without needing `.next`** — a fabricated `apps/digichat/.next/standalone/apps/digichat/AGENTS.md` with a dangling link: old script `failures` / exit 1, new script `OK (459 markdown files scanned)` / exit 0. The artifact is invisible to `git status` and correctly reported by `check-ignore` (`apps/digichat/.gitignore:17:/.next/`).
- **New untracked docs are still scanned and still fail** — an untracked `docs/` scratch with a dangling link was collected and reported, so the filter does not become a blanket suppressor.
- **Degradation is sound** — `FileNotFoundError("git")` is an `OSError` → `frozenset()`; a non-checkout → rc 128 → `frozenset()`; an empty candidate set short-circuits, so a copy in `/tmp` still scans 0 files without invoking git.
- **`EXCLUDE_PREFIXES` is not dead** and 4 entries are irreplaceable: `check-ignore --verbose` reports nothing for `.git/config`, `.claude/settings.json`, `digisearch/devdata/foo.md`, `projects/README.md` (the repo ignores `/projects/*` then re-includes `!/projects/README.md`). It does report the other six. "Stays as the fast path" is accurate.
- **Perf is a non-issue** — exactly one `subprocess.run` per scan; 459 candidates on stdin (21,880 bytes); end-to-end 182 ms → 225 ms.
- **"CI unaffected" holds** — `ci-docs.yml:45` and `pipeline-maintenance.yml:215` run straight after `actions/checkout@v4` with no digichat build.
- **PR title scope `root` is valid** (`ci-pr-title.yml:94`); `Validate PR title`, `doc-links + agents-init`, `ruff-and-scripts` and `Required checks passed` all green on #5021.

## Reviewer's own caveats, recorded for honesty

- It could not verify the underlying Next build claim (no `node_modules`; a full build was out of scope for a read-only review) — everything used a fabricated artifact exercising the identical code path. F8 is therefore a claim-strength nit, not a blocker.
- F3 and F4 were proven in throwaway scratch repos, not in the digithings tree, since neither condition can be produced there without a hostile committed filename or editing a user's global git config.
- It did not run full `make test-unit` / `make doc-check` (no `.venv`; the NautilusTrader SIGABRT caveat); it ran `python3 scripts/check_doc_links.py` directly → `OK (459 markdown files scanned)`, matching the commit message.
- It could not check whether an `<!-- in-session-review -->` comment existed, because at review time #5021 had no labels and an empty `reviewDecision` — which is itself the gap this comment closes.

## Post-fix verification

| Check | Result |
|---|---|
| `python3 -m pytest tests/scripts/test_check_doc_links.py -q` | 6 passed |
| Revert-detection (script swapped back to the develop version) | **5 failed, 1 passed** — the filter test is among them |
| `python3 -m ruff check scripts/check_doc_links.py tests/scripts/test_check_doc_links.py` | All checks passed |
| `python3 -m ruff format --check` on both files | already formatted |
| `python3 scripts/check_doc_links.py` | `OK (459 markdown files scanned)` |