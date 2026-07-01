---
provider: "Cloudflare Workers AI"
slug: cloudflare-workers-ai
url: https://developers.cloudflare.com/workers-ai
api_base: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run
litellm_prefix: cloudflare
openai_compatible: false
free_tier: true
free_tier_type: standing
access_requirements:
  - email
  - cloudflare_account
data_privacy_on_free: no_training
verified_at: 2026-05-03
source_urls:
  - https://developers.cloudflare.com/workers-ai/platform/pricing/
  - https://developers.cloudflare.com/workers-ai/models/
---

# Cloudflare Workers AI

> **Free tier type:** standing — 10,000 neurons/day, no expiry, no credit card  
> **Access:** Cloudflare account (free)  
> **Privacy:** Cloudflare privacy policy; data processed at Cloudflare edge

Cloudflare Workers AI runs inference at the Cloudflare edge network, metered in "neurons" (an internal unit roughly proportional to compute cost). The 10,000 neuron/day free allowance equates to a few thousand small-model API calls, making it best suited as a supplemental provider or edge-deployed inference companion rather than a primary research engine. Context windows are small (~8k on most models). The neuron accounting is opaque and varies by model.

---

## Free-Tier Models (selection)

| Model ID | Context Window | Max Output | Neurons/call (approx) | Notes |
|---|---|---|---|---|
| `@cf/meta/llama-3.3-70b-instruct` | 8,192 | 8,192 | ~100–200 | Llama 3.3 70B |
| `@cf/meta/llama-3.1-8b-instruct` | 8,192 | 8,192 | ~20–50 | Llama 3.1 8B; cheapest |
| `@cf/qwen/qwen1.5-14b-chat-awq` | 8,192 | 8,192 | ~50 | Qwen 1.5 14B |
| `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | 8,192 | 8,192 | ~100 | DeepSeek R1 Qwen distill |
| `@cf/baai/bge-large-en-v1.5` | 512 | — | ~5 | BGE embeddings |
| `@cf/openai/whisper` | — | — | variable | Whisper STT |
| `@cf/black-forest-labs/flux-1-schnell` | — | — | variable | Image generation |

> At ~100–200 neurons per 70B call, the 10k daily budget = ~50–100 Llama 70B calls.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| Neurons / day | 10,000 |
| RPM | Not published |
| Context window | ~8,192 (most models) |
| Quota reset | Calendar day |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: cloudflare-llama
    litellm_params:
      model: cloudflare/@cf/meta/llama-3.3-70b-instruct
      api_key: os.environ/CLOUDFLARE_API_KEY
      # Also requires: api_base with account_id
      api_base: https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run
```

**Env vars:** `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID`  
**Signup / key:** https://dash.cloudflare.com → Workers & Pages → Workers AI → API Token

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Low-volume supplemental calls; edge-deployed inference from Workers runtime; embeddings |
| DIGI_LLM_MODE tier | `test` (supplemental — small context and low daily budget) |
| Single-shot 100k | **No** — 8k context cap requires heavy chunking |
| Privacy safe | Yes (Cloudflare processes data; no model training) |
| Atlas/Hermes role | BGE embeddings for DigiSearch; not suitable for research pipeline |

---

## Caveats

- Neuron accounting is opaque — exact cost per call varies by model and input length. Monitor your dashboard.
- 8k context is a hard cap on all current Workers AI models — unsuitable for large document research.
- Best used from within Cloudflare Workers runtime (Workers R2 + AI is a natural pairing for edge RAG).
- REST API works outside Workers but `api_base` must include account ID — set `CLOUDFLARE_ACCOUNT_ID` in env.
- No structured output (JSON mode) or tool-calling on most models.

---

## Paid Upgrade

$0.011 per 1,000 neurons beyond the free 10,000/day. Effective cost: ~$0.001–$0.002 per Llama 70B call.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
