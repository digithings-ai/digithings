# Groq

**Free tier:** Yes — standing. ~30 RPM, 14,400 RPD per model. No credit card required.

**Selling point:** 500–1500 tok/s inference on Llama, Qwen, Kimi.

## 1. Sign up

- Go to https://console.groq.com and sign in (Google/GitHub/email).

## 2. Create API key

- Left sidebar → **API Keys** → **Create API Key**.
- Name it (e.g. `digithings-dev`), copy (starts with `gsk_...`).

## 3. Add to `.env`

```bash
GROQ_API_KEY=gsk_...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: groq-llama-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY

  - model_name: groq-coder
    litellm_params:
      model: groq/qwen-2.5-coder-32b
      api_key: os.environ/GROQ_API_KEY

  - model_name: groq-reasoner
    litellm_params:
      model: groq/deepseek-r1-distill-llama-70b
      api_key: os.environ/GROQ_API_KEY

  - model_name: groq-kimi
    litellm_params:
      model: groq/moonshotai/kimi-k2-instruct
      api_key: os.environ/GROQ_API_KEY
```

## 5. Verify

```bash
curl -s https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"Say hi"}]}'
```

## Gotchas

- Rate limits are bursty — wrap client calls in exponential backoff.
- Model catalog rotates; check https://console.groq.com/docs/models for current list.

## Docs

https://console.groq.com/docs
