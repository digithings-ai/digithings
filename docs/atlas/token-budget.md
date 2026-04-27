# Atlas Pipeline — Token Budget & Model Routing

*Last updated: 2026-04-26.*

---

## Capability tiers

Every phase in the pipeline is assigned a **capability tier** that defines the class of model it requires. Use these tiers when substituting paid models or configuring a custom provider stack.

| Tier | What the phase does | Key model attributes | Free default | Paid upgrade |
|------|--------------------|-----------------------|--------------|--------------|
| **extraction** | Structured JSON parsing from short, constrained inputs. Pulls scores, tickers, and numeric signals from pre-fetched text. No multi-step inference. | Schema compliance, speed, concurrency tolerance | Groq `llama-3.1-8b-instant` | Claude Haiku 4.5, GPT-4o-mini, Gemma 2 9B |
| **research** | Multi-factor financial analysis over moderate context. Macro regime reads, sector deep-dives, asset-class conviction calls. Coherent analytical prose required. | Financial domain knowledge, analytical depth, 32k+ context | Gemini `gemini-2.5-flash` | Claude Sonnet 4.6, GPT-4o, Gemini 2.5 Pro |
| **reasoning** | High-stakes synthesis and portfolio decision-making. Reconciles 20+ upstream signals, resolves contradictions, ranks priorities, and produces output that drives real investment decisions. | Cross-domain synthesis, internal consistency, financial judgment; extended thinking / chain-of-thought beneficial | Ollama Cloud `deepseek-v4-flash:cloud` (284B MoE, 1M ctx) | Claude Opus 4.7 (extended thinking), GPT-o1/o3, Gemini 2.5 Pro (paid) |

---

## Per-phase routing

### Phase 1 — Alt-data extraction `[tier: extraction]`

**Model:** `groq/llama-3.1-8b-instant`  
**Segments:** 4 parallel (sentiment-news, cta-positioning, options-derivatives, politician-signals)

Task is structured extraction from pre-fetched text: classify sentiment, extract CTA positioning signals, read options flow numbers. No multi-step reasoning required. 4 parallel calls; Groq's 20k TPM free tier handles the fan-out without throttling.

**Token budget per segment:** ~500 in + ~400 out = 900 × 4 = **~3,600 tokens**

---

### Phase 2 — Institutional flow extraction `[tier: extraction]`

**Model:** `groq/llama-3.1-8b-instant`  
**Segments:** 2 parallel (institutional-flows, hedge-fund-intel)

Extraction of hedge fund 13F signals and institutional order-flow tables. Short context, structured output, same rationale as Phase 1.

**Token budget per segment:** ~800 in + ~500 out = 1,300 × 2 = **~2,600 tokens**

---

### Phase 3 — Macro regime `[tier: research]`

**Model:** Gemini `gemini-2.5-flash` (via `defaults[DIGI_LLM_MODE]`)  
**Segments:** 1 sequential

Synthesizes 5+ macro series (Fed, CPI, yield curve, DXY, energy) into a coherent regime label with conviction and factors. This regime flows into every downstream phase, so quality matters. Sequential — no concurrency pressure.

**Token budget:** ~2,000 in + ~800 out = **~2,800 tokens**

---

### Phase 4 — Asset classes `[tier: research]`

**Model:** Gemini `gemini-2.5-flash` (via `defaults[DIGI_LLM_MODE]`)  
**Segments:** 5 parallel (bonds, commodities, forex, crypto, international)

Each segment reconciles macro context with asset-class technicals and produces a conviction call. Medium reasoning depth; parallel fan-out is manageable for Gemini's free tier.

**Token budget per segment:** ~1,500 in + ~600 out = 2,100 × 5 = **~10,500 tokens**

---

### Phase 5 — Equities + sectors `[tier: research]`

**Model:** Gemini `gemini-2.5-flash` (via `defaults[DIGI_LLM_MODE]`)  
**Segments:** 1 equity top-down + 11 sector nodes (parallel) + 1 scorecard (deterministic, no LLM)

Each segment reads upstream macro and asset-class context, requiring coherent multi-document analysis. The sector scorecard synthesises all 11 sector slots deterministically — no additional LLM call.

**Token budget:**
- Equity top-down: ~2,500 in + ~700 out = 3,200
- Per sector: ~2,000 in + ~500 out = 2,500 × 11 = 27,500

**Phase 5 total: ~30,700 tokens**

---

### Phase 7C — Per-ticker analyst fan-out `[tier: extraction — throughput-constrained]`

**Model:** `groq/llama-3.1-8b-instant`  
**Segments:** up to 25 tickers in CI (`ATLAS_MAX_ANALYSTS=25`)

> **Why not research tier?** Writing a 1,200-char investment thesis and conviction score (−5 to +5) ideally belongs in the research tier. However, 25 parallel calls × ~1.4k tokens ≈ 35k tokens exceeds Groq's 70B model free limit (12k TPM) but fits within the 8B model (20k TPM). The 8B assignment is a concurrency tradeoff.
>
> **To upgrade:** Reduce `ATLAS_MAX_ANALYSTS` (fewer tickers → fewer tokens per minute), switch to a paid Groq plan and use `llama-3.3-70b-versatile`, or route Phase 7C to Gemini and accept rate-limiting with backoff.

**Token budget per ticker:** ~1,000 in + ~400 out = 1,400 × 25 = **~35,000 tokens (CI)**  
*Full watchlist (98 tickers): ~137k tokens — serialised across 7+ minutes at 20k TPM.*

---

### Phase 7 — Master digest synthesis `[tier: reasoning]`

**Model:** `ollama-cloud/deepseek-v4-flash:cloud`

