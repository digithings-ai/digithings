# Ollama Cloud

**Free tier:** Metered by GPU-seconds on rolling 5h / 7-day windows. 1 concurrent model. Good for spot-checks, not sustained agent loops.

**Best for:** gpt-oss, DeepSeek V3.2, Qwen 3, Kimi K2.5, and other open models not free elsewhere.

## 1. Sign up

- Go to https://ollama.com and click **Sign in**.
- Go to https://ollama.com/settings → **Cloud** to enable.

## 2. Create API key

- Settings → **Keys** → **Generate API key**.
- Copy the key.

## 3. Add to `.env`

```bash
OLLAMA_API_KEY=...
```

## 4. LiteLLM entry

LiteLLM has no dedicated Ollama-Cloud provider. Use the OpenAI-compatible passthrough:

```yaml
model_list:
  - model_name: ollama-gpt-oss-120b
    litellm_params:
      model: openai/gpt-oss:120b-cloud
      api_base: https://ollama.com/v1
      api_key: os.environ/OLLAMA_API_KEY

  - model_name: ollama-deepseek-v3
    litellm_params:
      model: openai/deepseek-v3.2:cloud
      api_base: https://ollama.com/v1
      api_key: os.environ/OLLAMA_API_KEY

  - model_name: ollama-kimi-k2
    litellm_params:
      model: openai/kimi-k2.5:cloud
      api_base: https://ollama.com/v1
      api_key: os.environ/OLLAMA_API_KEY
```

## 5. Verify

```bash
curl -s https://ollama.com/v1/chat/completions \
  -H "Authorization: Bearer $OLLAMA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:120b-cloud","messages":[{"role":"user","content":"Say hi"}]}'
```

## Paid upgrade

- **Pro** ($20/mo or $200/yr): 50× free usage, 3 concurrent models, private model uploads.
- **Max** ($100/mo): 5× Pro, 10 concurrent.

## Model catalog

Browse https://ollama.com/search?c=cloud — all cloud models have the `-cloud` suffix.

## Docs

https://docs.ollama.com/cloud
