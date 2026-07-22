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
verified_at: 2026-07-19
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

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `Meta-Llama-3.3-70B-Instruct` | 131,072 | 16,384 | active |
| `Meta-Llama-4-Scout-17B-16E-Instruct` | 131,072 | 16,384 | **deprecated** |
| `Llama-4-Maverick-17B-128E-Instruct` | 65,536 | 16,384 | **deprecated** |
| `DeepSeek-R1` | 32,768 | 16,384 | **deprecated** |
| `gpt-oss-120b` | 131,072 | 16,384 | active |
| `MiniMax-M2.7` | 131,072 | 16,384 | **deprecated** |
| `Qwen3-32B` | 32,768 | 8,192 | **deprecated** |
| `DeepSeek-V3.1` | 131,072 | 16,384 | active |
| `DeepSeek-V3.2` | 131,072 | 16,384 | active |
| `gemma-4-31B-it` | 131,072 | 16,384 | active |

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
| 2026-07-19 | Automated snapshot sync | provider-review scan |
