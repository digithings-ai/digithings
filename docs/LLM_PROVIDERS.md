# LLM Provider Catalog — Free Tiers, Cheap APIs, Local Options

*Reference snapshot: April 2026. Pricing and quotas change frequently — treat numbers as directional and verify against each provider's console before committing to production use. Items marked (uncertain) could not be confirmed at time of writing.*

## Why this document exists

DigiThings is designed to make AI **accessible and modular** — not locked to a single vendor or a single price point. This doc catalogs every legitimate way a developer can plug an LLM into the stack via LiteLLM, ordered from "free for dev testing" to "production-grade paid." The principle: **clever engineering over expensive tokens.** Flagship models (Opus, GPT-5, Gemini Pro) are reserved for real evals; day-to-day work runs on free tiers and cheap fallbacks.

Future work (see [VISION.md](VISION.md)): DigiChat will expose a model picker where the user supplies their own API key for any provider listed here, and the UI routes through our LiteLLM proxy.

**Setup guides:** for step-by-step instructions on obtaining an API key and configuring each provider, see [providers/](providers/) — one file per provider.

**Deep-reference docs:** for complete model listings, exact rate limits, context windows, and DigiThings-specific usage notes for every free-tier provider, see [free-providers/](free-providers/) — maintained weekly by the `provider-review` workflow. Start there when making provider selection decisions.

## How providers plug into LiteLLM

DigiThings routes all LLM traffic through `config/litellm.yaml`. Each provider below lists its LiteLLM prefix. The pattern:

```yaml
model_list:
  - model_name: free-fast
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
  - model_name: free-fast  # fallback on same alias
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
```

Set `DIGI_LLM_MODE` to pick a tier (`test` / `medium` / `best`). Free providers are chained as fallbacks so rate-limit hits degrade gracefully instead of failing.

## Subscriptions that do NOT give you API access

Common confusion — these are **chat-only** and cannot be used as a LiteLLM backend:

| Subscription | Why not |
|---|---|
| Claude Pro / Max | Bound to claude.ai + Claude Code CLI. Anthropic API billed separately. |
| ChatGPT Plus | Bound to chatgpt.com. OpenAI API billed separately. |
| GitHub Copilot | Editor-bound. Unofficial proxies violate ToS. See GitHub Models (below) for the legit free API. |
| Cursor Pro | Cursor editor only. |

---

## Free-tier providers

### 1. Google AI Studio (Gemini)

- **URL:** https://aistudio.google.com
- **Free tier:** Standing, no expiry. Gemini 2.5 Flash ~10 RPM / 250K TPM / 250 RPD; Flash-Lite ~15 RPM / 1M TPM / 1000 RPD; Pro ~5 RPM / 250K TPM / 100 RPD.
- **Best free models:** `gemini-2.5-pro` (top reasoning, 1M ctx, strong coding), `gemini-2.5-flash` (workhorse, vision, 1M ctx), `gemini-2.5-flash-lite` (highest RPD). Embeddings: `text-embedding-004`.
- **Paid:** Flash ~$0.30 / $2.50 per 1M; Flash-Lite ~$0.10 / $0.40; Pro ~$1.25 / $10 (≤200K), $2.50 / $15 above.
- **LiteLLM:** `gemini/gemini-2.5-flash`. Env: `GEMINI_API_KEY`.
- **Gotcha:** **Free-tier prompts/responses are used to improve Google products.** Never send confidential data on free. Paid tier is zero-retention.

### 2. Groq

- **URL:** https://console.groq.com
- **Free tier:** Standing. ~30 RPM, 14,400 RPD per model. TPM varies 6K–30K.
- **Best free models:** `llama-3.3-70b-versatile`, `llama-4-scout-17b-16e-instruct`, `llama-4-maverick-17b-128e`, `moonshotai/kimi-k2-instruct`, `qwen-2.5-coder-32b`, `deepseek-r1-distill-llama-70b`. Plus Whisper STT.
- **Paid:** Llama 3.3 70B ~$0.59 / $0.79; Llama 4 Scout ~$0.11 / $0.34; Llama 3.1 8B ~$0.05 / $0.08.
- **LiteLLM:** `groq/llama-3.3-70b-versatile`. Env: `GROQ_API_KEY`.
- **Selling point:** 500–1500 tok/s inference. Use exponential backoff for bursts.

