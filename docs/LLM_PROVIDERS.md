# LLM Provider Catalog — Free Tiers, Cheap APIs, Local Options

*Reference snapshot: July 2026. Pricing and quotas change frequently — treat numbers as directional and verify against each provider's console before committing to production use. Items marked (uncertain) could not be confirmed at time of writing.*

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
- **Free tier:** Standing, no expiry. Gemini 2.5 Flash 15 RPM / 1,500 RPD / 1M TPM; Flash-Lite 30 RPM / 1,500 RPD / 1M TPM (double the RPM of Flash at the same RPD/TPM). Pro is **paid-only** (free 2 RPM tier removed 2026-04-01).
- **Best free models:** `gemini-2.5-flash` (workhorse, vision, 1M ctx), `gemini-2.5-flash-lite` (highest RPM). Embeddings: `text-embedding-004`. Gemini 3 generation (`gemini-3-flash-preview`, `gemini-3.5-flash`, `gemini-3.1-pro-preview`) is paid-only for now — exact free-tier availability for the 3.x line is unconfirmed this cycle.
- **Paid:** Flash ~$0.30 / $2.50 per 1M; Flash-Lite ~$0.10 / $0.40; Pro ~$1.25 / $10 (≤200K), $2.50 / $15 above. Gemini 3-flash-preview $0.50/$3.00, 3.5-flash $1.50/$9.00, 3.1-pro-preview $2/$12 (≤200K), $4/$18 above.
- **LiteLLM:** `gemini/gemini-2.5-flash`. Env: `GEMINI_API_KEY`.
- **Gotcha:** **Free-tier prompts/responses are used to improve Google products.** Never send confidential data on free. Paid tier is zero-retention.

### 2. Groq

- **URL:** https://console.groq.com
- **Free tier:** Standing. 30 RPM, **1,000 RPD (binding constraint)**, ~12,000 TPM on `llama-3.3-70b-versatile` (varies by model).
- **Best free models:** `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`. Plus Whisper STT. `llama-4-scout-17b-16e-instruct` was **deprecated from the free/developer tier 2026-06-17** — migrate to `gpt-oss-120b` or `qwen3.6-27b`.
- **Paid:** Llama 3.3 70B ~$0.59 / $0.79; gpt-oss-120b ~$0.15 / $0.60 (prompt caching $0.075/1M); Llama 4 Scout ~$0.11 / $0.34 (paid-only now).
- **LiteLLM:** `groq/llama-3.3-70b-versatile`. Env: `GROQ_API_KEY`.
- **Selling point:** 500–1500 tok/s inference. Use exponential backoff for bursts. Groq entered a non-exclusive inference-tech licensing deal + acquihire with Nvidia (announced May 2026); GroqCloud continues operating independently — no observed effect on free-tier limits/pricing so far.

### 3. Cerebras

- **URL:** https://cloud.cerebras.ai
- **Free tier (unconfirmed this cycle — sources conflict):** Cerebras's current docs describe a "Free Trial" of 5 RPM / 30K TPM / 1M TPD on `gpt-oss-120b`, `zai-glm-4.7`, `gemma-4-31b`, requiring a verified payment method for $5 in credits (30-day expiry) — a departure from the previously-documented no-CC 30 RPM tier. `llama-3.3-70b` no longer appears on Cerebras's free-tier page at all (404s on probe). Treat quota numbers here as directional pending a direct signup-flow check.
- **Best free models:** `gpt-oss-120b` (~3000 tok/s). `llama-3.3-70b`/`llama-4-scout`/`qwen-3-32b`/`qwen3-235b` are no longer confirmed on the free tier as of 2026-07-19. >2000 tok/s — fastest on market.
- **LiteLLM:** `cerebras/llama-3.3-70b`. Env: `CEREBRAS_API_KEY`.
- **Gotcha:** Context often clipped below native (8K–32K) on free. Model roster and CC requirement are in flux — re-verify before depending on this provider.

### 4. OpenRouter

- **URL:** https://openrouter.ai
- **Free tier:** Routes `:free` variants. 20 RPM; 50 RPD with <$10 balance, 1000 RPD after.
- **Best `:free` models:** `openai/gpt-oss-20b:free` (reliable, near o3-mini on coding), `qwen/qwen3-coder:free` (480B MoE, 1M ctx, strong agentic/tool-calling). **`meta-llama/llama-3.3-70b-instruct:free` is sunsetting 2026-07-19 — do not use.** `deepseek/deepseek-chat-v3:free`, `deepseek/deepseek-r1:free`, `google/gemini-2.0-flash-exp:free`, `qwen/qwen3-235b-a22b:free` status is unconfirmed this cycle (one secondary source suggests they may no longer be free — verify before relying on them). Roster rotates.
- **Paid:** Aggregator markup ~0–5% over upstream. BYO-key supported (5% surcharge).
- **LiteLLM:** `openrouter/openai/gpt-oss-20b:free`. Env: `OPENROUTER_API_KEY`.
- **Gotcha:** `:free` routes can be slow / queue-prone, and individual models are retired with little notice (see llama-3.3-70b-instruct:free above). Providers may log prompts — check each model card.

