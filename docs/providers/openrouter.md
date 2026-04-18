# OpenRouter

**Free tier:** Yes — routes `:free` variants of models. 20 RPM; 50 RPD with <$10 balance, 1000 RPD after topping up $10+.

**Why it's useful:** one API key → access to DeepSeek, Llama, Qwen, Gemini, Mistral, Claude, GPT via a single OpenAI-compatible endpoint. Ideal as a fallback chain or for BYO-key routing.

## 1. Sign up

- Go to https://openrouter.ai and sign in (Google/GitHub/email/MetaMask).

## 2. Create API key

- Top-right profile → **Keys** → **Create Key**.
- Set an optional credit limit per key.
- Copy (starts with `sk-or-v1-...`).

## 3. Add to `.env`

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: or-deepseek-v3-free
    litellm_params:
      model: openrouter/deepseek/deepseek-chat-v3:free
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: or-deepseek-r1-free
    litellm_params:
      model: openrouter/deepseek/deepseek-r1:free
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: or-llama-70b-free
    litellm_params:
      model: openrouter/meta-llama/llama-3.3-70b-instruct:free
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: or-qwen-coder-free
    litellm_params:
      model: openrouter/qwen/qwen-2.5-coder-32b-instruct:free
      api_key: os.environ/OPENROUTER_API_KEY

  # Paid routes (no :free suffix) — pay upstream + ~5% OR markup
  - model_name: or-claude-sonnet
    litellm_params:
      model: openrouter/anthropic/claude-sonnet-4
      api_key: os.environ/OPENROUTER_API_KEY
```

## 5. Verify

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-chat-v3:free","messages":[{"role":"user","content":"Say hi"}]}'
```

## BYO-key mode

You can bring your own Anthropic/OpenAI/Gemini keys to OpenRouter (Settings → Integrations). Requests route through OR's UX with a 5% surcharge but direct upstream pricing — useful for observability.

## Gotchas

- `:free` routes can be slow / queue-prone under load.
- Providers behind `:free` may log prompts — check each model's card on openrouter.ai.
- Model list rotates — check https://openrouter.ai/models?max_price=0 for current free models.

## Docs

https://openrouter.ai/docs
