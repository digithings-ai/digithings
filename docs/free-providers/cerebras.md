---
provider: "Cerebras Cloud"
slug: cerebras
url: https://cloud.cerebras.ai
api_base: https://api.cerebras.ai/v1
litellm_prefix: cerebras
openai_compatible: true
free_tier: true
free_tier_type: standing
access_requirements:
  - email
data_privacy_on_free: no_training
verified_at: 2026-07-19
source_urls:
  - https://inference-docs.cerebras.ai/introduction
  - https://inference-docs.cerebras.ai/api-reference
---

# Cerebras Cloud

> **Free tier type:** standing — no expiry, no credit card  
> **Access:** email signup  
> **Privacy:** no training on free-tier data

The fastest inference provider by raw throughput (>2,000 tok/s on Llama 3.3 70B via custom Wafer-Scale Engine silicon). Free tier provides ~1M tokens/day — the highest daily token budget of any free provider. The catch: context is capped at 8k tokens on the free tier for most models, making chunking mandatory for large research payloads. Best used for high-volume, fast-processing passes on pre-chunked inputs.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `llama-3.3-70b` | 128,000 | 8,192 | ⚠️ Error code: 404 - {'message': 'Model does not exist or you do not have access to it.', 'type': 'not_found_error', 'param': 'model', 'code': 'model_not_found'} |
| `llama-4-scout` | 131,072 | 8,192 | active |
| `qwen-3-32b` | 32,768 | 8,192 | active |
| `openai/gpt-oss-120b` | 131,072 | 8,192 | active |
| `qwen3-235b` | 131,072 | 8,192 | active |

> The 8k context cap on free tier is a platform policy, not a model limit. Full context (128k) requires the paid tier.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| RPM | 30 |
| RPD | 60 |
| Tokens / day | ~1,000,000 |
| TPM | Not published (infer from ~1M/day) |
| Max output / request | 8,192 |
| Quota reset | Calendar day |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: cerebras-llama-70b
    litellm_params:
      model: cerebras/llama-3.3-70b
      api_key: os.environ/CEREBRAS_API_KEY

  - model_name: cerebras-llama4-scout
    litellm_params:
      model: cerebras/llama-4-scout
      api_key: os.environ/CEREBRAS_API_KEY

  - model_name: cerebras-qwen
    litellm_params:
      model: cerebras/qwen-3-32b
      api_key: os.environ/CEREBRAS_API_KEY
```

**Env var:** `CEREBRAS_API_KEY` (prefix `csk-...`)  
**Signup / key:** https://cloud.cerebras.ai → API Keys → Generate

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | High-volume fast inference on pre-chunked inputs; speed-sensitive passes |
| DIGI_LLM_MODE tier | `test` (secondary to Groq; use for burst volume) |
| Single-shot 100k | **No** — free tier caps at 8k; chunk into 7k segments |
| Privacy safe | Yes |
| Atlas/Hermes role | Fast parallel extraction on chunked earnings/filing text |

**Chunking strategy for 100k payloads:**

```python
# Split into 7k-token chunks with 200-token overlap
# ~15 chunks for a 100k input; 15 * 8k = 120k total capacity
# At 1M tokens/day budget: ~125 full research payloads/day
```

---

## Caveats

- Context cap at ~8k on free tier is the primary limitation. Add a sleep between calls to avoid TPM accumulation — `time.sleep(0.5)` between consecutive requests.
- `qwen-3-32b` has native 32k context which fits fully on free tier — consider it when inputs are under 30k.
- Model catalog is narrower than Groq — treat as secondary fallback, not primary.
- RPD of 60 limits to 60 API calls/day; structure batching accordingly.
- Speed advantage (>2000 tok/s) is most valuable for agentic loops requiring fast turn-around.

---

## Paid Upgrade

Paid tier unlocks full 128k context and higher RPM/RPD. Llama 3.3 70B ~$0.60/$0.60 per 1M in/out. No monthly minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
