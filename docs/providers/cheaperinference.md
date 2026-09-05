# Cheaper Inference (hosted)

**Cost:** usage-based wallet. Cheaper Inference is a **hosted** OpenAI-compatible
discount gateway (`https://api.cheaperinference.com/v1`). It is the **digillm house
default** whenever `CHEAPERINFERENCE_API_KEY` is set — distinct from self-hosted
[OmniRoute](omniroute.md) (`OMNIROUTE_*`).

**Best for:** routing house DeepSeek / Gemini Flash / GPT-5.6 pins through a
cheaper upstream while keeping OpenRouter for catalog misses (`perplexity/sonar`,
`:online`, `meta-llama/llama-4-maverick`, `x-ai/grok-4.3|4.6`, and Anthropic until
a quality bake-off).

House traffic remains **service → digillm → LiteLLM** (or the CLI/GHA OpenAI-compat
rewrite). Do not call Cheaper Inference from application code with a vendor SDK
bypass.

## Guardrails

- Secrets via env only (`.env`, GitHub Actions secrets, Cloudflare `wrangler secret`).
  Never commit keys.
- Key prefix: `ci_live_…`. Base: `https://api.cheaperinference.com/v1`.
- **Do not** cut quality-tier Anthropic pins to CI without a bake-off.
- **Do not** confuse this with OmniRoute (`OMNIROUTE_*`, `docs/providers/omniroute.md`).
- Catalog ids are **bare** (`deepseek-v4-flash`). digiquant pins stay OpenRouter-style
  (`deepseek/deepseek-v4-flash`); LiteLLM / digillm map them.

## 1. Credentials

```bash
# .env — key alone enables house default
CHEAPERINFERENCE_API_KEY=ci_live_...
CHEAPERINFERENCE_API_BASE=https://api.cheaperinference.com/v1
# Force OpenRouter for house traffic even when the CI key is set:
# DIGI_HOUSE_UPSTREAM=openrouter
# (alias off) CHEAPERINFERENCE_HOUSE=0
```

GitHub Actions: repository secret `CHEAPERINFERENCE_API_KEY` and optional var/secret
`CHEAPERINFERENCE_API_BASE`. `pipeline-digiquant.yml` passes both into the job env.
`.github/digiquant-pipeline.yml` may still set `DIGI_HOUSE_UPSTREAM=cheaperinference`
explicitly; that is redundant once the key is present.

### Force OpenRouter

Set `DIGI_HOUSE_UPSTREAM=openrouter` (or `or`), or `CHEAPERINFERENCE_HOUSE=0`.

## 2. LiteLLM overlay (stack / proxy)

LiteLLM has no include directive. Merge the overlay over the default config when
the CI key is present (house default):

```bash
python scripts/merge_litellm_cheaperinference.py -o /tmp/litellm.merged.yaml
# then LITELLM_CONFIG=/tmp/litellm.merged.yaml  (compose or litellm --config)
```

Overlay file: `config/litellm.cheaperinference.yaml`. Matching `model_name` keys
are replaced; OpenRouter entries for sonar / `:online` / maverick / grok-4.3|4.6 /
anthropic remain from `config/litellm.yaml`.

The digithings Cloudflare stack container merges this overlay at boot when
`CHEAPERINFERENCE_API_KEY` is set (unless OpenRouter is forced). Put the key/base
via `wrangler secret put CHEAPERINFERENCE_API_KEY` (and optional base).

Mapped house slugs → CI bare ids:

| House pin (`digiquant_models.yaml`) | CI model id |
|---|---|
| `deepseek/deepseek-v4-flash` | `deepseek-v4-flash` |
| `deepseek/deepseek-v4-pro` | `deepseek-v4-pro` |
| `google/gemini-3.7-flash` | `gemini-3.7-flash` |
| `openai/gpt-5.6-luna` | `gpt-5.6-luna` |
| `openai/gpt-5.6-sol` | `gpt-5.6-sol` |

Stay on OpenRouter: `meta-llama/llama-4-maverick`, `perplexity/sonar`, all `:online`
variants, `x-ai/grok-4.3`, `x-ai/grok-4.6` (CI lists `grok-4.5` only — do not silently
remap), `anthropic/claude-sonnet-5` (bake-off).

## 3. CLI / GHA without LiteLLM

`apply_digiquant_openrouter_env()` (chain startup + validate-providers preflight):

- If `OPENAI_API_BASE` is already set (LiteLLM), leave it alone.
- Else if Cheaper Inference is preferred (`CHEAPERINFERENCE_API_KEY` set and not
  forced to OpenRouter), set `OPENAI_API_BASE` / `OPENAI_API_KEY` from
  `CHEAPERINFERENCE_*`.
- Else keep the OpenRouter rewrite (unchanged).

digillm then rewrites mapped house slugs to bare CI ids on the CI base, and routes
catalog misses to the OpenRouter client (`OPENROUTER_API_KEY` still required for
grounding / unmapped pins).

## 4. Verify

```bash
curl -sS "${CHEAPERINFERENCE_API_BASE%/}/models" \
  -H "Authorization: Bearer $CHEAPERINFERENCE_API_KEY" | head
```

Do not print the key. Unit tests register the overlay without calling the paid API.

## Out of scope

- digichat / dashboard BYOK UI centralization (follow-up #3647)
- Cutting Anthropic quality pins to CI without bake-off
- Renaming or replacing OmniRoute docs
- Silently mapping `grok-4.3` / `grok-4.6` → `grok-4.5`

## Docs

https://cheaperinference.com/docs
