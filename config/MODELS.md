# Model list and mode selection (for agents)

**Purpose:** Central place for LLM model config. Agents should update the model list when new Ollama Cloud (or other) models appear so model selection stays self-updating.

## Files

| File | Role |
|------|------|
| `config/litellm.yaml` | LiteLLM router: all models (OpenAI, Ollama Cloud, local Ollama). Add new entries here. |
| `config/model_modes.yaml` | Mode → default model and full lists for test / medium / best. Update when adding models. |

## Modes (DIGI_LLM_MODE)

Set in `.env`:

- **`test`** (default) – Smallest/fastest models for minimal token usage (Ollama free tier).
- **`medium`** – Balanced quality/speed.
- **`best`** – Largest/best for hard tasks.

DigiGraph reads `DIGI_LLM_MODE` and picks the default model from `config/model_modes.yaml`. If the file is missing or the mode is unset, it falls back to `test` and then to the env `OLLAMA_MODEL` or a built-in default.

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
   - Restart the stack (`docker compose up -d`) so LiteLLM and DigiGraph reload config.  
   - No code change is required for new models; only config and (if needed) this doc.

## Future: router (Claw-style)

Goal: route by task (e.g. simple extraction → test, coding → medium, deep reasoning → best) to reduce token usage. The lists in `model_modes.yaml` under `test` / `medium` / `best` are intended for that router; the current implementation uses only the default model per mode.
