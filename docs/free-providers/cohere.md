---
provider: "Cohere"
slug: cohere
url: https://cohere.com
api_base: https://api.cohere.com/v2
litellm_prefix: cohere
openai_compatible: false
free_tier: true
free_tier_type: trial
access_requirements:
  - email
data_privacy_on_free: unknown
verified_at: 2026-05-03
source_urls:
  - https://cohere.com/pricing
  - https://docs.cohere.com/docs/rate-limits
---

# Cohere (Trial Tier)

> **Free tier type:** trial — 20 RPM, non-production only  
> **Access:** email signup  
> **Privacy:** trial keys not for production; prompts may be used for evaluation  
> **⚠️ ToS:** trial tier explicitly restricted to **non-production, evaluation use only**

Cohere's trial key provides access to Command A (their flagship 256k context model) and best-in-class Embed v3 / Rerank v3 models at no cost. The 20 RPM rate limit and non-production restriction make it suitable for prototyping RAG pipelines and evaluating document analysis quality — not for automated daily research runs. Command A with 256k context is the most compelling free offering for financial document RAG (full 10-K in one shot).

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `command-a-03-2025` | 256,000 | 8,192 | Flagship; 256k context; RAG-optimised |
| `command-r-plus` | 128,000 | 4,096 | Previous flagship; good RAG |
| `command-r` | 128,000 | 4,096 | Fast; lower cost |
| `embed-english-v3.0` | 512 | — | Best-in-class embeddings |
| `embed-multilingual-v3.0` | 512 | — | Multilingual embeddings |
| `rerank-english-v3.0` | — | — | Reranking; excellent for RAG |
| `rerank-multilingual-v3.0` | — | — | Multilingual reranking |

---

## Rate Limits (Trial Tier)

| Limit | Value |
|---|---|
| RPM | 20 |
| API calls / month | ~1,000 (trial cap) |
| Max output | 8,192 |
| Quota reset | Monthly |

The ~1,000 calls/month cap makes daily automation impossible — at 1 call/day you'd exhaust it in 3 months.

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: cohere-command-a
    litellm_params:
      model: cohere/command-a-03-2025
      api_key: os.environ/COHERE_API_KEY

  - model_name: cohere-embed
    litellm_params:
      model: cohere/embed-english-v3.0
      api_key: os.environ/COHERE_API_KEY

  - model_name: cohere-rerank
    litellm_params:
      model: cohere/rerank-english-v3.0
      api_key: os.environ/COHERE_API_KEY
```

**Env var:** `COHERE_API_KEY`  
**Signup / key:** https://dashboard.cohere.com/api-keys

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Evaluating RAG quality; testing Rerank v3 for DigiSearch; 256k context prototyping |
| DIGI_LLM_MODE tier | Not in automated pipeline — trial only |
| Single-shot 100k | Yes — 256k context on Command A; ideal for full 10-K |
| Privacy safe | Trial keys not for production use |
| Atlas/Hermes role | **Not in pipeline** — Embed v3 / Rerank v3 are the standout tools |

---

## Caveats

- Trial **non-production restriction** is hard — don't use trial keys in any automated workflow touching real data.
- Monthly call cap (~1,000) makes it unsuitable for any recurring automated analysis.
- **Embed v3 and Rerank v3 are genuinely best-in-class** — worth evaluating for DigiSearch even if Command A isn't used in production.
- API is not OpenAI-compatible natively — Cohere has its own SDK + LiteLLM handles translation.
- For production: Embed v3 is very cheap ($0.10/1M tokens); Rerank v3 is $2/1k searches.

---

## Paid Upgrade

Remove the trial restriction by adding billing. Command A: $2.50/$10 per 1M in/out. Embed v3: $0.10/1M. Rerank v3: $2.00/1k searches. No monthly minimum.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
