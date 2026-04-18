# Together AI

**Free tier:** ~$1 signup credit (uncertain — was $5). Some rotating free endpoints (e.g. Llama 3.3 70B Turbo Free historically).

**Best for:** open-weight hosting, fine-tuning, FLUX image models.

## 1. Sign up

- Go to https://together.ai and sign in (Google/GitHub/email).

## 2. Create API key

- Dashboard → **Settings** → **API Keys** → **New key**.
- Copy the token.

## 3. Add to `.env`

```bash
TOGETHER_API_KEY=...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: together-llama-70b
    litellm_params:
      model: together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo
      api_key: os.environ/TOGETHER_API_KEY

  - model_name: together-deepseek-v3
    litellm_params:
      model: together_ai/deepseek-ai/DeepSeek-V3
      api_key: os.environ/TOGETHER_API_KEY

  - model_name: together-qwen-coder
    litellm_params:
      model: together_ai/Qwen/Qwen2.5-Coder-32B-Instruct
      api_key: os.environ/TOGETHER_API_KEY
```

## 5. Verify

```bash
curl -s https://api.together.xyz/v1/chat/completions \
  -H "Authorization: Bearer $TOGETHER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Llama-3.3-70B-Instruct-Turbo","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.together.ai
