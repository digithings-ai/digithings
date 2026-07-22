---
provider: "Fireworks AI"
slug: fireworks-ai
url: https://fireworks.ai
api_base: https://api.fireworks.ai/inference/v1
litellm_prefix: fireworks_ai
openai_compatible: true
free_tier: true
free_tier_type: credit-based
access_requirements:
  - email
data_privacy_on_free: no_training
verified_at: 2026-05-03
source_urls:
  - https://docs.fireworks.ai/api-reference/rate-limiting
  - https://fireworks.ai/pricing
---

# Fireworks AI

> **Free tier type:** credit-based — $1 starter credit on signup  
> **Access:** email signup  
> **Privacy:** US-based; no training on user data

Fireworks AI specialises in fast open-weight model inference with a focus on agentic workflows and function-calling. The $1 starter credit is minimal but functional for initial evaluation. Key value-adds: hosting large-context models like Kimi K2.5 (256k) and access to DeepSeek V3 in a Western jurisdiction — solving the China-data-law problem for DeepSeek. The FireFunction v2 model is purpose-built for reliable tool-calling.

---

## Free-Tier Models ($1 credit)

| Model ID | Context Window | Max Output | $/1M in | $/1M out | Notes |
|---|---|---|---|---|---|
| `accounts/fireworks/models/llama-v3p3-70b-instruct` | 131,072 | 8,192 | $0.90 | $0.90 | Llama 3.3 70B |
| `accounts/fireworks/models/deepseek-r1` | 163,840 | 16,384 | $3.00 | $8.00 | DeepSeek R1 (Western-hosted) |
| `accounts/fireworks/models/deepseek-v3` | 163,840 | 8,192 | $0.90 | $0.90 | DeepSeek V3 (Western-hosted) |
| `accounts/fireworks/models/kimi-k2-instruct` | 262,144 | 16,384 | (verify) | (verify) | Kimi K2.5; 256k context |
| `accounts/fireworks/models/qwen2p5-72b-instruct` | 131,072 | 8,192 | $0.90 | $0.90 | Qwen 2.5 72B |
| `accounts/fireworks/models/firefunction-v2` | 32,768 | 4,096 | $0.90 | $0.90 | Best free-tier tool-calling |

---

## Rate Limits (Free / Credit Tier)

| Limit | Value |
|---|---|
| Starter credit | $1.00 USD |
| Credit expiry | Not published |
| RPM | Not hard-limited (credit-gated) |
| Max output | 8,192 – 16,384 (model-dependent) |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: fireworks-llama
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct
      api_key: os.environ/FIREWORKS_API_KEY

  - model_name: fireworks-deepseek-v3
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/deepseek-v3
      api_key: os.environ/FIREWORKS_API_KEY

  - model_name: fireworks-deepseek-r1
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/deepseek-r1
      api_key: os.environ/FIREWORKS_API_KEY
```

**Env var:** `FIREWORKS_API_KEY`  
**Signup / key:** https://fireworks.ai → API → Keys

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Western-jurisdiction DeepSeek V3/R1; large-context Kimi K2.5 (256k); reliable tool-calling |
| DIGI_LLM_MODE tier | `medium` (DeepSeek via Fireworks for privacy-safe research) |
| Single-shot 100k | Yes — 131k–262k context on key models |
| Privacy safe | Yes — US-hosted, no training |
| Atlas/Hermes role | Privacy-safe DeepSeek R1 for quantitative reasoning; Kimi K2.5 for large filings |

---

## Caveats

- $1 credit is very limited — approximately 1,100 Llama 70B calls or 330 DeepSeek V3 calls.
- Fireworks is effectively a **cheap paid provider** more than a free one — treat the $1 as trial runway.
- FireFunction v2 is purpose-built for agent tool-calling reliability.
- Kimi K2.5 with 256k context is a strong option for full-document analysis if pricing is competitive.

---

## Paid Upgrade

Add credit — no monthly minimum. Llama 70B: $0.90/$0.90 per 1M. DeepSeek V3: $0.90/$0.90. DeepSeek R1: $3.00/$8.00.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