### 5. Cloudflare Workers AI

- **URL:** https://developers.cloudflare.com/workers-ai
- **Free tier:** **10,000 neurons/day standing free** (~few thousand small-model calls) — confirmed unchanged, and the free-tier model was explicitly excluded from Cloudflare's 2026-05-30 deprecation wave.
- **Best models:** Llama 3.3/4, DeepSeek, Qwen, Mistral, GLM-5.2 (new, added 2026-06-16, supersedes GLM-4.7-flash), BGE embeddings, Whisper, image models.
- **Paid:** $0.011 per 1000 neurons beyond free.
- **LiteLLM:** `cloudflare/@cf/meta/llama-3.3-70b-instruct`. Env: `CLOUDFLARE_API_KEY` + account ID.
- **Gotcha:** Neuron accounting is opaque; best used from inside Workers runtime. Kimi K2.5 now auto-aliases to the pricier K2.6.

### 6. Mistral La Plateforme

- **URL:** https://console.mistral.ai
- **Free tier:** "Experimental" — reported ~1 RPS (2 RPM), ~1B tokens/month across chat models, phone verification required. **Low confidence:** Mistral's public docs no longer publish exact numeric limits (gated behind the logged-in Admin Console "Limits" page) — verify before depending on this figure.
- **Best free models:** `mistral-large-latest`, `mistral-small-latest`, `codestral-latest` (coding), `pixtral-large` (vision), `ministral-8b`.
- **Paid:** Large ~$2 / $6; Small ~$0.20 / $0.60; Codestral ~$0.30 / $0.90; Medium 3.5 $1.50/$7.50 (262K ctx, new).
- **LiteLLM:** `mistral/mistral-large-latest`. Env: `MISTRAL_API_KEY`.
- **Gotcha:** Free tier explicitly **allows training on your data** unless on paid. Codestral commercial use requires paid.

### 7. SambaNova Cloud

- **URL:** https://cloud.sambanova.ai
- **Free tier:** 20 RPM **and 20 RPD** (requests/day — the harder binding constraint), ~200,000 TPD.
- **Best models:** Llama 3.3 70B, DeepSeek V3.1/V3.2, gpt-oss-120b. Llama 4 Scout/Maverick, DeepSeek R1, MiniMax-M2.7, and Qwen3-32B dropped off the official free-tier table this cycle (MiniMax-M2.7 moved to paid Developer tier). Very fast RDU inference.
- **LiteLLM:** `sambanova/Meta-Llama-3.3-70B-Instruct`. Env: `SAMBANOVA_API_KEY`.

### 8. Nvidia NIM (build.nvidia.com)

- **URL:** https://build.nvidia.com
- **Free tier:** 1,000 credits on signup; 5,000 more with Developer Program. Credits don't refill. 40 RPM practical ceiling.
- **Best models:** Nemotron 3 Ultra (550B MoE, 1M ctx), Llama Nemotron 70B (reasoning), Llama 3.3/4, DeepSeek R1, NVIDIA embeddings.
- **LiteLLM:** `nvidia_nim/<model>`. Env: `NVIDIA_NIM_API_KEY`.
- **Best use:** Evaluating models before choosing a long-term host.
- **Gotcha:** Free tier has **chronic latency/overload under load** — community reports of multi-minute timeouts, not a one-off outage. Expect to need long timeouts and retries.

### 9. GitHub Models

- **URL:** https://github.com/marketplace/models
- **⚠️ RETIRING 2026-07-30.** GitHub announced full retirement of the platform (playground, model catalog, inference API, BYOK) for everyone, including existing customers. Already blocked for new customers/orgs since 2026-06-16, with brownouts on 2026-07-16 and 2026-07-23. **Do not build new dependencies on this provider** — migrate to Microsoft Foundry or GitHub Copilot, or another provider in this catalog.
- **Free tier (moot after 2026-07-30):** Free for GitHub users. Rate-limited by Copilot tier: Free ~50 RPD low-tier, 10 RPD high-tier. Context often capped (8K in / 4K out on free). Access requires a token with the `models:read` permission explicitly granted — the default Actions `GITHUB_TOKEN` does **not** carry this scope automatically.
- **Best models:** GPT-5 family, Claude subset, Llama, Mistral, Phi, Cohere, DeepSeek.
- **LiteLLM:** `github/gpt-4.1`. Env: `GITHUB_TOKEN` (PAT, with `models:read`).
- **Gotcha:** **ToS restricts free tier to evaluation — not production.** With the full retirement 11 days out (as of this snapshot), plan removal rather than a production upgrade.

### 10. Ollama Cloud

- **URL:** https://ollama.com/cloud
- **Free tier:** Metered usage levels 1–4 (lightest to heaviest), 1 concurrent model.
- **Best models:** gpt-oss:20b (lightest), deepseek-v3.1:671b, deepseek-v4-flash, cogito-2.1:671b, nemotron-3-super:cloud. Current live catalog also includes gemma4, qwen3.5, glm-5.1/5.2, minimax-m2.x/m3, kimi-k2.5/2.6/2.7-code, mistral-large-3 — some older model ids may have been superseded by these, unconfirmed. kimi-k2-thinking is paid-only.
- **Paid:** Pro $20/mo (50× free, 3 concurrent); Max $100/mo.
- **LiteLLM:** OpenAI-compatible passthrough — `openai/gpt-oss:120b-cloud` with `api_base=https://ollama.com/v1`.
- **Gotcha:** verify model ids against `ollama.com/search?c=cloud` before adding to config — not every plausible-looking `:cloud`-suffixed id is real.

