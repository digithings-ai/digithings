# Review — model names out of code (#5029, PR #5046)

- **Subject:** `task/5023-model-names-to-config` → `develop`, PR [#5046](https://github.com/digithings-ai/digithings/pull/5046), `git diff refs/remotes/github/develop...HEAD`, commits `ec5427ca1` + `23f723312`
- **Reviewer:** in-session review on three fresh-context subagents, split by concern. The author session did not review its own work: every finding below was re-verified with a command in the author session before acting, and two of the reviewer's claims narrowed a mistake the author had already shipped into the PR body.
- **Date:** 2026-10-04
- **Verdicts:** `approve-with-nits` (config honesty) · `request-changes` (loader behaviour) · `approve-with-nits` (completeness) → **approve** after `23f723312` (all 5 actionable findings addressed)

## Severity counts

| Severity | Count | Addressed |
|----------|-------|-----------|
| blocker  | 0 | — |
| major    | 1 | 1 |
| minor    | 1 | 1 |
| nit      | 5 | 2 (3 accepted with a recorded reason) |

Reviewers' own summaries, kept because they are the useful part:

- **Config honesty:** *"Every number, marker, and provider table is byte-for-byte faithful to its cited source, and both Docker `COPY` lines are correct for their build contexts; the only defects are three cosmetic nits."*
- **Loader behaviour (the one that mattered):** *"Three of the four loaders are behaviourally equivalent to the code they replaced; `pricing.py` regresses in every container because its config file is never copied into either image."*
- **Completeness:** *"The 8 target files are genuinely literal-free in real code and the config move is verified load-bearing, but the digichat consumer change substitutes elided placeholders (`openai/…`) rather than a real catalog lookup, so that half is cosmetic."*

### Why three subagents and not one

A single reviewer given the whole diff **returned no output at all** — no verdict, no findings. That is not a review, so nothing could be claimed from it. The scope was split into three single-question reviews (config honesty + deploy wiring; loader behaviour equivalence; completeness + test quality), each told to reply in a fixed format *even when clean*, each scoped to a question small enough to answer. All three answered. A large prompt with many sub-questions is what produced the empty return; a single question with a mandated output shape did not.

---

## The major finding

### F1 · `config/digiquant-model-prices.json` shipped into no image at all

`Dockerfile.digiquant-runner:44-50`, `digiquant/Dockerfile`, `digiquant/src/digiquant/research/pricing.py:69`.

This is a regression **this PR introduced**, and the reviewer labelled it major for the right reason: the pre-PR table was a literal in `pricing.py` and therefore worked with zero configuration. Post-PR it needs a file that no Dockerfile copied.

The dangerous part is not the omission, it is the shape of the omission. The house runner copies sources under `./digiquant`, so `_REPO_ROOT` resolves to `/app`, and this image already ships an `/app/config/` directory holding `byok-providers.json` and `model-policy.json`. The loader therefore **found a config directory, found no price file inside it, and returned an empty table without warning** — in the image that actually runs chain steps. `diagnostics.est_cost_usd` would report `$0` for every model, and the telemetry spend alert (#4596) could never fire. Fail-soft is the right design; this is precisely the case where fail-soft hides a mistake.

Verified in the author session before acting:

```
grep -c digiquant-model-prices Dockerfile.digiquant-runner digiquant/Dockerfile
  → Dockerfile.digiquant-runner:0
  → digiquant/Dockerfile:0

grep -n "COPY config" Dockerfile.digiquant-runner digiquant/Dockerfile
  → Dockerfile.digiquant-runner:46  COPY config/byok-providers.json …
  → Dockerfile.digiquant-runner:50  COPY config/model-policy.json …
    (digiquant/Dockerfile copies no config files at all)

python3 -c "from pathlib import Path; print(Path('/app/digiquant/src/digiquant/research/pricing.py').parents[4])"
  → /app          # runner: config/ exists, prices file missing → SILENT
python3 -c "from pathlib import Path; print(Path('/app/src/digiquant/research/pricing.py').parents[4])"
  → /             # digiquant service: no config/ → loud missing-dir warning
```

**Fix (`23f723312`)** — `COPY config/digiquant-model-prices.json ./config/digiquant-model-prices.json` beside the two fail-loud copies, with a comment recording *why this one is different* (it is the only config file the image loads softly, so its absence is silent rather than a crash-loop), and a matching needle in `exec_job_test.py` so it cannot drop out again.

**This finding also overturned an author decision.** `ec5427ca1`'s commit message and the PR body both argued the missing digiquant config was a *pre-existing class* of graceful degradation, citing `_node_factory.py:20` which already reads `config/digiquant_models.yaml` and falls back the same way. That reasoning was right about the bare `digiquant` container and wrong about the runner, which was not "no config here" but "this one file missing here". The PR body has been corrected.

### F2 · the docstring rationale that hid F1

`digiquant/src/digiquant/research/pricing.py:65-68`. The comment explained the container case by claiming the path resolves to `/`. It resolves to `/app`, and the table **is** found there. Right answer, wrong reasoning — and that false rationale is precisely what made F1 look acceptable on a first read.

**Fix (`23f723312`)** — rewritten to state the real behaviour: the runner finds the table; an image that does not copy it resolves to a root with no `config/` at all, which takes the missing-file warning rather than pretending the table is legitimately empty.

### F3 · the fail-closed guard had no test for the branch that throws

`apps/digichat/src/lib/deploy-config/deploy-models.ts:39-43`. `default ∈ available` is enforced by a `throw`, but every one of the 12 tests asserted the *good* table — **deleting the `if` left all 12 green.** Also noted: `route.ts:193` reaches the table via `await import("@/lib/deploy-config/loader")`, so a bad table surfaces as a 500 on the first request rather than at build.

**Fix (`23f723312`)** — one `vi.doMock` case with `default` outside `available`, asserting the import rejects. `vi.doMock` rather than a hoisted `vi.mock`, so the already-imported good module is unaffected.

Revert-detection, author session:

```
npx vitest run src/lib/deploy-config/deploy-models.test.ts   → 13 passed (was 12)
# backup to .keep_deploy-models.ts INSIDE the worktree, strip the guard:
npx vitest run src/lib/deploy-config/deploy-models.test.ts
  → × refuses to load a table whose default is not offered
    1 failed | 12 passed
mv .keep_deploy-models.ts apps/digichat/src/lib/deploy-config/deploy-models.ts
cmp <restored> <git show HEAD:…>   → RESTORE byte-identical to HEAD
```

---

## Completeness and the minor finding

### F4 · the digichat chat route elided the example instead of deriving it

`apps/digichat/src/app/api/chat/route.ts:493`.

**The PR's own change had replaced a concrete id with new hardcoded literals** — `(e.g. openai/…, anthropic/…, gemini/…)` — which is the same class of defect the PR exists to remove, just spelled differently. The digigraph half of the same fix (`llm_auth.byok_model_example()`) already read the provider's catalog; the digichat half did not.

**Fix (`23f723312`)** — new server-side `apps/digichat/src/lib/byok-model-example.ts` reading `config/byok-providers.json`, mirroring `llm_auth.byok_model_example()` so the two refusals cannot drift. `route.ts` now renders the caller's own provider's example.

This is also where the *original* bug is most visible: the pre-existing `server.py` refusal offered `openai/gpt-4o-mini` **for every provider**, so an xai caller was told to send a model x.ai does not serve.

**An approach was tried and rejected.** Adding the helper to `byok-providers.ts` and importing the JSON there broke three vitest files — that module's importers resolve a different tree than a repo-root JSON import needs. Reverted with `git checkout`; the helper is a separate module precisely because `byok-providers.ts` is imported by client components and this one reaches outside the Next app root, keeping the catalog out of the client bundle.

The old test asserted the elided string and matched no concrete slug — the *wrong* contract, which is why the gap survived the first commit. Replaced by two tests that assert the caller receives a model their own provider serves, and that an OpenAI model is never offered to a non-OpenAI provider. Vitest 1460 → 1462.

### F5 · completeness — the claim holds, and it was verified independently

The PR claimed all 8 target files have zero model-id literals *in real code*. The completeness reviewer **wrote its own checker** rather than trusting the author's method — for Python, regex only the lines carrying `ast.Constant` string nodes; for TypeScript, strip `//` and `/* */` first. Result: **all 8 targets return 0.** `llm_auth.py` shows 7 raw hits, every one confirmed inside a docstring.

Whole-tree sweep: 492 hits across 15 files = 405 intentional (`model-catalog.generated.ts`) + 5 intentional (chat skins) + 20 test fixtures + 13 docstrings, leaving **45 real-code hits in 5 files** — all PR2 scope (below).

The reviewer also independently revert-tested: restoring `Dockerfile.digiquant-runner` to its develop state makes `exec_job_test.py` fail with `house image missing COPY config/model-policy.json`, and the restore was verified byte-identical with the backup kept **inside** the worktree.

---

## Nits

### F6 · `digiquant-model-prices.json` gemini note enumerated 4 of 6 models — **fixed**

`config/digiquant-model-prices.json:70`. The note listed `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.5-flash`. The snapshot's `paid_tier` carries six — `gemini-2.5-pro` and `gemini-3.1-pro-preview` were missing. The *conclusion* (the slug is absent → unpriced rather than guessed) was correct and independently confirmed; only the enumeration was wrong.

Author-session re-verification of both halves:

```
python3 -c "import yaml; d=yaml.safe_load(open('docs/providers/snapshots/gemini.yaml')); \
  print(len(d['paid_tier']['models']), [m['name'] for m in d['paid_tier']['models']])"
  → last_checked 2026-08-30, six models, gemini-2.5-pro and gemini-3.1-pro-preview present
grep -c "gemini-3.7-flash" docs/providers/snapshots/gemini.yaml   → 0   # genuinely absent
```

**Fixed (`23f723312`)** — all six models named explicitly.

### F7 · ollama `api_key_env` fallback differs in the both-unset case — **accepted, no change**

`scripts/validate-provider-keys.py::_apply_env_overrides`. develop resolved `OPENAI_API_KEY` when neither var was set; the new code leaves `OLLAMA_API_KEY`. Both paths SKIP without `--strict` and both fail with it — only the displayed "…not set (optional)" label differs. Recorded, not changed.

### F8 · `digigraph/Dockerfile`'s COPY is unpinned by any test — **accepted, pre-existing**

`digigraph/Dockerfile:59`. The runner image's equivalent COPY *is* asserted by `exec_job_test.py`. Confirmed in the author session: `grep -rln "digigraph/Dockerfile" tests/` → no hits. develop's `COPY config/byok-providers.json` was never pinned either, so this is a pre-existing asymmetry rather than something this PR introduced. Closing it is a follow-up, not a blocker on a refactor.

### F9 · `docs/MODELS.md` / `docs/LLM_PROVIDERS.md` omit the new `model-policy.json` — **superseded**

Raised by the first pass, then re-checked: `config/MODELS.md` and `digigraph/ARCHITECTURE.md` **were** updated in `ec5427ca1`, and the concern as stated (routing policy is undocumented) does not hold. Noted only so the reviewer can see it was examined rather than dropped.

### F10 · the import-time fail-loud in `model_config` is unreachable in practice — **note, not a defect**

`model_config.py:52` imports `llm_auth`, which is itself fail-loud-at-import on `byok-providers.json`. So a wholly-missing `config/` raises in `llm_auth._load_byok_catalog` *before* `_load_model_policy` is reached; the new raise is reachable only on a partial volume mount. `digigraph/__init__.py` imports only `project_config`, so `import digigraph` never touches the policy, and `import digillm` / `import digiquant` do not load it. Both Dockerfiles and `infra/digichat-release/config/` ship both files, so the partial-mount case is unreachable from any shipped artifact.

Worth recording so a future reader does not go looking for a gap that is not there.

---

## Two claims the author got wrong, corrected by the review

Both were shipped into `ec5427ca1`'s commit message and PR body, and both were wrong. The reviewers caught them by reading the code rather than the brief.

**1. "The policy markers widened the flagship set."** False. The author asserted eight markers (`o1-`, `o1/`, `o3-`, `o3/`, `o4-`, `claude-3-opus`, `claude-3-5-sonnet`, `claude-4`) were newly added. Re-derived independently in the author session:

```
dev flagship (14) == new flagship (14)   IDENTICAL: True
dev-only: []   new-only: []
dev balanced == new balanced == ['gpt-5.6-luna']
```

develop already carried all fourteen. The extraction needed a tweak — develop wraps the set in `frozenset({...})`, so `ast.literal_eval` on the assignment value raises `ValueError: malformed node` until the `Call` is unwrapped. The marker set is byte-identical; nothing is reclassified.

**2. "`google/gemini-3.7-flash` is absent from `digiquant_models.yaml`."** False — it is in the `cheap`, `balanced` and `quality` pools.

A reviewer correcting the author's brief on two points, one of which the author would otherwise have shipped as a claim in a merged commit message, is the process working.

---

## What the review verified as correct

**Prices are faithful to their sources.** All four priced entries match `docs/providers/snapshots/<provider>.yaml` exactly (`0.07/0.28`, `1.00/6.00`, `5.00/30.00`, `1.32/3.96`), and all four `snapshot_last_checked` stamps match their files' own `last_checked`. The `deepseek-v4-pro` `rate: "peak"` claim is supported verbatim by `deepseek.yaml:75-78`: `# PEAK hours …, effective 2026-08-16` and `# OFF-PEAK (all other hours) — repurposed this field for time-of-day, not a context-length tier`. Deliberately using the peak figures when the snapshot's `*_long` fields now hold off-peak numbers is a judgement call, and it is documented in the config rather than left to be silently "corrected" later.

**The provider tables are exact.** `ast.literal_eval` on develop's `PROVIDERS` versus both new JSONs: `added: []`, `removed: []`, `altered: NONE` across all 8 providers × 3 fields. Dropping `github_models` is correct — develop's set was already empty. Pinned by `test_probe_table_is_config_not_code`, which asserts `probe_mod.PROVIDERS == committed["providers"]`.

**`pricing.py` degrades safely and correctly.** Missing / malformed / renamed file each yield an empty table plus a warning, never an exception (`27 passed`). One bad entry does not zero the table — three entries with missing, blank and wrong-prefix `source` were each dropped by name while the good entries survived *and priced*. Hot reload works without a restart (edit in place → `1.0` → `100.0`). **`import digiquant` does zero config I/O** — an audit-hook probe recorded 3 `open()` calls, all in `digiquant/__init__.py`, none in `config/`. Resolution is CWD-independent (`os.chdir('/private/tmp')` still resolves the repo-root table) and honours `DIGI_CONFIG_PATH` when set.

**`llm_auth.byok_model_example()` returns models each provider actually declares.** `xai → grok-4.3`, `anthropic → claude-sonnet-4-6`, `gemini → gemini/gemini-3.5-flash-lite`, `openrouter → openai/gpt-4o-mini`, `openai → gpt-4o-mini`, unknown → `None`. The xai mis-offer is fixed.

**`model_config.py` fails loudly and precisely.** Missing, malformed, empty-file and renamed policy each raise a distinct named error; empty `flagship_model_id_markers` and blank markers are both refused; resolution is `__file__`-relative. Refusing an empty marker set matters — without it, a typo would silently reclassify every model as non-flagship.

**Deploy wiring resolves in both build contexts.** `docker-compose.yml:99` uses `context: .` with `dockerfile: digigraph/Dockerfile`, and `.dockerignore` does not exclude `config/`. The runner's identical path form sits beside the already-shipping `byok-providers.json` COPY, and `wrangler.toml:43` resolves `../../Dockerfile.digiquant-runner` to the repo root.

**The vendored release copy is necessary, not cargo-culted.** `cmp config/model-policy.json infra/digichat-release/config/model-policy.json` → byte-identical. Both compose files mount `- ./config:/app/config:ro`, a whole-directory bind, so it **shadows rather than merges** — the vendored copy is required, and the corrected comments in all three files now say so.

**The digichat duplication is closed.** The two byte-identical copies in `loader.ts` and `client-projection.ts` were **unfalsifiable before this PR**: the pre-existing tests passed 45/45 with the sources reverted, because every test asserted literal values that both copies satisfied equally. That is why the new test is structural — it asserts no consumer names a model — rather than value-based. The export is a defensive copy, so mutating it cannot reach the imported JSON.

---

## Verification after the fixes (`23f723312`)

```
digichat   npx vitest run                        136 files / 1462 tests
digichat   npm run lint                          0 errors, 27 warnings (exact baseline)
digichat   npm run build                         exit 0
runner     exec_job_test.py                      ok ×4
python     pytest tests/dg tests/config tests/dq/research/test_pricing.py
           tests/scripts/test_provider_config_tables.py tests/provider_review/
                                                    1424 passed, 20 failed, 1 skipped
ruff       check + format --check                clean
docs       make doc-check                        OK (460 markdown files)
lockfile   git diff vs github/develop -- package-lock.json   empty
```

The 20 python failures are **unchanged from the pre-fix baseline** and environmental: this worktree has no `.venv`, so 19 are `ModuleNotFoundError: No module named 'mcp'` (`test_mcp_server.py`, `test_mcp_ssrf.py`) and 1 is the absent `langgraph-checkpoint-sqlite` checkpointer (`test_graph.py`). Diagnosed from the error text rather than a stash comparison, which is the stronger evidence; neither file is in the diff.

One `RUF100 Unused noqa directive (unused: E402)` at `apps/digiquant-runner/container/exec_job_test.py:13` is **pre-existing** — confirmed by `git stash -u` reproducing it on the develop state — and deliberately left alone.

---

## Not this PR — remaining scope

Four production files still carry real literals. All are PR2 (`generate`) work, per the plan on #5029:

| File | Literals |
|------|---------|
| `apps/digichat/src/hooks/use-byok-key.ts` | 17 |
| `digillm/src/digillm/client.py` | 16 — must be **generated**, not read; `digillm/AGENTS.md` forbids runtime file reads |
| `apps/digithings-web/lib/providerSettings.ts` | 14 |
| `packages/ui/…/skins/base/model.ts`, `scripts/validate_model_routing.py` | 1 each |

The AST guard added here covers only the three digigraph modules, so nothing prevents regression in these four — which is precisely what PR3's CI check closes. Decided up front and still true: test fixtures stay inline, and `packages/ui/…/skins/{grok,perplexity}.tsx` are exempt because a skin *is* a provider binding and `packages/ui` cannot read repo-root config at build time.

`scripts/check_architecture_drift.py:54-57,137-143` has the same class of gap on a hardcoded `_SKIP_DIR_PARTS`.