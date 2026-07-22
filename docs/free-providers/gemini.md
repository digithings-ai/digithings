---
provider: "Google AI Studio (Gemini)"
slug: google-ai-studio
url: https://aistudio.google.com
api_base: https://generativelanguage.googleapis.com/v1beta
litellm_prefix: gemini
openai_compatible: false
free_tier: true
free_tier_type: standing
access_requirements:
  - google_account
data_privacy_on_free: trains_on_data
verified_at: 2026-05-03
source_urls:
  - https://ai.google.dev/gemini-api/docs/rate-limits
  - https://ai.google.dev/gemini-api/docs/models
  - https://ai.google.dev/pricing
---

# Google AI Studio (Gemini)

> **Free tier type:** standing — no expiry, no credit card  
> **Access:** Google account only  
> **Privacy:** ⚠️ Free-tier prompts/responses are used to improve Google products. Never send confidential data on free tier.

The context king of the free-tier landscape. Gemini 2.5 Flash offers the largest free context window available (1M tokens) with the highest free RPD, making it the default choice for single-shot large-document ingestion (earnings transcripts, 10-Ks, multi-file research payloads). Flash-Lite maximises volume; Pro provides deeper reasoning at lower rate limits.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | RPM | RPD | TPM | Notes |
|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | 1,048,576 (1M) | 65,536 | 10 | 250 | 250,000 | Workhorse; vision, audio, structured output |
| `gemini-2.5-flash-lite` | 1,048,576 (1M) | 65,536 | 15 | 1,000 | 1,000,000 | Highest free RPD; use for volume |
| `gemini-2.5-pro` | 2,097,152 (2M) | 65,536 | 5 | 100 | 250,000 | Strongest reasoning; 2M ctx |
| `text-embedding-004` | 2,048 | — | 1,500 | — | — | Embeddings; task-type param supported |

---

## Rate Limits (Free Tier)

Per-model limits above. Account-level summary:

| Limit | Flash | Flash-Lite | Pro |
|---|---|---|---|
| RPM | 10 | 15 | 5 |
| RPD | 250 | 1,000 | 100 |
| TPM | 250,000 | 1,000,000 | 250,000 |
| Quota reset | Calendar day (UTC) | Calendar day (UTC) | Calendar day (UTC) |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: gemini-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-flash-lite
    litellm_params:
      model: gemini/gemini-2.5-flash-lite
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-2.5-pro
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-embeddings
    litellm_params:
      model: gemini/text-embedding-004
      api_key: os.environ/GEMINI_API_KEY
```

**Env var:** `GEMINI_API_KEY`  
**Signup / key:** https://aistudio.google.com → Get API key

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Single-shot 100k–1M context ingestion; long-doc synthesis; embeddings |
| DIGI_LLM_MODE tier | `test` (Flash-Lite), `medium` (Flash), `best` (Pro) |
| Single-shot 100k | Yes — up to 1M tokens without chunking |
| Privacy safe | **No** — free tier trains on data; use paid for confidential research |
| Atlas/Hermes role | Initial large-context ingestion pass before routing to reasoning model |

---

## Caveats

- Free-tier quotas tightened in April 2026; Pro now heavily rate-limited (100 RPD).
- **Data privacy:** Google may use free-tier inputs for model training. Do not send MNPI, client data, or confidential filings on the free key.
- Context window vs effective rate: at 100k tokens/request, 1M TPM Flash-Lite allows ~10 requests/minute — context and TPM can co-limit.
- JSON mode and tool-calling are available on all Flash/Pro variants.
- `gemini/` prefix in LiteLLM uses the Gemini SDK path, not OpenAI-compatible. For OpenAI-compat endpoint: `https://generativelanguage.googleapis.com/v1beta/openai`.

---

## Paid Upgrade

Enable billing on the linked Google Cloud project — same API key, zero extra config. Paid tier is **zero-retention**. Pricing: Flash ~$0.30/$2.50 per 1M in/out; Flash-Lite ~$0.10/$0.40; Pro ~$1.25/$10 (≤200k), $2.50/$15 (>200k). Prompt caching available on paid.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
