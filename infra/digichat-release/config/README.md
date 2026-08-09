# Profile A config mount

Mounted read-only into LiteLLM and digigraph as `/app/config`.

- `litellm.yaml` — proxy models / timeouts. Edit locally; do not commit API keys.
- `model_modes.yaml` — digigraph `DIGI_LLM_MODE` defaults (`test` / `medium` / `best`).
- digigraph reads this path via `DIGI_CONFIG_PATH`. Keep filenames stable.

Provider keys belong in `.env.profile-a` (`OPENROUTER_API_KEY`, `GROQ_API_KEY`,
`OPENAI_API_KEY`, optional `LITELLM_*`), not in these YAML files.
