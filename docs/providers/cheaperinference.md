# Cheaper Inference (hosted)

House upstream for digiquant (and digichat house when keyed) is **hosted Cheaper
Inference** at `https://api.cheaperinference.com/v1` — Chris’s “OmniRoute” naming
here means this product, **not** self-hosted OmniRoute Docker / `OMNIROUTE_*`.

## Prefer CI when keyed

When `CHEAPERINFERENCE_API_KEY` is set, digillm prefers CI and maps house slugs
in `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE` to bare CI model ids (#3648 / #3660).

Force OpenRouter: `DIGI_HOUSE_UPSTREAM=openrouter` (or `or`), or
`CHEAPERINFERENCE_HOUSE=0|false|no|off`.

## Fail closed (no quiet OpenRouter)

If CI is the selected house upstream and a house slug is **not** on the CI
catalog, digillm **raises** instead of silently falling back to OpenRouter.

Explicit override only: `DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK=1` (or
`true`/`yes`/`on`) restores quiet OpenRouter for catalog misses — loud log on
use. Prefer remapping pins to CI instead of enabling the override.

## Grounding (Chris lock, #3660)

CI has **no** Perplexity/sonar / `:online` search models. House grounding is:

1. **Retrieval** in-house: digisearch / digiquant `live_search` / data tools.
2. **Synthesis** on CI: primary `google/gemini-3.1-flash-lite`, alt
   `deepseek/deepseek-v4-flash` (see `web_search_models` in
   `config/digiquant_models.yaml` for all house tiers).

Do not pin `perplexity/sonar`, `meta-llama/llama-4-maverick`, or `:online`
variants in house phase pools or `web_search_models` when CI is preferred.

## Env (names only)

```bash
CHEAPERINFERENCE_API_KEY=...
CHEAPERINFERENCE_API_BASE=https://api.cheaperinference.com/v1   # optional
# DIGI_HOUSE_UPSTREAM=cheaperinference|openrouter
# DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK=0
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
- The `DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK` override is per-tenant — setting it
  for one does not affect the other.

It is an operator error to share a single `CHEAPERINFERENCE_API_KEY` between
different tenants expecting isolated model routing; each tenant should have its
own key and upstream configuration.
