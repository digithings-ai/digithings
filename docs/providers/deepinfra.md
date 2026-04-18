# DeepInfra

**Free tier:** None standing; occasional signup credit.

**Selling point:** among the cheapest hosted open-weight inference. Llama 3.3 70B at ~$0.23 / $0.40; DeepSeek V3 at ~$0.49 / $0.89; Llama 3.1 8B at ~$0.03 / $0.05.

## 1. Sign up

- Go to https://deepinfra.com and sign in (GitHub).

## 2. Create API key

- Dashboard → **API Keys** → **New key**.
- Copy the token.

## 3. Add to `.env`

```bash
DEEPINFRA_API_KEY=...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: di-llama-70b
    litellm_params:
      model: deepinfra/meta-llama/Meta-Llama-3.3-70B-Instruct
      api_key: os.environ/DEEPINFRA_API_KEY

  - model_name: di-deepseek-v3
    litellm_params:
      model: deepinfra/deepseek-ai/DeepSeek-V3
      api_key: os.environ/DEEPINFRA_API_KEY

  - model_name: di-llama-8b
    litellm_params:
      model: deepinfra/meta-llama/Meta-Llama-3.1-8B-Instruct
      api_key: os.environ/DEEPINFRA_API_KEY
```

## 5. Verify

```bash
curl -s https://api.deepinfra.com/v1/openai/chat/completions \
  -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Meta-Llama-3.3-70B-Instruct","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://deepinfra.com/docs
