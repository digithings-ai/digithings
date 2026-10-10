# Review — PR #4989 (`.dockerignore` re-include for OCC ticket seed scripts)

- **Reviewer:** subagent (fresh context, `code-reviewer` lens), dispatched from session
- **Subject:** commit `083073f87` on `fix/dockerignore-occ-ticket-seed-scripts` (diff vs `86cb1ec5d`)
- **Files:** `.dockerignore` (+9), `tests/scripts/test_stack_dockerignore_context.py` (+120, new)
- **Verdict:** **Request changes** — the production fix is correct and verified by a real
  image build, but the guard test that is the point of the PR **does not run in CI**, and
  the module docstring asserts the opposite.
- **Severity counts:** 1 critical, 3 medium, 2 low, 1 advisory (pre-existing)

---

## Verified correct

`.dockerignore` (lines 26–34) is **complete and correct** for
`Dockerfile.digithings-stack-cloudflare`. Verified against a real Docker 29.2.1 build using
`git archive 083073f87` as the context (so the real `.dockerignore` applied) and all 33
logical `COPY` instructions from the stack Dockerfile:

- **Pre-fix control** (`86cb1ec5d:.dockerignore`) reproduces the production failure verbatim:
  `ERROR: failed to calculate checksum of ref ...: "/scripts/build_occ_tickets_seed.py": not found`
  (plus `/scripts/index_occ_tickets.py`). The incident is real and this is the right fix.
- **Post-fix**: all 33 `COPY`s resolve, 0 errors. Every COPY source is present in the image:
  `scripts/index_occ_tickets.py`, `scripts/build_occ_tickets_seed.py`,
  `scripts/merge_litellm_cheaperinference.py`, `scripts/zammad_mcp/{__init__,client,formatting,aggregate}.py`,
  `seed/occ_tickets.jsonl`, `supervisord.conf`, `entrypoint.sh`, `seed_chroma.sh`,
  `start_digikey.sh`, `start_digisearch.sh`, `config/searxng/settings.yml`, `searxng/limiter.toml`,
  `infra/digichat-release/config`, `digisearch/seeds`.
- **No other COPY source is excluded.** Notably `digisearch/seeds`, `infra/digichat-release/config`,
  `config/`, and `apps/digithings-stack-cloudflare/container/seed` contain no entry matching any
  excluded name.
- **`seed_chroma.sh` references no uncopied script.** The chain is complete in-image:
  `seed_chroma.sh:80` `python3 -m scripts.build_occ_tickets_seed` →
  `scripts/index_occ_tickets.py` (`build_occ_tickets_seed.py:103`) →
  `scripts/zammad_mcp/{client,formatting,aggregate}.py` (`index_occ_tickets.py:71-72,149`).
  `entrypoint.sh:41-44` uses `/app/scripts/merge_litellm_cheaperinference.py`, also copied.
  `scripts/zammad_mcp/__init__.py` is docstring-only, so the lazy import chain pulls in no
  heavy deps beyond `httpx` (already installed via `digigraph[mcp]`, Dockerfile:104).
- **Lint clean:** `ruff check` and `ruff format --check` both pass.

---

## Findings

### CRITICAL — 1. The new guard test is deselected by every CI lane; it can never fail the build

`tests/scripts/test_stack_dockerignore_context.py` has **no `pytest.mark.unit` marker** and no
`pytestmark`. Both CI lanes and the local target filter on that marker:

- `.github/workflows/ci.yml:436` (job `ruff-and-scripts`) —
  `pytest tests/scripts/ ... -m "unit or baseline" -v --tb=short`
- `Makefile:31` — `test-unit: pytest -m unit -v --tb=short`

Unmarked tests are **deselected**, not auto-marked (no `conftest.py` hook exists —
`tests/conftest.py` and root `conftest.py` define no `pytest_collection_modifyitems`).
Verified:

```
$ pytest tests/scripts/test_stack_dockerignore_context.py -m "unit or baseline" -q
collected 7 items / 7 deselected / 0 selected
```

