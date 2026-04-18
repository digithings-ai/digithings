# Provider Setup Guides

Step-by-step instructions for obtaining API keys and wiring each LLM provider into DigiThings via LiteLLM.

**For the full catalog of what each provider offers (free tier limits, pricing, recommendations) see [../LLM_PROVIDERS.md](../LLM_PROVIDERS.md).** This directory is the *how-to* companion — one file per provider, focused on setup only.

## Setup pattern (same for every provider)

1. **Sign up** at the provider's console.
2. **Create an API key** (each provider's console has a "API keys" section).
3. **Add to `.env`** at the repo root:
   ```bash
   PROVIDER_API_KEY=sk-...
   ```
4. **Register in `config/litellm.yaml`** (see each provider guide for the exact `model_list` entry).
5. **Restart the stack:** `make down && make up`.
6. **Verify** with the `curl` snippet at the bottom of each guide.

Never commit `.env`. Use `.env.example` as the template and keep real keys out of git.

## Providers

### Free tier available

| Provider | Guide | Best for |
|---|---|---|
| Google AI Studio (Gemini) | [gemini.md](gemini.md) | Long-context, vision, highest free RPD |
| Groq | [groq.md](groq.md) | Fast inference, Llama/Qwen/Kimi |
| Cerebras | [cerebras.md](cerebras.md) | Fastest inference on market |
| OpenRouter | [openrouter.md](openrouter.md) | One key → many `:free` models |
| Cloudflare Workers AI | [cloudflare.md](cloudflare.md) | 10K neurons/day standing free |
| Mistral La Plateforme | [mistral.md](mistral.md) | Codestral, Pixtral, Mistral Large |
| SambaNova | [sambanova.md](sambanova.md) | Fast Llama 3.3/4 inference |
| Nvidia NIM | [nvidia_nim.md](nvidia_nim.md) | Nemotron + eval catalog |
| GitHub Models | [github_models.md](github_models.md) | GPT-5 / Claude for **eval only** |
| Ollama Cloud | [ollama_cloud.md](ollama_cloud.md) | gpt-oss, DeepSeek V3.2, Kimi |
| Hugging Face | [huggingface.md](huggingface.md) | Model discovery + router |

### Paid only (no meaningful free tier)

| Provider | Guide | Best for |
|---|---|---|
| Anthropic | [anthropic.md](anthropic.md) | Claude — flagship reasoning |
| OpenAI | [openai.md](openai.md) | GPT family |
| DeepSeek | [deepseek.md](deepseek.md) | Cheapest frontier-class |
| DeepInfra | [deepinfra.md](deepinfra.md) | Cheap open-weight hosting |
| Together AI | [together.md](together.md) | Open-weight, fine-tuning |
| Fireworks AI | [fireworks.md](fireworks.md) | Open-weight, FireFunction |
| Perplexity | [perplexity.md](perplexity.md) | Web-grounded Sonar |
| xAI (Grok) | [xai.md](xai.md) | Grok models |

### Local / self-hosted

| Option | Guide | Best for |
|---|---|---|
| Ollama (local) | [ollama_local.md](ollama_local.md) | Zero per-token cost, runs on Mac/GPU |

## After adding a provider

Update `config/litellm.yaml` to include the new model in your fallback chain. Example alias `test-tier` falling back across Groq → Gemini → OpenRouter:

```yaml
model_list:
  - model_name: test-tier
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
  - model_name: test-tier
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: test-tier
    litellm_params:
      model: openrouter/deepseek/deepseek-chat-v3:free
      api_key: os.environ/OPENROUTER_API_KEY

router_settings:
  fallbacks:
    - test-tier: [test-tier]  # cycle through chain on rate-limit
```

Then set `DIGI_LLM_MODE=test` and all workflow calls route through this chain.
