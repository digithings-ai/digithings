---
provider: "Groq"
slug: groq
url: https://console.groq.com
api_base: https://api.groq.com/openai/v1
litellm_prefix: groq
openai_compatible: true
free_tier: true
free_tier_type: standing
access_requirements:
  - email
data_privacy_on_free: no_training
verified_at: 2026-07-19
source_urls:
  - https://console.groq.com/docs/rate-limits
  - https://console.groq.com/docs/models
---

# Groq

> **Free tier type:** standing — no expiry, no credit card  
> **Access:** email signup  
> **Privacy:** no training on free-tier data (based on current policy)

The fastest inference provider on the market (500–1,500 tok/s on Llama/Qwen via custom TSMC silicon). Free tier offers 14,400 RPD on flagship models — the highest daily request volume of any standing free provider. Primary role in DigiThings: high-throughput dev testing and production fallback where raw speed matters more than context depth.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `llama-3.3-70b-versatile` | 128,000 | 32,768 | active |
| `llama-4-scout-17b-16e-instruct` | 131,072 | 8,192 | **deprecated** |
| `openai/gpt-oss-120b` | 131,072 | 32,768 | active |
| `qwen/qwen3.6-27b` | 131,072 | 8,192 | active |

> Note: Kimi K2 (`moonshotai/kimi-k2-instruct`) moved to paid tier in early 2026 — verify current status at console.groq.com/docs/models before using.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| RPM (per model) | 30 |
| RPD (per model) | 14,400 |
| TPM (varies by model) | 6,000 – 30,000 |
| Quota reset | Rolling 24h |
| Max output tokens | 8,192 – 32,768 (model-dependent) |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: groq-llama
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY

  - model_name: groq-coder
    litellm_params:
      model: groq/qwen-2.5-coder-32b
      api_key: os.environ/GROQ_API_KEY

  - model_name: groq-reasoning
    litellm_params:
      model: groq/deepseek-r1-distill-llama-70b
      api_key: os.environ/GROQ_API_KEY
```

**Env var:** `GROQ_API_KEY`  
**Signup / key:** https://console.groq.com → API Keys

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | High-throughput dev testing; fast coding completions; production fallback chain anchor |
| DIGI_LLM_MODE tier | `test` (primary anchor) |
| Single-shot 100k | Yes — 128k context, but TPM (6k) limits throughput at large payloads |
| Privacy safe | Yes — no training on free data |
| Atlas/Hermes role | Fast extraction pass; structured JSON generation on chunked inputs |

---

## Caveats

- TPM limit of 6,000 on `llama-3.3-70b-versatile` is the binding constraint for large payloads — a 6k-token request saturates the TPM window in one call. Use exponential backoff.
- `llama-4-scout` and `llama-4-maverick` have higher TPM (30k) — prefer these for large-context work on Groq.
- Whisper STT is limited by audio-minutes/day (distinct quota from text models).
- Kimi K2 may have moved to paid — always check the model status page.
- Free tier is rate-limited per model, not per account, so rotating across multiple models can increase effective throughput.

---

## Paid Upgrade

Pay-as-you-go after free tier. Llama 3.3 70B ~$0.59/$0.79 per 1M in/out; Llama 4 Scout ~$0.11/$0.34; Llama 3.1 8B ~$0.05/$0.08. No monthly minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