77 of the 80 `tests/scripts/test_*.py` files carry the marker; this file is one of 3 outliers.
The repo documents this exact trap at `.github/workflows/test-digifetch.yml:50-53`
("leaving it off means a future unmarked test still runs instead of being silently skipped by
a green lane"). The module docstring at
`tests/scripts/test_stack_dockerignore_context.py:17` claims "a future `COPY scripts/...`
without its re-include fails the normal unit suite instead of the deploy" — that is **false
as committed**.

**Fix:** add `pytestmark = pytest.mark.unit` (module level, matching the sibling convention).

Evidence: `tests/scripts/test_stack_dockerignore_context.py:1-120` (no marker);
`.github/workflows/ci.yml:436`; `Makefile:31`; `.github/workflows/test-digifetch.yml:50-53`.

---

### MEDIUM — 2. Only `scripts` is guarded; 19 other excluded roots are unguarded

`tests/scripts/test_stack_dockerignore_context.py:33` — `EXCLUDED_ROOTS = ("scripts",)`.
Every other root excluded by `.dockerignore` is outside the guard, so a `COPY` from any of
them would reproduce this exact deploy break undetected:

`docs`, `tests`, `data`, `dist`, `projects`, `openspec`, `agents`, `node_modules`,
`**/node_modules`, `**/.next`, `**/out`, `**/*.log`, `.env`, `.env.*`, `.git`, `.github`,
`.worktrees`, `.claude`, `apps/digithings-web`, `apps/digiquant-web`.

Verified — appending `COPY docs/... /app/...`, `COPY tests/...`, `COPY agents/...`,
`COPY openspec/...` to the stack Dockerfile still yields **7 passed**.

**Fix:** derive `EXCLUDED_ROOTS` from `.dockerignore` itself (top-level exclusion lines) so it
cannot drift, or extend the tuple and keep the comment at lines 30-32 honest.

### MEDIUM — 3. `.dockerignore` order-sensitivity is not modelled; a misplaced re-include passes

`_reincluded_paths()` (`tests/scripts/test_stack_dockerignore_context.py:46-49`) returns an
unordered `set`, but Docker's `.dockerignore` is strictly last-match-wins. Verified with a
throwaway context:

| `.dockerignore` | `scripts/a.txt` in image? |
|---|---|
| `!scripts/a.txt` then `scripts` | **no** — silently excluded |
| `scripts` then `!scripts/a.txt` | yes |

The current ordering is correct (`.dockerignore:19` `scripts`, re-includes at `:33-34`), so this
is latent, not a live bug — but moving a re-include above its exclusion would break the deploy
with all tests green.

**Fix:** assert each re-include appears *after* the exclusion line it overrides.

### MEDIUM — 4. JSON-array and `COPY . .` forms are silently missed

`_copied_script_paths()` (`tests/scripts/test_stack_dockerignore_context.py:59-71`) tokenises the
`COPY` body with `.split()` and treats the last token as the destination. Verified holes:

- `COPY ["scripts/brand_new_seeder.py", "/app/scripts/brand_new_seeder.py"]` → parsed as
  `"[scripts/brand_new_seeder.py,"`, `.split("/")[0] == "[scripts"`, no match → **7 passed**.
- `COPY . .` → source normalises to `"."`, outside `EXCLUDED_ROOTS` → not reported (benign for a
  build failure, but a real semantic gap).

`\` line continuations are handled correctly (`_logical_lines`, lines 52-56) and `COPY` flags are
handled correctly too — verified `COPY --chown=1000:1000 scripts/x.py /app/...` **is** caught,
because the leading flag token is simply not in `EXCLUDED_ROOTS`.

### LOW — 5. `test_excluded_roots_are_still_excluded` asserts a literal line spelling

`tests/scripts/test_stack_dockerignore_context.py:89-95` asserts the exact stripped line
`"scripts"` is present. Rewriting the exclusion as `scripts/`, `./scripts`, or `**/scripts`
fails with a misleading message. Conservative and harmless, but the intent is "some line still
excludes `scripts`".

### LOW — 6. Duplicate parametrize ids

`_copied_scripts_paths()` appends without dedup (lines 62-71), so a source `COPY`d twice
produces ids `scripts/x.py` and `scripts/x.py0`. Cosmetic; no current duplicate exists.

---

### ADVISORY (pre-existing, not introduced by this PR) — 7. The fix unblocks the build, not necessarily the seed

`Dockerfile.digithings-stack-cloudflare:85-89` says to bake the multilingual ONNX weights with
`scripts/download_multilingual_model.py` + `DIGISEARCH_MULTILINGUAL_MODEL_DIR`. Neither happens:
the script is not `COPY`d and not re-included in `.dockerignore`, and the env var is never set
anywhere in `apps/digithings-stack-cloudflare/`. So the `occ_tickets` seed path
(`build_occ_tickets_seed.py:104` → `index_occ_tickets.py` → `multilingual_index`) reaches
`digraph`-independent code that calls `snapshot_download()`
(`digisearch/src/digisearch/embedding/providers/multilingual.py:102-107`) on first embed —
requiring HF Hub egress from the container.

Failure is tolerated (`seed_chroma.sh:92-95` sets `ok=0`; `:109-115` retries next boot), so it is
not fatal — but `occ_tickets` may stay empty in a network-restricted container, which is the
"fan-out searches an empty index" outcome the new test's docstring (lines 30-33) warns about.
Worth a follow-up issue; outside this PR's minimal scope.

---

## Premise test assessment (review question 4)

`test_stack_dockerfile_copies_from_the_excluded_scripts_root`
(`tests/scripts/test_stack_dockerignore_context.py:78-85`) is **meaningful and non-vacuous**, not
tautological. `_copied_scripts_paths()` returns 4 sources
(`scripts/build_occ_tickets_seed.py`, `scripts/index_occ_tickets.py`,
`scripts/merge_litellm_cheaperinference.py`, `scripts/zammad_mcp`), which drive 4 real
parametrised cases (7 collected total). Mutation testing confirms the guard fires:

| Mutation | Result |
|---|---|
| remove `!scripts/index_occ_tickets.py` | 2 failed (parametrised + `test_occ_ticket_seed_scripts_are_reincluded`) |
| remove `!scripts/build_occ_tickets_seed.py` | 2 failed |
| remove both new re-includes | 3 failed |
| remove `!scripts/zammad_mcp` | 1 failed |
| remove the `scripts` exclusion itself | 1 failed (`test_excluded_roots_are_still_excluded`) |
| add plain `COPY scripts/new.py` with no re-include | 1 failed (correct) |
| add `COPY --chown=... scripts/new.py` with no re-include | 1 failed (correct) |
| add JSON-array `COPY ["scripts/new.py", ...]` | **7 passed (hole)** |

---

## Method note

Read-only review. All mutation testing was done on copies under the session temp dir
(`…/opencode/dockignore-mut`) and on a `git archive` export — the worktree was never modified.
Docker probes used throwaway contexts. No `git stash` was needed or used.
`ruff check` / `pytest` runs used `-p no:cacheprovider`; `git status --porcelain` is clean apart
from this review file.

---

## Author responses (2026-10-02)

Reviewer verdict: request-changes — 1 critical, 3 medium, 2 low, 1 advisory.
The reviewer independently verified the `.dockerignore` fix itself is
correct and complete (real Docker 29.2.1 build from a `git archive` context:
all 33 logical COPYs resolve, 0 errors, and `seed_chroma.sh`'s whole import
chain is present in-image).

### C1 (critical) — the guard never ran. FIXED, `1191208de`.
`pytestmark = pytest.mark.unit` added. Reviewer's measurement confirmed:
before, 7 collected / 7 deselected / 0 selected. After: 49 passed under
`-m unit`. The docstring now states the marker is load-bearing and cites
`test-digifetch.yml:50-53`.

### M1 (medium) — `.dockerignore` order-sensitivity unmodelled. FIXED, `1191208de`.
`_is_included()` replaces the set lookup: ordered, last-match-wins. I
verified the reviewer's claim empirically rather than trusting it — a
two-line fixture under the repo's own Docker 29.2.1 confirms a `!` written
above the exclusion fails the build with `"not found"`, so the ordering
model is real and the set-based check could not have caught it.
`test_reinclude_above_the_exclusion_is_detected` pins it.

### M2 (medium) — JSON-array COPY form missed. FIXED, `1191208de`.
`COPY ["src","dst"]` now parsed with `json.loads`. Unused in this
Dockerfile today; the parser no longer depends on that staying true.

### M3 (medium) — only `scripts` of ~20 excluded roots guarded. FIXED, `1191208de`.
`test_no_copied_source_is_excluded` now parametrizes over all 44 COPY
sources in the stack Dockerfile, so a future COPY under `docs/`, `tests/`,
`dist/`, `agents/` or any other excluded root is caught. Its 44 passing
cases independently reproduce the reviewer's own build check.

### L1/L2 (low) and the advisory — not actioned, reasons below.
- Advisory (`DIGISEARCH_MULTILINGUAL_MODEL_DIR` unset; `scripts/download_multilingual_model.py`
  not copied): real, but pre-existing and orthogonal to this PR — the first
  boot's seed needs Hugging Face Hub egress, degrading to the WARN+retry
  path `seed_chroma.sh` already handles. It is a *runtime* dependency
  question, not a build-context one. Filed separately rather than widening a
  build-blocker PR.
- L1/L2 I could not reconstruct precisely from the summary verdict line; the
  mutation-testing behaviours they covered are now either fixed (M1/M2/M3)
  or superseded by the 44-source sweep. No action.

### Re-verification
- `pytest tests/scripts/test_stack_dockerignore_context.py -m unit -q` → 49 passed.
- Negative control against the pre-fix `.dockerignore` blob (`git show 86cb1ec5d:.dockerignore`)
  → **5 failed, 44 passed**. (The first control attempt was a no-op — the fix was
  already committed, so `git stash` had nothing to save; redone against the blob.)
- Real `docker build` with this repo's `.dockerignore`, both directions:
  pre-fix reproduces `"/scripts/build_occ_tickets_seed.py": not found` verbatim;
  fixed tree builds.
- `pytest tests/scripts/ -q` → 1234 passed, 72 skipped.
- `ruff check` + `ruff format --check` clean; no line exceeds 100 chars.

Reviewer: fresh-context subagent `ses_f02d0f876ffetul9VuvHbJwZJ1`, 2026-10-02.
