# Profile A config mount

Mounted read-only into LiteLLM and digigraph as `/app/config`.

- `litellm.yaml` — proxy models / timeouts. Edit locally; do not commit API keys.
- `model_modes.yaml` — digigraph `DIGI_LLM_MODE` defaults (`test` / `medium` / `best`).
- `digiproject.yaml` — **chat-only** digigraph project (`research_rag`, research agent,
  `digisearch` + `digivault_search_notes` only). No digiquant / backtest.
- digigraph reads this path via `DIGI_CONFIG_PATH` and
  `DIGI_PROJECT_CONFIG=/app/config/digiproject.yaml`. Keep filenames stable.

### Chat-only service set (website digichat / OCC)

| In Profile A | Role |
|---|---|
| digikey | JWT / BFF exchange |
| digigraph | Chat brain |
| digisearch | RAG (loopback in stack image) |
| digivault | Notes (loopback in stack image) |
| LiteLLM | LLM router (loopback) |
| Redis | digikey blocklist |

**Not in Profile A:** digiquant, digismith HTTP, Ollama, heartbeat. Do not set
`DIGIQUANT_DATA_DIR` or probe digiquant from digichat
(`DIGICHAT_ENABLED_SERVICES=digigraph`).

Provider keys belong in `.env.profile-a` / `.env.profile-a-bundle`
(`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, optional `LITELLM_*`),
not in these YAML files.
