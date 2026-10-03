# Unified model catalog — design spec

- **Issue:** [#4994](https://github.com/digithings-ai/digithings/issues/4994) — "Consolidate provider model lists on a single unified catalog source (models.dev primary)"
- **Date:** 2026-10-03
- **Status:** Approved for implementation
- **Branch:** `task/4994-unified-model-catalog` → `develop`

---

## Goal

One curated, vendored catalog of provider model metadata (capabilities, pricing, context windows) generated from [models.dev](https://models.dev), consumed by digichat and validated against every model id the house pins today.

Today **at least eleven files across nine lists** answer "what models does this provider have?", each maintained by hand:

| # | Location | What it holds | How it is maintained |
|---|----------|---------------|----------------------|
| 1 | `config/byok-providers.json` | 5 BYOK providers, `keyPrefix`, `requiresModel`, 15 `fallbackModels` | hand, mirrored into TS + digigraph + digillm + litellm regex |
| 2 | `infra/digichat-release/config/byok-providers.json` | byte-identical vendored copy of (1) | copy, guarded by `TestByokCatalogVendoredCopy` (`tests/dg/test_llm_auth.py`) |
| 3 | `apps/digichat/src/lib/byok-providers.ts` | TS mirror of (1)'s ids/prefixes | hand + `byok-providers.catalog-parity.test.ts` |
| 4 | `apps/digichat/src/hooks/use-byok-key.ts` `byokModelPresets()` (`:53-83`) | a **fourth** copy of (1)'s `fallbackModels` | hand + exact `toEqual` parity test |
| 5 | `apps/digichat/src/lib/openrouter-catalog.ts` `OPEN_WEIGHT_PUBLISHER_PREFIXES` (`:19-28`) | open-weight publisher prefixes | hand; OpenRouter has no universal open-weight signal |
| 6 | `config/litellm.yaml` + `litellm.dev.yaml` + `litellm.cheaperinference.yaml` + `litellm.omniroute.yaml` | 149 pinned routes | hand |
| 7 | `config/digiquant_models.yaml` | `cheap`/`balanced`/`quality` pools + phase capabilities | hand |
| 8 | `config/model_modes.yaml` + `model_modes.local.yaml` | mode defaults + `phase_models` | hand |
| 9 | `digillm/src/digillm/client.py` | `_BYOK_CATALOG_API_BASES` (5 urls, `:578-586`), `_EXTERNAL_PROVIDERS` (4, `:231-248`), `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE` (9, `:457-467`), `_OPENROUTER_HOUSE_SLUG_PREFIXES` (8, `:627-636`) | hand, CI-pinned |
| 10 | `apps/digichat/src/app/api/byok/test/route.ts` | 4 hardcoded model-list URLs — 3 × `/v1/models` (openai `:163`, anthropic `:182`, xai `:262`) + google `/v1beta/models` (`:237`); 3 payload shapes (`data[]`, `models[].name`, and xai's `{ok, model}` with no `models[]`) | inline literals |
| 11 | `scripts/provider_review/probe.py` (`:27-66`) | 8-entry provider → probe-model table | hand |

Plus `apps/digithings-web/functions/api/byok/test.ts` and `apps/digithings-web/lib/providerSettings.ts:5` (a legacy Pages surface with its own `ProviderId` union) — out of scope, listed so the inventory is honest.

**What this PR does.** Generates a normalized snapshot of ten providers from models.dev into `config/model-catalog.json` + a generated TypeScript module, serves catalog-backed model tiers in digichat's BYOK picker for the providers that have no list today, **records** the six BYOK fallback ids the catalog proves are retired (as reasoned exemptions, not silent swaps — see [D11](#decisions)), and adds a coverage test that fails when a pinned id stops existing upstream.

**What this PR explicitly does not do.** It does not generate `config/litellm.yaml` (deliberate routing policy, not catalog data), does not touch digillm's runtime (no file reads, no new hard deps), and does not touch `scripts/refresh_model_routes.py` (see [Out of scope](#out-of-scope)).

---

## Deviations from the issue's acceptance criteria

| Issue AC | Deviation | Why |
|---|---|---|
| "models.dev as the single source of truth" | models.dev is the single source for **capability + pricing + context metadata**. It is explicitly **not** the source of truth for route-suffix spellings (`:free`, `:cloud`), OpenRouter alias pairs, or the full OpenRouter surface — measured: its `openrouter` slice is 390 entries and does not carry our `:free` slugs consistently, and its `ollama-cloud` ids carry no `:cloud` tag. | models.dev is a curated DB, not a live route registry. Treating it as one produces false coverage failures. |
| "replace individual provider endpoints" | The OpenRouter live `GET /api/v1/models` call is **kept**. It is demoted from *only source* to *liveness cross-check* for OpenRouter, whose tiers and prices are blended per-infra and change faster than a refresh cycle. | OpenRouter is the only source that answers "can I call this right now, at what price". Removing it would make the picker confidently wrong. |
| "replace hand-maintained model lists" | `config/byok-providers.json`, `config/litellm.yaml`, `config/digiquant_models.yaml` stay hand-maintained. The catalog **validates** them; it does not generate them. | These files encode routing policy (tier assignment, `requiresModel`, phase pins, strict no-fallback routing), not fetched facts. Generating them would automate a judgement call. |
| — | The six BYOK `fallbackModels` ids the catalog proves are retired are **exempted, not replaced**. The swap is a follow-up. | Every `fallbackModels` entry must also be a `model_name` in `config/litellm.yaml` (`test_every_advertised_byok_preset_is_a_litellm_model_group`, #3605), so replacing one is a routing change to an upstream slug that cannot be confirmed without a provider key. See [D11](#decisions). |

---

## Decisions

| # | Question | Decision |
|---|----------|----------|
| **D1** | Which upstream? | **models.dev `catalog.json`** (MIT, 226 providers, PR-validated, ~daily). LiteLLM's `model_prices_and_context_window.json` is pricing-first and lacks `structured_output`/`attachment`/`modalities`; OpenRouter's `/models` is OpenRouter-only. |
| **D2** | Live fetch at runtime, or vendored? | **Vendored snapshot.** The catalog is 5.7 MB with no server-side provider filtering, so every instance would re-download 5.7 MB on a TTL miss — and a models.dev outage would take the BYOK picker down with it, from a shared Cloudflare egress IP. A vendored file is deterministic, offline-testable, and diffable in review. |
| **D3** | How does digichat read it? | **Build-time codegen.** digichat is a Next standalone bundle; `apps/digichat/Dockerfile:53` copies only `apps/digichat/config` (operator skin YAML) into `/app/config` — repo-root `config/` is not in the image, so `fs.readFile` is not available to it. The generator emits `apps/digichat/src/lib/model-catalog.generated.ts` as a module import. |
| **D4** | Does codegen contradict the existing pattern? | It **supersedes** it, deliberately and only for the catalog. `apps/digichat/src/lib/byok-providers.ts:14-16` documents the established pattern as "mirrors (but is not generated from — see `ARCHITECTURE.md`'s BYOK section)". The provider catalog keeps mirror + parity test (five hand-maintained fields with a deliberate `requiresModel` judgement is not worth codegen). The model catalog does not: 606 rows × 12 fields, refreshed from upstream. `apps/digichat/ARCHITECTURE.md`'s BYOK section is updated to say which mechanism applies to which file, and why. |
| **D5** | Where is the drift guard? | `scripts/refresh_model_catalog.py --check`, run in CI. Mirrors `scripts/agents_init.py --check` (`.github/workflows/ci-docs.yml:58`). **`--check` is network-free**: it re-renders the TS module from the committed JSON and asserts structural invariants. |
| **D6** | Which providers ship? | Ten: `openai`, `anthropic`, `google`, `xai`, `groq`, `togetherai`, `fireworks-ai`, `deepseek`, `openrouter`, `ollama-cloud`. Every one is referenced by `config/` or `config/litellm.yaml`. models.dev has 226 providers; shipping all of them would put ~150 KB of noise in every review diff. |
| **D7** | BYOK id ↔ models.dev provider key? | An explicit, bidirectional map in the generator — `gemini ↔ google`, `together ↔ togetherai`, `fireworks ↔ fireworks-ai`, `xai ↔ xai`, `openrouter ↔ openrouter`, `openai ↔ openai`, `anthropic ↔ anthropic`. Note `scripts/refresh_model_routes.py:69-72` already carries a models.dev→house map; the direction there is preserved and this PR does not touch that file ([Out of scope](#out-of-scope)). |
| **D8** | Coverage test: strict or advisory? | **Scoped by confidence.** *Strict* (fails CI) for `config/byok-providers.json` `fallbackModels` — five first-party providers, ids we control, with a committed exemption list for structurally-unmappable ids. *Advisory* (warns, does not fail) for the 149 litellm route spellings, because the `:free`/`:cloud`/alias-pair surface is exactly where models.dev is empirically incomplete. |
| **D9** | Does `OPEN_WEIGHT_PUBLISHER_PREFIXES` survive? | **Yes — unioned, not replaced.** `OpenRouterCatalogEntry` (`openrouter-catalog.ts:7-13`) has no `open_weights` field, so live entries still need the prefix list. `isOpenSource()` (`:60-63`) becomes `hugging_face_id || prefixMatch || catalogOpenWeights`. Catalog-only coverage would have shrunk the `opensource` bucket by up to 216 entries (only 174 of 390 openrouter rows are `open_weights: true`). |
| **D10** | Ordering in the picker's `modelOptions` IIFE? | Unchanged precedence, with one new lowest-priority tier. (1) live OpenRouter buckets → (2) key-scoped `models[]` from the post-key ping → (3) **catalog buckets, only when (1) and (2) are both empty** → (4) `byokModelPresets()`. Also: an empty bucket at the active tier falls through to (4). Putting the catalog above the key-scoped list would let a user pick a model their key cannot call. |
| **D11** | The six dead BYOK pins? | **Record them as reasoned exemptions; do not replace them here.** The catalog proves all six are retired (five genuinely, `grok-4-3` because xAI publishes `grok-4.3`), and that is a real bug — `fallbackModels` feeds `llm_auth.py:309-341` `byok_default_model_refusal`, whose whole job is to hand the user a working alternative. But every `fallbackModels` entry must *also* be a `model_name` in `config/litellm.yaml` (`test_every_advertised_byok_preset_is_a_litellm_model_group`, #3605), so a swap is a **routing change**, not a catalog edit: it needs a new LiteLLM group whose `litellm_params.model` points at the successor slug, and that slug cannot be confirmed against a live provider without a provider key. Shipping a guessed one is a 500 on every BYOK chat that picks it — a worse outcome than an exhausted fallback. So each entry is exempted with the specific replacement it waits on (see `docs/MODEL_CATALOG.md`), and the swap is tracked as a follow-up that a maintainer with provider keys can execute. |
| **D12** | Does digillm consume the catalog at runtime? | **No.** `digillm/AGENTS.md`: hard deps are `openai` + `pydantic`, no file reads, importable standalone. Consumption is test-only, extending `tests/config/test_litellm_house_models.py:208-211` (which already pins `_BYOK_CATALOG_API_BASES` against `byok-providers.json`) with a provider-set assertion. |

---

## Architecture — approaches considered

### Approach A — Runtime fetch of `catalog.json` from the BFF (rejected)

Fetch on cache miss, slice, bucket, return. Rejected on three independent grounds:

1. **Size.** 5.7 MB, no provider filter (`api.json?provider=anthropic` returns the full 5,310,370 bytes — the parameter is ignored). `MAX_RESPONSE_BYTES = 2_000_000` (`byok/models/route.ts:26`) exists for good reason and is not a number to raise by 3×.
2. **Egress and shared fate.** 5.7 MB per instance per refresh, from a CDN with no SLA and no auth, over a shared Cloudflare egress IP. Every digichat instance fails together if models.dev is slow or rate-limits us.
3. **It still doesn't serve Python.** `digillm` cannot read files and cannot import npm. The issue's actual point — one source across the stack — needs a committed artifact, not a fetch.

### Approach B — Vendored snapshot + live OpenRouter cross-check (**chosen**)

A script fetches models.dev once, normalizes ten providers, and writes two artifacts: `config/model-catalog.json` (canonical, reviewable) and `apps/digichat/src/lib/model-catalog.generated.ts` (what digichat imports). `--check` is network-free. OpenRouter's live list stays for its own provider.

### Approach C — LiteLLM's `model_prices_and_context_window.json` (rejected as primary)

Broadest raw breadth (~3.2k models / 82 providers) and already fetched by `scripts/provider_review/bootstrap.py:48-52`. Rejected as primary because it is pricing-first: no `structured_output`, `attachment`, `modalities`, or `open_weights`. Those are precisely the fields `bucketOpenRouterModels` needs to replace the hand-maintained prefix list. Also, adding `litellm` to digillm's hard deps is forbidden by `digillm/AGENTS.md`.

### Approach D — Generate `config/litellm.yaml` from the catalog (rejected)

Would eliminate 149 hand-maintained routes. Rejected: `litellm.yaml` encodes routing *policy* — bare + `openrouter/`-prefixed alias pairs (`:253-322`), `configurable_clientside_auth_params` regexes per BYOK host (`:514-589`), dev-only ollama fallbacks, and a deliberate strict-no-fallback policy (`:6`). Generating it would automate judgement calls and make the diff unreviewable. The catalog instead **validates** it (advisory tier, [D8](#decisions)).

**What would let us delete `OPEN_WEIGHT_PUBLISHER_PREFIXES`:** if the catalog were the sole source for OpenRouter tiers, `open_weights` would replace the prefix list. It is not, so the list stays and the two are unioned ([D9](#decisions)).

---

## Data model

### `config/model-catalog.json` (generated)

```jsonc
{
  "_meta": {
    "schema_version": 1,
    "source": "models.dev",
    "source_url": "https://models.dev/catalog.json",
    "fetched_at": "2026-10-03T12:00:00Z",
    // sorted ascending — `--check` asserts `providers == sorted(providers)`
    "providers": [
      "anthropic", "deepseek", "fireworks-ai", "google", "groq",
      "ollama-cloud", "openai", "openrouter", "togetherai", "xai"
    ]
  },
  "models": {
    "openai": [
      {
        "id": "gpt-5.4",
        "label": "GPT-5.4",
        "cost_input_usd_per_million": 2.5,
        "cost_output_usd_per_million": 15.0,
        "context_window": 1050000,
        "max_output_tokens": 128000,
        "modalities_input": ["text", "image", "pdf"],
        "modalities_output": ["text"],
        "tool_call": true,
        // null, not false — models.dev omits structured_output on 8 of openai's
        // 53 rows. Unknown must never read as "does not support".
        "structured_output": null,
        "reasoning": true,
        "vision": true,
        "attachment": true,
        "open_weights": false,
        "tier": "flagship"
      }
    ]
  }
}
```

Invariants, all asserted by `--check` and `tests/config/test_model_catalog.py`:

1. `_meta.schema_version == 1`; `_meta.providers` is sorted ascending and equals the generator's constant.
2. Every provider key in `models` is in `_meta.providers`; every entry's `id` is unique **within** its provider.
3. `context_window` is a positive integer or `null`. models.dev ships `limit.context: 0` for image models (e.g. openai `chatgpt-image-latest`); `0` normalizes to `null`, never to `0`.
4. `cost_input_usd_per_million` / `cost_output_usd_per_million` are non-negative numbers or `null`. models.dev omits `cost` entirely on 4 of openai's 53 rows.
5. `structured_output` is `true`, `false`, or `null` (null = upstream did not say).
6. `tier ∈ {"free", "flagship", "opensource", null}`.
7. Entries are sorted by `id` ascending within each provider, so diffs are stable.
8. No URL, key, or env-var field anywhere in the file.

### Tier derivation

Evaluated top-down, first match wins — the same order as `tierFor()` (`openrouter-catalog.ts:70-75`):

| Rule | Condition |
|---|---|
| `free` | both costs present **and** both `== 0` |
| `flagship` | `cost_input_usd_per_million >= 3.0` — `FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M` (`openrouter-catalog.ts:34`), carried over unchanged |
| `opensource` | `open_weights == true` |
| `null` | otherwise |

`null` cost can never produce `free` or `flagship`; such entries land in `all` only. This is the deliberate no-guessing rule — models.dev omits `cost` on 8 of xai's 13 rows and 10 of groq's 16.

### `config/model-catalog-exemptions.json` (hand-maintained)

The coverage test's escape hatch, reviewed like any other config. Shape as shipped — a
`_comment` documenting the schema, then the entries, each keyed by `id` + `provider` + `reason`:

```json
{
  "_comment": "Coverage-test exemptions. Each names one pinned id the catalog does not carry …",
  "exemptions": [
    {
      "id": "claude-sonnet-4-20250514",
      "provider": "anthropic",
      "reason": "LITELLM_MODEL_GROUP_PINNED: replacing it needs a LiteLLM model group routing claude-sonnet-4-5 …"
    }
  ]
}
```

All six shipped entries are the retired BYOK `fallbackModels` ids from [D11](#decisions). Every entry
needs a non-empty `reason` **and** a `provider` — an unscoped exemption would excuse the same id on
every provider. `--check` fails if an entry no longer needs to exist, scoped to that entry's own
provider (ids repeat across providers, so an unscoped check would call a stale pin resolved because
*another* provider happens to carry a similarly-named model) — exemptions are not allowed to silently
accumulate.

### `apps/digichat/src/lib/model-catalog.generated.ts` (generated)

```ts
// GENERATED by scripts/refresh_model_catalog.py — do not edit by hand.
// Run `python3 scripts/refresh_model_catalog.py` after refreshing config/model-catalog.json.
import type { ModelCatalogEntry } from "./model-catalog";

export const MODEL_CATALOG_SCHEMA_VERSION = 1 as const;
export const MODEL_CATALOG_PROVIDERS = [
  "anthropic", "deepseek", "fireworks-ai", "google", "groq",
  "ollama-cloud", "openai", "openrouter", "togetherai", "xai",
] as const;
export const MODEL_CATALOG_BY_PROVIDER: Record<
  (typeof MODEL_CATALOG_PROVIDERS)[number],
  readonly ModelCatalogEntry[]
> = { /* … */ };
export const MODEL_CATALOG_META = {
  fetchedAt: "2026-10-03T12:00:00Z",
  source: "models.dev",
} as const;
```

---

## Data flow

### Refresh (manual, network)

```
python3 scripts/refresh_model_catalog.py
  │
  ├─ GET https://models.dev/catalog.json            (~5.7 MB, 226 providers)
  ├─ keep the 10 in D6                                (≈ 606 entries)
  ├─ normalize: per-million floats stay as-is;
  │             limit.context 0/absent → null;
  │             absent cost / structured_output → null;
  │             derive vision / tier (no guessing)
  ├─ write config/model-catalog.json                 (committed)
  └─ write apps/digichat/src/lib/model-catalog.generated.ts
```

### Drift guard (CI, no network)

```
uv run --frozen --no-sync python scripts/refresh_model_catalog.py --check
  ├─ parse config/model-catalog.json
  ├─ assert the 8 invariants + provider-set coverage of config/byok-providers.json
  ├─ assert every exemption is still needed
  ├─ re-render the TS module from the committed JSON, compare byte-for-byte
  └─ non-zero + "run `python3 scripts/refresh_model_catalog.py --offline`" on drift
```

### Runtime (digichat BYOK picker)

```
browser  byok-cli-flow.tsx
  │
  │  GET /api/byok/models?provider=<any of the 5 BYOK ids>
  ▼
BFF  api/byok/models/route.ts
  ├─ requireDigiChatAuth()  → embed-IP rate limit | BFF rate limit   (unchanged)
  ├─ provider not in BYOK_PROVIDER_LIST → 400 unsupported_provider   (widened from openrouter-only)
  ├─ provider === "openrouter"
  │     └─ live GET ${OPENROUTER_API_BASE}/models  → bucketOpenRouterModels() → cache   (unchanged)
  │        MAX_RESPONSE_BYTES + content-length pre-check still applies to *this* call only
  └─ otherwise
        └─ read MODEL_CATALOG_BY_PROVIDER[mapByokProvider(provider)]
           → bucketCatalogEntries()  → 200
  │
  ▼  { ok, provider, source: "catalog"|"live", fetchedAt,
      free, opensource, flagship, all }        ← existing keys unchanged, three added

browser  modelOptions IIFE (byok-cli-flow.tsx:252-271), precedence per D10:
  1. tieredOptions          live OpenRouter buckets        (openrouter only — unchanged)
  2. liveKeyStepModels      key-scoped list from the ping  (unchanged)
  3. catalogTieredOptions   NEW — only when 1 and 2 are both empty
  4. byokModelPresets()     unchanged; also the fallback when the active tier is empty
```

The `all` slice is **not** capped and **is** sorted by `id` ascending. The live path caps at `OPENROUTER_CATALOG_ENTRY_CAP = 2000` (`openrouter-catalog.ts:36`); the largest catalog provider is openrouter at 390 rows, so a cap would be dead configuration.

---

## Components touched

### New

| File | Purpose |
|---|---|
| `scripts/refresh_model_catalog.py` | Fetch + normalize + write both artifacts. Flags: none (fetch), `--offline` (re-render TS from committed JSON), `--check` (CI drift guard). |
| `config/model-catalog.json` | Generated. Canonical catalog. |
| `config/model-catalog-exemptions.json` | Hand-maintained coverage-test exemptions, one reason each. |
| `apps/digichat/src/lib/model-catalog.generated.ts` | Generated. digichat's import surface. |
| `apps/digichat/src/lib/model-catalog.ts` | Hand-written. `ModelCatalogEntry` type, provider-key map, `catalogEntriesFor(byokProvider)`, `bucketCatalogEntries()`. |
| `docs/MODEL_CATALOG.md` | What the catalog is, how to refresh it, what it is and is not authoritative for. |
| `tests/scripts/test_refresh_model_catalog.py` | Normalization unit tests + `--check` semantics. |
| `tests/config/test_model_catalog.py` | The coverage test ([D8](#decisions)). |

### Modified

| File | Change |
|---|---|
| `config/byok-providers.json` | **Unchanged, deliberately.** The catalog proves 6 `fallbackModels` ids are retired (5 genuinely; xai's `grok-4-3` because models.dev carries only the dotted `grok-4.3`), and that is a real defect — but replacing one is a `config/litellm.yaml` **routing** change (#3605 pins every `fallbackModels` entry to a `model_name`), and the successor slug cannot be confirmed against a live provider without a provider key. So they are recorded in `config/model-catalog-exemptions.json` with the replacement each waits on; the swap is a follow-up ([D11](#decisions)). |
| `infra/digichat-release/config/byok-providers.json` | Same 6 replacements. Must stay byte-identical to `config/byok-providers.json` or `TestByokCatalogVendoredCopy` fails. |
| `apps/digichat/src/app/api/byok/models/route.ts` | `:80-86` guard widens from `provider !== "openrouter"` to `!BYOK_PROVIDER_LIST.includes(provider)` → still `400 unsupported_provider`. Response **widens** — `ok`, `free`, `opensource`, `flagship`, `all` unchanged; `provider`, `source`, `fetchedAt` added. openrouter keeps the live path including `MAX_RESPONSE_BYTES`. |
| `apps/digichat/src/app/api/byok/models/route.test.ts` | `:42-47` `it("returns 400 for any provider other than openrouter")` is invalidated by the widened allowlist. Replaced with: 400 for an unknown provider id; 200 + catalog buckets for each of the 5; openrouter still takes the live path. |
| `apps/digichat/src/lib/openrouter-catalog.ts` | `isOpenSource()` (`:60-63`) becomes `hugging_face_id \|\| prefixMatch \|\| catalogOpenWeights`. `OPEN_WEIGHT_PUBLISHER_PREFIXES` (`:19-28`) **retained** ([D9](#decisions)). No other change. |
| `apps/digichat/src/components/byok-cli-flow.tsx` | `modelOptions` IIFE (`:252-271`) gains `catalogTieredOptions` as tier 3 and an empty-tier fallback to tier 4, per [D10](#decisions). `:292-307` prefetch gate widens from `provider !== "openrouter"` to "any BYOK provider". `:497-503` loading TermLine follows the same gate. **`:237`'s live-tier gate stays openrouter-only.** `byokModelPresets()` at `:595` is **unchanged**. |
| `Makefile` | `model-catalog` (refresh) and `model-catalog-check` targets. |
| `.github/workflows/ci.yml` | One step in the existing `ruff-and-scripts` lane: `uv run --frozen --no-sync python scripts/refresh_model_catalog.py --check`. |
| `scripts/ci_paths.yaml` | Add `apps/digichat/src/lib/model-catalog.generated.ts` to `ruff_and_scripts`, then regenerate via `scripts/generate_ci_path_filters.py` (CI enforces `ci.yml` ⇄ `ci_paths.yaml` sync at `ci.yml:376-377`). Without this, a digichat-only PR never runs `--check`. |
| `apps/digichat/ARCHITECTURE.md` | BYOK section: the model catalog is generated; `byok-providers.ts` remains mirror + parity test; state why ([D4](#decisions)). |
| `docs/MODELS.md` (or a pointer to `docs/MODEL_CATALOG.md`) | Catalog freshness and the refresh command. |

### Untouched, on purpose

| File | Why |
|---|---|
| `apps/digichat/src/hooks/use-byok-key.ts` | `byokModelPresets()` is asserted **exactly** against `fallbackModels` (`use-byok-key.catalog-parity.test.ts:79-84`) and consumed at `byok-cli-flow.tsx:595` and `embed-provider-flow.ts:88,:103`. Deriving it from the catalog changes its return shape (bare ids, not options) and makes the placeholder arbitrary. The catalog is an **advisory overlay**, not the preset source. |
| `apps/digichat/src/app/api/byok/test/route.ts` | The credentialed ping still validates keys. Its `models[]` payload stays and keeps precedence over catalog tiers ([D10](#decisions)). |
| `apps/digichat/src/lib/byok-providers.ts`, `config/litellm.yaml`, `config/digiquant_models.yaml`, `config/model_modes.yaml` | Routing policy, not fetched facts ([Approach D](#architecture--approaches-considered)). |
| `digillm/src/digillm/client.py` | No file reads, no new hard deps ([D12](#decisions)). Test-only consumption. |
| `scripts/refresh_model_routes.py` | See [Out of scope](#out-of-scope). |
| `apps/digithings-web/**` | Legacy Pages surface with its own `ProviderId` union. Deleting it is a separate decision. |

---

## Error handling

| Condition | Response | Rationale |
|---|---|---|
| Unknown / non-BYOK `provider` query param | `400 unsupported_provider` | Preserves the anti-fetch-proxy guard from `:80-86`. The catalog is a module import — there is no URL to validate. |
| Catalog has no entry for a valid BYOK provider | `200`, empty buckets, `meta.count === 0` | The client falls through to `byokModelPresets()` per [D10](#decisions)). Never `500`. |
| models.dev unreachable during refresh | Script exits non-zero with the URL and the underlying error; **no artifact is written** | A partial refresh must not be committable. |
| models.dev returns a shape the generator does not recognize (e.g. `providers` key renamed) | Script exits non-zero, writes nothing, prints the offending keys | Fail loud. `refresh_model_routes.py` learned this in #3847. |
| OpenRouter live fetch fails | Unchanged: `502 upstream_unavailable` | Existing behavior at `:119-122`. |
| OpenRouter live body exceeds `MAX_RESPONSE_BYTES` | Unchanged: `502 response_too_large` | The 2 MB guard now guards a ~1 MB OpenRouter body, not a 5.7 MB catalog. |

---

## Testing

Both new Python test files **must** carry `pytestmark = pytest.mark.unit`. `pytest.ini` has no auto-marking, and the CI lane runs `-m "unit or baseline"` (`ci.yml:427-428`), so an unmarked file is collected and silently deselected — verified empirically.

**`tests/config/test_model_catalog.py`** — the coverage test ([D8](#decisions)):

1. Every `config/byok-providers.json` `fallbackModels` id resolves in the catalog for its mapped provider, after author-stripping (`gemini/gemini-2.5-flash` → `gemini-2.5-flash` → google). **Strict.**
2. Every exemption in `config/model-catalog-exemptions.json` is still needed, and each has a non-empty `reason`. **Strict** — prevents silent accumulation.
3. Every BYOK provider in `config/byok-providers.json` maps to a provider key present in `MODEL_CATALOG_PROVIDERS`. **Strict.**
4. `_BYOK_CATALOG_API_BASES`' provider set equals the catalog's provider set. **Strict.** Provider-set only — the catalog carries no URL field, so there is nothing to compare against. Extends `tests/config/test_litellm_house_models.py:208-211`, which already pins that frozenset against `byok-providers.json`.
5. The 149 `model_name:` routes across the four `config/litellm*.yaml` files resolve, after the documented `:free`/`:cloud` normalization. **Advisory — `pytest.warns`, never fails.** models.dev's openrouter slice is 390 rows and does not carry our `:free` slugs consistently; its ollama-cloud ids carry no `:cloud` tag. Making this strict would produce 38 permanent false failures.
6. The eight data-model invariants hold.

**`tests/scripts/test_refresh_model_catalog.py`** — normalization against fixtures, not the network:

7. `limit.context == 0` → `null`; absent `cost` → `null`; absent `structured_output` → `null`.
8. Tier table: free/flagship/opensource/never-guessed, including `null` cost never producing `free` or `flagship`.
9. `--check` exits non-zero on a mutated JSON, on a stale TS module, and on an exemption that is no longer needed.
10. `--offline` is network-free (monkeypatched transport that raises if called).

**digichat (`npm run test`)**:

11. `bucketCatalogEntries()` returns the same buckets for a hand-built `ModelCatalogEntry[]`, including `null`-cost entries landing in `all` only.
12. `isOpenSource()` is true when *any* of `hugging_face_id`, a publisher prefix, or `catalogOpenWeights` matches.
13. `GET /api/byok/models` returns catalog buckets for all five providers, still 400s an unknown provider, and still takes the live path for openrouter.
14. `modelOptions` precedence: catalog tiers are used only when live and key-scoped lists are both absent, and an empty active tier falls through to presets.

**Lint/gates:** `make model-catalog-check`, `ruff check scripts/ tests/ config/` (`ruff` is bounded to its current major — #1705), `npm run lint` + `npm run test` in `apps/digichat`.

---

## Security considerations

- **No egress at runtime.** The catalog is a committed file and a generated module. Adding a third-party fetch to the BFF would have put a models.dev outage on the BYOK picker's critical path from a shared egress IP. Avoided by [D2](#decisions).
- **No SSRF surface.** The route takes a `provider` from a closed allowlist and never a URL. `isAllowedServiceUrl()` remains the guard for user-supplied endpoints elsewhere; the catalog adds no new user-supplied-URL path.
- **No secrets in the artifact.** Invariant 8 forbids URL, key, and env-var fields. models.dev carries provider `env` and `api` names upstream; the normalizer drops them.
- **No new dependency.** No npm or pip package is added. The model catalog arrives as generated code, not a runtime import of `@opencode-ai/models`.
- **The browser still holds no key.** Unchanged — `POST /api/byok/test` keeps the credentialed call server-side.
- **Fail-loud on unknown upstream shape.** A models.dev schema change must stop the refresh, not silently produce an empty catalog that reads as "these providers have no models".

---

## Out of scope

- **`scripts/refresh_model_routes.py`.** It keeps its own models.dev fetch. Rewiring it to the vendored catalog would shrink the ops snapshot: `render_table()` (`:241-243`) groups by provider *from routes only*, and litellm, cheaperinference, and local ollama have no models.dev provider key — they would lose every table row, and Cheaper Inference is the upstream the house phase-routing depends on. The follow-up is to have it **import the tier/normalization rules** from `refresh_model_catalog.py` while keeping its live-provider sweep, so the two normalizers cannot drift without the ops script losing rows. Filed as the top follow-up of #4994.
- **Generating `config/litellm.yaml`**, `config/digiquant_models.yaml`, `config/model_modes.yaml` ([Approach D](#architecture--approaches-considered)).
- **`apps/digithings-web/**`** — its own `ProviderId` union and duplicate key validation.
- **Local Ollama enumeration.** `GET {base}/api/tags` is per-machine and must never be BFF-proxied from a user-supplied host (SSRF). It stays a client-local operation, and `byokModelPresets()` plus free-text custom entry remain its path.
- **Cheaper Inference and the LiteLLM proxy as catalog *providers*.** They are OpenAI-compatible endpoints, not curated model sets. models.dev has no key for either.
- **digillm runtime catalog loading.** Would require a generated module or a new dependency; both violate `digillm/AGENTS.md` for marginal gain over a test.
- **`digiquant/src/digiquant/research/pricing.py`.** Its rule — no price without `docs/providers/snapshots/<provider>.yaml` corroboration — is sound. Adding a third source creates a conflict when models.dev and OpenRouter disagree, which they do by construction (OpenRouter blends per-infra prices).

---

## Rollout note

**Base branch is `develop`, not `module/digichat`.** #4994 is labelled `component:root,component:digichat,component:digillm`. `scripts/worktree_task.sh:80` takes the first `component:` match from `gh issue view --json labels`, which returns `component:root` first, and `scripts/project_routing.json` maps `component:root` → `develop`. Independently confirmed: `module/digichat` is ~210 commits behind `origin/develop` with 48 changed files under `apps/digichat`, so a digichat-rooted branch would be cut from dead code and `make task` would refuse. This change is genuinely cross-cutting — a `config/` artifact consumed by a Python script, a generated TS module, and the digichat BFF — not module-specific work smuggled onto `develop`.

**Rollout order within the PR.** Phase 1 (catalog core: generator, artifacts, tests, CI, prune) is self-contained and reviewable on its own. Phase 2 (digichat consumption: route widening, bucketing, picker wiring) is additive and fails soft. If Phase 2 needs to be split into its own PR for review size, the catalog lands first and nothing regresses.

---

## Spec self-review

An adversarial fresh-context review produced 16 findings (2 blockers, 8 major, 3 minor, 3 nit). Every one was independently verified before being accepted; all 16 were accurate. Resolutions:

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | blocker | The coverage test as first drafted was **red on commit**: 6 of 15 BYOK `fallbackModels` do not resolve, and the "`presets ⊆ catalog ∧ ⊇ fallbackModels`" assertion is arithmetically unsatisfiable. | Coverage is now **scoped** ([D8](#decisions)): strict for BYOK fallbacks, advisory for litellm spellings. The unsatisfiable assertion is gone. The 6 ids are **exempted with the specific replacement each waits on** ([D11](#decisions)) — replacing them is a `config/litellm.yaml` routing change that needs a provider key to confirm the upstream slug. Also corrected: "the suffix rule `refresh_model_routes.py` uses" is `_is_listed_live` (`:224-234`), a live-list comparison that does not author-strip — the matcher specified here is a new, explicitly defined author-strip. |
| 2 | blocker | Self-contradiction on `OPEN_WEIGHT_PUBLISHER_PREFIXES` — the table said "deleted", Approach D said "let us delete", the draft's self-review said "survives, unioned". | **Unioned, not deleted** ([D9](#decisions)). Verified: `OpenRouterCatalogEntry` (`:7-13`) has no `open_weights`, so live entries still need the prefix list; catalog-only coverage would shrink the `opensource` bucket by up to 216 entries. The union site is named: `isOpenSource()` (`:60-63`). |
| 3 | major | Dropping the openrouter gate on `tieredOptions` (`:237`) would put the catalog **above** the key-scoped list in the `:252-271` IIFE — reproducing the exact "membership ≠ key-scoped availability" conflation the spec claims to fix. `if (tieredOptions)` is also truthy with empty buckets, so the claimed presets fallback did not exist. | The live-tier gate stays **openrouter-only**; catalog tiers are **tier 3**, used only when tiers 1 and 2 are both empty ([D10](#decisions)). The empty-bucket fallback is added to the Modified list. The full ordering is stated. |
| 4 | major | `byokModelPresets()` derivation from the catalog breaks its exact `toEqual` parity test, changes its return shape, and would make `byok-cli-flow.tsx:595`'s placeholder an arbitrary id. | **Not done.** `use-byok-key.ts` and its parity test are untouched and listed under "Untouched, on purpose" with the reason. |
| 5 | major | Rewiring `refresh_model_routes.py` would silently shrink the ops snapshot — litellm / cheaperinference / local ollama have no models.dev provider, and `render_table()` groups from routes only. The alias map also maps models.dev→house, opposite to the draft's table. | The file is **out of scope** with the reason recorded, plus a concrete follow-up. [D7](#decisions) now notes the direction conflict explicitly and says this PR does not touch that file. |
| 6 | major | Neither new test file had a marker, and `pytest.ini` does not auto-mark — so the "load-bearing CI test" would be silently deselected. Verified empirically. | The Testing section now **requires** `pytestmark = pytest.mark.unit` in both files, with the mechanism explained. |
| 7 | major | The digichat-can't-read-config rationale cited `infra/digichat-release/compose.profile-a.yml:176-178` — but that `volumes:` block belongs to the **digigraph** service (header at `:141`), and it mounts the whole directory. And `byok-providers.ts:14-16` documents mirror + parity test as explicitly *not* codegen. | [D3](#decisions) now gives the real reason (`apps/digichat/Dockerfile:53` ships only `apps/digichat/config`). [D4](#decisions) acknowledges the precedent and states why codegen applies to the model catalog but not the provider catalog, with the required `ARCHITECTURE.md` update. |
| 8 | major | The cited precedent `digillm/tests/test_byok_isolation.py:281` does not reference `_BYOK_CATALOG_API_BASES` at all. | Corrected to `tests/config/test_litellm_house_models.py:208-211`, which is the real pin. Testing item 4 restated as a **provider-set-only** assertion, since the catalog carries no URL field. |
| 9 | major | Inventory undercounted: missed `embed-provider-flow.ts` (a second `byokModelPresets` consumer), the vendored `infra/` copy, the 3 extra litellm overlays (32 routes), `model_modes.local.yaml`, the 8-entry `_OPENROUTER_HOUSE_SLUG_PREFIXES`, `provider_review/probe.py`'s 8-entry table, and `digithings-web/lib/providerSettings.ts`. | Inventory rewritten to "at least eleven files across nine lists", with each added; `digithings-web` is listed as out of scope so the count is honest rather than quietly smaller. |
| 10 | major | The CI step used bare `python3` where the lane uses `uv run --frozen --no-sync python`; and `scripts/ci_paths.yaml`'s `ruff_and_scripts` does not cover `apps/digichat/**`, so a digichat-only PR never runs `--check`. | Both corrected. The generated TS file is added to `ci_paths.yaml` with the `generate_ci_path_filters.py` regeneration step and the `ci.yml:376-377` sync enforcement noted. |
| 11 | minor | `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE` is 9 entries, not 7; `_OPENROUTER_HOUSE_SLUG_PREFIXES` was omitted entirely. | Corrected in the inventory table (9 and 8). |
| 12 | minor | `tierFor()` cited as `:71-78` — that range is `supportsTools`. | Corrected to `:70-75`. |
| 13 | minor | `route.test.ts` was missing from the Modified table; "response shape unchanged" contradicted "response gains `meta`"; the `all` slice's cap/sort was unstated. | `route.test.ts` added with the specific invalidated assertion (`:42-47`). Response **widens** — one claim, stated once. Cap and sort stated: uncapped, sorted by `id`. |
| 14 | minor | "4 hardcoded `/v1/models` URLs" is wrong — 3 are `/v1/models`, google's is `/v1beta/models`; and there are 3 payload shapes, not 2. | Corrected, including the note that xai already returns no `models[]`, which is why xai already falls through to presets today. |
| 15 | nit | The `_meta.providers` example violated the spec's own sorted invariant (`openai` before `ollama-cloud`). | Reordered to `anthropic, deepseek, fireworks-ai, google, groq, ollama-cloud, openai, openrouter, togetherai, xai`, in both the JSON example and the generated TS. |
| 16 | nit | "210 commits behind" is 209, and the file count is 48, not "16+". | Softened to "~210" and "48", and the number is presented as the reason for the base decision rather than as a load-bearing claim. |