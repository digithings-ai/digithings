---
provider: "Ollama Cloud"
slug: ollama-cloud
url: https://ollama.com/cloud
api_base: https://ollama.com/v1
litellm_prefix: openai
openai_compatible: true
free_tier: true
free_tier_type: metered
access_requirements:
  - email
  - ollama_account
data_privacy_on_free: unknown
verified_at: 2026-07-19
source_urls:
  - https://ollama.com/cloud
---

# Ollama Cloud

> **Free tier type:** metered — GPU-seconds on rolling 5h / 7-day windows; 1 concurrent model  
> **Access:** Ollama account  
> **Privacy:** not published

Ollama Cloud extends the popular local Ollama CLI into a cloud-hosted inference service via an OpenAI-compatible endpoint. The free tier is GPU-second metered on rolling windows — you get a compute budget that resets, not a fixed request count. The standout feature is the model catalog: very large open-weight models (DeepSeek V3.1 671B, Cogito 671B) are available on the free tier, giving access to frontier-class open-source models without a paid subscription. Context windows on these models are generous (163k on DeepSeek).

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `gpt-oss:20b` | 131,072 | 32,768 | active |
| `deepseek-v3.1:671b` | 163,840 | 32,768 | active |
| `cogito-2.1:671b` | 131,072 | 32,768 | active |
| `nemotron-3-super:cloud` | 1,048,576 | 32,768 | active |
| `deepseek-v4-flash` | 1,048,576 | 65,536 | active |
| `deepseek-v4-pro:cloud` | 1,048,576 | 65,536 | active |
| `kimi-k2-thinking` | 131,072 | 32,768 | **paid-only** |

> Model availability and free status change frequently. Verify at https://ollama.com/search.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| Compute budget | GPU-seconds on rolling 5h + 7-day windows |
| Concurrent models | 1 |
| RPM | Not published (budget-limited) |
| Context window | Model-dependent (up to 1M on Nemotron) |
| Quota reset | Rolling 5h and 7-day windows |

---

## LiteLLM Configuration

```yaml
# Ollama Cloud uses OpenAI-compatible passthrough
model_list:
  - model_name: ollama-deepseek-v3
    litellm_params:
      model: openai/deepseek-v3.1:671b
      api_key: os.environ/OLLAMA_API_KEY
      api_base: https://ollama.com/v1

  - model_name: ollama-nemotron
    litellm_params:
      model: openai/nemotron-3-super:cloud
      api_key: os.environ/OLLAMA_API_KEY
      api_base: https://ollama.com/v1
```

**Env var:** `OLLAMA_API_KEY`  
**Signup / key:** https://ollama.com → sign in → account settings

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Accessing very large open-weight models (671B) without paid tier; single-shot on DeepSeek |
| DIGI_LLM_MODE tier | `medium` (for 671B models with large context) |
| Single-shot 100k | Yes — DeepSeek V3.1 671B supports 163k; Nemotron supports 1M |
| Privacy safe | Unknown |
| Atlas/Hermes role | Large open-weight single-shot when DeepSeek API credits exhausted |

---

## Caveats

- GPU-second metering is opaque — hard to predict exactly how many calls your free budget supports. A 671B model call uses more seconds than an 8B call.
- Only 1 concurrent model on free — cannot run parallel requests to different models.
- Model catalog changes frequently; verify free status before building dependencies.
- Uses OpenAI-compatible passthrough — use `openai/` prefix in LiteLLM with custom `api_base`.

---

## Paid Upgrade

Ollama Cloud Pro: $20/month (50× free compute, 3 concurrent models). Max: $100/month.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
