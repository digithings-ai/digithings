# Atlas Pipeline — Token Budget & Model Routing Justification

*Last updated: 2026-04-26. Estimates are theoretical; verify against provider dashboards after key installation.*

---

## Three-tier provider strategy

The Atlas pipeline routes each phase to the cheapest free-tier provider that is sufficient for the task. The assignment is deliberate — not arbitrary — and documented here so any change can be evaluated against the same criteria.

| Tier | Provider | Model | Free limit | Use case |
|------|----------|-------|------------|----------|
| 1 | **Groq** | `llama-3.1-8b-instant` | ~20k TPM | Fast extraction, high concurrency |
| 2 | **Ollama Cloud** | `qwen3.5:cloud` (via `DIGI_LLM_MODE`) | ~unlimited* | Deep analysis, sequential reasoning |
| 3 | **Gemini** | `gemini-2.0-flash` | 1M TPM | Long-context synthesis, best reasoning |

*Ollama Cloud is free during preview; enforces soft concurrent-request limits (1–2/s per key) rather than a token cap — the existing exponential-backoff retry handles this.

---

## Per-phase routing decisions

### Phase 1 — Alt-data extraction (4 parallel segments)

**Model:** `groq/llama-3.1-8b-instant`

**Why Groq:**
- Task is structured extraction from pre-fetched text: classify sentiment, extract CTA positioning signals, read options flow numbers. No multi-step reasoning required.
- 4 parallel calls; Groq's high concurrency tolerance (20k TPM free) handles the fan-out without 429s.
- llama-3.1-8b-instant scores well on structured JSON output for extraction tasks.

**Token budget per segment:** ~500 tokens in, ~400 tokens out → 900 tokens × 4 = **~3,600 tokens total**

---

### Phase 2 — Institutional flow extraction (2 parallel segments)

**Model:** `groq/llama-3.1-8b-instant`

**Why Groq:** Same rationale as Phase 1 — extraction of hedge fund 13F signals and institutional order-flow tables. Short context, structured output, high concurrency.

**Token budget per segment:** ~800 tokens in, ~500 tokens out → 1,300 tokens × 2 = **~2,600 tokens total**

---

### Phase 3 — Macro regime (1 segment)

**Model:** Ollama `qwen3.5:cloud` (default via `DIGI_LLM_MODE`)

**Why Ollama:** Macro requires genuine multi-step reasoning across 5+ macro series (Fed, CPI, yield curve, etc.) and must synthesize a coherent regime label with evidence. The 397B MoE qwen3.5 model handles this well. Sequential (1 call) — no concurrency pressure.

**Token budget:** ~2,000 tokens in, ~800 tokens out = **~2,800 tokens total**

---

### Phase 4 — Asset classes (5 parallel segments)

**Model:** Ollama `qwen3.5:cloud` (default via `DIGI_LLM_MODE`)

**Why Ollama:** Each asset class (bonds, commodities, forex, crypto, international) needs to reconcile macro context with technicals and produce a conviction call. Medium reasoning depth, 5 parallel calls. Ollama's soft concurrency limit is fine at this fan-out width (5 calls vs. Groq's 20k TPM).

**Token budget per segment:** ~1,500 tokens in, ~600 tokens out → 2,100 tokens × 5 = **~10,500 tokens total**

---

### Phase 5 — Equities (1 top-down + 11 sectors)

**Model:** Ollama `qwen3.5:cloud` (default via `DIGI_LLM_MODE`)

**Why Ollama:** The equity top-down and each sector analysis reads upstream macro and asset class context, requiring coherent multi-document synthesis. Sectors are parallel (11 calls) but Ollama handles this at this scale. Sector scorecard is deterministic (no LLM).

**Token budget:**
- Equity top-down: ~2,500 tokens in, ~700 out = 3,200
- Per sector: ~2,000 tokens in, ~500 out = 2,500 × 11 = 27,500

**Phase 5 total: ~30,700 tokens**

---

### Phase 7 — Master digest synthesis

**Model:** `gemini/gemini-2.0-flash`

**Why Gemini:** The digest reads ALL phase 1–6 outputs (~6,000–8,000 tokens of context) and must produce a coherent, actionable 7-section snapshot. This is the highest-stakes single LLM call in the pipeline — quality matters most here. Gemini 2.0 Flash has 1M TPM free and excels at long-context synthesis with strong reasoning. Single call — no concurrency pressure.

**Token budget:** ~8,000 tokens in, ~2,000 tokens out = **~10,000 tokens total**

---

### Phase 7C — Per-ticker analyst fan-out (25 tickers in CI)

