# DeepSeek API

**Free tier:** None standing; occasional bonus credit on signup.

**Selling point:** cheapest frontier-class open model — DeepSeek V3 at $0.27 / $1.10, R1 reasoner at $0.55 / $2.19. Off-peak discounts of 50–75%.

**Jurisdiction warning:** hosted in China. For Western-jurisdiction hosting of the same weights, use Fireworks / Together / DeepInfra instead.

## 1. Sign up

- Go to https://platform.deepseek.com and sign up (email).
- Add top-up (minimum $2).

## 2. Create API key

- Left sidebar → **API Keys** → **Create new API key**.
- Copy (starts with `sk-...`).

## 3. Add to `.env`

```bash
DEEPSEEK_API_KEY=sk-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

  - model_name: deepseek-reasoner
    litellm_params:
      model: deepseek/deepseek-reasoner
      api_key: os.environ/DEEPSEEK_API_KEY
```

## 5. Verify

```bash
curl -s https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://api-docs.deepseek.com
