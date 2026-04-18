# Fireworks AI

**Free tier:** ~$1 signup credit (uncertain, historically $1–5).

**Best for:** open-weight hosting with FireFunction tool-use support, serverless and dedicated GPUs.

## 1. Sign up

- Go to https://fireworks.ai and sign in (Google/GitHub/email).

## 2. Create API key

- Dashboard → **API Keys** → **Create**.
- Copy (starts with `fw_...`).

## 3. Add to `.env`

```bash
FIREWORKS_API_KEY=fw_...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: fw-llama-70b
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct
      api_key: os.environ/FIREWORKS_API_KEY

  - model_name: fw-deepseek-v3
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/deepseek-v3
      api_key: os.environ/FIREWORKS_API_KEY

  - model_name: fw-firefunction
    litellm_params:
      model: fireworks_ai/accounts/fireworks/models/firefunction-v2
      api_key: os.environ/FIREWORKS_API_KEY
```

## 5. Verify

```bash
curl -s https://api.fireworks.ai/inference/v1/chat/completions \
  -H "Authorization: Bearer $FIREWORKS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"accounts/fireworks/models/llama-v3p3-70b-instruct","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.fireworks.ai
