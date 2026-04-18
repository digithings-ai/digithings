# Anthropic API (Claude)

**Free tier:** None standing. Historical $5 signup credit is discontinued.

**Best for:** flagship reasoning, long-running agents, tool use. Use sparingly — reserve for evals.

## 1. Sign up

- Go to https://console.anthropic.com and sign up.
- Verify phone number.
- Add payment method (Settings → Billing → Add Credit).

## 2. Create API key

- Settings → **API Keys** → **Create Key**.
- Set optional workspace / spend limit.
- Copy (starts with `sk-ant-api03-...`).

## 3. Add to `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: claude-haiku
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: claude-opus
    litellm_params:
      model: anthropic/claude-opus-4-7
      api_key: os.environ/ANTHROPIC_API_KEY
```

## 5. Verify

```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":50,"messages":[{"role":"user","content":"Say hi"}]}'
```

## Cost control

- **Prompt caching**: 90% discount on cached input tokens — huge win for agent loops with static system prompts.
- **Batch API**: 50% discount, async turnaround ≤24h.
- **Spend limits**: set per-key in console.

## Alternatives

If you can't justify direct Anthropic pricing, access Claude via:
- **Amazon Bedrock** (`bedrock/anthropic.claude-...`) — similar pricing + AWS billing.
- **Google Vertex AI** (`vertex_ai/claude-...`) — GCP billing.
- **OpenRouter** (`openrouter/anthropic/claude-...`) — +5% markup, BYO-key option.

## Docs

https://docs.anthropic.com
