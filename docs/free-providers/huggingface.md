---
provider: "Hugging Face Inference API"
slug: huggingface
url: https://huggingface.co/inference-providers
api_base: https://api-inference.huggingface.co/models
litellm_prefix: huggingface
openai_compatible: false
free_tier: true
free_tier_type: credit-based
access_requirements:
  - email
data_privacy_on_free: unknown
verified_at: 2026-07-19
source_urls:
  - https://huggingface.co/docs/api-inference/en/rate-limits
  - https://huggingface.co/docs/api-inference/en/index
---

# Hugging Face Inference API

> **Free tier type:** credit-based — PRO plan ($9/month) includes ~$2 inference credits routed to upstream providers  
> **Access:** email signup; free tier very limited; PRO for meaningful usage  
> **Privacy:** routes to underlying providers (Together AI, Fireworks, SambaNova, etc.)

Hugging Face Inference Providers is a routing layer: your HF API call is routed to an underlying compute provider (Together AI, Fireworks, SambaNova, or others depending on the model). It's best thought of as a model-discovery hub rather than a primary inference provider. The free anonymous tier has very tight limits. PRO plan gives $2/month in credits. Most useful for: discovering and testing models, embeddings for DigiSearch, and prototyping before moving to a direct provider.

---

## Free-Tier Access Levels

| Tier | Cost | Credits / month | Rate limit |
|---|---|---|---|
| Anonymous | Free | None — very limited | Very tight |
| Free account | Free | None — slightly higher limits | Low |
| PRO | $9/month | ~$2 inference credits | Higher |

---

## Notable Models (PRO credits route to)

| Model ID | Context Window | Provider routed to |
|---|---|---|
| `meta-llama/Llama-3.3-70B-Instruct` | 131,072 | Together / Fireworks / SambaNova |
| `deepseek-ai/DeepSeek-R1` | 163,840 | Fireworks |
| `Qwen/Qwen2.5-72B-Instruct` | 131,072 | Together |
| `BAAI/bge-large-en-v1.5` | 512 | HF direct | Embeddings |
| `sentence-transformers/all-MiniLM-L6-v2` | 512 | HF direct | Embeddings (free) |

---

## Rate Limits

Rate limits are not published per-model on HF; they inherit from the underlying provider. Anonymous tier: effectively unusable for automation. PRO: limited by the $2 monthly credit.

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: hf-llama
    litellm_params:
      model: huggingface/meta-llama/Llama-3.3-70B-Instruct
      api_key: os.environ/HF_TOKEN

  - model_name: hf-embed
    litellm_params:
      model: huggingface/BAAI/bge-large-en-v1.5
      api_key: os.environ/HF_TOKEN
```

**Env var:** `HF_TOKEN` (HF User Access Token)  
**Signup / key:** https://huggingface.co/settings/tokens

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Model discovery; free embeddings (sentence-transformers models); DigiSearch indexing |
| DIGI_LLM_MODE tier | Not in primary chain — embeddings only |
| Single-shot 100k | Not recommended — credit limits too low |
| Privacy safe | Unknown (routes to third parties) |
| Atlas/Hermes role | **Not in research pipeline** — embeddings for DigiSearch only |

---

## Caveats

- The $2/month PRO credit depletes quickly with 70B model calls (~$0.001/call × 2000 = budget).
- HF is best as a unified model discovery and embedding endpoint, not as a primary LLM provider.
- Sentence-transformers embeddings (`all-MiniLM-L6-v2`, `all-mpnet-base-v2`) are effectively free and excellent for DigiSearch.
- LiteLLM's `huggingface/` prefix works for hosted inference endpoints; use `openai/` passthrough for HF Inference Endpoints (dedicated).

---

## Paid Upgrade

PRO plan at $9/month includes $2 inference credits. Inference Endpoints: dedicated compute starting at ~$0.06/hr for small GPUs.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
