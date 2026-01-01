# Cloudflare Workers AI

**Free tier:** 10,000 neurons/day standing free on all Cloudflare plans (~few thousand small-model calls).

**Best for:** edge-deployed apps, embeddings, Whisper, lightweight chat.

## 1. Sign up

- Go to https://dash.cloudflare.com and sign up (free account is fine).

## 2. Get account ID + API token

- Dashboard home → right sidebar shows **Account ID**. Copy it.
- Top-right profile → **My Profile** → **API Tokens** → **Create Token**.
- Use template **"Workers AI"** (or create custom with `Workers AI: Read`).
- Copy the token.

## 3. Add to `.env`

```bash
CLOUDFLARE_API_KEY=...
CLOUDFLARE_ACCOUNT_ID=...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: cf-llama-70b
    litellm_params:
      model: cloudflare/@cf/meta/llama-3.3-70b-instruct
      api_key: os.environ/CLOUDFLARE_API_KEY
      api_base: https://api.cloudflare.com/client/v4/accounts/CLOUDFLARE_ACCOUNT_ID/ai/v1

  - model_name: cf-deepseek
    litellm_params:
      model: cloudflare/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b
      api_key: os.environ/CLOUDFLARE_API_KEY

  - model_name: cf-embeddings
    litellm_params:
      model: cloudflare/@cf/baai/bge-large-en-v1.5
      api_key: os.environ/CLOUDFLARE_API_KEY
```

(Replace `CLOUDFLARE_ACCOUNT_ID` in `api_base` with the literal account ID or use env interpolation via `os.environ/CLOUDFLARE_ACCOUNT_ID` at runtime — check LiteLLM docs for the current syntax.)

## 5. Verify

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/ai/run/@cf/meta/llama-3.3-70b-instruct" \
  -H "Authorization: Bearer $CLOUDFLARE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hi"}]}'
```

## Gotchas

- "Neuron" accounting is opaque — 1 neuron ≠ 1 token. Check the model's neuron cost at https://developers.cloudflare.com/workers-ai/platform/pricing.
- Paid overage: $0.011 per 1000 neurons beyond free.

## Docs

https://developers.cloudflare.com/workers-ai
