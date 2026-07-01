# Provider Review System — Design Spec

**Date:** 2026-05-01
**Status:** Approved
**Author:** Chris Stefan

---

## Problem

DigiThings routes all LLM traffic through LiteLLM and depends heavily on free-tier providers to stay nimble. Free-tier quotas, model availability, and pricing change without notice. Today there is no automated mechanism to:

- Detect when a free-tier limit drops or a model moves behind a paywall
- Verify that configured models are actually reachable with the keys we have
- Evaluate whether model/provider decisions made across the project (Atlas phases, Hermes, DigiChat defaults) are still optimal given the current free-tier landscape
- Surface when a paid option becomes cost-justified relative to a free alternative

---

## Goals

1. Maintain a comprehensive, machine-readable snapshot of every LLM provider's current offering (free and paid) in `docs/providers/snapshots/`
2. Live-probe all providers where we have API keys to verify reachability and latency
3. Weekly automated evaluation of all `# llm-decision:` tagged config entries against current provider data
4. Auto-create GitHub issues when any trigger condition is met
5. Keep `docs/LLM_PROVIDERS.md` regenerated and current at all times

---

## Non-goals

- A centralised decisions registry (intent lives as inline comments in config files)
- Replacing the existing `docs/providers/*.md` setup guides (those remain human-maintained)
- Automated remediation — issues are created for human review, never auto-fixed

---

## Architecture

### Component 1: Provider snapshot YAMLs

**Location:** `docs/providers/snapshots/<provider>.yaml` — one file per provider.

These are the machine-readable source of truth. The agent diffs them week-over-week to detect changes. The existing `docs/providers/*.md` files remain as human-readable setup guides and are not replaced.

**Full schema:**

```yaml
provider: gemini
last_checked: 2026-05-01
source: agent-research          # agent-research | litellm | manual

free_tier:
  available: true
  tier_type: standing           # standing | credits | trial
  credit_amount_usd: null       # if credits: initial grant value in USD
  credit_expiry_days: null      # if credits: days until expiry; null = no expiry
  privacy_warning: "Free-tier prompts used for Google model training"
  signup_required: false
  cc_required: false
  models:
    - name: gemini-2.5-flash
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      status: active            # active | deprecated | paid-only
      verified: true
      last_verified: 2026-05-01
      last_verified_latency_ms: 842
      verification_error: null  # last error message if probe failed
  rate_limits:
    rpm: 10
    rpd: 250
    tpm: 250000
    input_tpm: null             # null = provider does not publish separate input cap
    concurrent_requests: null
    reset_window: calendar_day  # calendar_day | rolling_24h | rolling_minute

paid_tier:
  available: true
  models:
    - name: gemini-2.5-flash
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      cost_per_1m_input: 0.30
      cost_per_1m_input_long: null   # null = no long-context surcharge
      cost_per_1m_output: 2.50
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.075
      status: active
    - name: gemini-2.5-pro
      context_window: 2097152
      max_input_tokens: 2097152
      max_output_tokens: 65536
      cost_per_1m_input: 1.25
      cost_per_1m_input_long: 2.50  # >200k tokens
      cost_per_1m_output: 10.00
      cost_per_1m_output_long: 15.00
      cost_per_1m_input_cached: 0.31
      status: active
  batching:
    available: true
    discount_pct: 50
    max_batch_size: null            # null = unlimited
    turnaround_hours: 24
    notes: "Async batch API; results via polling"
  prompt_caching:
    available: true
    min_cacheable_tokens: 1024
    ttl_seconds: 3600
    cost_per_1m_cached_writes: 0.375
    cost_per_1m_cached_reads: 0.075
    notes: "Cache writes billed once; reads at ~75% discount"

capabilities:
  tool_calling: true
  structured_output: true         # native JSON mode
  thinking_mode: true             # extended reasoning / CoT
  streaming: true
  vision: true
  embeddings: true
  modalities: [text, image, audio, video]

data_privacy:
  trains_on_free_tier: true
  retention_days: null            # null = provider-managed / unknown
  zero_retention_on_paid: true
  gdpr_compliant: true
  soc2: false

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []     # ISO-3166 country codes where blocked

verification:
  method: litellm_probe           # litellm_probe | direct_api | skipped
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: gemini-flash # alias in config/litellm.yaml used for probe
  github_secret_key: GEMINI_API_KEY

notes: "Paid: same API key, enable GCP billing."
```

`null` throughout means the provider does not publish or offer that feature.

---

