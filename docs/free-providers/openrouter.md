---
provider: "OpenRouter"
slug: openrouter
url: https://openrouter.ai
api_base: https://openrouter.ai/api/v1
litellm_prefix: openrouter
openai_compatible: true
free_tier: true
free_tier_type: standing
access_requirements:
  - email
data_privacy_on_free: unknown
verified_at: 2026-07-19
source_urls:
  - https://openrouter.ai/docs#rate-limits
  - https://openrouter.ai/models?q=%3Afree
  - https://openrouter.ai/docs/api-reference
---

# OpenRouter

> **Free tier type:** standing — `:free` model routing  
> **Access:** email signup; adding $10 credit unlocks higher RPD  
> **Privacy:** varies by model — each `:free` endpoint routes to a third-party host; check individual model cards for data policies

OpenRouter is an aggregator that routes requests to underlying providers via a single OpenAI-compatible API key. The `:free` suffix on a model ID routes to a subsidised endpoint at no cost. Context windows on `:free` variants are often lower than the paid equivalents (hosts cap free context to manage costs). Best used for model experimentation and as a fallback chain last-resort — reliability varies by underlying host.

---

## Free-Tier Models (`:free` endpoints — roster rotates)

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `deepseek/deepseek-chat-v3:free` | 163,840 | 8,192 | active |
| `deepseek/deepseek-chat-v3-0324:free` | 163,840 | 8,192 | active |
| `deepseek/deepseek-r1:free` | 163,840 | 8,192 | active |
| `meta-llama/llama-3.3-70b-instruct:free` | 131,072 | 8,192 | ⚠️ Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'meta-llama/llama-3.3-70b-instruct:free is temporarily rate-limited upstream...', 'provider_name': 'Venice'}}} |
| `google/gemini-2.0-flash-exp:free` | 1,048,576 | 8,192 | active |
| `qwen/qwen3-235b-a22b:free` | 131,072 | 8,192 | active |
| `openai/gpt-oss-20b:free` | 131,072 | 8,192 | active |
| `qwen/qwen3-coder:free` | 1,048,576 | 8,192 | active |

> **The `:free` roster changes weekly.** Check https://openrouter.ai/models?q=:free for the current list. Models listed above were active as of 2026-05-03.

---

## Rate Limits (Free Tier)

| Limit | Condition | Value |
|---|---|---|
| RPM | All free accounts | 20 |
| RPD | Balance < $10 | 50 |
| RPD | Balance ≥ $10 | 1,000 |
| Context window | `:free` vs paid | Often lower — check per model |

Adding $10 once (not recurring) permanently unlocks 1,000 RPD.

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: openrouter-deepseek
    litellm_params:
      model: openrouter/deepseek/deepseek-chat-v3-0324:free
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: openrouter-gemini
    litellm_params:
      model: openrouter/google/gemini-2.0-flash-exp:free
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: openrouter-llama
    litellm_params:
      model: openrouter/meta-llama/llama-3.3-70b-instruct:free
      api_key: os.environ/OPENROUTER_API_KEY
```

**Env var:** `OPENROUTER_API_KEY`  
**Signup / key:** https://openrouter.ai → Settings → API Keys

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Model experimentation; last-resort fallback in chain; accessing models not available elsewhere |
| DIGI_LLM_MODE tier | `test` (fallback tail in chain) |
| Single-shot 100k | Yes, via `google/gemini-2.0-flash-exp:free` (1M ctx) — when available |
| Privacy safe | Unknown — check per-model data policy card on openrouter.ai |
| Atlas/Hermes role | Fallback if primary providers hit rate limits |

---

## Caveats

- `:free` endpoints have variable latency and queue depth — not suitable as primary in production.
- Some `:free` models become paid without notice; implement model-availability checks.
- The `google/gemini-2.0-flash-exp:free` endpoint offers 1M context at no cost — valuable when Gemini AI Studio RPD is exhausted.
- Check `X-RateLimit-*` response headers for dynamic limit feedback.
- BYO-key mode (bring your own Anthropic/OpenAI key via OpenRouter) adds a 5% surcharge.

---

## Paid Upgrade

Deposit credit ($10 minimum recommended to unlock 1,000 RPD). Routes to upstream providers with ~0–5% markup. No monthly minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
