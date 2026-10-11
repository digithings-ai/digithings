# Unified model catalog

**Part of [digithings](../README.md) (digithings.ai).**
**Issue:** [#4994](https://github.com/digithings-ai/digithings/issues/4994) ·
**Spec:** [`docs/superpowers/specs/2026-10-03-unified-model-catalog-design.md`](superpowers/specs/2026-10-03-unified-model-catalog-design.md) ·
**Plan:** [`docs/superpowers/plans/2026-10-03-unified-model-catalog.md`](superpowers/plans/2026-10-03-unified-model-catalog.md)

One normalized, vendored snapshot of per-model metadata — price, context
window, modalities, tool-call / structured-output / reasoning / vision
capability, open-weight flag — for the ten providers this repo routes to.
It **validates** a dozen hand-maintained lists that had to be kept in sync by
hand, against one normalized snapshot — it does not generate or replace them.

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

It is **empty** (`{"exemptions": []}`) today. It carried six entries for one
month after this catalog landed, and the reason they ever existed is the first
real thing the catalog found:

> Every id in `byok-providers.json` `fallbackModels` must also be a `model_name`
> in `config/litellm.yaml` (`test_every_advertised_byok_preset_is_a_litellm_model_group`).
> So replacing a stale pin is a **routing** change, not a catalog edit — the new id
> needs its own LiteLLM model group, and a wrong `litellm_params.model` is a 500 on
> every BYOK chat that picks it.

That is why the strict test could not simply be loosened. Every entry was cleared
in #5000, each successor verified against the provider's own API first — except
the three anthropic ids, for which no key is held, and which were instead
cross-checked against **two** independent public keyspaces (models.dev and
LiteLLM's pricing table), which agree on every claude id.

| Retired pin | Why it was retired | Replaced with |
|-------------|--------------------|---------------|
| `google/gemini-2.0-flash` (openrouter) | absent from `openrouter.ai/api/v1/models` | `google/gemini-2.5-flash` |
| `claude-sonnet-4-20250514` (anthropic) | absent from both keyspaces — only Bedrock/Vertex spellings survive | `claude-sonnet-4-6` |
| `claude-haiku-4-20250514` (anthropic) | absent, same | `claude-haiku-4-5` |
| `claude-opus-4-20250514` (anthropic) | absent, same | `claude-opus-4-5` |
| `gemini/gemini-2.0-flash` (gemini) | Google's live list has no `gemini-2.0-*` at all | `gemini/gemini-3.5-flash-lite` |
| `grok-4-3` (xai) | xAI publishes `grok-4.3`, dotted; a completion on `grok-4-3` is a hard 404 | `grok-4.3` |

Two of those successors are worth calling out, because neither is the successor a
catalog-only lookup suggests. `claude-sonnet-4-5` is in models.dev but LiteLLM
marks it `deprecated 2026-11-30`, so shipping it would have recreated this exact
bug in three months — hence `-4-6`. `gemini-2.5-flash-lite` is likewise in
models.dev and is what the natural successor lookup returns, but Google 404s it
for a fresh key ("no longer available to new users"), hence `gemini-3.5-flash-lite`.
**Existence in the catalog is not servability for a new key** — that gap is
exactly what the per-provider live verification in #5000 closed by hand.

The file stays: it is the escape hatch for the next retired pin, and `--check`
fails if an entry is no longer needed.

## What this is **not** authoritative for

models.dev is a **curated capability and pricing database**, not a live route
registry. Do not treat it as one:

- **Route-suffix spellings.** Its `openrouter` slice is 390 rows and does not
  carry our `:free` slugs consistently (`liquid/lfm-2.5-2.6b:free` and friends
  miss). 48 of our 149 litellm route entries miss for this and related reasons —
  33 of the 88 distinct ids involved, which is why that check warns instead of
  failing.
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