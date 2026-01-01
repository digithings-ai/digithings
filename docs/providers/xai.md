# xAI (Grok)

**Free tier:** Historically $25/mo via data-sharing opt-in; reduced or discontinued as of 2026 (uncertain — verify on console).

**Selling point:** real-time X data access, Grok-4 flagship.

## 1. Sign up

- Go to https://console.x.ai and sign in (X/Google/email).
- Add payment.

## 2. Create API key

- Dashboard → **API Keys** → **Create key**.
- Copy (starts with `xai-...`).

## 3. Add to `.env`

```bash
XAI_API_KEY=xai-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: grok-4
    litellm_params:
      model: xai/grok-4
      api_key: os.environ/XAI_API_KEY

  - model_name: grok-3
    litellm_params:
      model: xai/grok-3
      api_key: os.environ/XAI_API_KEY
```

## 5. Verify

```bash
curl -s https://api.x.ai/v1/chat/completions \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"grok-4","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.x.ai
