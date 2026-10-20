# Cheaper Inference (hosted)

House upstream for digiquant (and digichat house when keyed) is **hosted Cheaper
Inference** at `https://api.cheaperinference.com/v1` — Chris’s “OmniRoute” naming
here means this product, **not** self-hosted OmniRoute Docker / `OMNIROUTE_*`.

## Prefer CI when keyed

When `CHEAPERINFERENCE_API_KEY` is set, digillm prefers CI and maps house slugs
in `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE` to bare CI model ids (#3648 / #3660).
That holds even if `OPENROUTER_API_KEY` is also set and `OPENAI_API_BASE` still
points at OpenRouter — mapped house slugs do **not** stay on OpenRouter.
On the Cloudflare stack container, entrypoint merges the CI LiteLLM overlay and
exports `ENV_LITELLM_CONFIG` for the LiteLLM supervisor (#3674). LiteLLM proxy
keeps house `model_name` keys (overlay routes them).

The merge is verified, and it fails loudly: the merged `model_list` must carry
every curated house model (`DIGI_SESSION_MODEL_ALLOWLIST`), and a merge that
fails, or an overlay asset that is missing, stops the container boot with a
FATAL line instead of serving the base file. The base file the image ships has
no curated model, so serving it answers every curated tenant model with
model-not-found while the health probe stays green (DIG-4512).

Force OpenRouter: `DIGI_HOUSE_UPSTREAM=openrouter` (or `or`), or
`CHEAPERINFERENCE_HOUSE=0|false|no|off`.

## Fail fast (no OpenRouter fallback)

If CI is the selected house upstream and a house slug is **not** on the CI
catalog, digillm **raises** — there is no fallback to OpenRouter. A bad pin
fails the run loudly so it can be fixed, instead of spending silently on
another upstream.

## Grounding (tool-only, #3859)

CI has **no** Perplexity/sonar / `:online` search models. House grounding is
tool-only: the first-party digisearch `web_search` tool (searxng sidecar with
ddgs fallback). There are no synthesis-model pins and no fallback.

Do not pin `perplexity/sonar`, `meta-llama/llama-4-maverick`, or `:online`
variants in house phase pools when CI is preferred.

## Env (names only)

```bash
CHEAPERINFERENCE_API_KEY=...
CHEAPERINFERENCE_API_BASE=https://api.cheaperinference.com/v1   # optional
# DIGI_HOUSE_UPSTREAM=cheaperinference|openrouter
```

GitHub Actions: repository secret `CHEAPERINFERENCE_API_KEY` (pipeline already
passes it). Weekday house bill/route proof via CI logs is a Human Gate after
land — not automated in this PR.

## Tenant isolation (digithings.ai digichat vs digiquant.io dashboard)

- **digithings.ai digichat** is a separate tenant/product with its own
  `CHEAPERINFERENCE_API_KEY` and house upstream configuration. Its LiteLLM
  overlay is merged per the same rules as digiquant, but model pins and tier
  policies are independent — changes to digiquant `config/digiquant_models.yaml`
  do not affect digichat, and vice versa.
- **digiquant.io dashboard** (embedded) uses its own `CHEAPERINFERENCE_API_KEY`
  and `config/digiquant_models.yaml` tier policy. The dashboard UI owns embed/tenant
  UX (#3664). Do not conflate digichat tenant configs with digiquant dashboard
  embed configs.
- When `DIGI_HOUSE_UPSTREAM=cheaperinference` is set on either tenant, the
  corresponding `digillm` client maps house slugs to CI bare ids independently.

It is an operator error to share a single `CHEAPERINFERENCE_API_KEY` between
different tenants expecting isolated model routing; each tenant should have its
own key and upstream configuration.

## digichat public picker (#3829)

digithings.ai and the OCC embed resolve the picker from
`apps/digichat/config/model-picker-catalog.json`: presets first (Auto,
Reasoning, Fast, Light, and the OpenRouter router when that key is set), then
the newest generation of each family that is tool-capable, at or above the
context floor, and under the deployment's output-price cap. Older generations
stay in the catalog file; the resolver drops them. Models above that cap and
at or under the premium cap ($2.50) are a separate Premium group: manual
picks only, never Auto, the other presets, or the router. digithings.ai meters
those picks at $0.0125565 per user per rolling day (three typical turns of
GLM 5.3). OCC meters the same amount because its picker is on. The default
preset is `deepseek/deepseek-v4.1-flash-1017` (DeepSeek V4.1 Flash 1017 on
Cheaper Inference). Cheaper Inference has no router model. OpenRouter is not a
free model list on that picker; `openrouter/auto` appears only as the Router
preset, and only when `OPENROUTER_API_KEY` is set at load. The router receives
the deployment's allowed ids except the Premium group. digillm drops any
Premium id that still arrives on `X-Digi-Premium-Models`.

The dashboard (`dashboard-modal.yaml`) keeps its own three-slug list:
`deepseek/deepseek-v4.1-flash-1017`, `openai/gpt-oss-120b`, and
`z-ai/glm-5.3-flash`. The Foundry trial embed uses Azure Foundry and does not
inherit this catalog.

Every house id on the catalog is on `config/litellm.cheaperinference.yaml`
(tested). `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE` maps the ids added for the
catalog; some older ids are not in that map. The BFF rejects any other house
`X-Digi-Model`, and digigraph binds only ids on the capped
`DIGI_SESSION_MODEL_ALLOWLIST`. The OpenRouter router preset is off in the
shipped configs.

The 2026-10-21 snapshot was left as fetched. A later markets HTML differed
on six non-premium rows (mimo-v2.6-flash 0.2013 vs 0.2380, qwen3.8-flash
0.3055 vs 0.3289, qwen3.8-max 4.1251 vs 3.9, gpt-6-luna 0.3734 vs 0.3763,
gpt-5.6-luna 0.4935 vs 0.48, deepseek-v4-pro-0813 1.6830 vs 0.99).
`deepseek-v4-flash-0731-fast` is not on that listing. The Premium rows
match, and the preset winners at the $2 cap are unchanged. Re-pulling the
catalog is deferred.

**BYOK** (`gate.showByok`): connecting a visitor provider replaces `/models`
with that provider’s presets (existing BYOK catalog). The house allowlist does
not apply while a BYOK key is bound.

House LiteLLM overlay routes those slugs to `api.cheaperinference.com` when
`CHEAPERINFERENCE_API_KEY` is set. Direct digillm clients do the same even when
`OPENAI_API_BASE` still points at OpenRouter. Force OpenRouter:
`DIGI_HOUSE_UPSTREAM=openrouter`.
