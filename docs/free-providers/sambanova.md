---
provider: "SambaNova Cloud"
slug: sambanova
url: https://cloud.sambanova.ai
api_base: https://api.sambanova.ai/v1
litellm_prefix: sambanova
openai_compatible: true
free_tier: true
free_tier_type: standing
access_requirements:
  - email
data_privacy_on_free: unknown
verified_at: 2026-05-03
source_urls:
  - https://docs.sambanova.ai/sambanova-cloud/latest/get-started/rate-limits.html
  - https://docs.sambanova.ai
---

# SambaNova Cloud

> **Free tier type:** standing — no expiry, no credit card  
> **Access:** email signup  
> **Privacy:** not published; treat as unknown

SambaNova runs a custom RDU (Reconfigurable Dataflow Unit) architecture that delivers very fast Llama 3.3/4 inference, competitive with Groq. The free tier provides standing access with no daily token cap published — making it a good secondary fallback after Groq and Cerebras for speed-first pipelines. Limited paid-tier pricing details available; mainly a dev-friendly free offering.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | RPM | Notes |
|---|---|---|---|---|
| `Meta-Llama-3.3-70B-Instruct` | 131,072 | 16,384 | 20 | Primary workhorse |
| `Meta-Llama-4-Scout-17B-16E-Instruct` | 131,072 | 16,384 | 20 | Llama 4 Scout |
| `DeepSeek-R1` | 32,768 | 16,384 | 20 | Reasoning model; limited context |
| `Qwen2.5-72B-Instruct` | 131,072 | 16,384 | 20 | Qwen 2.5 72B |

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| RPM | 20 |
| RPD | Not published |
| TPM | Not published |
| Max output | 16,384 |
| Quota reset | Rolling minute |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: sambanova-llama
    litellm_params:
      model: sambanova/Meta-Llama-3.3-70B-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY

  - model_name: sambanova-llama4
    litellm_params:
      model: sambanova/Meta-Llama-4-Scout-17B-16E-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY
```

**Env var:** `SAMBANOVA_API_KEY`  
**Signup / key:** https://cloud.sambanova.ai → API Keys

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Fast Llama inference; secondary fallback to Groq/Cerebras |
| DIGI_LLM_MODE tier | `test` (fallback) |
| Single-shot 100k | Yes — 131k context on Llama models |
| Privacy safe | Unknown |
| Atlas/Hermes role | Speed fallback when Groq/Cerebras hit limits |

---

## Caveats

- RPD not published — may have hidden daily limits; monitor for 429s.
- DeepSeek-R1 on SambaNova only has 32k context — limited for large-document work.
- Rate limits lower than Groq (20 vs 30 RPM) — treat as secondary.
- Paid tier availability and pricing not widely documented.

---

## Paid Upgrade

Paid tier available; pricing not publicly documented as of 2026-05-03. Contact sales at cloud.sambanova.ai.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
