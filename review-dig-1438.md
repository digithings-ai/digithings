# Review — PR #5198 (commit 2741cf9ae, DIG-1438)

- Reviewer: subagent (fresh-context in-session review; read-only)
- Subject: digithings-ai/digithings#5198 — `fix(digisearch): drop the develop-only [program:seed_occ_tickets] boot step`
- Base: `github/develop` · diff: `git diff github/develop...HEAD` (16 files, +420/−166)
- Verdict: **Changes requested** — the removals themselves are correct and boot-safe, but the
  PR's regression pins do not run in CI or `make test-unit` (Blocking, one-line fix). Everything
  else is Minor/Info.

## Severity counts

- Blocking: 1 | Major: 0 | Minor: 4 | Info: 3

---

## Blocking

### B1 — the entire new test module is deselected; no DIG-1438 pin ever runs

`tests/scripts/test_stack_seed_config_parity.py` has no `pytestmark = pytest.mark.unit`. The
repo's own CI lane and `make test-unit` both select by marker, so every test in the file —
including all eight new DIG-1438 tests — is collected and then dropped.

Evidence:

```
$ pytest tests/scripts/test_stack_seed_config_parity.py -q -m "unit or baseline"
collected 19 items / 19 deselected / 0 selected

$ pytest tests/scripts/ -m "unit or baseline" --collect-only -q | grep -c test_stack_seed_config_parity
0
```

- CI selector: `.github/workflows/ci.yml:442` —
  `pytest tests/scripts/ tests/config/ ... -m "unit or baseline"`.
- Local gate: `Makefile:30` — `test-unit: pytest -m unit`.
- Sibling modules in the same directory do carry it (`tests/scripts/test_check_tenant_corpus_map.py`,
  `tests/scripts/test_d1_sync.py`), and the repo states the rule explicitly:
  `tests/scripts/test_stack_dockerignore_context.py` (main) — *"`pytestmark = pytest.mark.unit`
  is load-bearing, not boilerplate: `ci.yml` collects with `-m "unit or baseline"` … so a module
  without the marker is silently deselected and the guard never runs."*

Run ad-hoc (`pytest tests/scripts/test_stack_seed_config_parity.py`, no `-m`) it is 16 passed /
3 skipped — so the assertions are correct; they are simply never reached by any gate.

Note for the record: `main`'s 104-line copy also lacks the marker (`git show
github/main:tests/scripts/test_stack_seed_config_parity.py | grep pytestmark` → no match), so the
defect is inherited by the copy. That does not excuse it here — this PR extends the file to 366
lines and makes the pins the stated deliverable, and a re-added `[program:seed_occ_tickets]`
would then ship the unmasked-ticket-PII boot step with a green CI.

**Fix:** add `pytestmark = pytest.mark.unit` next to the imports (after `import yaml`,
`tests/scripts/test_stack_seed_config_parity.py:36`), then confirm
`pytest tests/scripts/test_stack_seed_config_parity.py -m unit -q` selects 19.

---

## Minor

### M1 — `.dockerignore` and `Dockerfile` justify the kept re-include with a test that is not in this tree

Both files cite `tests/scripts/test_stack_dockerignore_context.py` as the thing pinning
`!scripts/index_occ_tickets.py`:

- `.dockerignore:40-44` — "…`tests/scripts/test_stack_dockerignore_context.py` pins it."
- `Dockerfile.digithings-stack-cloudflare:133-139` — same claim.

That file exists on `main` only. On this branch it is absent:

```
$ git ls-tree HEAD tests/scripts/ --name-only | grep -i dockerignore   # no output
$ git ls-tree github/develop tests/scripts/ --name-only | grep -i dockerignore   # no output
$ git ls-tree github/main   tests/scripts/ --name-only | grep -i dockerignore
tests/scripts/test_stack_dockerignore_context.py
```

So on `develop` nothing pins the re-include, and a reader following the comment finds no such
test. The re-include itself is harmless (it only widens the build context), but the stated
justification is false in this tree.

**Fix:** reword to say the re-include is retained for parity with `main` / DIG-1210, without
naming a test that `develop` does not carry.

### M2 — `needs_4987` keys on a literal that can never appear on develop, so it never self-flips

`tests/scripts/test_stack_seed_config_parity.py:71-93`:

```python
def _legacy_marker_clearing_merged() -> bool:
    seeder = (CONTAINER_SCRIPTS / "seed_chroma.sh").read_text(encoding="utf-8")
    return ".stack_chroma_seeded_v1" in seeder