The highest-stakes single LLM call in the pipeline. Reads ALL phase 1–6 outputs (~8k tokens of context) and produces a 7-section snapshot: market regime, segment summaries, actionable items with priorities, risk radar, portfolio recommendations. The model must reconcile 20+ upstream signals into a coherent, non-contradictory narrative. Quality differences between model tiers are most visible here.

> **Why not Gemini 2.5 Pro?** Moved to paid-only in December 2025.  
> **Why not Groq reasoning models?** Free tier caps at 6k TPM — this call alone needs ~10k tokens.  
> Ollama Cloud handles 2 sequential reasoning calls/day well within free session limits. Uses the existing `OPENAI_API_KEY` credential.

**Token budget:** ~8,000 in + ~2,000 out = **~10,000 tokens**

---

### Phase 7D — PM rebalance decision `[tier: reasoning]`

**Model:** `ollama-cloud/deepseek-v4-flash:cloud`

Reads the full set of analyst payloads (25–98 tickers) plus current portfolio weights, then synthesises a rebalance action list with rationale. Real portfolio allocation decisions with financial stakes. DeepSeek V4 Flash (284B MoE, 13B active, 1M context) is a strong reasoning model with enough context window to handle the full analyst payload.

**Token budget:** ~12,000 in (25 analysts) + ~1,500 out = **~13,500 tokens**

---

### Phase 9 — Pipeline evolution / post-mortem `[tier: research]`

**Model:** `gemini/gemini-2.5-flash`

Reads the digest and evaluates prediction quality across prior snapshots. Generates a quality scorecard and up to 2 improvement proposals. Important for pipeline health but not a live investment decision — research tier is appropriate.

**Token budget:** ~4,000 in + ~800 out = **~4,800 tokens**

---

## Per-run token summary (CI, 25 analysts)

| Phase | Tier | Provider | Model | Tokens |
|-------|------|----------|-------|--------|
| 1 — Alt-data (4 segments) | extraction | Groq | llama-3.1-8b-instant | 3,600 |
| 2 — Institutional (2 segments) | extraction | Groq | llama-3.1-8b-instant | 2,600 |
| 7C — Analyst fan-out (25 tickers) | extraction* | Groq | llama-3.1-8b-instant | 35,000 |
| **Groq subtotal** | | | | **41,200** |
| 3 — Macro | research | Gemini | gemini-2.5-flash | 2,800 |
| 4 — Asset classes (5 segments) | research | Gemini | gemini-2.5-flash | 10,500 |
| 5 — Equities + sectors (12 segments) | research | Gemini | gemini-2.5-flash | 30,700 |
| 9 — Evolution | research | Gemini | gemini-2.5-flash | 4,800 |
| **Gemini Flash subtotal** | | | | **48,800** |
| 7 — Master digest | reasoning | Ollama Cloud | deepseek-v4-flash:cloud | 10,000 |
| 7D — PM rebalance | reasoning | Ollama Cloud | deepseek-v4-flash:cloud | 13,500 |
| **Ollama Cloud subtotal** | | | | **23,500** |
| **Grand total** | | | | **~113,500 tokens** |

*Phase 7C is throughput-constrained to extraction tier; see note above.*

---

## Free-tier headroom

| Provider | Model | Per-run estimate | Free limit | Notes |
|----------|-------|-----------------|------------|-------|
| Groq | llama-3.1-8b-instant | ~41k tokens | ~20k TPM | Phase 7C (25 calls) is tightest; backoff retry serialises across ~2 min |
| Gemini Flash | gemini-2.5-flash | ~49k tokens | 1M TPM, 1500 RPD | Negligible usage — 35× TPM headroom |
| Ollama Cloud | deepseek-v4-flash:cloud | ~24k tokens | Session-based (resets every 5h) | 2 calls/day — negligible vs. free quota |

---

## Paid / custom provider upgrade guide

To substitute paid models, replace values in `config/model_modes.yaml` → `phase_models`:

```yaml
# extraction tier upgrades (phases 1, 2, 7C)
alt-sentiment-news: "groq/llama-3.3-70b-versatile"   # paid Groq plan
analyst-: "anthropic/claude-haiku-4-5"                # or any fast model

# research tier upgrades (phases 3, 4, 5, 9 via defaults)
# change defaults.medium / defaults.best:
defaults:
  medium: "anthropic/claude-sonnet-4-6"
  best: "anthropic/claude-sonnet-4-6"

# reasoning tier upgrades (phases 7, 7D)
# Free default: ollama-cloud/deepseek-v4-flash:cloud
# Paid upgrades:
master-digest: "gemini/gemini-2.5-pro"         # paid Gemini key required
pm-rebalance:  "anthropic/claude-opus-4-7"     # + enable extended_thinking
```

To add a new provider, register it in `_EXTERNAL_PROVIDERS` in `digigraph/src/digigraph/llm.py` with its base URL and API key env var name.

---

## Getting API keys

### Groq (`GROQ_API_KEY`)
1. [console.groq.com](https://console.groq.com) → sign up free → **API Keys** → Create
2. Add as GitHub secret `GROQ_API_KEY` or local `GROQ_API_KEY=gsk_...`

### Gemini (`GEMINI_API_KEY`)
1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → Create API key
2. Add as GitHub secret `GEMINI_API_KEY` or local `GEMINI_API_KEY=AIza...`

Both Flash and Pro use the same key. Free tier includes both models.

---

## Fallback behaviour

If a provider key is missing at runtime, `chat_completion` raises `RuntimeError` (it does not silently fall back — a missing key on a reasoning-tier phase would silently degrade quality in a way that's hard to detect). CI will fail fast with a clear error message identifying which env var is absent.

For local dev without Groq/Gemini keys, set `DIGI_LLM_MODE=test` to route all phases through Ollama Cloud.
