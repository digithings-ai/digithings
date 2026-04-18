# Google AI Studio (Gemini)

**Free tier:** Yes — standing, no expiry. Flash-Lite ~15 RPM / 1000 RPD; Flash ~10 RPM / 250 RPD; Pro ~5 RPM / 100 RPD.

**Privacy warning:** free-tier prompts/responses are used to train Google models. Do not send confidential data unless on paid.

## 1. Sign up

- Go to https://aistudio.google.com and sign in with a Google account.
- Accept the developer ToS.

## 2. Create API key

- Click **Get API key** (top-left) → **Create API key**.
- Choose an existing Google Cloud project or create a new one.
- Copy the key (starts with `AIza...`).

## 3. Add to `.env`

```bash
GEMINI_API_KEY=AIzaSy...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: gemini-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-flash-lite
    litellm_params:
      model: gemini/gemini-2.5-flash-lite
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-2.5-pro
      api_key: os.environ/GEMINI_API_KEY

  - model_name: gemini-embeddings
    litellm_params:
      model: gemini/text-embedding-004
      api_key: os.environ/GEMINI_API_KEY
```

## 5. Verify

Direct (without LiteLLM):

```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"Say hi"}]}]}'
```

Through LiteLLM proxy:

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_PROXY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-flash","messages":[{"role":"user","content":"Say hi"}]}'
```

## Paid upgrade

Enable billing on your Google Cloud project — the same API key will switch to paid quotas automatically. Paid tier is zero-retention.

## Docs

https://ai.google.dev/gemini-api/docs
