# OmniRoute (optional, self-hosted)

**Cost:** operator-run. OmniRoute is a self-hosted OpenAI-compatible gateway. It is **off by default** in digithings — same pattern as optional local Ollama, not an always-on compose service.

**Best for:** operators who already self-host OmniRoute and want LiteLLM to treat it as one more upstream. It does **not** replace OpenRouter as the house default, and this change does **not** cut DigiQuant pins over to OmniRoute.

**Follow-up (not this work):** compare house OpenRouter `:free` routing vs the OmniRoute hosted catalog on the models we actually pin, then decide whether a bake-off issue is worth filing. Do not swap pins here.

## Guardrails

- Override the vendor default admin/master password. Compose refuses to start unless `OMNIROUTE_AUTH_PASSWORD` is set.
- Secrets via env only (`.env`, never committed).
- **Do not** enable OmniRoute cookie / MITM / web-session providers.
- Bind loopback only (`127.0.0.1:20128`).
- **Do not** default any hosted marketplace, and **do not** replace OpenRouter as the house upstream.

## 1. Run OmniRoute (optional compose profile)

```bash
# .env — required; do not use the vendor default password
OMNIROUTE_AUTH_PASSWORD=...   # dashboard / initial admin password
OMNIROUTE_API_KEY=...         # key you create in the OmniRoute UI for /v1
OMNIROUTE_API_BASE=http://127.0.0.1:20128/v1

docker compose --profile omniroute up -d omniroute
```

Default listen address is `http://localhost:20128/v1` (OpenAI-compat). Dashboard is on the same port.

Without Docker, follow [OmniRoute's Docker guide](https://github.com/diegosouzapw/OmniRoute/blob/main/docs/guides/DOCKER_GUIDE.md) and keep the process on loopback.

## 2. LiteLLM overlay (not loaded by default)

LiteLLM has no include directive. Copy or merge `config/litellm.omniroute.yaml` into a throwaway config, or pass it as `--config` only when you opt in:

```yaml
model_list:
  - model_name: omniroute/auto
    litellm_params:
      model: openai/auto
      api_base: os.environ/OMNIROUTE_API_BASE
      api_key: os.environ/OMNIROUTE_API_KEY
```

House DigiQuant pins stay on the OpenRouter slugs in `config/litellm.yaml`. Point a *caller* at `omniroute/auto` only if you are experimenting — do not change `config/olympus_models.yaml` for this.

When LiteLLM runs in Docker and OmniRoute is on the host, use `http://host.docker.internal:20128/v1` as `OMNIROUTE_API_BASE`.

## 3. Verify

```bash
curl -sS http://127.0.0.1:20128/v1/models \
  -H "Authorization: Bearer $OMNIROUTE_API_KEY"
```

## Out of scope

- Cookie / MITM / TPROXY / web-session OmniRoute providers
- Replacing OpenRouter as the default house upstream
- Cutting DigiQuant phase or grounding pins over to OmniRoute
- Cost bake-off vs OpenRouter `:free` (follow-up on the models we pin)
