# DigiKey – Security & Identity Foundation

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
Central control plane for **opaque API keys**, **scoped capabilities**, and **short-lived JWTs** for the Digi stack.

## Implemented (v0.1)

- **FastAPI service** (`digikey.server:app`, port **8005**): health, **JWKS** (`GET /.well-known/jwks.json`), **token exchange** (`POST /v1/oauth/token`), **admin key issue** (`POST /v1/admin/keys`).
- **Storage**: `DIGIKEY_DATABASE_URL` — Postgres or SQLite (`sqlite:////path/db.sqlite`).
- **Keys**: prefix `dgk_live_…`, bcrypt-hashed at rest; **`kind=dev_global`** requires `DIGIKEY_ALLOW_DEV_GLOBAL=1`.
- **JWT**: RS256; set **`DIGIKEY_PRIVATE_KEY_PEM`** / `DIGIKEY_KEY_ID` in production. For local Docker only, **`DIGIKEY_ALLOW_EPHEMERAL_KEY=1`** permits a generated key (JWKS changes on restart).
- **Grants**: `grant_type=api_key` | `bff_session` (BFF requires `Authorization: Bearer DIGIKEY_BFF_TOKEN` on the token request).
- **Scopes** (examples): `digigraph:workflow`, `digigraph:chat`, `digigraph:mcp`, `digiquant:backtest`, `digiquant:optimize`, `digisearch:query`, `digisearch:ingest`; `*` matches all.

## LiteLLM proxy key (token funnel)

When **`DIGIKEY_LITELLM_PROXY_KEY`** is set on the DigiKey service, **`POST /v1/oauth/token`** responses include **`litellm_proxy_api_key`** with the same value. DigiChat forwards it as **`X-LiteLLM-Proxy-Key`** to DigiGraph so each session uses one DigiKey exchange for both **service JWT** and **LiteLLM Bearer** (typically equal to **`LITELLM_MASTER_KEY`**). Upstream provider keys (OpenAI, Anthropic, Vertex, Ollama Cloud) remain on the **LiteLLM** container.

## Consumers

| Variable | Purpose |
|----------|---------|
| `DIGIKEY_JWKS_URL` | Fetch signing keys (e.g. `http://digikey:8005/.well-known/jwks.json`) |
| `DIGIKEY_PUBLIC_KEY_PEM` | Alternative to JWKS (PEM) |
| `DIGIKEY_ISSUER` | Must match claim `iss` on tokens |
| `DIGIKEY_AUDIENCE` | Default `digi-ecosystem` |

**DigiGraph**, **DigiQuant**, and **DigiSearch** use shared middleware (`digikey.integrations.service_middleware`): every protected route requires **`DIGIKEY_JWKS_URL` or `DIGIKEY_PUBLIC_KEY_PEM`** and a valid **`Authorization: Bearer <JWT>`** with sufficient scopes. If verification is not configured, those routes return **503** `auth_not_configured` (no anonymous access).

**DigiChat**: `DIGIKEY_URL`, `DIGIKEY_BFF_TOKEN` — exchanges `dgk_live_` machine keys or OIDC sessions for upstream JWTs to DigiGraph. Optionally set **`DIGIGRAPH_UPSTREAM_API_KEY`** for a static Bearer (emergency/bootstrap only); there is no silent placeholder.

## Design principles (unchanged)

- **Zero trust by default** between components when DigiKey env is set.
- **Secrets-as-code** for policies; **no plaintext keys in git**.
- **Auditable access**: workflow audit events include optional `key_prefix`, `tenant`, `project_id`, `jti` (see root `SECURITY.md`).

## CLI

```bash
export DIGIKEY_DATABASE_URL=sqlite:///./digikey.db
export DIGIKEY_ALLOW_DEV_GLOBAL=1
python -m digikey.cli issue-key --tenant default --label dev --scopes '*' --kind dev_global
```

## Docker

Service **`digikey`** in root `docker-compose.yml`. Example `.env`:

```bash
DIGIKEY_JWKS_URL=http://digikey:8005/.well-known/jwks.json
DIGIKEY_ISSUER=http://digikey:8005
DIGIKEY_ADMIN_TOKEN=…        # required for POST /v1/admin/keys
DIGIKEY_BFF_TOKEN=…          # optional; DigiChat session exchange
```

## Roadmap

- Vault/KMS-backed signing keys; OPA policies; revocation / `jti` blocklist; usage aggregation from `AUDIT_SINK_URL`.
