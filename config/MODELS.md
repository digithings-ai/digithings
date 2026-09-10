# Model list and mode selection (for agents)

**Part of [digithings](../README.md) (digithings.ai).**  
**Purpose:** Central place for LLM model config used by digigraph and other components. Agents should update the model list when new Ollama Cloud (or other) models appear so model selection stays self-updating.

## Files

| File | Role |
|------|------|
| `config/litellm.yaml` | LiteLLM router: house digiquant OpenRouter slugs, OpenAI, Ollama Cloud, local Ollama. Add new entries here. |
| `config/litellm.omniroute.yaml` | Optional OmniRoute overlay — **not** loaded by default (#3413). |
| `config/litellm.cheaperinference.yaml` | Hosted Cheaper Inference overlay — merged over `litellm.yaml` when `CHEAPERINFERENCE_API_KEY` is set (merge via `scripts/merge_litellm_cheaperinference.py` / stack boot), otherwise not loaded. |
| `config/model_modes.yaml` | Mode → default model and full lists for test / medium / best. Update when adding models. |

## Caching (two layers)

1. **LiteLLM proxy** — `config/litellm.yaml` sets **`litellm_settings.cache`** (default: **local** TTL cache). Optional **`litellm-cache`** Docker profile + **`REDIS_URL`** and **`cache_params.type: redis`** for Redis-backed cache across restarts/replicas. See the repo root `README.md` and `Makefile` for Docker Compose usage. **BYOK requests must not share this cache:** digillm sends `extra_body.cache = {no-cache: true, no-store: true}` on the proxy path (#3605).
2. **digigraph in-process** — Non-tool, non-streaming, non-BYOK `chat_completion` calls may hit **`DIGI_LLM_CACHE_*`** in digillm. This is **additional** to proxy caching, not a substitute. BYOK skips this layer too.

## Router fallbacks

`config/litellm.yaml` is strict routing: no `litellm_settings.fallbacks` and no
`default_fallbacks` — provider errors surface to the caller (house policy #3078:
fail fast, no fallback chains). The opt-in dev config `config/litellm.dev.yaml`
defines local-Ollama fallbacks (`ollama/deepseek-r1:14b`) for Docker Compose use.
Tuning **`num_retries`** / **`request_timeout`** lives in the same settings block.
`ollama/qwen3:8b` is banned house-wide and refused by digillm (`_BANNED_MODELS`); it
must not appear in any routing, fallback, or default.

## Modes (DIGI_LLM_MODE)

Set in `.env`:

- **`test`** (default) – Smallest/fastest models for minimal token usage (Ollama free tier).
- **`medium`** – Balanced quality/speed.
- **`best`** – Largest/best for hard tasks.

digigraph reads `DIGI_LLM_MODE` and picks the default model from `config/model_modes.yaml`. If the file is missing or the mode is unset, mode selection uses `test`, then env `OLLAMA_MODEL`, then a built-in default — that is **mode defaults only**, not a provider fallback chain. Provider errors still surface (see Router fallbacks / digillm ARCHITECTURE fail-fast).

## How agents should update the model list

1. **New model on Ollama Cloud (or another provider)**  
   - Add an entry to `config/litellm.yaml` under `model_list` (use the same pattern as existing `ollama-cloud/...` or `openai/...`).  
   - Add the same `model_name` to the appropriate list in `config/model_modes.yaml` under `test`, `medium`, or `best`.  
   - If it should be the new default for a mode, set it in `defaults` in `model_modes.yaml`.

2. **New local Ollama model**  
   - Add to `litellm.yaml` with `api_base: http://ollama:11434` (or `host.docker.internal:11434` if using host Ollama).  
   - Optionally add to `model_modes.yaml` in the right mode list.

3. **Retire or rename a model**  
   - Remove or update it in both `litellm.yaml` and `model_modes.yaml`.  
   - Ensure at least one model remains in `defaults` for each of `test`, `medium`, `best`.

4. **After editing**  
   - Restart the stack (`docker compose up -d`) so LiteLLM and digigraph reload config.  
   - No code change is required for new models; only config and (if needed) this doc.

## Grounding models (web search synthesis fallback)

`config/digiquant_models.yaml` pins cheap-only `web_search_models` per tier
(primary `google/gemini-3.1-flash-lite`, alt `deepseek/deepseek-v4-flash`).
digigraph `get_grounding_model()` selects the synthesis model. These pins serve
only the read-only synthesis fallback: the first-party digisearch `web_search`
tool (searxng sidecar with ddgs fallback, digifetch fetch + extract enrichment)
runs first in both the digigraph `web_search` handler and the digiquant research
grounding pre-pass, so synthesis traffic — and its cost — drops as tool coverage
lands. No sonar / `:online` pins: those are not on the house catalog and fail
closed. Monitor the fallback rate alongside per-engine 403/CAPTCHA rates to see
the cost win.

## Future: router (Claw-style)

Goal: route by task (e.g. simple extraction → test, coding → medium, deep reasoning → best) to reduce token usage. The lists in `model_modes.yaml` under `test` / `medium` / `best` are intended for that router; the current implementation uses only the default model per mode.
