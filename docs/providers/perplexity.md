# Perplexity API (Sonar)

**Free tier:** $5/mo credit for Perplexity Pro subscribers; none for non-subscribers.

**Best for:** web-grounded queries with live citations. Not a general LLM host — this is a search+LLM hybrid.

## 1. Sign up

- Go to https://perplexity.ai → sign in.
- Subscribe to Pro ($20/mo) for the API credit.
- Visit https://www.perplexity.ai/settings/api.

## 2. Create API key

- Settings → **API** → **Generate**.
- Add billing (required even as Pro).
- Copy (starts with `pplx-...`).

## 3. Add to `.env`

```bash
PERPLEXITYAI_API_KEY=pplx-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: sonar
    litellm_params:
      model: perplexity/sonar
      api_key: os.environ/PERPLEXITYAI_API_KEY

  - model_name: sonar-pro
    litellm_params:
      model: perplexity/sonar-pro
      api_key: os.environ/PERPLEXITYAI_API_KEY

  - model_name: sonar-reasoning
    litellm_params:
      model: perplexity/sonar-reasoning
      api_key: os.environ/PERPLEXITYAI_API_KEY
```

## 5. Verify

```bash
curl -s https://api.perplexity.ai/chat/completions \
  -H "Authorization: Bearer $PERPLEXITYAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"sonar","messages":[{"role":"user","content":"Latest news about Claude"}]}'
```

## Docs

https://docs.perplexity.ai
