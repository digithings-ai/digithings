# SambaNova Cloud

**Free tier:** Generous developer tier, ~20 RPM on Llama models.

**Selling point:** very fast inference on RDU hardware; good Llama/DeepSeek/Qwen hosting.

## 1. Sign up

- Go to https://cloud.sambanova.ai and sign in (Google/email).

## 2. Create API key

- Dashboard → **API Keys** → **Generate new key**.
- Copy the key.

## 3. Add to `.env`

```bash
SAMBANOVA_API_KEY=...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: sn-llama-70b
    litellm_params:
      model: sambanova/Meta-Llama-3.3-70B-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY

  - model_name: sn-llama4-maverick
    litellm_params:
      model: sambanova/Llama-4-Maverick-17B-128E-Instruct
      api_key: os.environ/SAMBANOVA_API_KEY

  - model_name: sn-deepseek-r1
    litellm_params:
      model: sambanova/DeepSeek-R1
      api_key: os.environ/SAMBANOVA_API_KEY
```

## 5. Verify

```bash
curl -s https://api.sambanova.ai/v1/chat/completions \
  -H "Authorization: Bearer $SAMBANOVA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Meta-Llama-3.3-70B-Instruct","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.sambanova.ai