### 11. Hugging Face Inference Providers

- **URL:** https://huggingface.co/docs/api-inference
- **Free tier:** Official docs now denominate credits in dollars — **$0.10/month free**, **$2.00/month on PRO** ($9/mo). This is a large drop from the previously-tracked "100K/2M credits" framing; flagged for manual re-verification against a live account before relying on it.
- **Best use:** Model discovery + eval; routes to Together/Fireworks/SambaNova/Cerebras/DeepInfra/fal/Replicate behind the scenes.
- **LiteLLM:** `huggingface/<model>`. Env: `HF_TOKEN`.

### 12. Other free-adjacent

- **Cohere** — free trial key, 1,000 calls/month, 20 RPM. Command A strong at RAG ($2.50/$10); Command A+ (218B MoE, Apache 2.0) is open-weight self-host — **not** on the public per-token rate card despite earlier records, hosted-endpoint pricing is "contact sales." Embed v4.0 (multimodal) $0.12/1M text tokens. `cohere/command-a-03-2025`. Trial keys forbidden for commercial.
- **AI21** — $10 signup credit. Jamba 1.5 Large/Mini (256K context). `ai21/jamba-1.5-large`.
- **xAI (Grok)** — no permanently-free model; $25 signup credit + up to $150/mo via data-sharing opt-in. New flagship `grok-4.5` (2026-07-08, "Opus-class") at $2/$6 (<200K), $4/$12 (≥200K). `xai/grok-4-3` is the default/cheapest current tier at $1.25/$2.50; `grok-3` fully retires 2026-08-15.

---

## Cheap paid APIs (for when free runs out)

| Provider | Model | Input $/1M | Output $/1M |
|---|---|---|---|
| DeepSeek direct | `deepseek-v4-flash` (replaces V3) | $0.07–0.14 (cache-miss figure unconfirmed) | $0.28 |
| DeepSeek direct | `deepseek-v4-pro` (replaces R1) | $0.435 | $0.87 |
| Gemini | Flash-Lite | $0.10 | $0.40 |
| Gemini | Flash | $0.30 | $2.50 |
| OpenAI | GPT-4.1-mini | $0.40 | $1.60 |
| OpenAI | GPT-4.1-nano | ~$0.10 | ~$0.40 |
| Groq | Llama 3.1 8B | $0.05 | $0.08 |
| Groq | gpt-oss-120b | $0.15 | $0.60 |
| DeepInfra | Llama 3.3 70B Turbo | $0.10 | $0.32 |
| DeepInfra | DeepSeek V3 | $0.32 | $0.89 |
| Fireworks | Llama 3.3 70B | $0.90 | $0.90 |
| Anthropic | Haiku 4.5 | $1.00 | $5.00 |
| Anthropic | Sonnet 4.6 / Sonnet 5 | $3 | $15 |
| Anthropic | Opus 4.7 / 4.8 | $5 | $25 |
| Perplexity | Sonar | $1 + $5/1k searches | $1 |

**Rule of thumb:** $5 topped up on DeepSeek or Gemini lasts weeks of dev testing. Batch APIs (OpenAI, Anthropic) and off-peak discounts (DeepSeek) halve effective cost.

**Note (2026-07-19):** Together AI's $25 no-CC signup credit has been discontinued — a $5 minimum prepaid purchase with a payment method is now required, so it no longer belongs in a "cheap/free" comparison without that caveat.

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
| High-volume dev testing | Groq + Gemini Flash-Lite + Cloudflare Workers AI (chained) | ~2.5K+ combined free RPD, no expiry (Groq RPD dropped to 1,000) |
| Fast coding completions | Groq `qwen/qwen3.6-27b` or Mistral `codestral-latest` | Fast on Groq; Codestral purpose-built |
| Long-context RAG | Gemini 2.5 Flash (1M ctx, free) | Only free 1M-context option at scale |
| Vision / multimodal | Gemini 2.5 Flash or Mistral Pixtral (free) | Native multimodal, no extra charge |
| Reasoning / math | DeepSeek `deepseek-v4-pro` (cheap paid, thinking mode) — free OpenRouter `deepseek/deepseek-r1:free` availability unconfirmed this cycle | Frontier reasoning at low cost even off free tier |
| Cheap bulk embeddings | Gemini `text-embedding-004` or Cloudflare BGE; paid: Cohere Embed v3/v4 | Free at dev scale |
| Production fallback chain | LiteLLM: Groq → Gemini Flash → DeepSeek → Anthropic | Speed-first, cost-second, quality-third. Cerebras and Together both now require a payment method / CC-backed credit — not reliable no-CC free links in this chain anymore |
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