### 3. Cerebras

- **URL:** https://cloud.cerebras.ai
- **Free tier:** ~30 RPM, 60 RPD, ~1M free tokens/day on flagships.
- **Best free models:** `llama-3.3-70b`, `llama-4-scout`, `llama-4-maverick`, `qwen-3-32b`. >2000 tok/s — fastest on market.
- **LiteLLM:** `cerebras/llama-3.3-70b`. Env: `CEREBRAS_API_KEY`.
- **Gotcha:** Context often clipped below native (8K–32K) on free.

### 4. OpenRouter

- **URL:** https://openrouter.ai
- **Free tier:** Routes `:free` variants. 20 RPM; 50 RPD with <$10 balance, 1000 RPD after.
- **Best `:free` models:** `deepseek/deepseek-chat-v3:free`, `deepseek/deepseek-r1:free`, `meta-llama/llama-3.3-70b-instruct:free`, `google/gemini-2.0-flash-exp:free`, `qwen/qwen-2.5-coder-32b-instruct:free`, `nvidia/llama-3.1-nemotron-70b:free`, `mistralai/mistral-small-3.1:free`. Roster rotates.
- **Paid:** Aggregator markup ~0–5% over upstream. BYO-key supported (5% surcharge).
- **LiteLLM:** `openrouter/deepseek/deepseek-chat-v3`. Env: `OPENROUTER_API_KEY`.
- **Gotcha:** `:free` routes can be slow / queue-prone. Providers may log prompts — check each model card.

### 5. Cloudflare Workers AI

- **URL:** https://developers.cloudflare.com/workers-ai
- **Free tier:** **10,000 neurons/day standing free** (~few thousand small-model calls).
- **Best models:** Llama 3.3/4, DeepSeek, Qwen, Mistral, BGE embeddings, Whisper, image models.
- **Paid:** $0.011 per 1000 neurons beyond free.
- **LiteLLM:** `cloudflare/@cf/meta/llama-3.3-70b-instruct`. Env: `CLOUDFLARE_API_KEY` + account ID.
- **Gotcha:** Neuron accounting is opaque; best used from inside Workers runtime.

### 6. Mistral La Plateforme

- **URL:** https://console.mistral.ai
- **Free tier:** "Experimental" — 1 RPS, 500K TPM, ~1B tokens/month across chat models. Phone verification required.
- **Best free models:** `mistral-large-latest`, `mistral-small-latest`, `codestral-latest` (coding), `pixtral-large` (vision), `ministral-8b`.
- **Paid:** Large ~$2 / $6; Small ~$0.20 / $0.60; Codestral ~$0.30 / $0.90; Ministral 8B ~$0.10 / $0.10.
- **LiteLLM:** `mistral/mistral-large-latest`. Env: `MISTRAL_API_KEY`.
- **Gotcha:** Free tier explicitly **allows training on your data** unless on paid. Codestral commercial use requires paid.

### 7. SambaNova Cloud

- **URL:** https://cloud.sambanova.ai
- **Free tier:** Generous developer tier, ~20 RPM on Llama models.
- **Best models:** Llama 3.3 70B, Llama 4 Maverick/Scout, DeepSeek R1, Qwen 2.5. Very fast RDU inference.
- **LiteLLM:** `sambanova/Meta-Llama-3.3-70B-Instruct`. Env: `SAMBANOVA_API_KEY`.

### 8. Nvidia NIM (build.nvidia.com)

- **URL:** https://build.nvidia.com
- **Free tier:** 1,000 credits on signup; 5,000 more with Developer Program. Credits don't refill.
- **Best models:** Llama Nemotron 70B (reasoning), Llama 3.3/4, DeepSeek R1, Mixtral, NVIDIA embeddings.
- **LiteLLM:** `nvidia_nim/<model>`. Env: `NVIDIA_NIM_API_KEY`.
- **Best use:** Evaluating models before choosing a long-term host.

### 9. GitHub Models

