---
# ── Machine-readable header (parsed by scripts/provider_review/generate_docs.py) ──
provider: "Provider Display Name"
slug: provider-slug
url: https://console.provider.com
api_base: https://api.provider.com/v1
litellm_prefix: prefix
openai_compatible: true
free_tier: true
free_tier_type: standing       # standing | credit-based | trial | metered
access_requirements:
  - email                      # email | google_account | github_account | phone_verification | credit_card
data_privacy_on_free: unknown  # trains_on_data | no_training | regional_law | unknown
verified_at: YYYY-MM-DD
source_urls:
  - https://docs.provider.com/rate-limits
  - https://provider.com/pricing
---

# Provider Display Name

> **Free tier type:** standing / credit-based / trial / metered  
> **Access:** signup requirements  
> **Privacy:** data policy on free tier

One-paragraph summary of the provider and its standing for DigiThings use cases.

---

## Free-Tier Models

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `model-id-exact` | 128k tokens | 8k | flagship |

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| Requests per minute (RPM) | — |
| Requests per day (RPD) | — |
| Tokens per minute (TPM) | — |
| Tokens per day (TPD) | — |
| Max output / request | — |
| Quota reset | daily UTC / rolling |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: alias
    litellm_params:
      model: prefix/model-id
      api_key: os.environ/PROVIDER_API_KEY
```

**Env var:** `PROVIDER_API_KEY`

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | — |
| DIGI_LLM_MODE tier | test / medium / best |
| Single-shot 100k | Yes / No — requires chunking at Xk |
| Privacy safe | Yes / No |

---

## Caveats

- Notable limits, stability issues, ToS restrictions.

---

## Paid Upgrade

Brief path to paid and rough pricing.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| YYYY-MM-DD | Initial entry | manual |