**Model:** `groq/llama-3.1-8b-instant`

**Why Groq:** This is the dominant cost driver (~85% of tokens at full watchlist scale). Per-ticker analysts perform structured conviction scoring (−5 to +5) from pre-processed sector/macro context. The task is constrained and schema-bound — a small, fast model does it well. Groq's 20k TPM free tier absorbs 25 parallel calls comfortably.

**`ATLAS_MAX_ANALYSTS` cap:** CI sets `ATLAS_MAX_ANALYSTS=25` to keep this phase within free-tier limits. Full watchlist (98 tickers) would require ~98k tokens; 25 tickers stays at ~25k.

**Token budget per ticker:** ~1,000 tokens in, ~400 tokens out = 1,400 tokens × 25 = **~35,000 tokens (CI)**

*Full watchlist (98 tickers): ~137,200 tokens — still within Groq's 20k TPM if serialized across 7+ minutes.*

---

### Phase 7D — PM rebalance decision

**Model:** `gemini/gemini-2.0-flash`

**Why Gemini:** Reads 25–98 analyst payloads plus current portfolio weights, then synthesizes a rebalance action list. Large input context, high-stakes output (actual portfolio actions). Gemini 2.0 Flash's 1M context window handles the full analyst payload set without truncation.

**Token budget:** ~12,000 tokens in (25 analysts), ~1,500 tokens out = **~13,500 tokens total**

---

### Phase 9 — Post-mortem + improvement proposals

**Model:** `gemini/gemini-2.0-flash`

**Why Gemini:** Reads the full digest and evaluates prediction quality across prior snapshots. Reasoning about quality of prior outputs benefits from the strongest available model. Short output (scorecard + rubric + max 2 proposals).

**Token budget:** ~4,000 tokens in, ~800 tokens out = **~4,800 tokens total**

---

## Total per-run estimate (CI with 25 analysts)

| Phase | Provider | Tokens |
|-------|----------|--------|
| 1 — Alt-data (4 segments) | Groq | 3,600 |
| 2 — Institutional (2 segments) | Groq | 2,600 |
| 7C — Analyst fan-out (25 tickers) | Groq | 35,000 |
| **Groq subtotal** | | **41,200** |
| 3 — Macro | Ollama | 2,800 |
| 4 — Asset classes (5 segments) | Ollama | 10,500 |
| 5 — Equities + sectors (12 segments) | Ollama | 30,700 |
| **Ollama subtotal** | | **44,000** |
| 7 — Master digest | Gemini | 10,000 |
| 7D — PM rebalance | Gemini | 13,500 |
| 9 — Evolution | Gemini | 4,800 |
| **Gemini subtotal** | | **28,300** |
| **Grand total** | | **~113,500 tokens/run** |

*Previous single-provider Ollama run: ~674k tokens (full watchlist, no tier routing). This design reduces load per provider by ~83% vs. the original approach.*

---

## Free-tier headroom

| Provider | Estimated per-run | Free limit | Headroom |
|----------|-------------------|------------|----------|
| Groq | ~41k tokens | ~20k TPM | Spread across ~2 min at 5 concurrent calls |
| Ollama Cloud | ~44k tokens | Soft (1–2 req/s) | Backoff retry handles limits |
| Gemini | ~28k tokens | 1M TPM | Negligible usage; 35× headroom |

*Groq note: 20k TPM is a rolling-minute limit. Phase 7C (25 calls, ~25k tokens) is the tightest; calls are parallelized by LangGraph's fan-out. If 429s occur, `_create_with_retry` (7 attempts, 5–120s backoff) will serialize them transparently.*

---

## Getting API keys

### Groq (`GROQ_API_KEY`)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up / log in (free account)
3. Navigate to **API Keys** → **Create API Key**
4. Copy the key and add it:
   - **GitHub Actions:** Settings → Secrets and variables → Actions → `GROQ_API_KEY`
   - **Local `.env`:** `GROQ_API_KEY=gsk_...`

### Gemini (`GEMINI_API_KEY`)
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with a Google account (free tier available)
3. Click **Create API key** → choose or create a Google Cloud project
4. Copy the key and add it:
   - **GitHub Actions:** Settings → Secrets and variables → Actions → `GEMINI_API_KEY`
   - **Local `.env`:** `GEMINI_API_KEY=AIza...`

After adding keys locally, run `python scripts/validate-provider-keys.py` to smoke-test all three providers.

---

## Fallback behavior

If a provider key is missing, `chat_completion` logs a warning and falls back to the Ollama client for that call. The pipeline will complete but with reduced quality on those phases. This means CI will work before keys are added — you'll see fallback warnings in the log.
