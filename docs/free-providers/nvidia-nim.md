---
provider: "NVIDIA NIM"
slug: nvidia-nim
url: https://build.nvidia.com
api_base: https://integrate.api.nvidia.com/v1
litellm_prefix: nvidia_nim
openai_compatible: true
free_tier: true
free_tier_type: credit-based
access_requirements:
  - email
data_privacy_on_free: unknown
verified_at: 2026-05-03
source_urls:
  - https://build.nvidia.com/explore/discover
  - https://docs.api.nvidia.com/nim/reference/llm-apis
---

# NVIDIA NIM (build.nvidia.com)

> **Free tier type:** credit-based — 1,000 inference credits on signup; 5,000 with Developer Program enrollment  
> **Access:** email signup at build.nvidia.com  
> **Privacy:** not published

NVIDIA NIM offers access to 80–200+ optimized open-weight models via a single OpenAI-compatible endpoint. Models run on NVIDIA hardware with TRT-LLM optimizations. The credit system is one-time (credits don't refill), making this best suited for evaluation and benchmarking rather than sustained production use. The catalog breadth is the standout feature — access to models like Nemotron, hosted DeepSeek R1, Kimi K2.5, and GLM alongside standard Llama variants.

---

## Free-Tier Models (selection — full catalog at build.nvidia.com)

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `meta/llama-3.3-70b-instruct` | 128,000 | 4,096 | Llama 3.3 70B |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | 131,072 | 4,096 | Nemotron reasoning |
| `nvidia/llama-3.1-nemotron-70b-instruct` | 131,072 | 4,096 | Nemotron 70B |
| `deepseek-ai/deepseek-r1` | 163,840 | 32,768 | DeepSeek R1 |
| `deepseek-ai/deepseek-v3-0324` | 163,840 | 16,384 | DeepSeek V3 |
| `moonshotai/kimi-k2-instruct` | 131,072 | 16,384 | Kimi K2 |
| `google/gemma-3-27b-it` | 131,072 | 8,192 | Gemma 3 27B |

> Catalog of 80–200+ models; verify current availability at build.nvidia.com/explore/discover.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| RPM | 40 |
| RPD | Credit-dependent |
| Inference credits | 1,000 on signup; +4,000 with NVIDIA Developer Program |
| Credit expiry | Credits do not expire; do not refill |
| Max output | 4,096 (model-dependent) |

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: nvidia-nemotron
    litellm_params:
      model: nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
      api_key: os.environ/NVIDIA_NIM_API_KEY
      api_base: https://integrate.api.nvidia.com/v1

  - model_name: nvidia-llama
    litellm_params:
      model: nvidia_nim/meta/llama-3.3-70b-instruct
      api_key: os.environ/NVIDIA_NIM_API_KEY
      api_base: https://integrate.api.nvidia.com/v1

  - model_name: nvidia-deepseek-r1
    litellm_params:
      model: nvidia_nim/deepseek-ai/deepseek-r1
      api_key: os.environ/NVIDIA_NIM_API_KEY
      api_base: https://integrate.api.nvidia.com/v1
```

**Env var:** `NVIDIA_NIM_API_KEY`  
**Signup / key:** https://build.nvidia.com → Get API Key

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | Model evaluation; accessing novel models before choosing a long-term host |
| DIGI_LLM_MODE tier | `best` (evaluation only — credits deplete) |
| Single-shot 100k | Yes — 128–163k context on supported models |
| Privacy safe | Unknown |
| Atlas/Hermes role | Benchmarking new models; evaluating Nemotron/reasoning variants |

---

## Caveats

- Credits are **one-time** — once depleted, you must use paid NIM or other providers. Don't use as a production fallback unless you have a paid plan.
- Max output of 4,096 on many models — check per-model for longer outputs (DeepSeek R1 supports 32k output).
- 40 RPM is decent for evaluation but not sustained production.
- For production NIM deployment, see NVIDIA's enterprise cloud or self-hosted NIM containers.

---

## Paid Upgrade

NVIDIA NIM API pay-per-token after credits. Pricing varies by model. Enterprise tier available with dedicated instances.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