```

`.stack_chroma_seeded_v1` exists only on `main` — `git log -S ".stack_chroma_seeded_v1" github/main
-- .../seed_chroma.sh` → `86cb1ec5d` (#4987). `develop`'s `seed_chroma.sh` never carried it; it
already has the provider-qualified `${SEED_TAG}` marker from `22f08b717` (#5048):

```
$ grep -c stack_chroma_seeded_v1 apps/digithings-stack-cloudflare/container/seed_chroma.sh   # HEAD: 0
$ git show github/main:.../seed_chroma.sh | grep -c stack_chroma_seeded_v1                   # main: 1
```

Consequence: the predicate is permanently `False` on develop, so
`test_seed_version_clears_every_prior_marker`, `test_embedding_provider_pinned_on_every_runtime_layer[compose]`
and `test_env_example_documents_the_same_provider` stay skipped forever — including after a
`develop → main` promotion, which does not add a v1 marker to develop's seeder. The docstring
claim at `:79-81` ("it flips by itself when the PR merges — no edit to this file needed at that
point") is therefore inaccurate for this branch. The skips are honest about *today's* state (the
compose override and env example genuinely lack the pin on develop), so nothing is currently
failing falsely — the guard is just permanently off rather than self-healing.

**Fix:** key the skip on the condition the skipped tests actually assert — e.g. presence of
`DIGISEARCH_EMBEDDING_PROVIDER` in the compose override / example env — instead of a
marker literal from the other branch.

### M3 — the trimmed OCC README now contradicts itself on the summary row

`docs/projects/online-compliance-center/README.md:20` still reads:

```
| digisearch index | `occ_help` docs + `occ_tickets` fan-out |
```

while this PR trims the same file's schematic (`:52`) and both env blobs (`:60`, `:66`) to
`occ_help` alone. `main` already has the short form at `:20`
(`git show github/main:docs/projects/online-compliance-center/README.md` → `| digisearch index | occ_help |`),
so this branch re-introduces drift against `main` in a file the PR is already editing.
`review-4983.md` flagged exactly this line as a leftover.

Note the new pin `test_no_layer_fans_out_to_occ_tickets` lists this file but greps for the
literal `occ_help,occ_tickets`, so the row passes the test while still advertising the fan-out.

**Fix:** `| digisearch index | `occ_help` |` at `:20`, matching `main`.

### M4 — promotion into `main` will conflict here, and one resolution breaks `main`'s own test

`git merge-tree --write-tree github/main HEAD` conflicts on 13 paths, including
`.dockerignore`, `Dockerfile.digithings-stack-cloudflare`, `.../container/seed_chroma.sh`,
`.../container/start_digisearch.sh`, `infra/digichat-release/compose.profile-a-bundle.override.yml`,
`scripts/index_occ_tickets.py`, `scripts/zammad_mcp/README.md`, and — new in this PR —
`tests/scripts/test_stack_seed_config_parity.py` (add/add: `main`'s 104-line file vs this
366-line one; 7 conflict hunks).

One resolution trap worth recording: `main`'s `Dockerfile:110-111` still carries

```
COPY scripts/index_occ_tickets.py /app/scripts/index_occ_tickets.py
COPY scripts/build_occ_tickets_seed.py /app/scripts/build_occ_tickets_seed.py
```

and `main`'s `tests/scripts/test_stack_dockerignore_context.py::test_occ_ticket_seed_scripts_are_reincluded`
requires **both** `scripts/index_occ_tickets.py` and `scripts/build_occ_tickets_seed.py` in the
re-include list. This branch's `.dockerignore` has only the former. If the `.dockerignore`
conflict is resolved toward this branch, that `main` test fails on `main` after promotion.

**Fix:** when resolving the promotion merge, keep `!scripts/build_occ_tickets_seed.py` in
`.dockerignore` (and reconcile the two `test_stack_seed_config_parity.py` copies by taking this
branch's, minus the `needs_4987` skips that `main` does not need).

---

## Info

### I1 — `scripts/zammad_mcp/README.md` still tells operators to flip the fan-out back on

`scripts/zammad_mcp/README.md:151` (`query_index` accepts `"occ_help,occ_tickets"`) and `:170-176`
("Refresh tickets: `python -m scripts.index_occ_tickets` … and flip the tenant map to
`"occ_help,occ_tickets"`") survive this PR, and the file is not in the
`test_no_layer_fans_out_to_occ_tickets` parametrisation. `main` carries the same text
(`git show github/main:scripts/zammad_mcp/README.md` → same two lines), so it is not a regression —
but the PR trims three other READMEs and leaves the one runbook whose whole job is the OCC ticket
corpus instructing operators to re-enable what DIG-1380 retired. Cheap to add to the param list
once the prose is updated.

### I2 — the prompt/map trim is byte-faithful to #5192

Verified programmatically, decoding each layer's escaping depth before comparing:

- `apps/digithings-stack-cloudflare/wrangler.toml` `[vars] DIGI_TENANT_CORPUS_MAP` — parsed map
  and `researchSystemPrompt` are **identical** to `github/main`.
- `infra/digichat-release/compose.profile-a-bundle.override.yml` `DIGI_TENANT_CORPUS_MAP` —
  **identical** to `main`.
- `apps/digithings-stack-cloudflare/src/index.ts` `?? '…'` fallback (TS single-quote decode:
  `\\`→`\`, `\'`→`'`, then `json.loads`) — **identical** to `main`.

The rewritten prompt drops the "Ticket content lives in TWO places" paragraph (which advertised
`occ_tickets` as searched with every question) and replaces it with "Ticket content is not part of
this corpus. For ticket questions use the read-only zammad tools…" — the same text `main` ships.
`occ_help` is preserved in the index, in the grounding sentence, and in the
"cross-check the occ_help docs" recipe. No layer still tells the model ticket content lives in
two places. `scripts/check_tenant_corpus_map.py` exits 0 (`corpus map ok: 2 tenant(s) agree
across 3 blobs`) and `scripts/check_doc_links.py` exits 0 (`OK (470 markdown files scanned)`).

### I3 — removals verified correct; no dead state, no hang, no stale priority

- **Wait loop.** `start_digisearch.sh` no longer references any ticket marker. The only remaining
  wait is the `SEED_MARKER`/`SEED_FAILED` loop (`:54-70`), which is still bounded (600 s) and still
  writes both an armed guard and a loud ERROR on timeout. No marker is awaited that nothing
  writes, so no new hang path. `sh -n` clean; also clean for `seed_chroma.sh`, `entrypoint.sh`.
- **Dead variables.** `TICKET_UNSEEDED` / `TICKET_MARKER` were removed with their only consumers;
  `SEED_TAG`, `SEED_MARKER`, `SEED_FAILED`, `UNSEEDED_LIST` all remain used. `DIGISEARCH_UNSEEDED_INDEXES`
  is still initialised, mutated and exported. No orphaned state.
- **Timeout branch.** The 600 s arm still names exactly `digithings_docs,occ_help` — the two
  indexes `seed_chroma.sh` actually seeds (`:96-97`). `occ_tickets` no longer appears anywhere in
  the guard.
- **`priority=`.** Remaining programs: 10, 15, 20, 25, 30, 40, 40, 45, 45, 45, 46, 50. Removing 35
  leaves a harmless gap; seed (30) still precedes digisearch (40), which is what the marker wait
  actually enforces. 13 → 12 program blocks, matching `main`'s count.
- **`Dockerfile`.** Dropping `COPY scripts/index_occ_tickets.py` leaves no runtime or test
  expectation for `/app/scripts/index_occ_tickets.py`: nothing else in the image imports it
  (`git grep -n index_occ_tickets -- '*.py'` → only `scripts/index_occ_tickets.py` itself,
  `scripts/download_multilingual_model.py:10` (docstring), `tests/ds/test_multilingual_embedder.py`
  (repo-side import, not image-side), and the new test file's prose). `scripts/zammad_mcp/` is
  still copied and imports nothing from it. The `chmod +x` list correctly drops
  `seed_occ_tickets.sh`. The v17 rebuild marker is present (`Dockerfile:183-191`).
- **Boot-path coverage.** No other entry point can still reach the writer:
  `git grep -n "index_occ_tickets|build_occ_tickets_seed" -- '*.yml' '*.yaml' '*.sh' '*.toml'
  Makefile '*.json' '.github/**' docker-compose.yml 'scripts/**'` returns only docstrings and
  Markdown. `entrypoint.sh`, compose, wrangler, workflows and `Makefile` are clean.
- **Missed fan-out sites (documented, deliberate).** `digisearch/src/digisearch/search/_stub.py:396`,
  `digigraph/src/digigraph/corpus_routing.py:36`, `digisearch/src/digisearch/core/models.py:104` and
  `digigraph/ARCHITECTURE.md:1114` still use `occ_help,occ_tickets` as a *capability example* in
  docstrings. Those describe the RRF fan-out feature, not a config value, and `main` keeps them —
  correctly left alone.
- **Lint.** `ruff check tests/scripts/test_stack_seed_config_parity.py tests/dg/test_tenant_corpus_parity.py`
  → `All checks passed!` (ruff 0.15.11).

---

## Checks run

```bash
pytest tests/scripts/test_stack_seed_config_parity.py -q                      # 16 passed, 3 skipped
pytest tests/scripts/test_stack_seed_config_parity.py -q -m "unit or baseline" # 19 deselected  ← B1
pytest tests/scripts/ -m "unit or baseline" --collect-only -q | grep -c test_stack_seed_config_parity  # 0  ← B1
python3.12 scripts/check_tenant_corpus_map.py                                 # exit 0
python3.12 scripts/check_doc_links.py                                         # exit 0
ruff check tests/scripts/test_stack_seed_config_parity.py tests/dg/test_tenant_corpus_parity.py
sh -n apps/digithings-stack-cloudflare/container/{start_digisearch,seed_chroma,entrypoint}.sh
git merge-tree --write-tree github/main HEAD        # 13 conflicted paths  ← M4
git merge-tree --write-tree --name-only github/main github/develop   # 16 paths, same set minus this PR's
```
