# Unified model catalog

**Part of [digithings](../README.md) (digithings.ai).**
**Issue:** [#4994](https://github.com/digithings-ai/digithings/issues/4994) ·
**Spec:** [`docs/superpowers/specs/2026-10-03-unified-model-catalog-design.md`](superpowers/specs/2026-10-03-unified-model-catalog-design.md) ·
**Plan:** [`docs/superpowers/plans/2026-10-03-unified-model-catalog.md`](superpowers/plans/2026-10-03-unified-model-catalog.md)

One normalized, vendored snapshot of per-model metadata — price, context
window, modalities, tool-call / structured-output / reasoning / vision
capability, open-weight flag — for the ten providers this repo routes to.
It replaces a dozen hand-maintained lists that had to be kept in sync by hand.

---

## The two artifacts

Both are **generated. Never hand-edit either one.**

| Artifact | Consumers |
|----------|-----------|
| `config/model-catalog.json` | Python: the coverage tests, `scripts/refresh_model_catalog.py --check`, human review |
| `apps/digichat/src/lib/model-catalog.generated.ts` | TypeScript: the digichat BFF behind `GET /api/byok/models` |

The TypeScript module is **generated** rather than imported from
`config/model-catalog.json` because digichat ships as a Next.js standalone
bundle — `apps/digichat/Dockerfile:53` copies only `apps/digichat/config`, so
there is no repo-root `config/` to read at runtime. Unlike the hand-mirrored
`BYOK_PROVIDER_CATALOG` in `apps/digichat/src/lib/byok-providers.ts`, this one
cannot drift: CI fails if the committed module is not what the generator emits.

## Provenance

`config/model-catalog.json` is generated from
[`https://models.dev/catalog.json`](https://github.com/anomalyco/models.dev)
(MIT, PR-curated, refreshed daily). `_meta` records the source, the URL and
`_meta.fetched_at`. Ten providers are vendored:

`anthropic`, `deepseek`, `fireworks-ai`, `google`, `groq`, `ollama-cloud`,
`openai`, `openrouter`, `togetherai`, `xai`

## Refreshing

```bash
make model-catalog          # fetch models.dev, rewrite both artifacts (network)
make model-catalog-check    # CI drift guard (network-free)
```

Two further modes on the script itself:

```bash
python3 scripts/refresh_model_catalog.py --offline   # re-render the TS module from the committed JSON
python3 scripts/refresh_model_catalog.py --timeout 90 # the body is ~5.7 MB; the 30s default is enough, but be explicit if the network is slow
```

**A refresh never edits a config file.** `config/litellm.yaml`,
`config/model_modes.yaml`, `config/digiquant_models.yaml` and
`config/byok-providers.json` stay hand-maintained — routing and tier policy are
judgement, not facts. The catalog validates them; it does not generate them.

## Tiers

Tier is derived once, at generation time, in the same order as
`tierFor()` in `apps/digichat/src/lib/openrouter-catalog.ts`. First match wins:

| Tier | Rule |
|------|------|
| `free` | `cost.input` **and** `cost.output` are both present **and** both `0` |
| `flagship` | `cost.input >= $3.00 / 1M` (the price floor carried over from `FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M`) |
| `opensource` | `open_weights` is `true` upstream |
| `null` | anything else — the entry still appears in the `all` bucket, just unclassified |

**A missing price is never a price of zero.** models.dev omits `cost` on 8 of
xai's 13 rows and 10 of groq's 16, so reading absence as `0` would mis-bucket a
third of two providers' models as free. The same rule applies to
`context_window` (a `limit.context` of `0` means unknown, not an empty window)
and to `structured_output`, which upstream leaves unset on 8 of openai's 53
rows — it normalizes to `null`, never `false`.

## Coverage tests

`tests/config/test_model_catalog.py` splits the pinned ids by confidence:

- **Strict** — every id in `config/byok-providers.json` `fallbackModels` must
  resolve in the catalog. These are the models a digichat user is offered
  before they have entered a key, so a retired one is a dead option in the UI.
  This test found six of them on its first run (#4994).
- **Advisory** — the 149 routes across `config/litellm*.yaml` are reported with
  `pytest.warns`, not failed. See the caveat below.
- **Provider sets** — every BYOK provider maps to a vendored provider, and
  digillm's `_BYOK_CATALOG_API_BASES` still matches `byok-providers.json`.

### Exemptions

`config/model-catalog-exemptions.json` is the only hand-maintained file here. It
exists for ids that are correct in our config and genuinely absent from
models.dev. Every entry needs a non-empty `reason`, and `--check` **fails when an
exemption is no longer needed** — a stale exemption is a silent hole in the
strict test. Advisory-only ids (below) are deliberately not exempt here, because
the advisory test reports them instead.

It currently carries **six** entries, all of them found on the strict test's
first run. They share one root cause, which is worth stating plainly because it
is the first real thing this catalog found:

> Every id in `byok-providers.json` `fallbackModels` must also be a `model_name`
> in `config/litellm.yaml` (`test_every_advertised_byok_preset_is_a_litellm_model_group`).
> So replacing a stale pin is a **routing** change, not a catalog edit — the new id
> needs its own LiteLLM model group, and a wrong `litellm_params.model` is a 500 on
> every BYOK chat that picks it.

| Advertised id | models.dev | What it would take to fix it |
|---------------|-----------|------------------------------|
| `google/gemini-2.0-flash` (openrouter) | absent | `google/gemini-2.5-flash` + a LiteLLM group routing `openrouter/google/gemini-2.5-flash` |
| `claude-sonnet-4-20250514` (anthropic) | absent — models.dev has **no Claude 4 generation at all** | route `anthropic/claude-sonnet-4-5` |
| `claude-haiku-4-20250514` (anthropic) | absent, same | route `anthropic/claude-haiku-4-5` |
| `claude-opus-4-20250514` (anthropic) | absent, same | route `anthropic/claude-opus-4-5` |
| `gemini/gemini-2.0-flash` (gemini) | absent — Google's slice starts at `gemini-2.5-flash` | route `gemini/gemini-2.5-flash-lite` |
| `grok-4-3` (xai) | absent — xAI publishes `grok-4.3`, dotted | correct the typo to `grok-4.3`, matching the `grok-4.5` group this repo already routes |

Every candidate in that table is present in models.dev today. None was applied
here, because each one needs a provider key to confirm the upstream slug before
it can become live routing — and a guessed `litellm_params.model` is worse than a
stale pin, since the pin at least returns a real upstream error. That check
belongs to whoever holds the keys, with `make test-unit` and a real BYOK ping as
the evidence.

## What this is **not** authoritative for

models.dev is a **curated capability and pricing database**, not a live route
registry. Do not treat it as one:

- **Route-suffix spellings.** Its `openrouter` slice is 390 rows and does not
  carry our `:free` slugs consistently (`liquid/lfm-2.5-2.6b:free` and friends
  miss). 38 of our 149 litellm routes miss for this and related reasons, which
  is why that check warns instead of failing.
- **OpenRouter alias pairs.** `config/litellm.yaml` registers bare and
  `openrouter/`-prefixed aliases for the same upstream; only one resolves.
- **`ollama-cloud` `:cloud` tags.** Our aliases read `qwen3.5:cloud`; models.dev
  carries `qwen3.5` and `qwen3.5:397b`, with no tag on the id itself.
- **Local Ollama.** A per-machine daemon has no catalog row; `ollama/deepseek-r1:14b`
  is enumerated from `GET /api/tags` at runtime. Never proxy that from the BFF —
  it is a user-supplied endpoint and an SSRF vector.
- **Cheaper Inference and the LiteLLM proxy router.** Both are OpenAI-compatible
  gateways, not curated model sets. digiquant's phase pools are annotated
  against the Cheaper Inference catalog (`digillm`'s
  `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE`), which models.dev does not carry.
- **Live availability.** A catalog entry means "this model is documented with
  this price", not "your key can call it". Credentialed availability is still
  decided by `POST /api/byok/test`, and digichat's live OpenRouter
  `GET /api/v1/models` cross-check is still the liveness signal for that
  provider.

## Tiering on open weights is a union, not a replacement

`OPEN_WEIGHT_PUBLISHER_PREFIXES` in
`apps/digichat/src/lib/openrouter-catalog.ts` is **still there**, and it has to
be. Live OpenRouter entries carry `hugging_face_id` and `supported_parameters`
only — no `open_weights` flag — so dropping the prefix list would shrink the
`opensource` bucket by up to 216 of OpenRouter's 390 rows (only 174 are flagged
open-weight upstream). `isOpenSource()` unions the two signals.

## Related

- [`config/MODELS.md`](../config/MODELS.md) — how to add, retire, and rename a
  pinned model
- [`docs/LLM_PROVIDERS.md`](LLM_PROVIDERS.md) — provider setup notes
- `docs/providers/snapshots/*.yaml` — the agent-researched provider snapshots
  that corroborate digiquant's price table
- `scripts/refresh_model_routes.py` — the separate house inventory snapshot
  (tier assignment stays manual there)