### Component 2: Decision comment convention

Config YAML files across the project use a two-line inline comment convention to declare model selection intent. The workflow scanner greps for these to build the list of entries to evaluate.

**Format:**

```yaml
# llm-decision: <space-separated tags>
# <optional prose: rationale, constraints, known trade-offs>
model: gemini/gemini-2.5-flash
```

**Standard tags:**

| Tag | Meaning |
|---|---|
| `extraction` | Structured JSON parsing from short, well-defined inputs |
| `research` | Multi-factor analytical prose over moderate context |
| `reasoning` | High-stakes synthesis, cross-domain reconciliation |
| `free-preferred` | Free tier strongly preferred; upgrade only if justified |
| `paid-acceptable` | Paid acceptable if cost delta is material |
| `cost-sensitive` | Flag even small cost increases |
| `throughput-constrained` | Throughput more important than single-call quality |

**Files scanned:**

- `config/model_modes.yaml`
- `config/litellm.yaml`
- `digiquant/src/digiquant/olympus/atlas/config/`
- `digiquant/src/digiquant/olympus/hermes/config/` (when it exists)
- Any `**/config/*.yaml` not in `.gitignore`

The existing `[tier: extraction|research|reasoning]` comments in `config/model_modes.yaml` will be migrated to the new `# llm-decision:` format as part of implementation.

---

### Component 3: Provider coverage

**Probeable providers** (live `litellm_probe` on each run):

| Provider | GitHub secret | LiteLLM prefix |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | `gemini/` |
| Groq | `GROQ_API_KEY` | `groq/` |
| Cerebras | `CEREBRAS_API_KEY` | `cerebras/` |
| Mistral | `MISTRAL_API_KEY` | `mistral/` |
| NVIDIA NIM | `NVIDIA_API_KEY` | `nvidia_nim/` |
| Ollama Cloud | `OLLAMA_API_KEY` | `ollama-cloud/` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/` |
| GitHub Models | `GITHUB_TOKEN` | `github/` |

**Research-only providers** (agent research, no live probe — tracked for cost-benefit analysis and future key addition):

xAI (Grok), OpenAI, Anthropic, Cohere, Fireworks, Together AI, DeepInfra, Perplexity, Cloudflare Workers AI, SambaNova, HuggingFace

When a key is added to the GitHub org for any research-only provider, the workflow automatically upgrades it to `litellm_probe` on the next run — no code change required.

**Note on Groq:** Known to be unreliable for this project. Pre-flagged as `known_instability: true` in snapshot. Probe failures will not generate issues unless Groq appears in an active `# llm-decision:` entry — in which case the issue fires once, not weekly.

---

### Component 4: Weekly workflow

**File:** `.github/workflows/pipeline-provider-review.yml`
**Schedule:** Sunday 00:00 UTC + `workflow_dispatch`
**Secret dependencies:** `CLAUDE_CODE_OAUTH_TOKEN`, `DIGITHINGS_PROJECT_TOKEN`, plus all provider keys above

**Step 1 — Probe** (~2 min, bash)

For each of the 9 probeable providers, send the probe prompt (`"Reply with the single word: ok"`) using the `litellm` Python library (not the running Docker proxy — CI has no stack). Each call uses the corresponding GitHub secret injected as an env var. Record success/failure, latency, and error message. Write `/tmp/review/probe-results.json`.

Probe failures are non-fatal — the step always exits 0. A provider that fails probe is flagged in the results; the agent decides significance.

**Step 2 — Bootstrap context** (~1 min, bash)

Assemble the agent's input package into `/tmp/review/`:

- All current snapshot YAMLs from `docs/providers/snapshots/`
- `probe-results.json` from Step 1
- LiteLLM `model_prices_and_context_window.json` fetched from upstream GitHub raw
- All `# llm-decision:` tagged comment blocks extracted via grep from scanned config files, with file path and line number for each

**Step 3 — Claude agent** (~10 min, `CLAUDE_CODE_OAUTH_TOKEN`)

The agent receives the full context package and executes in order:

1. **Research** each provider's current free-tier offerings using web search, cross-referencing against the bootstrapped context
2. **Update** all snapshot YAMLs in `docs/providers/snapshots/` with fresh data merged with probe results
3. **Regenerate** `docs/LLM_PROVIDERS.md` from updated snapshots
4. **Evaluate** each extracted `# llm-decision:` entry:
   - Is the current model still available and verified?
   - Has a materially better free option emerged for this role?
   - Is the cost delta for a paid upgrade now justified?
   - Include a one-line cost-benefit score (e.g., "current free scores 8.4; Sonnet at $0.43/run scores 9.4")
