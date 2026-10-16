# Mistral La Plateforme

**Free tier:** "Experimental" — 1 RPS, 500K TPM, ~1B tokens/month. Requires phone verification.

**Privacy warning:** free tier allows training on your data unless on paid. Codestral commercial use requires paid tier.

## 1. Sign up

- Go to https://console.mistral.ai and sign in (Google/GitHub/email).
- Complete phone verification.
- Accept the experimental plan for free access.

## 2. Create API key

- Left sidebar → **API Keys** → **Create new key**.
- Copy (starts with letters — no consistent prefix).

## 3. Add to `.env`

```bash
MISTRAL_API_KEY=...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: mistral-large
    litellm_params:
      model: mistral/mistral-large-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: mistral-small
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: codestral
    litellm_params:
      model: mistral/codestral-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: pixtral
    litellm_params:
      model: mistral/pixtral-large-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: ministral-8b
    litellm_params:
      model: mistral/ministral-8b-latest
      api_key: os.environ/MISTRAL_API_KEY
```

## 5. Verify

```bash
curl -s https://api.mistral.ai/v1/chat/completions \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral-small-latest","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.mistral.ai
