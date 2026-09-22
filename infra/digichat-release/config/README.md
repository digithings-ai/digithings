# Release config mount

Mounted read-only as `/app/config` into LiteLLM, digigraph, and digichat.

## digichat.yaml — the deployment

The digichat service reads `DIGICHAT_CONFIG_PATH` (default
`/app/config/digichat.yaml`). Start from the shipped template:

```bash
cp config/digichat.yaml.example config/digichat.yaml   # then edit it
make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml
```

That one file sets the skin, chrome, gate, backend, tools, and MCP for the
client. Fuller references live in `apps/digichat/config/examples/`
(`local-app.yaml`, `occ-embed.yaml`, `skins/<id>.yaml`, …), and
`docs/digichat/INSTALL.md` walks the install end to end.

Two traps to know:

- **The mount replaces `/app/config`.** The image's baked
  `/app/config/examples/*` is therefore *not* reachable in the release
  profiles — copy any reference config you want into this directory. If you
  only want a different catalog skin, set `DIGICHAT_CHROME_SKIN=<id>` instead.
- **Do not mix shapes.** `DIGICHAT_EMBED_TENANTS` (hosts mode) merges *with* a
  `deployment:` block in the file, which would register a stray anonymous
  install. Use `hosts:` in the file, or the env registry — not both.

## Other files

- `litellm.yaml` — proxy models / timeouts. Edit locally; do not commit API keys.
- `model_modes.yaml` — digigraph `DIGI_LLM_MODE` defaults (`test` / `medium` / `best`).
- `digiproject.yaml` — **D1 / Cloudflare stack** digigraph project (`research_rag`,
  research agent, `digisearch` + `digivault_search_notes` + `digivault_get_note`).
- `digiproject.profile-a-local.yaml` — **stock Profile A compose** (no D1): same
  chat-only profile but omits `digivault_get_note` (D1-only tool). Compose defaults
  `DIGI_PROJECT_CONFIG` to this file.
- `byok-providers.json` — BYOK provider allowlist for `llm_auth.py`. A vendored
  copy of the repo-root `config/byok-providers.json`; the two must stay in sync
  (see `tests/dg/test_llm_auth.py::TestByokCatalogVendoredCopy`, which compares
  parsed JSON — not byte-for-byte — and fails CI if the *content* drifts).
- digigraph reads this path via `DIGI_CONFIG_PATH` and `DIGI_PROJECT_CONFIG`.
  Keep filenames stable.

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
(`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, optional `LITELLM_*`,
optional house `CHEAPERINFERENCE_API_KEY` / `CHEAPERINFERENCE_API_BASE`),
not in these YAML files.
