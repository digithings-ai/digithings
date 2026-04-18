# GitHub Models

**Free tier:** Yes — free for GitHub users. Rate limits by Copilot tier: Free plan ~50 RPD low-tier models, 8 RPD high-tier; Pro higher; Enterprise highest. Context capped below native (8K in / 4K out on free).

**ToS warning:** **free tier is for evaluation and prototyping only — not production.** Commercial deployment requires graduating to Azure AI.

## 1. Sign up

- You already have this if you have a GitHub account.
- Go to https://github.com/marketplace/models and browse models.

## 2. Create API token

- Visit https://github.com/settings/personal-access-tokens/new
- Create a **fine-grained personal access token**.
- No special repo permissions needed; default scope is fine.
- Copy (starts with `github_pat_...` or `ghp_...`).

## 3. Add to `.env`

```bash
GITHUB_TOKEN=github_pat_...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: gh-gpt-4-1
    litellm_params:
      model: github/gpt-4.1
      api_key: os.environ/GITHUB_TOKEN

  - model_name: gh-gpt-5-mini
    litellm_params:
      model: github/gpt-5-mini
      api_key: os.environ/GITHUB_TOKEN

  - model_name: gh-llama-70b
    litellm_params:
      model: github/meta-llama-3.3-70b-instruct
      api_key: os.environ/GITHUB_TOKEN

  - model_name: gh-deepseek-v3
    litellm_params:
      model: github/deepseek-v3
      api_key: os.environ/GITHUB_TOKEN
```

## 5. Verify

```bash
curl -s https://models.github.ai/inference/chat/completions \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4.1","messages":[{"role":"user","content":"Say hi"}]}'
```

## Graduating to production

Once past eval, provision an Azure AI Foundry project and use the same code with an Azure endpoint + key. See https://learn.microsoft.com/azure/ai-foundry.

## Docs

https://docs.github.com/github-models
