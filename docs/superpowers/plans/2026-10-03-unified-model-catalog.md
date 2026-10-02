# Plan — unified model catalog (#4994)

- **Issue:** [#4994](https://github.com/digithings-ai/digithings/issues/4994)
- **Spec:** [`docs/superpowers/specs/2026-10-03-unified-model-catalog-design.md`](../specs/2026-10-03-unified-model-catalog-design.md) — read it first; the decision ids (D1–D12) are referenced from every task below.
- **Branch:** `task/4994-unified-model-catalog` → `develop` (see the spec's Rollout note for why not `module/digichat`)
- **Date:** 2026-10-03

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or `test-driven-development` if running solo). Write the failing test first in every task marked TDD; do not batch test-writing to the end.

---

## Global Constraints

1. **Never hand-edit a generated file.** `config/model-catalog.json` and `apps/digichat/src/lib/model-catalog.generated.ts` are written by `scripts/refresh_model_catalog.py`. `config/model-catalog-exemptions.json` **is** hand-maintained.
2. **`--check` is network-free.** It re-renders the TS module from the committed JSON and asserts invariants. It must never call out. A test pins this (Task 3, step 6).
3. **Both new Python test files carry `pytestmark = pytest.mark.unit`.** `pytest.ini` has no auto-marking and CI runs `-m "unit or baseline"`, so an unmarked file is silently deselected.
4. **No new runtime dependency.** No npm package, no pip package, not even `@opencode-ai/models`. The catalog arrives as generated code.
5. **Unknown is never false.** A missing `cost`, `structured_output`, or a `limit.context` of `0` normalizes to `null`, never to `false`/`0`. Tier derivation degrades to `null` (lands in `all` only) rather than guessing.
6. **`digillm` stays stdlib + `openai` importable.** No file reads at runtime, no `fastapi`, no new hard deps. Catalog consumption there is test-only.
7. **`byokModelPresets()` does not change.** `use-byok-key.catalog-parity.test.ts:79-84` asserts exact ordered equality against `fallbackModels`; the catalog is an advisory overlay, not the preset source.
8. **The live-tier gate stays openrouter-only.** `byok-cli-flow.tsx:237` keeps `provider === "openrouter"`. Catalog tiers are priority 3 in the `modelOptions` IIFE, never above the key-scoped list.
9. **`ruff` is bounded to its current major.** Do not bump it, and do not run a repo-wide `ruff format .` (it reformats Markdown — #1705). Scope every lint call.
10. **Digi names stay lowercase** in prose, comments, commit messages, and PR text.

---

# Phase 1 — catalog core

Phase 1 is self-contained: generator, artifacts, tests, CI, and the config fix. It has no dependency on Phase 2 and can ship alone.

## Task 1 — Normalizer (TDD)

**Files**
- Create: `scripts/refresh_model_catalog.py`
- Create: `tests/scripts/test_refresh_model_catalog.py`

**Interfaces**
- `normalize_catalog(payload: dict) -> dict` — pure; a models.dev `catalog.json` body in, a normalized catalog dict out.
- `CATALOG_PROVIDERS: tuple[str, ...]` — the ten provider keys (D6), sorted.
- `FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M = 3.0`
- `TIER_ORDER = ("free", "flagship", "opensource")`

**Steps**

- [ ] **Step 1:** Create `tests/scripts/test_refresh_model_catalog.py` with `pytestmark = pytest.mark.unit` and a minimal fixture builder:

  ```python
  import pytest

  pytestmark = pytest.mark.unit

  from scripts.refresh_model_catalog import (  # noqa: E402
      FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M,
      normalize_catalog,
  )


  def _models_dev_payload() -> dict:
      """Minimal models.dev-shaped payload: providers -> {models: {id: {...}}}."""
      return {
          "providers": {
              "openai": {
                  "id": "openai",
                  "models": {
                      "gpt-5.4": {
                          "id": "gpt-5.4",
                          "name": "GPT-5.4",
                          "cost": {"input": 2.5, "output": 15},
                          "limit": {"context": 1050000, "output": 128000},
                          "modalities": {"input": ["text", "image"], "output": ["text"]},
                          "tool_call": True,
                          "reasoning": True,
                          "attachment": True,
                          "open_weights": False,
                      },
                  },
              }
          }
      }
  ```

- [ ] **Step 2:** Add a failing test for the happy path and run it to confirm red:

  ```python
  def test_normalize_keeps_a_fully_populated_model():
      out = normalize_catalog(_models_dev_payload())
      entry = out["models"]["openai"][0]
      assert entry["id"] == "gpt-5.4"
      assert entry["cost_input_usd_per_million"] == 2.5
      assert entry["cost_output_usd_per_million"] == 15.0
      assert entry["context_window"] == 1050000
      assert entry["max_output_tokens"] == 128000
      assert entry["vision"] is True
      assert entry["structured_output"] is None  # upstream said nothing
      assert entry["tier"] == "flagship"
  ```

- [ ] **Step 3:** Write the constants and `normalize_catalog`. Per-model rules, each one a named helper so a failing test points at a rule rather than a dict comprehension:

  ```python
  CATALOG_PROVIDERS: tuple[str, ...] = (
      "anthropic", "deepseek", "fireworks-ai", "google", "groq",
      "ollama-cloud", "openai", "openrouter", "togetherai", "xai",
  )

  TIER_ORDER = ("free", "flagship", "opensource")
  FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M = 3.0
  SCHEMA_VERSION = 1
  MODELS_DEV_CATALOG_URL = "https://models.dev/catalog.json"

  # Provider entries are keyed by id under `providers`; models.dev omits whole
  # blocks for models it does not know. Everything absent below is `null`,
  # never a falsy stand-in — "upstream did not say" must not read as "no".
  def _positive_int(value: object) -> int | None:
      if not isinstance(value, (int, float)) or isinstance(value, bool):
          return None
      # models.dev ships limit.context == 0 for image models (openai
      # chatgpt-image-latest), which is "unknown", not "a zero-length window".
      return int(value) if int(value) > 0 else None

  def _cost_usd_per_million(cost: object, key: str) -> float | None:
      if not isinstance(cost, dict):
          return None
      raw = cost.get(key)
      if not isinstance(raw, (int, float)) or isinstance(raw, bool):
          return None
      return float(raw) if raw >= 0 else None

  def _optional_bool(raw: object) -> bool | None:
      return raw if isinstance(raw, bool) else None

  def _modalities(modalities: object, side: str) -> list[str]:
      if not isinstance(modalities, dict):
          return []
      values = modalities.get(side)
      return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []

  def derive_tier(cost_in: float | None, cost_out: float | None, open_weights: bool) -> str | None:
      """First match wins, in the same order as tierFor() (openrouter-catalog.ts:70-75).

      A missing cost can never yield free or flagship: models.dev omits `cost`
      on 8 of xai's 13 rows and 10 of groq's 16, so a `None`-as-0 reading would
      mis-bucket a third of two providers' models as free.
      """
      if cost_in is not None and cost_out is not None and cost_in == 0 and cost_out == 0:
          return "free"
      if cost_in is not None and cost_in >= FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M:
          return "flagship"
      if open_weights:
          return "opensource"
      return None
  ```

- [ ] **Step 4:** Add failing tests for each degradation rule, then implement them:

  ```python
  def test_absent_cost_normalizes_to_null_not_zero():
      payload = _models_dev_payload()
      del payload["providers"]["openai"]["models"]["gpt-5.4"]["cost"]
      entry = normalize_catalog(payload)["models"]["openai"][0]
      assert entry["cost_input_usd_per_million"] is None
      assert entry["tier"] is None          # never "free", never "flagship"


  def test_zero_context_window_normalizes_to_null():
      payload = _models_dev_payload()
      payload["providers"]["openai"]["models"]["gpt-5.4"]["limit"]["context"] = 0
      assert normalize_catalog(payload)["models"]["openai"][0]["context_window"] is None


  def test_absent_structured_output_is_null_not_false():
      # 8 of openai's 53 rows omit it. Reading absence as False would hide
      # tool-using models from any capability filter.
      entry = normalize_catalog(_models_dev_payload())["models"]["openai"][0]
      assert entry["structured_output"] is None


  def test_free_requires_both_costs_present_and_zero():
      assert derive_tier(0.0, 0.0, False) == "free"
      assert derive_tier(0.0, None, False) is None
      assert derive_tier(None, 0.0, False) is None


  def test_flagship_uses_the_carried_over_price_floor():
      assert derive_tier(FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M, 5.0, False) == "flagship"
      assert derive_tier(FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M - 0.01, 5.0, False) is None


  def test_tier_order_is_free_then_flagship_then_opensource():
      assert derive_tier(0.0, 0.0, True) == "free"
      assert derive_tier(9.0, 9.0, True) == "flagship"
      assert derive_tier(0.5, 0.5, True) == "opensource"
  ```

- [ ] **Step 5:** Assert in `normalize_catalog` that a provider present upstream but absent from `CATALOG_PROVIDERS` is skipped, that entries are sorted by `id` ascending, that no `url`/`env`/`api`/`npm` key survives, and that `_meta.providers == list(CATALOG_PROVIDERS)`. Add a test for the sort and one that asserts the emitted keys are exactly the twelve in the spec's data model.

- [ ] **Step 6:** `ruff check scripts/refresh_model_catalog.py tests/scripts/test_refresh_model_catalog.py` → clean, and `pytest tests/scripts/test_refresh_model_catalog.py -q` → green.

---

## Task 2 — Fetcher, writer, and the committed artifacts

**Files**
- Modify: `scripts/refresh_model_catalog.py`
- Create: `config/model-catalog.json` (generated — never hand-edited)
- Create: `config/model-catalog-exemptions.json` (hand-maintained)

**Interfaces**
- `fetch_catalog(timeout: float = 30.0) -> dict` — `httpx.get(MODELS_DEV_CATALOG_URL)`, `raise_for_status`, return `.json()`.
- `render_typescript_module(catalog: dict) -> str` — the committed `.generated.ts` body, deterministic.
- `write_artifacts(catalog: dict, *, ts_path: Path, json_path: Path) -> None`
- `main(argv: list[str] | None = None) -> int` — flags: none = fetch + write both; `--offline` = read the committed JSON, re-render the TS module, write only that; `--check` = [Task 3](#task-3--check-mode-and-drift-invariants).

**Steps**

- [ ] **Step 1:** Add `fetch_catalog`. Mirror `scripts/refresh_model_routes.py:82-93`'s `_get_json` shape (httpx, explicit timeout, `raise_for_status`) so the two scripts read alike.

- [ ] **Step 2:** Add `render_typescript_module`. It emits, in order: the "do not edit" header, `import type { ModelCatalogEntry } from "./model-catalog";`, `MODEL_CATALOG_SCHEMA_VERSION`, `MODEL_CATALOG_PROVIDERS`, `MODEL_CATALOG_BY_PROVIDER`, `MODEL_CATALOG_META`. Use `json.dumps(value, indent=2, sort_keys=False)` for the record bodies so the output is byte-stable across runs — **no timestamps inside the TS module** except the `fetchedAt` string taken verbatim from `_meta`, which changes only when the catalog is actually refreshed.

- [ ] **Step 3:** Create `config/model-catalog-exemptions.json` with the two entries from the spec. Anything upstream does not need must be removable, and every entry needs a non-empty `reason` — both are asserted in Task 4.

- [ ] **Step 4:** Add a failing test that `write_artifacts` refuses to write when normalization produced zero models (a models.dev schema change must not commit an empty catalog that reads as "these providers have no models"), then implement:

  ```python
  def write_artifacts(catalog: dict, *, ts_path: Path, json_path: Path) -> None:
      models = catalog.get("models", {})
      if not any(models.values()):
          msg = (
              "normalized catalog is empty — models.dev's shape likely changed. "
              "Refusing to write; no artifact was modified."
          )
          raise CatalogRefreshError(msg)
      ...
  ```

- [ ] **Step 5:** Run the refresh against the live endpoint. Use a generous timeout — the body is ~5.7 MB:

  ```bash
  python3 scripts/refresh_model_catalog.py
  ```

- [ ] **Step 6:** Verify the result and commit both artifacts:

  ```bash
  python3 -c "
  import json
  c = json.load(open('config/model-catalog.json'))
  print(c['_meta'])
  for p, rows in c['models'].items():
      print(f'{p:14} {len(rows):4} models')
  print('total', sum(len(v) for v in c['models'].values()))
  "
  wc -c config/model-catalog.json apps/digichat/src/lib/model-catalog.generated.ts
  ```

  Expect `_meta.providers` to equal `["anthropic","deepseek","fireworks-ai","google","groq","ollama-cloud","openai","openrouter","togetherai","xai"]` and the total to be ~606. If the total is wildly off, the provider keys moved — stop and re-probe upstream rather than widening the list to compensate.

---

## Task 3 — `--check` mode and drift invariants

**Files**
- Modify: `scripts/refresh_model_catalog.py`
- Modify: `tests/scripts/test_refresh_model_catalog.py`

**Steps**

- [ ] **Step 1:** Failing test first — `--check` on a clean tree exits `0`:

  ```python
  def test_check_passes_on_a_clean_tree(capsys):
      assert main(["--check"]) == 0
  ```

- [ ] **Step 2:** Implement the eight data-model invariants from the spec as a single `assert_invariants(catalog, *, exemptions_path) -> list[str]` returning a list of human-readable violations (empty list = clean). Cover: `schema_version == 1`; `_meta.providers` sorted and equal to `list(CATALOG_PROVIDERS)`; every `models` key is in `_meta.providers`; ids unique within a provider; `context_window` positive-or-null; costs non-negative-or-null; `structured_output` tri-state; `tier` in `TIER_ORDER + (None,)`; entries sorted by `id`; no `url`/`env`/`api`/`npm` key anywhere. Plus: every exemption carries a non-empty `reason`, and every exemption's id is one that genuinely does **not** resolve.

- [ ] **Step 3:** Implement `--check` as: parse the committed JSON → `assert_invariants` → re-render the TS module and compare **byte-for-byte** → on any violation, print each one and return `1` with a `run \`python3 scripts/refresh_model_catalog.py --offline\`` remedy line. `--check` must not import or call `fetch_catalog`.

- [ ] **Step 4:** Failing tests for each drift mode, then implement:

  ```python
  def test_check_fails_when_the_ts_module_is_stale(tmp_path, monkeypatch):
      # ... write a valid catalog JSON, then write a TS module missing one provider
      assert run_check(tmp_path) == 1


  def test_check_fails_on_a_mutated_schema_version(tmp_path):
      # ... "schema_version": 99
      assert run_check(tmp_path) == 1


  def test_check_fails_when_an_exemption_is_no_longer_needed(tmp_path):
      # ... exemption for "gpt-5.4", which the catalog does resolve
      assert run_check(tmp_path) == 1
  ```

- [ ] **Step 5:** `--offline` — read the committed JSON, re-render, write only the TS module, exit `0`. Add a test asserting `--offline` succeeds when the JSON is valid and the TS module is stale.

- [ ] **Step 6:** Pin the network-free property:

  ```python
  def test_check_and_offline_never_call_the_network(monkeypatch):
      import scripts.refresh_model_catalog as mod

      def _boom(*_a, **_kw):
          raise AssertionError("--check/--offline must not perform network I/O")

      monkeypatch.setattr(mod, "fetch_catalog", _boom)
      assert main(["--check"]) == 0
      assert main(["--offline"]) == 0
  ```

- [ ] **Step 7:** `pytest tests/scripts/test_refresh_model_catalog.py -q` → green; `python3 scripts/refresh_model_catalog.py --check` → exit 0 with a one-line OK.

---

## Task 4 — The coverage test

**Files**
- Create: `tests/config/test_model_catalog.py`

**Interfaces**
- `strip_author(model_id: str) -> str` — drop everything up to and including the first `/`. `gemini/gemini-2.5-flash` → `gemini-2.5-flash`; `gpt-4o` → `gpt-4o` (no slash, unchanged).
- `byok_provider_to_catalog_provider(byok_id: str) -> str | None` — D7's map, shared with the generator by importing it, not by re-declaring it.

**Steps**

- [ ] **Step 1:** Create the file with `pytestmark = pytest.mark.unit`, a `load_catalog()` helper reading `config/model-catalog.json` from the repo root (resolve the path from `__file__`, not `cwd`).

- [ ] **Step 2:** Add the strict BYOK-fallback coverage test (D8):

  ```python
  EXEMPT_IDS = {e["id"] for e in load_exemptions()}


  def test_every_byok_fallback_model_exists_in_the_catalog():
      unresolved = []
      for entry in load_byok_providers():
          provider = byok_provider_to_catalog_provider(entry["id"])
          assert provider is not None, f"no catalog provider mapped for BYOK {entry['id']}"
          known = {strip_author(m["id"]) for m in load_catalog()["models"][provider]}
          for model in entry.get("fallbackModels", []):
              if model in EXEMPT_IDS:
                  continue
              if strip_author(model) not in known:
                  unresolved.append(f"{entry['id']}: {model} (catalog provider {provider})")
      assert not unresolved, "pinned BYOK models the catalog does not carry:\n" + "\n".join(unresolved)
  ```

- [ ] **Step 3:** Add the remaining strict tests: every BYOK provider maps to a present catalog provider; every exemption still has a non-empty `reason`; every exemption is still needed; `_BYOK_CATALOG_API_BASES`'s provider set equals the catalog's provider set (extend `tests/config/test_litellm_house_models.py:208-211` rather than duplicating it); the eight data-model invariants.

- [ ] **Step 4:** Add the **advisory** litellm-route test — `pytest.warns`, never a failure:

  ```python
  def test_litellm_routes_resolve_advisory(recwarn):
      """models.dev is a curated DB, not a live route registry.

      Its openrouter slice is 390 rows and does not carry our :free slugs
      consistently, and its ollama-cloud ids carry no :cloud tag. 38 of the 149
      routes are therefore expected to miss; that is a known blind spot, not a
      regression, so this warns rather than fails.
      """
      ...  # strip :free/:online, then author-strip, then compare
      assert len(missing) > 0, "every route resolved — models.dev may have closed the :free gap"
      ```

  Assert `len(missing) > 0` deliberately: if a future models.dev release starts covering every route spelling, this test tells us to promote it to strict, rather than leaving a permanently-vacuous check.

- [ ] **Step 5:** Run it. It must be **green** — if the strict test is red, the six ids from Task 5 have not been replaced yet; do not paper over it with an exemption.

- [ ] **Step 6:** `pytest tests/config/test_model_catalog.py -q` → green.

---

## Task 5 — Replace the six dead BYOK fallback ids

**Files**
- Modify: `config/byok-providers.json`
- Modify: `infra/digichat-release/config/byok-providers.json`

**Steps**

- [ ] **Step 1:** In `config/byok-providers.json`, replace exactly these ids, preserving list order:

  | Provider | From | To |
  |---|---|---|
  | openrouter | `google/gemini-2.0-flash` | `google/gemini-2.5-flash` |
  | anthropic | `claude-sonnet-4-20250514` | `claude-sonnet-4-5` |
  | anthropic | `claude-haiku-4-20250514` | `claude-haiku-4-5` |
  | anthropic | `claude-opus-4-20250514` | `claude-opus-4-5` |
  | gemini | `gemini/gemini-2.0-flash` | `gemini/gemini-2.5-flash` |
  | xai | `grok-4-3` | `grok-4.3` |

  Five are retired upstream; `grok-4-3` → `grok-4.3` is a **rename** — xai has no dash spelling in the catalog.

- [ ] **Step 2:** Mirror the file exactly:

  ```bash
  cp config/byok-providers.json infra/digichat-release/config/byok-providers.json
  ```

- [ ] **Step 3:** Verify the vendored-copy guard still passes and the parity tests are unaffected:

  ```bash
  pytest tests/dg/test_llm_auth.py -q -k VendoredCopy
  cd apps/digichat && npm run test -- --run use-byok-key.catalog-parity byok-providers.catalog-parity
  ```

  `use-byok-key.catalog-parity.test.ts:79-84` asserts `byokModelPresets(provider) === fallbackModels`. Because both sides change together, it stays green — which is exactly why it is a parity test and not a liveness test.

- [ ] **Step 4:** Re-run `pytest tests/config/test_model_catalog.py -q` → the strict coverage test now passes with zero exemptions needed for BYOK.

---

## Task 6 — CI wiring and Makefile

**Files**
- Modify: `Makefile`
- Modify: `scripts/ci_paths.yaml`
- Modify: `.github/workflows/ci.yml` (generated filter block)

**Steps**

- [ ] **Step 1:** Add to the Makefile's `.PHONY` line and body, mirroring the `agents-init` precedent:

  ```make
  # Refresh the vendored model catalog from models.dev (network). Commits both artifacts.
  model-catalog:
  	python3 scripts/refresh_model_catalog.py

  # CI drift guard — network-free. Regenerate the TS module from the committed JSON.
  model-catalog-check:
  	python3 scripts/refresh_model_catalog.py --check
  ```

- [ ] **Step 2:** Add `apps/digichat/src/lib/model-catalog.generated.ts` to `scripts/ci_paths.yaml`'s `ruff_and_scripts` list. Without this, a PR touching only the generated module fires the digichat lane and never runs `--check` — the exact drift the guard exists for.

- [ ] **Step 3:** Regenerate the `ci.yml` filter block:

  ```bash
  python3 scripts/generate_ci_path_filters.py
  ```

  CI enforces `ci.yml` ⇄ `ci_paths.yaml` sync (`ci.yml:376-377`), so this must be committed together or the build fails.

- [ ] **Step 4:** Add one step to the existing `ruff-and-scripts` lane in `ci.yml`. Use the lane's runner, never bare `python3` — the lane `uv sync`s but does not activate the venv, so a bare `python3` is the runner's system interpreter:

  ```yaml
  - name: Model catalog drift guard
    run: uv run --frozen --no-sync python scripts/refresh_model_catalog.py --check
  ```

- [ ] **Step 5:** Verify locally that both paths agree:

  ```bash
  make model-catalog-check && echo "check ok"
  python3 scripts/generate_ci_path_filters.py --check && echo "filters in sync"
  ```

---

## Task 7 — Docs

**Files**
- Create: `docs/MODEL_CATALOG.md`
- Modify: `config/MODELS.md`

**Steps**

- [ ] **Step 1:** Write `docs/MODEL_CATALOG.md`: what the catalog is, the ten providers, the four-step refresh command, the `--check` / `--offline` flags, the tier table, the exemptions file and how to add one, and an explicit "what this is **not** authoritative for" section (route-suffix spellings, OpenRouter alias pairs, local Ollama, Cheaper Inference, the LiteLLM proxy router).

- [ ] **Step 2:** Add a pointer from `config/MODELS.md` so someone editing `litellm.yaml` finds the catalog and the advisory coverage test.

- [ ] **Step 3:** `make doc-check` → clean.

---

# Phase 2 — digichat consumption

Phase 2 is additive and fails soft. If it has to be split into its own PR, Phase 1 lands first and nothing regresses.

## Task 8 — Catalog module and provider map

**Files**
- Create: `apps/digichat/src/lib/model-catalog.ts`
- Create: `apps/digichat/src/lib/model-catalog.test.ts`

**Interfaces**
- `type ModelCatalogEntry` — the twelve fields from the spec's data model.
- `BYOK_PROVIDER_TO_CATALOG_PROVIDER: Readonly<Record<BYOKProvider, string>>` — D7.
- `catalogEntriesFor(byokProvider: BYOKProvider): readonly ModelCatalogEntry[]`
- `bucketCatalogEntries(entries): { free; opensource; flagship; all }`

**Steps**

- [ ] **Step 1:** Write the failing test first. The critical cases are the degradation rules, because they are what the upstream data actually does:

  ```ts
  import { describe, expect, it } from "vitest";
  import { bucketCatalogEntries, type ModelCatalogEntry } from "./model-catalog";

  const entry = (over: Partial<ModelCatalogEntry> = {}): ModelCatalogEntry => ({
    id: "m", label: "M",
    cost_input_usd_per_million: null, cost_output_usd_per_million: null,
    context_window: null, max_output_tokens: null,
    modalities_input: [], modalities_output: [],
    tool_call: false, structured_output: null, reasoning: false,
    vision: false, attachment: false, open_weights: false, tier: null,
    ...over,
  });

  describe("bucketCatalogEntries", () => {
    it("places an entry with no price in `all` only", () => {
      const b = bucketCatalogEntries([entry({ id: "unpriced" })]);
      expect(b.all.map((e) => e.id)).toEqual(["unpriced"]);
      expect(b.free).toEqual([]);
      expect(b.flagship).toEqual([]);
      expect(b.opensource).toEqual([]);
    });

    it("sorts `all` by id ascending", () => {
      const b = bucketCatalogEntries([entry({ id: "z" }), entry({ id: "a" }), entry({ id: "m" })]);
      expect(b.all.map((e) => e.id)).toEqual(["a", "m", "z"]);
    });
  });
  ```

- [ ] **Step 2:** Implement `model-catalog.ts`. `bucketCatalogEntries` buckets by the entry's precomputed `tier` (the generator already derived it) and returns `all` sorted by `id`. **Do not re-derive the tier here** — that would be a second copy of the rule, which is the drift this whole change exists to remove. Re-derive only if and only if the generated field is absent (defensive `?? null`).

- [ ] **Step 3:** `catalogEntriesFor` maps a BYOK provider id through `BYOK_PROVIDER_TO_CATALOG_PROVIDER` and reads `MODEL_CATALOG_BY_PROVIDER`. `gemini → google`. Unknown or unmapped → `[]`, never a throw.

- [ ] **Step 4:** Add a test pinning the D7 map against `config/byok-providers.json`, in the style of the existing parity tests:

  ```ts
  it("every BYOK provider maps to a provider present in the catalog", () => {
    const catalog = loadCatalog(); // readFileSync(resolve(process.cwd(), "../../config/model-catalog.json"))
    for (const id of BYOK_PROVIDER_LIST) {
      const key = BYOK_PROVIDER_TO_CATALOG_PROVIDER[id as BYOKProvider];
      expect(key, `no catalog provider for ${id}`).toBeTruthy();
      expect(catalog._meta.providers).toContain(key);
    }
  });
  ```

- [ ] **Step 5:** `cd apps/digichat && npm run test -- --run model-catalog` → green.

## Task 9 — Open-weight union

**Files**
- Modify: `apps/digichat/src/lib/openrouter-catalog.ts` (one function)
- Modify: `apps/digichat/src/lib/openrouter-catalog.test.ts`

**Steps**

- [ ] **Step 1:** Failing test first. Only 174 of openrouter's 390 catalog rows are `open_weights: true`, so the prefix list must survive:

  ```ts
  it("treats an entry as open source when the catalog says open weights", () => {
    // no hugging_face_id, no known publisher prefix, catalog openWeights === true
    expect(isOpenSource({ id: "vendor/new-open-weights-7b" }, true)).toBe(true);
  });

  it("still treats a known publisher prefix as open source", () => {
    expect(isOpenSource({ id: "meta-llama/llama-3.3-70b-instruct" }, false)).toBe(true);
  });
  ```

- [ ] **Step 2:** Change `isOpenSource` (`:60-63`) to take an optional `catalogOpenWeights` and union all three signals:

  ```ts
  function isOpenSource(entry: OpenRouterCatalogEntry, catalogOpenWeights = false): boolean {
    if (entry.hugging_face_id) return true;
    if (catalogOpenWeights) return true;
    return OPEN_WEIGHT_PUBLISHER_PREFIXES.some((prefix) => entry.id.startsWith(prefix));
  }
  ```

  `OPEN_WEIGHT_PUBLISHER_PREFIXES` (`:19-28`) **stays** — live `OpenRouterCatalogEntry` rows (`:7-13`) carry no `open_weights` field, so deleting the list would shrink the `opensource` bucket by up to 216 entries. Update the comment above it to say so.

- [ ] **Step 3:** `npm run test -- --run openrouter-catalog` → green; `npm run lint` → 0 errors.

## Task 10 — Widen the BYOK models route

**Files**
- Modify: `apps/digichat/src/app/api/byok/models/route.ts`
- Modify: `apps/digichat/src/app/api/byok/models/route.test.ts`

**Steps**

- [ ] **Step 1:** Rewrite the invalidated test. `route.test.ts:42-47` is `it("returns 400 for any provider other than openrouter")` — both title and assertion are wrong after the change. Replace with three cases: 400 + `unsupported_provider` for an **unknown** id (`?provider=not-a-provider`); 200 + catalog buckets for each of the five BYOK ids; openrouter still takes the live path (assert the stubbed `fetchWithTimeout` was called and that `source === "live"`).

- [ ] **Step 2:** Widen the guard at `:80-86` from `provider !== "openrouter"` to `!BYOK_PROVIDER_LIST.includes(provider as BYOKProvider)`. Keep the 400 and the `unsupported_provider` code — that guard is the anti-fetch-proxy boundary and it stays closed over a closed allowlist.

- [ ] **Step 3:** Branch on provider: openrouter keeps the existing live path verbatim, including `MAX_RESPONSE_BYTES` (`:26`), the content-length pre-check, and `writeOpenRouterCatalogCache`. Every other provider reads `catalogEntriesFor(provider)` → `bucketCatalogEntries` and returns immediately — **no fetch, no cache, no timeout**.

- [ ] **Step 4:** Widen the response. `ok`, `free`, `opensource`, `flagship`, `all` are unchanged; add `provider`, `source` (`"catalog" | "live"`), and `fetchedAt` from `MODEL_CATALOG_META`. Existing clients keep working.

- [ ] **Step 5:** `npm run test -- --run "byok/models"` → green; `npm run lint` → 0 errors.

## Task 11 — Picker wiring

**Files**
- Modify: `apps/digichat/src/components/byok-cli-flow.tsx`

**Steps**

- [ ] **Step 1:** Extend state with `catalogModels: Buckets | null` and `modelsFetchFailed` handling for the widened prefetch.

- [ ] **Step 2:** Widen the prefetch effect at `:292-307` from the `provider !== "openrouter"` early-return to "any BYOK provider", fetching `/api/byok/models?provider=${provider}`.

- [ ] **Step 3:** Add `catalogTieredOptions` to the `modelOptions` IIFE (`:252-271`) as **priority 3**, below `tieredOptions` (`:253`) and `liveKeyStepModels` (`:260`), above `byokModelPresets()` (`:266`). **Do not touch `:237`** — the live-tier gate stays openrouter-only.

- [ ] **Step 4:** Add the empty-tier fallback. `if (tieredOptions)` is truthy even when every bucket is empty, so a tier with no members currently collapses the picker to `[CUSTOM_MODEL]`. Make each tiered branch check the selected tier's length and fall through to presets when it is zero:

  ```ts
  const tierList = tieredOptions ? tieredOptions[tier] : [];
  if (tieredOptions && tierList.length > 0) { return [...tierList.map((m) => m.id), CUSTOM_MODEL]; }
  if (liveKeyStepModels && liveKeyStepModels.length > 0) { ... }
  if (catalogTiered && catalogTiered[tier].length > 0) { return [...catalogTiered[tier].map((m) => m.id), CUSTOM_MODEL]; }
  const presets = [...byokModelPresets(provider)];
  ```

- [ ] **Step 5:** Update the loading TermLine at `:497-503` to follow the widened prefetch gate, and leave `:505-511` (the key-ping line) alone.

- [ ] **Step 6:** Leave `:595` (`placeholder={byokModelPresets(provider)[0]}`) untouched. Do **not** derive presets from the catalog — see Global Constraint 7.

- [ ] **Step 7:** `npm run test -- --run byok-cli-flow` and `npm run lint` → green; then `npm run build`.

## Task 12 — digichat architecture doc

**Files**
- Modify: `apps/digichat/ARCHITECTURE.md` (BYOK section)

**Steps**

- [ ] **Step 1:** State that the **model** catalog is generated (`config/model-catalog.json` → `model-catalog.generated.ts`, refreshed by `scripts/refresh_model_catalog.py`, guarded by `--check` in CI) while the **provider** catalog (`byok-providers.ts`) remains hand-mirrored from `config/byok-providers.json` with a parity test.

- [ ] **Step 2:** Give the reason for the split, because `byok-providers.ts:14-16` currently asserts the opposite ("mirrors but is not generated from"): the provider catalog is 5 rows of deliberate policy (`keyPrefix`, `requiresModel`); the model catalog is 606 rows of upstream facts that change without review. Update that source comment too, or it will contradict the doc.

- [ ] **Step 3:** Record the `modelOptions` precedence order (D10) and that OpenRouter keeps a live path.

---

## Verification before opening the PR

- [ ] `pytest tests/scripts/test_refresh_model_catalog.py tests/config/test_model_catalog.py -q` — green, with `pytestmark` present in both files.
- [ ] `python3 scripts/refresh_model_catalog.py --check` — exit 0, no network.
- [ ] `python3 scripts/generate_ci_path_filters.py --check` — in sync.
- [ ] `ruff check scripts/refresh_model_catalog.py tests/scripts/test_refresh_model_catalog.py tests/config/test_model_catalog.py` — clean.
- [ ] `pytest tests/dg/test_llm_auth.py -q` — vendored copy + BYOK auth tests green.
- [ ] `cd apps/digichat && npm run test && npm run lint && npm run build` — green, 0 lint errors.
- [ ] `make doc-check` — clean.
- [ ] `git status` — no `.probe_*.py`, no scratch files, and `config/model-catalog.json` + `model-catalog.generated.ts` were both regenerated by the script rather than hand-edited.

## Open PR

- Title: `feat(digillm): unified models.dev catalog for provider model metadata (#4994)` — Conventional Commits with a required scope.
- Body: `Fixes #4994`. Link the spec and plan. Note the two deliberate out-of-scope items a reviewer will ask about: `scripts/refresh_model_routes.py` keeps its own fetch (rewiring it would drop litellm/cheaperinference/local-ollama rows from the ops snapshot), and `config/litellm.yaml` is validated rather than generated (routing policy, not catalog data).
- Review: run `/review` on a fresh-context subagent per [CODE_REVIEW_POLICY.md](../../../docs/agents/CODE_REVIEW_POLICY.md), post the findings as a PR comment opening with `<!-- in-session-review -->`, and apply the `reviewed:agent` label. Write the findings to `review-unified-model-catalog.md` beside this plan.
- Merge into `develop` once green, unconflicted, and reviewed — per the repo's merge-when-ready policy this task PR merges on its own; no human gate applies (no `digikey/`, no brokers, no new external network exposure — the catalog is a committed file, not a new dependency).