- **URL:** https://github.com/marketplace/models
- **Free tier:** Free for GitHub users. Rate-limited by Copilot tier: Free ~50 RPD low-tier, 8 RPD high-tier. Context often capped (8K in / 4K out on free).
- **Best models:** GPT-5 family, Claude subset, Llama, Mistral, Phi, Cohere, DeepSeek.
- **LiteLLM:** `github/gpt-4.1`. Env: `GITHUB_TOKEN` (PAT).
- **Gotcha:** **ToS restricts free tier to evaluation — not production.** Graduate to Azure AI for commercial.

### 10. Ollama Cloud

- **URL:** https://ollama.com/cloud
- **Free tier:** Metered in GPU-seconds on rolling 5h / 7-day windows, 1 concurrent model.
- **Best models:** Llama 3.3/4, Qwen 2.5/3, DeepSeek V3.2, Gemma, Kimi K2.5, gpt-oss 20b/120b.
- **Paid:** Pro $20/mo (50× free, 3 concurrent); Max $100/mo.
- **LiteLLM:** OpenAI-compatible passthrough — `openai/gpt-oss:120b-cloud` with `api_base=https://ollama.com/v1`.

### 11. Hugging Face Inference Providers

- **URL:** https://huggingface.co/docs/api-inference
- **Free tier:** Very limited anonymous; PRO users get ~$2/mo credits routed across providers.
- **Best use:** Model discovery + eval; routes to Together/Fireworks/Sambanova behind the scenes.
- **LiteLLM:** `huggingface/<model>`. Env: `HF_TOKEN`.

### 12. Other free-adjacent

- **Cohere** — free trial key, rate-limited, unlimited low-RPM for eval. Command R+ strong at RAG; Embed v3 + Rerank v3 best-in-class. `cohere/command-r-plus`. Trial keys forbidden for commercial.
- **AI21** — $10 signup credit. Jamba 1.5 Large/Mini (256K context). `ai21/jamba-1.5-large`.
- **xAI (Grok)** — historical $25/mo via data-sharing opt-in; reduced or discontinued as of 2026 (uncertain). `xai/grok-4`.

---

## Cheap paid APIs (for when free runs out)

| Provider | Model | Input $/1M | Output $/1M |
|---|---|---|---|
| DeepSeek direct | `deepseek-chat` (V3) | $0.27 | $1.10 |
| DeepSeek direct | `deepseek-reasoner` (R1) | $0.55 | $2.19 |
| Gemini | Flash-Lite | $0.10 | $0.40 |
| Gemini | Flash | $0.30 | $2.50 |
| OpenAI | GPT-4.1-mini | $0.15 | $0.60 |
| OpenAI | GPT-4.1-nano | ~$0.10 | ~$0.40 |
| Groq | Llama 3.1 8B | $0.05 | $0.08 |
| Groq | Llama 4 Scout | $0.11 | $0.34 |
| DeepInfra | Llama 3.3 70B | $0.23 | $0.40 |
| DeepInfra | DeepSeek V3 | $0.49 | $0.89 |
| Together | Llama 3.3 70B Turbo | $0.88 | $0.88 |
| Fireworks | Llama 3.3 70B | $0.90 | $0.90 |
| Anthropic | Haiku 4.5 | $1.00 | $5.00 |
| Anthropic | Sonnet 4.x | $3 | $15 |
| Anthropic | Opus 4.x | $15 | $75 |
| Perplexity | Sonar | $1 + $5/1k searches | $1 |

**Rule of thumb:** $5 topped up on DeepSeek or Gemini lasts weeks of dev testing. Batch APIs (OpenAI, Anthropic) and off-peak discounts (DeepSeek) halve effective cost.

**DeepSeek caveat:** direct platform is hosted in China — prompts subject to local data law. For Western-jurisdiction hosting of the same weights, use Fireworks, Together, or DeepInfra.

---

## Local / self-hosted (zero per-token cost)

For users with GPU or Apple Silicon:

