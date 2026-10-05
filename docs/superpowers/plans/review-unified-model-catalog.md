# Review — unified model catalog (#4994, PR #4997)

- **Subject:** `task/4994-unified-model-catalog` → `develop`, PR [#4997](https://github.com/digithings-ai/digithings/pull/4997), `git diff origin/develop...HEAD`
- **Reviewer:** in-session review on a fresh-context subagent (`subagent` session `ses_f00f0387dffeywLEFT5xBm1gH2`), prompted with `git diff origin/develop...HEAD` and an adversarial hunt list. The author session did not review its own work; every finding below was re-verified in the author session with a command before being accepted.
- **Spec / plan:** [`docs/superpowers/specs/2026-10-03-unified-model-catalog-design.md`](../specs/2026-10-03-unified-model-catalog-design.md) · [`docs/superpowers/plans/2026-10-03-unified-model-catalog.md`](2026-10-03-unified-model-catalog.md)
- **Date:** 2026-10-03
- **Initial verdict:** `request-changes`
- **Final verdict:** all 18 findings fixed and verified; **approve**

| Severity | Count | All fixed |
|----------|-------|-----------|
| major | 4 | F1, F2, F3, F4 |
| minor | 9 | F5–F13 |
| nit | 5 | F14–F18 |

The review's own summary of the shape of the diff: *"The generator, the drift guard, the CI wiring, and the security posture are genuinely solid; the problems are concentrated in the digichat consumption half and in doc honesty."*

---

## Major findings

### F1 · `(provider default)` disappeared for openai once a catalog list loaded
**Claim.** `apps/digichat/src/components/byok-cli-flow.tsx:312-318` — the catalog branch of the `modelOptions` IIFE returned `[...list.map((m) => m.id), CUSTOM_MODEL]` with no `""` sentinel, while the key-ping and presets branches both guard on `byokRequiresModel(provider)` before prepending `""`. openai is the only BYOK provider with `requiresModel: false` (`config/byok-providers.json:14`), so `(provider default)` — the one option that needs no model id — became unselectable.

**Verified.** Reviewer probe (its own reproduction):
```
catalog-loaded:   ["❯GPT-5.4"," GPT-4o"," GPT-4o mini"," custom…"]        ← no (provider default)
presets-fallback: ["❯(provider default)"," gpt-4o-mini"," gpt-4o"," o4-mini"," custom…"]
```
Existing tests missed it because their catch-all `fetch` mock returns a ping-shaped body to the models endpoint, so `asBuckets` returns `null` and the presets path runs.

**Fix.** The catalog branch now mirrors the others (`byokRequiresModel(provider) ? [...ids, CUSTOM_MODEL] : ["", ...ids, CUSTOM_MODEL]`), with a comment naming openai as the sole `requiresModel: false` provider. Added `keeps (provider default) for openai once the catalog list loads` to `byok-cli-flow.test.tsx`, which mocks a *distinct* catalog payload plus a `models`-less ping so the catalog branch is the only tiered list in play — red first (`getByText("(provider default)")` threw), then green. Suite 16 → 17 tests.

### F2 · The picker offered model ids the house cannot route
**Claim.** `byok-cli-flow.tsx:314-318` — the catalog branch offered every models.dev id for a provider. models.dev membership is not servability: `config/litellm.yaml:6` declares strict routing with no `fallbacks`, and `tests/config/test_litellm_house_models.py:151` `test_every_advertised_byok_preset_is_a_litellm_model_group` (#3605) exists precisely because a `fallbackModels` entry with no LiteLLM `model_name` cannot be served. For xai this was unconditional — xai has no key-step ping, so the catalog always owned its picker.

**Verified, and worse than reported.** Joining `config/model-catalog.json` against author-stripped `model_name` keys from all four `config/litellm*.yaml` (115 distinct routed keys):
```
provider     offered  routable
openai          53        5   ['gpt-4o','gpt-4o-mini','gpt-5.6-luna','gpt-5.6-sol','o4-mini']
anthropic       16        0   []
gemini          39        4   ['gemini-2.5-flash','gemini-2.5-pro','gemini-3.1-flash-lite','gemini-3.7-flash']
xai             13        1   ['grok-4.5']
openrouter     390       40
```
121 offered ids across the four non-openrouter providers, **10 routable**; anthropic **0 of 16**.

**Fix.** The generator now derives the BYOK-routable id set from a committed repo file (no network, so `--check` stays offline): `scripts/refresh_model_catalog.py::routable_byok_model_ids()` reads the four `config/litellm*.yaml`, keeps groups whose `litellm_params.configurable_clientside_auth_params` includes `api_key`, and attributes each group's `model_name` to the BYOK provider whose `config/byok-providers.json` `baseUrl` its `api_base` **regex** matches — the same regex-vs-host rule `test_litellm_house_models.py:165` already implements, so there is one rule in the repo, not two. Groups no provider host matches (the ollama-cloud house-proxy groups) are dropped. It renders as `MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS`, and `catalogEntriesFor` intersects with it. anthropic therefore legitimately falls back to `byokModelPresets`, which is today's behaviour. Three generator tests added (red `AttributeError` first) and two `model-catalog.test.ts` tests, one of which asserts the filter is non-vacuous (`catalogEntriesFor("gemini").length < catalog.models.google.length`) and one that no advertised preset is lost.

### F3 · Doc claimed six pins were replaced; they were exempted
**Claim.** `tests/config/test_model_catalog.py:122-128`, spec **D11**, spec line 32 ("prunes BYOK fallback ids"), spec line 45 and plan **Task 5** all describe replacing the six retired `fallbackModels` ids.

**Verified.** `git diff origin/develop...HEAD --stat | grep -c byok-providers` → **0**; `grep -c 20250514 config/byok-providers.json` → **3**. `docs/MODEL_CATALOG.md` and `ARCHITECTURE.md` were honest; the spec and plan were not.

**Fix.** The swap is a **routing** change, not a catalog edit, and needs a provider key to confirm the upstream slug (a guessed `litellm_params.model` is a 500 on every BYOK chat that picks it). Eight edits across three files now state the ids are **exempted pending a routing change**: the test docstring, spec line 32, the spec line 45 Deviations row, the D11 decision row (rewritten to "Record them as reasoned exemptions; do not replace them here."), the Spec-self-review row, the Components-touched row (`config/byok-providers.json` → "Unchanged, deliberately."), the exemptions data-model section (now the as-shipped shape, not the stale 2-entry example), and plan Task 5 (heading rewritten, steps 1–3 `[x]`, step 4 left open as the deferred work). Also fixed two stale plan lines: Task 2 step 3 no longer refers to "the two entries from the spec", and Task 4 step 5 now says the strict test is expected to be **red** on those six ids and that recording them is Task 5's job "not to weaken the assertion". The actual swap is tracked as [#5000](https://github.com/digithings-ai/digithings/issues/5000).

### F4 · `reasoning` / `attachment` typed `boolean`, generator emits `null`
**Claim.** `apps/digichat/src/lib/model-catalog.ts:34,36` declared `reasoning: boolean; attachment: boolean;`, but `scripts/refresh_model_catalog.py:225,230` emit `_optional_bool(...)` (→ `null`) and `assert_invariants:508` blesses the tri-state. Latent: upstream ships both as booleans on all 606 rows (only `structured_output` has 80 non-bool values), so the *next* refresh that sees an omitted flag would write a literal the generated module's own type rejects — a red `next build` while `--check` reported in-sync.

**Verified.** Reviewer patched one row to `null` and got `TS2322: Type 'null' is not assignable to type 'boolean'` from `tsc`. Author confirmed `refresh_model_catalog.py:225,230` are `_optional_bool(raw.get("reasoning"))` / `_optional_bool(raw.get("attachment"))`.

**Fix.** Both fields are `boolean | null`, with a comment recording why plain `boolean` is wrong. `tsc --noEmit` reports no `model-catalog` errors (the ~13 it prints are all pre-existing, in untouched files).

---

## Minor findings

| # | Claim | Fix |
|---|-------|-----|
| F5 | The `ci.yml` comment claimed `--check` catches a hand-edited artifact; it does not (reviewer hand-edited a price, re-rendered with `--offline`, `--check` exited 0). | Rewrote the comment: the guard "catches a stale artifact, NOT a hand-edited one — an offline guard cannot tell a fabricated price from a real one; that is what the review of the refresh PR is for." |
| F6 | `test_refresh_model_catalog.py:334-340` asserted `render(c) == render(c)` — a tautology that would still pass if `render_typescript_module` read a clock. | Now renders `_load_committed_catalog()` **twice** (two distinct parses from disk) and compares the two renders. |
| F7 | `route.test.ts:47-67` passed with `bucketCatalogEntries: () => ({all: [], …})`, because `Array.isArray([])` is true. | Loop asserts `body.all.length > 0`; added two spot-checks — xai's `all` equals exactly `["grok-4.5"]`, and **anthropic's equals `[]`** with a comment recording that this is the deliberate empty case, so a future models.dev row or new litellm route shows up as the count moving off zero. The tightened test failed red on anthropic, which is why the loop list was narrowed and anthropic got its own assertion. |
| F10 | Non-finite upstream numbers escaped: `_positive_int(inf)` raised `OverflowError`, `_positive_int(nan)` raised `ValueError` (both outside the documented `CatalogRefreshError` contract), and `_cost_usd_per_million({'input': inf})` reached `json.dumps` as a bare `Infinity` token — neither valid JSON nor a valid TS literal, and `assert_invariants` accepted it. JSON reaches inf/nan via `1e999`. | `math.isfinite` guards in both helpers (with docstrings), plus `allow_nan=False` on both `json.dumps` call sites. The TS side already had the guard (`promptPricePerMillion`, `openrouter-catalog.ts:47-48`). |
| F11 | The forbidden-key invariant covered neither `_meta` nor non-exact key names; injecting `_meta.url`, `_meta.api_base`, `entry.api_base`, `entry.base_url` produced only the generic key-set message, and `_meta.source_url` is itself a URL field. | `FORBIDDEN_KEY_SUBSTRINGS` + `FORBIDDEN_KEY_EXEMPTIONS = {"source_url"}` (provenance, never requested at runtime), a `_forbidden_keys()` helper matching case-insensitive substrings, and a `_meta` walk in `assert_invariants`. |
| F12 | `openrouter-catalog.ts:117` is the only production `tierFor(` call and passes one argument, so `catalogOpenWeights` is dead in production — the "union of three signals" is two in practice. | Kept the parameter (it is what stops the generator and this module growing separate copies of the rule) and rewrote the `isOpenSource` doc comment with an explicit scoping paragraph naming `bucketOpenRouterModels` as the sole call site, stating that catalog-sourced rows get their tier precomputed by the generator, and that "nothing passes `true` yet". |
| F13 | `docs/MODEL_CATALOG.md:134` said 38 of 149 litellm routes miss. | Corrected to the reviewer's own count: 48 missing route entries, 33 of the 88 distinct ids involved. |

## Nit findings

| # | Claim | Fix |
|---|-------|-----|
| F14 | `docs/MODEL_CATALOG.md:11` "It replaces a dozen hand-maintained lists" is false — nothing is generated from the catalog. | Now: "It **validates** a dozen hand-maintained lists … against one normalized snapshot — it does not generate or replace them." |
| F15 | `route.ts:115-116` cited "the generator's own entry cap"; no such cap exists and the spec says `all` is uncapped. | Comment replaced with the real reason: the catalog branch "is a module import rather than an upstream read — none of the response-size guards below apply." |
| F16 | Plan Task 4 step 3 / spec D12 promised a `_BYOK_CATALOG_API_BASES` ↔ catalog provider-set assertion; never written. | Added `test_every_base_url_digillm_trusts_has_rows_in_the_model_catalog()` to `tests/config/test_litellm_house_models.py`, directly after the existing digillm test, so the constant has exactly one pin site. The catalog carries no URL by design (spec D1), which is exactly why the connection has to be made by provider identity rather than by comparing URLs. `test_litellm_house_models.py` 15 → 16 tests. |
| F17 | `ruff format --check` would reformat all three new Python files. | Scoped `python3 -m ruff format` on all four changed files; `ruff format --check` now reports "4 files already formatted". The only `ruff check --fix` applied was an extraneous `f` prefix. |
| F18 | The exemptions `provider` field was never read, so a mis-scoped exemption excused the same id on another provider; and the stale-test rule differed from the generator's. | `_resolved_ids(catalog, *, provider=None)` is now provider-scoped and both `_exemption_violations` and the config test match on `id` **and** provider; a `provider` field is required. One subtlety handled explicitly: `byok_provider_to_catalog_provider` is the wrong mapper for this file because it also covers pins with no catalogued row at all (local ollama, `config/model_modes.local.yaml` → `ollama/deepseek-r1:14b`), so an unmapped provider that is not a catalog key is skipped rather than reported. Two new generator tests (55 total). Fixing F18 also surfaced two real bugs: `FORBIDDEN_KEY_SUBSTRINGS` contained `"token"`, which substring-matched `max_output_tokens` and failed every entry, and three test fixtures lacked the now-required `provider`. |

---

## What the reviewer independently verified as correct

Recorded so the next reader does not re-derive it.

- `--check` is genuinely network-free — socket primitives stubbed to raise still exits 0 with no network primitive invoked.
- The committed artifacts reproduce exactly from a live models.dev fetch (5,716,245 bytes → 606 rows, **zero** field-level diffs, `fetched_at 2026-10-02T23:38:18+00:00`).
- The TS render is byte-deterministic across processes, single trailing newline, no CRLF, `tsc --noEmit` clean in all new files.
- The drift guard catches artifact-to-artifact drift, and `ci.yml ⇄ ci_paths.yaml` are in sync so a digichat-only edit fires `--check`.
- **Both** new Python test files are collected by the `-m "unit or baseline"` lane (1134 passed for `tests/scripts/ tests/config/`, the new two contributing 57) — the unmarked-file trap found earlier in this task was not repeated.
- Security posture clean: the only URL in either artifact is `_meta.source_url`; zero hits for `api_key` / `sk-` / `AIza` / `env` / `npm` / `base_url`; the catalog branch takes no URL and does no fetch; `provider` is a closed 5-id allowlist; the one live fetch uses the hardcoded `OPENROUTER_API_BASE`.
- `model-catalog.ts` is **not reachable from any `"use client"` module** — the only importers are `route.ts` and its own test; `byok-cli-flow.tsx` re-declares the response shape structurally, so the ~330 KB stays server-side.
- The key-scoped list really does outrank the catalog; tier derivation matches `tierFor()` exactly (both floors are `3`, free requires both costs present and zero, a null cost yields neither free nor flagship; committed distribution 81 flagship / 240 opensource / 25 free / 260 null); the empty-tier → presets fallback works and its test is meaningful; `write_artifacts` refuses an empty catalog.
- Full digichat suite green, eslint clean on all four changed TS files, `tests/dg/test_llm_auth.py` 295 passed with `TestByokCatalogVendoredCopy` holding, provider-change state resets complete and `modelsFetchFailedFor` correctly keyed.

## Post-fix verification

```
pytest tests/scripts/test_refresh_model_catalog.py tests/config/ tests/dg/test_llm_auth.py -q → 375 passed
python3 scripts/refresh_model_catalog.py --check                                      → OK, artifacts in sync
python3 scripts/generate_ci_path_filters.py --check                                    → ci path filters OK
ruff check / ruff format --check (4 changed Python files)                             → clean / already formatted
apps/digichat: npx vitest run                                                          → 132 files, 1430 tests
apps/digichat: npm run lint                                                            → 0 errors (27 pre-existing warnings)
apps/digichat: npm run build                                                           → succeeded
make doc-check                                                                         → OK, 457 markdown files
```

One caveat on `make doc-check`: run it **before** `npm run build`, or `rm -rf apps/digichat/.next` afterwards. `scripts/check_doc_links.py` has no gitignore skip logic, so it walks the gitignored `apps/digichat/.next/standalone/` tree and reports three broken links inside a copy of `AGENTS.md`. Pre-existing, unrelated to this change, and not fixed here (CI's `doc-links` job runs in a clean tree). Worth its own small issue.