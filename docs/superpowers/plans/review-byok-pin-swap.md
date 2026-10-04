# Review — BYOK pin swap (#5000)

- **Subject:** `task/5000-byok-pin-swap` → `develop`, PR [#5020](https://github.com/digithings-ai/digithings/pull/5020), `git diff refs/remotes/github/develop...HEAD`
- **Reviewer:** in-session review on a fresh-context subagent (`ses_efcaddaadffeOic4Efb5miE1E6`). The author session did not review its own work: every finding below was re-verified with a command in the author session before acting, and one was narrowed on that basis.
- **Spec / plan:** [spec for the catalog this completes](../specs/2026-10-03-unified-model-catalog-design.md) · [plan](../plans/2026-10-03-unified-model-catalog.md) · [the review that produced the exemptions this PR clears](./review-unified-model-catalog.md)
- **Date:** 2026-10-03
- **Verdict:** `request-changes` → **approve** (all 10 findings addressed)

## Severity counts

| Severity | Count | Addressed |
|----------|-------|-----------|
| blocker  | 0 | — |
| major    | 3 | 3 |
| minor    | 2 | 2 |
| nit      | 5 | 4 (F8 explicitly required no change) |

The reviewer's own summary: *"the six claimed swaps are all verified live and the config is internally consistent, but the diff leaves three dead/unroutable ids in production code (one of which this PR created), shows users wrong model names on the public site, and the PR description understates its own scope."* No blockers — *"Nothing here makes the approach wrong."*

## Majors

### F1 · deleting the `gemini/gemini-2.5-flash` group broke the default Gemini selection

`config/litellm.yaml` (group at develop `:568`), `apps/digichat/src/app/api/byok/test/route.ts`, `apps/digichat/src/components/byok-cli-flow.tsx`.

`gemini/gemini-2.5-flash` was not one of the six catalog-exempted ids and is alive upstream, but it *was* routed. Google returns `gemini-2.5-flash` first in its model list, `testGeminiKey` returns `models[0]?.id`, and the picker highlights index 0 — so the default-highlighted Gemini option became an unroutable id, which digraph refuses on activation.

Verified in the author session before acting:

```
grep -n 'model_name: gemini/gemini-2\.5-flash$' config/litellm*.yaml                     -> NOT FOUND
git show refs/remotes/github/develop:config/litellm.yaml | grep -n 'model_name: gemini/gemini-2\.5-flash'
                                                                                        -> 568
```

**Fix — filter the key-scoped list server-side, in `byok/test/route.ts`.** Two module-scope helpers (`routableIds(provider)`, `routableOnly(provider, models)`) intersect each provider's `/models` response with `MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS`, and `testXaiKey`'s default `model` now comes from the same filtered set. The fix went here rather than in `byok-cli-flow.tsx` because that file is `"use client"` and must not import the 335 KB generated module, and rather than by restoring the one group because the unfiltered ping list was already leaky (Google returns 61 ids, most unrouted) — the intersection closes the class, not the instance. The reviewer credited this as the pre-existing part: *"it removed the one rung that worked."*

### F2 · `digigraph/src/digigraph/server.py:187` advertised a newly-unroutable id

The hardcoded 400 example `(e.g. openai/gpt-4o-mini, gemini/gemini-2.5-flash, claude-sonnet-4-6)` — one example in it was dead before this PR and a different one after.

**Fix:** `gemini/gemini-2.5-flash` → `gemini/gemini-3.5-flash-lite`. All three examples are now routable.

### F3 · `apps/digithings-web/lib/providerSettings.ts` — ids updated, labels not

The literal id sweep changed the ids but left the seven labels, and `apps/digithings-web/components/ProviderSettings.tsx:222` renders `{m.label}` — so a user read "Gemini 2.5 Pro" and sent `gemini/gemini-3.7-flash`. The reviewer invoked the repo's own failure mode (PR #1891, "two false public claims to production"). Untested: `providerSettings.test.ts` asserted ids only.

**Fix:** all seven labels corrected; `apps/digithings-web/components/ProviderSettings.contract.test.tsx:120` updated from `"Gemini 2.0 Flash"` to `"Gemini 3.5 Flash Lite"` when it failed against the corrected label.

## Minors

| # | Finding | Resolution |
|---|---------|------------|
| F4 | `byok/test/route.ts:196` still fell back to `claude-3-haiku-20240307` — same defect class as the two this PR fixed at `:258` and `:276`, and absent from both models.dev and the LiteLLM keyspace | `?? "claude-haiku-4-5"` |
| F5 | Three docs/tests asserted the opposite of what shipped: the load-bearing test's docstring still said the six ids were "exempted, not replaced"; `docs/MODEL_CATALOG.md` still said the file "carries six entries" and concluded "None was applied here"; `docs/LLM_PROVIDERS.md` cited a `model_name` that no longer exists and named `grok-4-3` as the current tier, as did `docs/providers/snapshots/xai.yaml` | All rewritten. `docs/MODEL_CATALOG.md` now keeps the durable #3605 lesson ("replacing a stale pin is a **routing** change, not a catalog edit") and its table is now "Retired pin \| Why it was retired \| Replaced with", plus an explicit paragraph on the two successors a catalog-only lookup gets wrong — `claude-sonnet-4-5` (deprecated 2026-11-30) and `gemini-2.5-flash-lite` (404 for new keys). Its conclusion is the lesson this whole exercise produced: **existence in the catalog is not servability for a new key.** |

## Nits

| # | Finding | Resolution |
|---|---------|------------|
| F6 | A comment this PR added attributed Google's "no longer available to new users" to `gemini-2.0-flash`; that phrasing belongs to `gemini-2.5-flash-lite` (`gemini-2.0-flash` says "is no longer available.") | Attribution corrected in the `testGeminiKey` comment |
| F7 | `model-catalog.test.ts:138-157`: a stale comment (claimed anthropic's 3 routable ids were absent from the catalog — they are now served) and a tautological `offered.has(id) \|\| routable.has(id)` that collapses to `routable.has(id)` because `offered` is by construction a subset | Comment rewritten; `presets` gained anthropic + gemini; the redundant disjunct removed |
| F8 | The two exemption tests are tautologies now the file is empty | **No change** — the reviewer explicitly agreed these are guards for future entries, and `test_committed_catalog_satisfies_every_data_model_invariant` still does real work |
| F9 | `refresh_model_catalog.py` used the retired `grok-4-3` as a running example | Replaced with a description of the bug instead of a stale id |
| F10 | The PR description said six swaps; the diff has **eight** | Corrected in the PR body — see below |

### F10 · the scope was understated

The two undeclared swaps were `gemini/gemini-2.5-flash` → `gemini/gemini-3.5-flash` and `gemini/gemini-2.5-pro` → `gemini/gemini-3.7-flash`. Neither was catalog-exempted — both were *in* models.dev — so "the catalog proved six of them retired" did not cover them. They were found by live verification: `gemini-2.5-pro` returns 404 on a completion while Google's own `ListModels` still lists it, which is exactly the existence-is-not-servability trap the first six pins also sat on. The PR body now states eight swaps, and says which six the catalog proved retired and which two only a live call did.

## What the reviewer independently verified as correct

Not re-litigated; recorded so the next reader knows it was checked rather than assumed.

- **Live verification of all six claimed new pins** against the providers' own APIs: xAI's `GET /v1/models` carries `grok-4.3` and not `grok-4-3`; Google's three `gemini-3.x` ids answer real completions 200; OpenRouter carries `google/gemini-2.5-flash` and not `2.0`. All six also resolve in models.dev.
- **Anthropic slugs** cross-confirmed by models.dev **and** LiteLLM's keyspace.
- **Config consistency**: every one of the 15 `fallbackModels` ids resolves to a `model_name` with a matching `litellm_params.model`; all five YAML anchors defined exactly once; all three `api_base` regexes still match their `byok-providers.json` `baseUrl`; the generator's own intersection agrees. The two `byok-providers.json` copies are byte-identical (`shasum -a 256 91f848b6…`).
- **Regeneration honest**: `--check` passes and `--offline` reproduces a byte-identical file. `MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS` is derived, not declared — the reviewer recomputed it independently and agreed.
- **Every new pin survives** `byok_routable_model()` and `byok_default_model_refusal` (all 15 correctly provider-prefixed, `routes_elsewhere=False`, the `gemini/` fixpoint-strip idempotent), and the refusal picks up each provider's new first-fallback.
- `byokModelPresets` parity holds — exact ordered equality against `config/byok-providers.json`, across all three hand-mirrored copies.
- 617 Python tests pass across the config/dg/digillm suites, including `test_every_advertised_byok_preset_is_a_litellm_model_group` (#3605).
- Remaining old-id occurrences are legitimate parser/predicate fixtures (`models/gemini-2.0-flash` prefix-strip payloads in `byok/test/route.test.ts`, the `it.each` activation fixture, `chat-panel.test.tsx`, `digillm/tests/test_byok_isolation.py:134`, ~20 foreign-prefix cases in `tests/dg/test_llm_auth.py`).
- The anthropic tier assertion in `byok/models/route.test.ts` was **upgraded** from `toEqual([])` to an exact 3-element set — strictly stronger than before.

The reviewer also declared its own tooling limit: it could not run `byok-cli-flow.test.tsx` cleanly (no `node_modules` in its environment, jest-dom matchers unregistered), so it did **not** independently confirm that file's changed assertions. The author session did: `npm ci` in the worktree, then the full 135-file / 1447-test suite green.

## Post-fix verification

```
pytest tests/config/ tests/scripts/test_refresh_model_catalog.py tests/dg/test_llm_auth.py -q
  -> 375 passed
python3 scripts/refresh_model_catalog.py --check        -> OK — committed artifacts are in sync
python3 -m ruff check <5 touched python files>           -> All checks passed!
apps/digichat        npx vitest run                      -> 135 files / 1447 tests passed
apps/digichat        npm run lint                        -> 0 errors, 27 pre-existing warnings
apps/digithings-web  npx vitest run                      -> 29 files / 194 tests passed
rm -rf apps/digichat/.next && make doc-check             -> OK (458 markdown files)
```

Two tests failed on the first post-fix run, both because they pinned pre-#5000 behaviour and both fixed in the tests rather than in production code — the correct direction:

- `byok/test/route.test.ts:361` asserted a Gemini `models[].name` list survives intact; the F1 routable filter now drops unroutable ids, so it was retitled to *"returns the routable subset"* and its fixture made mixed, which pins the response shape, the `models/` prefix-strip, **and** the filter in one assertion.
- `ProviderSettings.contract.test.tsx:120` asserted the stale `"Gemini 2.0 Flash"` label — i.e. it failed *because* F3's fix landed.

## Follow-up noted, not filed

`docs/LLM_PROVIDERS.md:119` asserts `toContain("Claude Sonnet 4")`, which still passes only because `"Claude Sonnet 4.6"` contains it as a substring. A pre-existing weak assertion in a file outside this sweep's reach; left alone rather than widened here.