---
provider: "DeepSeek API"
slug: deepseek
url: https://platform.deepseek.com
api_base: https://api.deepseek.com/v1
litellm_prefix: deepseek
openai_compatible: true
free_tier: true
free_tier_type: credit-based
access_requirements:
  - email
data_privacy_on_free: regional_law
verified_at: 2026-05-03
source_urls:
  - https://api-docs.deepseek.com/quick_start/pricing
  - https://platform.deepseek.com/api-docs
---

# DeepSeek API

> **Free tier type:** credit-based — 5M free tokens on signup (new accounts)  
> **Access:** email signup  
> **Privacy:** ⚠️ Servers hosted in China — prompts subject to Chinese data law. Use Western-jurisdiction mirrors (Fireworks, Together, DeepInfra) for sensitive inputs.

DeepSeek offers the strongest math/quantitative reasoning of any free-accessible model, making it the top choice for financial modeling, ratio extraction, earnings analysis, and structured output generation. The 5M token signup grant provides meaningful runway for evaluation; after that, pricing is the cheapest frontier-class inference available. The direct API is China-hosted — for MNPI or client data, use the same model weights via Fireworks or Together AI instead.

---

## Free-Tier Models (5M token grant)

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `deepseek-chat` | 65,536 | 8,192 | DeepSeek V3; strong reasoning + coding |
| `deepseek-reasoner` | 65,536 | 8,192 | DeepSeek R1; chain-of-thought reasoning |

> DeepSeek V4 / R2 variants may be available by the time you read this — check platform.deepseek.com for the current model list.

---

## Rate Limits (Credit / Free Tier)

| Limit | Value |
|---|---|
| Free token grant | 5,000,000 tokens (new accounts) |
| Grant expiry | Check platform — may be time-limited |
| RPM | Dynamic — no hard published limit |
| RPD | Dynamic |
| Concurrent requests | Not published |
| Context window | 65,536 (V3/R1) |

Rate limits scale dynamically with load — no hard caps published. Implement retries regardless.

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

  - model_name: deepseek-reasoner
    litellm_params:
      model: deepseek/deepseek-reasoner
      api_key: os.environ/DEEPSEEK_API_KEY
```

**Env var:** `DEEPSEEK_API_KEY`  
**Signup / key:** https://platform.deepseek.com → API Keys

---

## Western-Jurisdiction Mirrors (for sensitive data)

Same weights, Western data jurisdiction:

| Provider | Model ID | $/1M in | $/1M out |
|---|---|---|---|
| Fireworks | `accounts/fireworks/models/deepseek-v3` | $0.90 | $0.90 |
| Together AI | `deepseek-ai/DeepSeek-V3` | $0.90 | $0.90 |
| DeepInfra | `deepseek-ai/DeepSeek-V3` | $0.49 | $0.89 |
| OpenRouter | `deepseek/deepseek-chat-v3:free` | $0 (free tier) | $0 |

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Financial math/reasoning; structured JSON extraction; quantitative analysis |
| DIGI_LLM_MODE tier | `medium` to `best` (for reasoning tasks) |
| Single-shot 100k | **Partial** — 65k context; 100k inputs require chunking or use V4 variants |
| Privacy safe | **No (direct)** — China-hosted; use Fireworks/Together for sensitive inputs |
| Atlas/Hermes role | Deep quantitative reasoning pass; EPS/guidance extraction; risk scoring |

---

## Caveats

- China-hosted: all prompts sent to `api.deepseek.com` pass through servers subject to Chinese data regulation. Do not send MNPI, client data, or confidential filings to the direct API.
- 65k context on current V3/R1 is below 100k — chunking or map-reduce required for full 10-K analysis. DeepSeek V4 targets 1M context (verify availability).
- The 5M token grant is one-time on new accounts — verify if it has an expiry date at signup.
- After credits: among the cheapest frontier inference ($0.27/$1.10 per 1M in/out for V3).
- Off-peak discount available (50% off between UTC 16:30–00:30) — use for batch Atlas runs.

---

## Paid Upgrade

After grant: $0.27/$1.10 per 1M in/out (V3/chat); $0.55/$2.19 (R1/reasoner). Off-peak 50% discount. No minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