- **Ollama** — simplest. One command pulls and runs Llama 3.3, Qwen 2.5/3, DeepSeek, Gemma, Phi. OpenAI-compatible server on `:11434`. LiteLLM: `ollama_chat/<model>`.
- **LM Studio** — GUI + local OpenAI-compatible server. Best for non-CLI users.
- **vLLM** — production-grade serving with PagedAttention. Deploy on your own GPU. LiteLLM: `openai/<model>` with `api_base`.
- **llama.cpp / llamafile** — CPU-only or constrained hardware.
- **TGI (Text Generation Inference)** — Hugging Face's serving stack.

Hardware rule of thumb: 7–14B runs on 16GB Mac / consumer GPU (Q4/Q5 quant). 70B needs 48GB+ VRAM or aggressive quantization. DeepSeek V3 and Llama 4 Maverick require multi-GPU or MoE-aware offload.

## Edge / browser

- **WebLLM** — Llama/Mistral/Qwen in-browser via WebGPU. Zero server cost, privacy-friendly, capped at ~1–8B.
- **Transformers.js** — HF's JS/WASM runtime for embeddings, small LLMs, Whisper, CLIP in-browser.

## BYO-key aggregators

- **LiteLLM proxy (self-hosted)** — the canonical DigiThings pattern. `config/litellm.yaml` registers every provider above with prefixed model names, one OpenAI-compatible endpoint, unified auth, caching, budgets, fallback chains.
- **OpenRouter BYO-key** — bring your Anthropic/OpenAI/Gemini key, pay upstream + 5% surcharge. Useful when you want OR's routing UX without double-paying margins.
- **Portkey, Helicone, TrueFoundry** — alternative gateways with observability focus.

---

## Recommendation matrix

| Use case | Best free pick | Why |
|---|---|---|
| High-volume dev testing | Groq + Gemini Flash-Lite + Cloudflare Workers AI (chained) | ~15K+ combined free RPD, no expiry |
| Fast coding completions | Groq `qwen-2.5-coder-32b` or Mistral `codestral-latest` | 500+ tok/s on Groq; Codestral purpose-built |
| Long-context RAG | Gemini 2.5 Flash (1M ctx, free) | Only free 1M-context option at scale |
| Vision / multimodal | Gemini 2.5 Flash or Mistral Pixtral (free) | Native multimodal, no extra charge |
| Reasoning / math | DeepSeek R1 via OpenRouter `:free` or Groq distill | Frontier reasoning, zero cost |
| Cheap bulk embeddings | Gemini `text-embedding-004` or Cloudflare BGE; paid: Cohere Embed v3 | Free at dev scale |
| Production fallback chain | LiteLLM: Groq → Cerebras → Together → Anthropic | Speed-first, cost-second, quality-third |
| Zero-retention commercial | Anthropic, OpenAI, Gemini paid, Cloudflare | Default no-training. Avoid Mistral/Gemini **free** for confidential data |

---

## DigiThings integration plan

1. **`config/litellm.yaml`** — define model aliases (`test`, `medium`, `best`, `coding`, `vision`, `embeddings`) each backed by a fallback chain of providers from this doc.
2. **`DIGI_LLM_MODE`** — env var picks the alias tier.
3. **DigiChat model picker** (future) — UI surfaces provider list from this doc; user pastes their API key; DigiChat writes to LiteLLM proxy config at runtime.
4. **Cost guard** — LiteLLM budgets enforce monthly caps per alias. Flagship tier (`best`) requires explicit opt-in.
5. **Audit** — all routed calls logged via `digibase.audit.redact_mapping` so secrets never persist.

## Maintenance

This catalog is updated automatically. The `provider-review` workflow runs every Monday and:

1. Probes all providers with live API calls (`scripts/provider_review/probe.py`).
2. Claude agent researches rate-limit pages and updates `docs/providers/snapshots/*.yaml`.
3. Regenerates this file and `docs/free-providers/_index.md` from the updated snapshots.
4. Creates GitHub issues for significant changes (model removed, quota dropped ≥20%, free tier discontinued).
5. Evaluates `# llm-decision:` tagged entries in `config/` against current provider state.

**Manual review triggers:** issues labelled `provider-change` mean a solution decision should be reassessed. See `docs/free-providers/_index.md` for the current state of all free-tier limits.

*Verification pointers: each provider's rate-limits + pricing page is authoritative. Cross-check before codifying in `config/litellm.yaml`.*
