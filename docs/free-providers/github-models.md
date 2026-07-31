---
provider: "GitHub Models"
slug: github-models
url: https://github.com/marketplace/models
api_base: https://models.inference.ai.azure.com
litellm_prefix: github
openai_compatible: true
free_tier: true
free_tier_type: standing
access_requirements:
  - github_account
data_privacy_on_free: unknown
verified_at: 2026-07-19
source_urls:
  - https://docs.github.com/en/github-models/about-github-models
  - https://docs.github.com/en/github-models/prototyping-with-ai-models
---

# GitHub Models

> **Free tier type:** standing — free for any GitHub account  
> **Access:** GitHub account (PAT with `models:read` scope)  
> **Privacy:** routes through Azure AI; check Microsoft/Azure data policy  
> **⚠️ ToS:** explicitly restricted to **evaluation and prototyping only** — not production use

GitHub Models provides free access to GPT-5, Claude (subset), Llama, Mistral, and others via a GitHub Personal Access Token. Rate limits are intentionally tight to enforce the eval-only posture. The key strength is native integration into GitHub Actions workflows for code review and PR automation — no separate API key management. For production workloads, graduate to Azure AI Foundry.

---

## Free-Tier Models (selection — full list at github.com/marketplace/models)

| Model ID | Context Window | Max Output | Notes |
|---|---|---|---|
| `gpt-4o-mini` | 128,000 | 16,384 | ⚠️ Error code: 401 - {'error': {'code': 'unauthorized', 'message': 'The `models` permission is required to access this endpoint', 'details': 'The `models` permission is required to access this endpoint'}} |
| `gpt-4o` | 128,000 | 16,384 | **deprecated** |
| `meta-llama/Llama-3.3-70B-Instruct` | 131,072 | 4,096 | **deprecated** |
| `mistral-large-2411` | 131,072 | 4,096 | **deprecated** |

> Context windows are model native values; **effective context in playground may be capped**. API access uses full context.

---

## Rate Limits (Free Tier — by Copilot account tier)

| Tier | Low-complexity models | High-complexity models |
|---|---|---|
| Free (no Copilot) | 15 RPM / 150 RPD | 10 RPM / 50 RPD |
| Copilot Free | 15 RPM / 150 RPD | 10 RPM / 50 RPD |
| Copilot Pro | 15 RPM / 300 RPD | 10 RPM / 100 RPD |
| Copilot Business / Enterprise | 15 RPM / 500 RPD | 10 RPM / 150 RPD |

*Low-complexity: Phi, small Llama, etc. High-complexity: GPT-4o, Llama 70B, Claude.*

---

## LiteLLM Configuration

```yaml
model_list:
  - model_name: github-gpt4o
    litellm_params:
      model: github/gpt-4o
      api_key: os.environ/GITHUB_TOKEN
      api_base: https://models.inference.ai.azure.com

  - model_name: github-llama
    litellm_params:
      model: github/meta-llama/Llama-3.3-70B-Instruct
      api_key: os.environ/GITHUB_TOKEN
      api_base: https://models.inference.ai.azure.com
```

**Env var:** `GITHUB_TOKEN` (PAT with `models:read`, or Actions `secrets.GITHUB_TOKEN`)  
**Signup:** No extra signup — use existing GitHub account

---

## DigiThings Use

| Field | Value |
|---|---|
| Best for | GitHub Actions CI/CD integration; PR review automation; code analysis |
| DIGI_LLM_MODE tier | `test` (CI workflows only — not for research pipelines) |
| Single-shot 100k | Yes (context window supports it) but RPD is too low for bulk research |
| Privacy safe | Unknown (Azure AI backend) |
| Atlas/Hermes role | **Not recommended** — eval/ToS-restricted; too low RPD for research pipelines |

---

## Caveats

- **ToS explicitly prohibits production use** — for evaluation only. Graduate to Azure AI Foundry for commercial workloads.
- RPD of 50–150 on high-complexity models is insufficient for daily automated research runs.
- The `GITHUB_TOKEN` from Actions has the right scope automatically — no separate secret needed in CI.
- Useful for: automated PR review, code review workflows, CI commentary.
- Not useful for: Atlas/Hermes research pipelines, bulk document analysis, any sustained volume.

---

## Paid Upgrade

Graduate to Azure AI Foundry (same models, production SLA, full rate limits). Pricing via Azure consumption model.

---

## Changelog

| Date | Change | Source |
|---|---|---|
| 2026-05-03 | Initial deep-reference entry | manual + snapshot |
| 2026-07-19 | Automated snapshot sync | provider-review scan |