5. **Write** `/tmp/review/findings.json` — one object per trigger condition found
6. **Commit** all snapshot and doc changes directly to `develop`

**Step 4 — Issue creation** (~1 min, Python + gh CLI)

Read `findings.json`, deduplicate against open issues tagged `provider-review`, open one GitHub issue per novel finding.

**Issue labels:** `exec:claude,component:root,type:research,priority:medium,risk:low,provider-review`

**Prerequisite:** The `provider-review` label must exist in the GitHub repo. Implementation creates it via `gh label create` if absent.

---

### Trigger conditions (any one opens an issue)

| Condition | Description |
|---|---|
| Quota drop | Free-tier RPM/RPD/TPM drops on a provider referenced in an active `# llm-decision:` entry |
| Model deprecated or paid-only | A model currently configured in the project fails probe or is documented as removed from free tier |
| Better free option available | A new free model materially outperforms the current choice for a given decision role (agent judges materiality) |
| Paid cost increase >20% | A paid provider used in fallback chains raises prices above threshold |

---

### Issue format

```markdown
<!-- provider-review -->
## Provider change detected: <provider> — <one-line summary>

**Trigger:** <which of the 4 conditions>
**Affected config:** `config/model_modes.yaml:42` (`# llm-decision: reasoning free-preferred`)
**Current model:** `ollama-cloud/deepseek-v3.1:671b`
**Finding:** Model returned 403 on probe (2026-05-01). Likely moved to subscription tier.

### Cost-benefit assessment
| Option | Score | Est. cost/run | Notes |
|---|---|---|---|
| Current (deepseek-v3.1) | — | $0 | Probe failing |
| DeepSeek R1 via API | 9.1 | $0.08 | DEEPSEEK_API_KEY already set |
| Claude Sonnet 4.6 | 9.4 | $0.43 | CLAUDE_CODE_OAUTH_TOKEN available |

**Recommendation:** Switch reasoning tier to DeepSeek R1 via direct API — minimal cost, key already present, strong reasoning benchmark parity.

### Next steps
- [ ] Review affected config entry
- [ ] Run `make task ISSUE=<N>` to execute update
```

---

## File layout after implementation

```
docs/
  LLM_PROVIDERS.md              # regenerated weekly from snapshots
  providers/
    README.md                   # existing, unchanged
    *.md                        # existing setup guides, unchanged
    snapshots/
      gemini.yaml
      groq.yaml
      cerebras.yaml
      mistral.yaml
      nvidia_nim.yaml
      ollama_cloud.yaml
      openrouter.yaml
      deepseek.yaml
      github_models.yaml
      xai.yaml                  # research-only, no probe
      openai.yaml
      anthropic.yaml
      cohere.yaml
      fireworks.yaml
      together.yaml
      deepinfra.yaml
      perplexity.yaml
      cloudflare.yaml
      sambanova.yaml
      huggingface.yaml
.github/
  workflows/
    provider-review.yml
scripts/
  provider_review/
    probe.py                    # Step 1: live probe runner
    bootstrap.py                # Step 2: context assembler
    create_issues.py            # Step 4: issue dedup + creation
```

---

## Decision comment migration

As part of implementation, the existing `[tier: extraction|research|reasoning]` comment blocks in `config/model_modes.yaml` will be augmented (not replaced) with `# llm-decision:` tags. Existing prose is preserved. Example:

**Before:**
```yaml
  # Phase 1 — alt-data extraction
  # [tier: extraction] — sentiment scores, CTA signals
  alt-sentiment-news: "gemini/gemini-2.5-flash"
```

**After:**
```yaml
  # Phase 1 — alt-data extraction
  # llm-decision: extraction free-preferred throughput-constrained
  # [tier: extraction] — sentiment scores, CTA signals; Gemini Flash chosen over Groq
  # (Groq TPM too low at 6k; Flash handles 41k tokens/run at 250k TPM)
  alt-sentiment-news: "gemini/gemini-2.5-flash"
```

---

## Open questions (resolved)

- **Groq instability**: Pre-flagged `known_instability: true`; probe failures suppressed unless active in a decision entry
- **Research-only providers**: Full snapshot schema applied, no probe; agent research populates data
- **Key addition**: Adding a new org secret automatically upgrades a provider to probe on next run
- **Centralized registry**: Explicitly not maintained; inline comments are the source of intent
