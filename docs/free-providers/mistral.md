---
provider: "Mistral AI (La Plateforme)"
slug: mistral
url: https://console.mistral.ai
api_base: https://api.mistral.ai/v1
litellm_prefix: mistral
openai_compatible: true
free_tier: true
free_tier_type: trial
access_requirements:
  - email
  - phone_verification
data_privacy_on_free: trains_on_data
verified_at: 2026-05-03
source_urls:
  - https://docs.mistral.ai/deployment/cloud/laplateforme/
  - https://mistral.ai/technology/#pricing
  - https://docs.mistral.ai/api/
---

# Mistral AI (La Plateforme — Experiment Tier)

> **Free tier type:** trial ("Experimental") — ongoing but explicitly for evaluation  
> **Access:** email + phone verification required  
> **Privacy:** ⚠️ Free tier allows training on your data. Use paid for any non-public inputs.

Mistral's "Experimental" free tier gives access to their full model lineup including Mistral Large and Codestral, with a generous ~1B tokens/month allowance. The tier is designed for evaluation and prototyping, not production. Strong European data sovereignty option on paid tier (GDPR, zero-retention). The 128k context on Large and the 262k context on Codestral make single-shot 100k+ document analysis possible without chunking.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `mistral-large-latest` | 131,072 | 131,072 | Flagship; strong reasoning |
| `mistral-small-latest` | 32,768 | 32,768 | Fast, cheap; good for extraction |
| `codestral-latest` | 262,144 | 262,144 | Best coding model; 256k ctx |
| `pixtral-large-latest` | 131,072 | 131,072 | Vision multimodal |
| `ministral-8b-latest` | 131,072 | 131,072 | Small fast model |
| `mistral-embed` | 8,192 | — | Embeddings |

> Codestral commercial use requires a paid Codestral plan even when accessed via Experimental tier — check ToS.

---

## Rate Limits (Free / Experimental Tier)

| Limit | Value |
|---|---|
| RPS (requests per second) | 1 |
| RPM | ~60 |
| TPM | 500,000 |
| Tokens / month | ~1,000,000,000 (1B) |
| Quota reset | Rolling minute; monthly reset |
| Max output | Model context window |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: mistral-large
    litellm_params:
      model: mistral/mistral-large-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: mistral-small
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: codestral
    litellm_params:
      model: mistral/codestral-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: mistral-embed
    litellm_params:
      model: mistral/mistral-embed
      api_key: os.environ/MISTRAL_API_KEY
```

**Env var:** `MISTRAL_API_KEY`  
**Signup / key:** https://console.mistral.ai → API Keys. Phone verification required.

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Large-context single-shot analysis (128k+); privacy-preferred open-weights on paid |
| DIGI_LLM_MODE tier | `medium` (Large); `test` (Small) |
| Single-shot 100k | Yes — 128k on Large, 256k on Codestral |
| Privacy safe | **No (free)** / Yes (paid — zero-retention) |
| Atlas/Hermes role | 128k single-shot research summarisation; Codestral for code analysis |

---

## Caveats

- 1 RPS (60 RPM) limit requires retries with exponential backoff — implement `tenacity` or similar.
- Experimental tier is not guaranteed SLA — treat as best-effort.
- Privacy: Mistral explicitly states free tier data may be used for model improvement.
- Codestral requires a separate Codestral licence for commercial use even on free tier.
- Phone verification is one-time; key persists after verification.

---

## Paid Upgrade

Enable billing in console. Same API key. Large ~$2/$6 per 1M in/out; Small ~$0.20/$0.60; Codestral ~$0.30/$0.90. Paid tier: GDPR-compliant, zero-retention, no training. No monthly minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
