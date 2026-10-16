# OpenAI API

**Free tier:** None standing. Batch API gives 50% discount; Flex pricing on some models.

**Best for:** GPT-5 / GPT-4.1 frontier, embeddings (text-embedding-3-small/large), Whisper, TTS.

## 1. Sign up

- Go to https://platform.openai.com and sign up.
- Verify phone.
- Add payment method under **Billing**.

## 2. Create API key

- https://platform.openai.com/api-keys → **Create new secret key**.
- Scope by project if you have multiple; set permissions (default: all).
- Copy (starts with `sk-proj-...` or `sk-...`).

## 3. Add to `.env`

```bash
OPENAI_API_KEY=sk-proj-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: gpt-mini
    litellm_params:
      model: openai/gpt-4.1-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-nano
    litellm_params:
      model: openai/gpt-4.1-nano
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-flagship
    litellm_params:
      model: openai/gpt-5
      api_key: os.environ/OPENAI_API_KEY

  - model_name: openai-embeddings
    litellm_params:
      model: openai/text-embedding-3-small
      api_key: os.environ/OPENAI_API_KEY
```

## 5. Verify

```bash
curl -s https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hi"}]}'
```

## Cost control

- **Batch API**: 50% discount, async.
- **Prompt caching**: automatic ~50% discount on repeated prefixes ≥1024 tokens.
- **Usage limits**: set a hard monthly cap under Billing → Limits.

## Docs

https://platform.openai.com/docs
