# Cerebras Cloud

**Free tier:** Yes — ~30 RPM, 60 RPD, ~1M free tokens/day on flagship models.

**Selling point:** >2000 tok/s inference on Llama/Qwen (fastest on market).

## 1. Sign up

- Go to https://cloud.cerebras.ai and sign in (Google/email).

## 2. Create API key

- Dashboard → **API Keys** → **Generate**.
- Copy (starts with `csk-...`).

## 3. Add to `.env`

```bash
CEREBRAS_API_KEY=csk-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: cerebras-llama-70b
    litellm_params:
      model: cerebras/llama-3.3-70b
      api_key: os.environ/CEREBRAS_API_KEY

  - model_name: cerebras-llama4-scout
    litellm_params:
      model: cerebras/llama-4-scout
      api_key: os.environ/CEREBRAS_API_KEY

  - model_name: cerebras-qwen
    litellm_params:
      model: cerebras/qwen-3-32b
      api_key: os.environ/CEREBRAS_API_KEY
```

## 5. Verify

```bash
curl -s https://api.cerebras.ai/v1/chat/completions \
  -H "Authorization: Bearer $CEREBRAS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b","messages":[{"role":"user","content":"Say hi"}]}'
```

## Gotchas

- Context windows on free tier often clipped below native (8K–32K).
- Narrower catalog than Groq — good as secondary, not primary.

## Docs

https://inference-docs.cerebras.ai
