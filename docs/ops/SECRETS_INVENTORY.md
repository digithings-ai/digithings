# Secrets inventory — digithings

Names and locations only. **This file never contains secret values.** Cloudflare Worker secrets are stored as `secret_text`, which is write-only: `wrangler secret list` returns each name and its type but never the value, so no readback path exists even for the operator. Local `.env` files and committed example templates are referenced by path and line; any literal found committed is masked `***` and labelled `plaintext-literal`. Every claim below carries a `file:line` or a named command.

Rebuilt from four read-only sweeps (cloudflare / python / plumbing / docs) plus a live `wrangler secret list` against the three Workers, at `origin/develop` commit `35d91f641`. Two sweep claims were rechecked and corrected here: `.env.example:240` and `.env.example:278` are `replace-with-…` placeholders (not live values), and four workflows do declare `environment: production` (the sweep's "no workflow uses `environment:`" was wrong).

## How to read this table

- **Name** — the environment-variable name read by code. Alias families (`CLOUDFLARE_API_TOKEN` / `VECTORIZE_API_TOKEN` / `D1_API_TOKEN`) are merged into one row, separated by `·`.
- **Consumer (file:line)** — where the value is read at runtime.
- **Defined in (file:line)** — where the name is declared or stored (Worker-secret checklist in `wrangler.toml`, GitHub secret reference, `.env` template, compose).
- **Readback?** — whether an operator can read the stored value back. `no — write-only` for a Worker `secret_text`; `yes` for plain `[vars]`, `.env` files, and GitHub variables.
- **Rotation blast radius** — what breaks if the value changes without updating every copy.
- **Duplicate copies** — other surfaces holding the same logical credential. Equality is **inferred from config, never verified against live state**.
- **Notes** — coupling, dead/inert status, or `plaintext-literal`.

## Storage surfaces

**Cloudflare Worker secret (`secret_text`).** Set with `wrangler secret put` or the Workers Secrets HTTP API (`{"type":"secret_text"}` — [`.github/workflows/sync-cheaperinference-cf-secrets.yml`](../../.github/workflows/sync-cheaperinference-cf-secrets.yml)). Write-only. Live sets at this audit's commit, names only:

- `digithings-digichat` (10): AUTH_SECRET, CHEAPERINFERENCE_API_KEY, DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY, DIGICHAT_DASHBOARD_SUPABASE_URL, DIGICHAT_EMBED_TENANTS, DIGICHAT_PLAN_PROOF_SECRET, DIGIGRAPH_INTERNAL_URL, DIGIKEY_BFF_TOKEN, DIGIKEY_URL, OPENROUTER_API_KEY
- `digithings-stack` (16): CHEAPERINFERENCE_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, D1_DATABASE_MAP, DIGIKEY_ADMIN_TOKEN, DIGIKEY_BFF_TOKEN, DIGIKEY_DATABASE_URL, DIGIKEY_PRIVATE_KEY_PEM, GROQ_API_KEY, LITELLM_MASTER_KEY, LITELLM_PROXY_API_KEY, MCP_EDGE_KEY, OPENROUTER_API_KEY, VECTORIZE_ACCOUNT_ID, VECTORIZE_API_TOKEN, ZAMMAD_API_TOKEN
- `digithings-cron` (1): GH_DISPATCH_TOKEN

**Container env (Worker `envVars` whitelist).** A Container only receives what the Worker's `envVars` object forwards ([`cloudflare/digichat-cloudflare/src/index.ts:32`](../../cloudflare/digichat-cloudflare/src/index.ts), [`cloudflare/digithings-stack-cloudflare/src/index.ts:60`](../../cloudflare/digithings-stack-cloudflare/src/index.ts)). A secret that is `put` on the Worker but missing from `envVars` never reaches the process — silently. Known drops: `DIGICHAT_DATABASE_URL`, `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY` on digichat; `DIGI_CONFIG_PATH`, `DIGI_PROJECT_CONFIG`, `DIGI_WORKFLOW_PROFILE`, `DIGI_ALLOWED_TOOLS` on the stack.

**GitHub repo secret / var.** Repo-scoped by default. Only 4 of 72 workflows declare `environment: production` (`deploy-digithings-stack-cloudflare.yml:79`, `db-migrate.yml:105`, `sync-architecture-vault.yml:40`, `docs-onboard-digithings.yml:144`); every other `secrets.*` / `vars.*` read has no deployment gate. The repo-level sets were read back on 2026-09-18: **14 secrets** — `CHEAPERINFERENCE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CORE_POSTGRES_URI`, `CORE_SUPABASE_SERVICE_KEY`, `CORE_SUPABASE_URL`, `DIGIQUANT_DIGIKEY_API_KEY`, `DIGITHINGS_PROJECT_TOKEN`, `FRED_API_KEY`, `GH_DISPATCH_TOKEN`, `R2_ACCESS_KEY_ID`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_SECRET_ACCESS_KEY` — and **11 variables** (`CHEAPERINFERENCE_API_BASE`, `DIGIKEY_URL`, `DIGI_*_PROJECT_NUMBER`). `make secrets-audit` reproduces both directions (reads with no repo secret, and repo secrets nothing reads) and, with `admin:org` on the token since 2026-09-18, classifies every read by level: 11 repo variables, **13 org secrets** (`CEREBRAS_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CURSOR_API_KEY`, `DEEPSEEK_API_KEY`, `FRED_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `LANGSMITH_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`; all `all` visibility, so every repo inherits them) and the `production` environment's 3 names. `FRED_API_KEY` is the one name defined at **both** repo and org level — the tool's `repo-over-org` line — and the repo copy silently wins, so rotating the org copy alone changes nothing here. `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are the mirror case, `env-over-repo`: the `production` environment holds its own copies, and the 4 environment-declaring workflows read those, not the repo ones — both copies are live, so a rotation has to touch both. The 68 legacy `||`-alias fallbacks this table used to imply (the real name followed by `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VECTORIZE_API_TOKEN`, `D1_API_TOKEN`, `VECTORIZE_ACCOUNT_ID` or `D1_ACCOUNT_ID` in 10 workflows) were removed on 2026-09-18: `CORE_*` was always set, so no fallback ever fired (#4338).

Six repo secrets that no `.github` YAML read were deleted on 2026-09-17/18: `COPILOT_GITHUB_TOKEN` (its requesting job was removed in #1894) and `DIGI_CHECKPOINTER_POSTGRES_URI` (alias collapsed into `CORE_POSTGRES_URI` by #4317), plus four whose live copies are Cloudflare Worker / runtime env values rather than CI inputs — `DIGICHAT_PLAN_PROOF_SECRET`, `DIGICHAT_DASHBOARD_SUPABASE_URL`, `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY`, `EXA_API_KEY`. Nothing in CI read them, and GitHub secrets are write-only, so no retrievable value was lost.

**Local `.env` / `.dev.vars`.** Gitignored, dev only. Root `.env` (`.gitignore:31`), `cloudflare/digichat/.env.local`, `cloudflare/digithings-web/.dev.vars` (nested `.gitignore`), `.local/secrets/digithings-byok.env` (`.gitignore:34`), `projects/*/.env`.

**Plaintext literal committed in config.** A real value committed to the repo. Two exist: the FRED / CoinGecko / Alpha Vantage keys, in a gitleaks-allowlisted path ([`.gitleaks.toml:14`](../../.gitleaks.toml)); and the `local-dev-unused-first-party` embed token, which the allowlist does **not** cover — the default ruleset simply does not detect it.

## Inventory

### (a) identity, auth & signing

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `AUTH_SECRET` · `NEXTAUTH_SECRET` | `cloudflare/digichat-cloudflare/src/index.ts:47` | `cloudflare/digichat-cloudflare/wrangler.toml:50`; `docker-compose.yml:550` | no — write-only | every Auth.js session/JWT invalid; all logins | digichat Worker, compose profiles, root `.env` | `AUTH_URL` must change in lockstep |
| `DIGIKEY_PRIVATE_KEY_PEM` | `cloudflare/digithings-stack-cloudflare/src/index.ts:67`; `digikey/src/digikey/crypto_keys.py:61` | `cloudflare/digithings-stack-cloudflare/wrangler.toml:137` | no — write-only | every minted JWT + JWKS; org-wide 401 | password manager; **not** a repo-level or `production`-env secret at the 2026-09-18 read-back | RS256, static `kid=digikey-1`, no overlap |
| `DIGIKEY_ADMIN_TOKEN` | `cloudflare/digithings-stack-cloudflare/src/index.ts:68`; `digikey/src/digikey/server.py:60` | `cloudflare/digithings-stack-cloudflare/wrangler.toml:138`; `docker-compose.yml:37` | no — write-only | key-issue / revoke admin ops (503 when unset) | stack Worker; compose | static bearer, `compare_digest` |
| `DIGIKEY_BFF_TOKEN` | `cloudflare/digichat-cloudflare/src/index.ts:51`; `cloudflare/digithings-stack-cloudflare/src/index.ts:66`; `digikey/src/digikey/settings.py:20` | both `wrangler.toml:54` / `:136` | no — write-only | digichat BFF session exchange; chat auth | 2 Workers + compose + profiles | **must match across both Workers** |
| `DIGICHAT_PLAN_PROOF_SECRET` | `cloudflare/digichat-cloudflare/src/index.ts:52` | `cloudflare/digichat-cloudflare/wrangler.toml:55` | no — write-only | Desk+ plan proofs (`X-Embed-Plan-Proof`) | digichat Worker only | must match digiquant verifier |
| `DIGICHAT_EMBED_TENANTS` | `cloudflare/digichat-cloudflare/src/index.ts:48` | `cloudflare/digichat-cloudflare/wrangler.toml:51` | no — write-only | all tenant routing + per-tenant `token` | digichat Worker; release profiles | carries literal `MCP_EDGE_KEY` copy; profile value `plaintext-literal` |
| `MCP_EDGE_KEY` · `MCP_EDGE_KEYS` | `cloudflare/digithings-stack-cloudflare/src/index.ts:343` | `cloudflare/digithings-stack-cloudflare/wrangler.toml:35` (comment) | no — write-only | `/_stack/mcp/*` returns 401 | literal inside `DIGICHAT_EMBED_TENANTS` | rotate both places |
| `CRON_KICK_SECRET` | `cloudflare/digithings-cron/src/index.ts:86` | `cloudflare/digithings-cron/wrangler.toml:19` | no — write-only | `POST /kick` returns 404 | cron Worker only | optional, fail-closed |
| `GH_DISPATCH_TOKEN` | `cloudflare/digithings-cron/src/dispatch.ts:92` | `cloudflare/digithings-cron/wrangler.toml:18` | no — write-only | all cron→GitHub dispatch | GH repo secret (source) | fine-grained PAT |
| `DIGITHINGS_PROJECT_TOKEN` | 10 workflow files, 25 `secrets.*` refs (`agent-backlog-snapshot.yml:28` … `project-status.yml:112`) | GH repo secret | n/a (GH secret) | GitHub Projects v2 / GraphQL automation | widest CI token | see R13 |
| `DIGIQUANT_DIGIKEY_API_KEY` · `DIGICLAW_DIGIKEY_API_KEY` · `DIGIKEY_API_KEY` | `digibase/src/digibase/service_auth.py:107`; `digiclaw/src/digiclaw/digikey_auth.py:13` | GH repo secret; `.env` | n/a | service-to-service JWT exchange fails | GH + local `.env` | `dgk_*` key, scopes per service |
| `AUTH_OIDC_CLIENT_SECRET` | Auth.js OIDC flow | `cloudflare/digichat/.env.example:24` | yes (`.env`) | OIDC login breaks | IdP + digichat env | empty default |
| `DIGISEARCH_SEED_API_KEY` | `scripts/seed_digisearch_local.py:7` | shell export (`Makefile:159`) | n/a | local seed ingest 403 | dev only | needs `digisearch:ingest` |
| `E2E_BEARER_TOKEN` | `.github/workflows/test-e2e.yml:67` | nothing at any level (2026-09-18) — `unresolved` | n/a | mock e2e fails | CI only | test fixture |

### (b) provider / LLM API keys

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `OPENROUTER_API_KEY` | `digillm/src/digillm/client.py:242`; stack `src/index.ts:101` | org secret; stack `wrangler.toml:145` | no — write-only | house LLM routing 401 | GH + stack Worker + digichat Worker (**dead**) + local `.env` | triplicated; see R4 |
| `CHEAPERINFERENCE_API_KEY` | `digillm/src/digillm/client.py:485`; stack `src/index.ts:104` | GH repo secret; stack `wrangler.toml:146` | no — write-only | house default LiteLLM upstream 401 | GH + stack Worker + digichat Worker (**dead**) | synced by `sync-cheaperinference-cf-secrets.yml:56` |
| `GROQ_API_KEY` | stack `src/index.ts:100`; GH workflows | org secret; stack `wrangler.toml:145` | no — write-only | digigraph/LiteLLM calls 401 | GH + stack Worker + `.env` | |
| `OPENAI_API_KEY` | stack `src/index.ts:102`; `digigraph/src/digigraph/model_config.py:510` | nothing at any level (2026-09-18) — `unresolved`; documented at `wrangler.toml:145` | no — write-only | OpenAI models + embeddings 401 | GH + stack (documented) + `.env` | absent from live stack set (R9) |
| `GEMINI_API_KEY` · `ANTHROPIC_API_KEY` · `XAI_API_KEY` · `OLLAMA_API_KEY` | `digigraph/src/digigraph/model_config.py:510`; `digillm/src/digillm/client.py:233` | `project_config.py:26-27`; `.env.example:24,34` | yes (`.env`) | respective provider models 401 | local `.env` only | BYOK / operator keys |
| `LITELLM_MASTER_KEY` · `LITELLM_PROXY_API_KEY` · `DIGIKEY_LITELLM_PROXY_KEY` | `digillm/src/digillm/client.py:362`; stack `src/index.ts:109`; `digikey/src/digikey/server.py:300` | stack `src/index.ts:108-109`; `docker-compose.yml:36,127` | no — write-only | LiteLLM proxy auth; digichat proxy bearer | stack Worker + compose `DIGIKEY_*` fallback | `LITELLM_MASTER_KEY` live but undocumented |
| `MISTRAL_API_KEY` · `CEREBRAS_API_KEY` · `DEEPSEEK_API_KEY` · `NVIDIA_API_KEY` | `pipeline-provider-review.yml:92-97` | org secrets | n/a | provider-review job probes fail | CI only | not used by services |
| `LANGSMITH_API_KEY` · `OPENWIKI_LANGSMITH_API_KEY` | `digismith/src/digismith/config.py:27`; `openwiki-update.yml:73` | `LANGSMITH_API_KEY`: org secret · `OPENWIKI_LANGSMITH_API_KEY`: no level (2026-09-18) — `unresolved` | n/a | tracing export stops | GH only | distinct key for OpenWiki runs |
| `FRED_API_KEY` | stack `src/index.ts:180`; `digiquant/src/digiquant/cli/prices.py:519` | repo secret **and** org secret (repo copy wins — `repo-over-org`); `wrangler.toml:151`; committed example | no — write-only | macro/market-data reads fail | GH + stack (documented) + committed example | absent live (R9); `plaintext-literal` in example |
| `EXA_API_KEY` · `EXA_MONITOR_WEBHOOK_SECRET` | `digisearch/src/digisearch/web_exa.py:34`; monitors | `.env.example:102,112` | yes (`.env`) | web search dormant; webhook fails closed | local `.env` | |
| `AZURE_SEARCH_API_KEY` · `COHERE_API_KEY` | `digisearch/.../azure_search.py:36`; `search/reranker.py:50` | `.env.example` | yes (`.env`) | backend disabled / rerank falls back | local `.env` | optional backends |
| `ZAMMAD_API_TOKEN` | stack `src/index.ts:111` | stack `wrangler.toml:150`; `docker-compose.yml:457-458` | no — write-only | read-only Zammad MCP 401 | stack Worker + `.env` | raw token or `Token token=` |
| `MAILGUN_API_KEY` · `MAILGUN_DOMAIN` · `NOTIFY_FROM` | `execution-cron-check.yml:45-47`; `digiquant/.../staging_secrets.py:24` | no level defines any of the three (2026-09-18) — `unresolved` | n/a | notification email stops | GH + `.env` | domain/from kept as secrets (R? see f) |
| `DIGISEARCH_SMTP_USER` · `DIGISEARCH_SMTP_PASS` | `digisearch/src/digisearch/monitors/delivery.py:320` | `.env.example:109` | yes (`.env`) | monitor email delivery fails | local `.env` | |
| `FRED_API_KEY` · `COINGECKO_API_KEY` · `ALPHA_VANTAGE_API_KEY` · `SEC_EDGAR_USER_AGENT` | `digiquant/.../research ingest` | `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5-12` | n/a | research ingest fails | committed example, gitleaks-allowlisted | `plaintext-literal`; owner-confirmed dead 2026-06-18 |
| `OMNIROUTE_API_KEY` · `OMNIROUTE_AUTH_PASSWORD` | `docker-compose.yml:358,384-385` | `.env.example:14-15` | yes (`.env`) | omniroute profile breaks | local `.env` | vendor default forbidden |

### (c) infrastructure tokens (Cloudflare / Supabase / DB)

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` · `VECTORIZE_API_TOKEN` · `D1_API_TOKEN` | stack `src/index.ts:89-93`; `digivault/src/digivault/server.py:171`; `scripts/d1_sync.py:442` | stack `wrangler.toml:159,190-193`; GH repo secret (`CLOUDFLARE_API_TOKEN` only — the `VECTORIZE_*` / `D1_*` aliases are not repo-level in the 2026-09-18 read-back) | no — write-only | Vectorize + D1 sync; deploy workflows | stack Worker (canonical + legacy), GH, local `.env` | **also wrangler's own auth var** — see R7 |
| `CLOUDFLARE_ACCOUNT_ID` · `VECTORIZE_ACCOUNT_ID` · `D1_ACCOUNT_ID` · `R2_ACCOUNT_ID` | stack `src/index.ts:88-93` | stack `wrangler.toml:156,190-193`; GH repo secret (`CLOUDFLARE_ACCOUNT_ID` · `R2_ACCOUNT_ID`; the Vectorize/D1 aliases are not repo-level) | no — write-only | account selection for Vectorize/D1/R2 | stack Worker (4 aliases), GH, `.env` | account id, not a credential |
| `D1_DATABASE_MAP` | stack `src/index.ts:94`; `digivault/src/digivault/server.py:235` | stack `wrangler.toml:165`; GH `production` environment secret — not repo-level | no — write-only | per-tenant D1 corpus routing | stack Worker + GH | JSON of names→ids |
| `CORE_SUPABASE_URL` · `SUPABASE_URL` | `digibase/src/digibase/connectors/supabase.py:112`; many pipelines | GH repo secret; `.env` | n/a | Supabase/PostgREST access breaks | GH + `.env` | canonical + legacy alias |
| `CORE_SUPABASE_SERVICE_KEY` · `SUPABASE_SERVICE_ROLE_KEY` · `CORE_SUPABASE_ANON_KEY` | `digibase/.../supabase.py:113`; `digisearch`, `digivault`, `digiquant` | GH repo secret; `.env` | n/a | full DB read/write | GH + `.env` (multi-service) | service key = full access |
| `DIGICHAT_DASHBOARD_SUPABASE_URL` · `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY` | `cloudflare/digichat-cloudflare/src/index.ts:53-55` | `cloudflare/digichat-cloudflare/wrangler.toml:56-57` | no — write-only | dashboard token verify | digichat Worker + dashboard `NEXT_PUBLIC_*` | anon key is publishable |
| `CORE_POSTGRES_URI` | `db-migrate.yml:114`; `digigraph/.../graph.py:179` | GH repo secret | n/a | migrations + checkpointer fail | GH only | see [core-postgres-uri secret](core-postgres-uri-secret.md) |
| `DIGIKEY_DATABASE_URL` | stack `src/index.ts:72`; `digikey/src/digikey/db.py:38` | stack `wrangler.toml:139` | no — write-only | **digikey refuses to start when unset** (#4080) | stack Worker only | carries Postgres password |
| `DIGICHAT_POSTGRES_PASSWORD` · `DIGICHAT_DATABASE_URL` | `docker-compose.yml:514`; stack `wrangler.toml:58` (inert) | `infra/digichat-release/.env.profile-a.example:21` | yes (profile env) | digichat conversations DB; Auth.js | compose + profiles | `DIGICHAT_DATABASE_URL` not forwarded (R4) |
| `DIGISEARCH_DATABASE_URL` · `DIGISEARCH_PGVECTOR_URL` | `digisearch/src/digisearch/retrieval/pgvector.py:27` | `.env.example` | yes (`.env`) | pgvector retrieval fails | local `.env` | DSN carries DB creds |
| `R2_ACCESS_KEY_ID` · `R2_SECRET_ACCESS_KEY` · `R2_BUCKET` | stack `src/index.ts:183-184,182`; `digiquant/.../checkpoint_archive.py:868` | stack `wrangler.toml:153-155`; GH repo secret | no — write-only | market-data / checkpoint archive reads/writes | stack Worker + GH + `.env` | S3-style R2 auth |
| `STRIPE_SECRET_KEY` · `STRIPE_WEBHOOK_SECRET` · `STRIPE_PRICE_*` (6) | Supabase Edge billing fns; `digiquant/.../staging_secrets.py:20-24` | `.env.example:136-143` (names only) | n/a | payments + webhooks break | Supabase secrets + `.env` | never a value in repo |
| `SUPABASE_ACCESS_TOKEN` | `digiquant` CLI / scripts | `.env` | yes (`.env`) | management-API calls fail | local `.env` | |
| `DIGIQUANT_STAGING_USER_JWT` · `_PASSWORD` · `_ANON_KEY` | `digiquant/.../envcompat.py:19-23`; `staging_secrets.py:40` | `.env` | yes (`.env`) | staging e2e probes fail | local `.env` | alias `KAIROS_STAGING_USER_JWT` |

### (d) data store & broker / vault

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `DIGIQUANT_VAULT_MASTER_KEY` · `DIGIQUANT_VAULT_KEY_ID` | `digiquant/src/digiquant/vault/envelope.py:79,80` | `.env` (no default) | yes (`.env`) | every sealed broker credential unreadable | local secret store | AES-256-GCM, base64 32 bytes; `v1` label |
| `ALPACA_OAUTH_CLIENT_ID` · `ALPACA_OAUTH_CLIENT_SECRET` | `digiquant/.../staging_secrets.py:28-29` | `.env`; `cloudflare/dashboard/.env.local.example` | yes (`.env`) | broker OAuth connect fails | Supabase EF + `.env` | broker path — human gate |
| `GLOOMBERB_SESSION_COOKIE` | `digiquant/src/digiquant/data/gloomberb/client.py:262` | `.env`; `digits` worker (hosted) | yes (`.env`) | session-gated digifetch tools off | `.env` + Worker | import-time read → restart after change |
| `DIGIKEY_BLOCKLIST_REDIS_URL` · `DIGIKEY_REQUIRE_BLOCKLIST` | `digikey/src/digikey/blocklist.py:36,41` | `.env`; container env | yes | revoked JTIs stay valid / fail-closed 503 | compose default `1` (`docker-compose.yml:35`); `.env.example:229` documents the production default `1`; code fallback `0` (`blocklist.py:41`) | see [ADR-0007](../adr/0007-digikey-revocation.md) |
| per-watch delivery secret (HMAC) | `digisearch/src/digisearch/server.py:1941`; `monitors/delivery.py:102` | monitor store (not a fixed env) | n/a | webhook signature verify fails | per-watch row | rotates per watch |
| `DIGIQUANT_EXECUTION_ROUTING` | `digiquant/.../envcompat.py:14` | `.env` | yes (`.env`) | live-routing kill switch | local `.env` | alias `OLYMPUS_KAIROS_ROUTING`; broker path |
| `BYOK_PROVIDER` · `BYOK_API_KEY` | `scripts/digiquant_seal_byok.py:4` | `.local/secrets/digithings-byok.env` | yes (local file) | sealed BYOK provider unusable | local secret file | gitignored `.gitignore:34` |

### (e) dev-only affordances that weaken security

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `DIGIKEY_ALLOW_EPHEMERAL_KEY` · `DIGIKEY_ALLOW_DEV_GLOBAL` | `digikey/src/digikey/crypto_keys.py:65`; `settings.py:12`; stack `src/index.ts:64-65` | stack `wrangler.toml:203-204` (`"0"`); `run_stack_local.sh:76,78` (`1`) | yes | `1` = silent RSA rotation / `*`-scope `dev_global` keys | wrangler + compose + local script | keep `0` in prod — see R2 |
| `DIGICHAT_DEV_AUTH` · `DIGICHAT_DEV_PASSWORD` · `DIGICHAT_LOCAL_AUTH_KEY` | digichat dev auth | `cloudflare/digichat/.env.example:70,72`; `.env` | yes (`.env`) | weakens/removes auth | local `.env` | dev only |
| `DIGICHAT_BOOTSTRAP_API_KEY` | digichat bootstrap | `cloudflare/digichat/.env.example:62`; `.env` | yes (`.env`) | bootstrap key-issue path | local `.env` | prefer `db:create-key` in prod |
| `DIGICHAT_LEGACY_EMBED_ENABLED` · `DIGICHAT_EMBED_ENABLED` · `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS` | `cloudflare/digichat-cloudflare/src/embed-flag.ts:1-20` | `wrangler.toml:74`; release profiles | yes | `1` = **anonymous embed relay** | wrangler + profiles | fail-closed default `0` |
| `DIGICHAT_REQUIRE_ROOT_AUTH` | `cloudflare/digichat-cloudflare/src/index.ts:39` | `wrangler.toml:73` (`"0"`) | yes | root-auth wall off | wrangler + index default | shipped `"0"` |
| `DIGI_DISABLE_RATE_LIMIT` | `digigraph/src/digigraph/rate_limit.py:249`; digisearch | `.env`/test env | yes | rate limiting off | tests/local | never prod |
| `DIGISEARCH_ALLOW_MEMORY_RETRIEVAL` | `digisearch/src/digisearch/retrieval/pgvector.py:302` | test env | yes | in-memory retrieval fallback | tests/local | never prod |
| `DIGI_TRUSTED_PROXIES` · `DIGICHAT_TRUSTED_PROXIES` | `digigraph/src/digigraph/rate_limit.py:160`; digichat `index.ts:44` | env / unset | yes | IP allowlist for rate-limit headers | env | referenced, not always defined |

### (f) non-secret config still deployed as a secret

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `DIGIGRAPH_INTERNAL_URL` · `DIGIKEY_URL` · `DIGIQUANT_INTERNAL_URL` · `DIGISMITH_INTERNAL_URL` · `DIGISEARCH_INTERNAL_URL` | digichat `src/index.ts:49-50` | digichat `wrangler.toml:52-53` | no — write-only | chat backend / JWT exchange upstream | digichat Worker; GH var `DIGIKEY_URL` | URLs stored as secrets |
| `DIGISEARCH_URL` | `docs-reindex-guide.yml:86`; `pipeline-digiquant.yml:155` | nothing at any level (2026-09-18) — `unresolved` (not a repo variable either) | n/a | reindex workflow / pipeline | — | if either job needs it, a repo variable is the right store |
| `DIGIKEY_ISSUER` · `DIGIKEY_AUDIENCE` · `DIGIKEY_KEY_ID` · `DIGIKEY_JWKS_URL` | stack `src/index.ts:61-62,73`; `jwt_verify.py:60` | stack `wrangler.toml:202-203`; code defaults `src/index.ts:62,73`, `digikey/src/digikey/crypto_keys.py:62` | yes | `iss`/`aud` mismatch fails all verification | wrangler + entrypoint defaults | plain vars, not secrets |
| `DIGICHAT_EMBED_HOSTS` | `cloudflare/digichat-cloudflare/src/index.ts:41` | `cloudflare/digichat-cloudflare/wrangler.toml:74` | yes | embed CSP `frame-ancestors` | wrangler + index default | not a secret |
| `CHEAPERINFERENCE_API_BASE` · `OPENAI_API_BASE` · `DIGI_HOUSE_UPSTREAM` | stack `src/index.ts:78,106-107` | `wrangler.toml:147,212` | yes | LiteLLM upstream selection | GH var + secret + defaults | base URL |
| `STUB_TSV_ENABLED` · `DIGI_MAINTENANCE_PROJECT_NUMBER` · `ENABLE_CLAUDE_PR_REVIEW` | GH workflows | GH repo **vars** | n/a | CI toggles | GH only | vars, correctly |
| `DIGI_CONFIG_PATH` · `DIGI_PROJECT_CONFIG` · `DIGI_WORKFLOW_PROFILE` · `DIGI_ALLOWED_TOOLS` | stack `wrangler.toml:213-221` | wrangler `[vars]` | yes | nothing — container default wins | inert | documented dead config (#2304/#2306) |
| `DIGIQUANT_MARKET_DATA_BACKEND` · `CHROMA_PATH` · `DIGIVAULT_ROOT` · `DIGISEARCH_INDEX` · `DIGI_TENANT_CORPUS_MAP` · `DIGI_LLM_MODE` | stack `src/index.ts:79-96,179` | stack `wrangler.toml:211,222-233` | yes | RAG index / market-data seam / LLM mode | wrangler + code defaults | plain vars |

## Risk register

**R1 — `DIGIKEY_PRIVATE_KEY_PEM` has no rollover path.** Severity: critical. Evidence: `digikey/src/digikey/crypto_keys.py:61`, `digikey/src/digikey/jwt_issue.py:88`, [`digikey/ARCHITECTURE.md`](../../digikey/ARCHITECTURE.md):305-335. Why: static `kid=digikey-1`, no JWKS overlap or grace period; rotating invalidates every outstanding JWT until each consumer refetches (300 s cache, `DIGIKEY_JWKS_CACHE_SEC`). Action: run `docs/ops/SECRETS_ROTATION.md`; implement multi-key JWKS overlap per `docs/adr/0029-secrets-management.md`.

**R2 — dev bypass flags (`DIGIKEY_ALLOW_DEV_GLOBAL`, `DIGIKEY_ALLOW_EPHEMERAL_KEY`) silently weaken auth if set in prod.** Severity: critical. Evidence: `digikey/src/digikey/settings.py:12`, `crypto_keys.py:65`, stack `wrangler.toml:203-204` (`"0"`), `scripts/run_stack_local.sh:76,78` (`1`). Why: `dev_global` mints `*`-scope keys; ephemeral key rotates JWKS on restart, breaking cross-instance verification. Action: assert `0` at deploy; keep the fail-closed default.

**R3 — real API keys are committed in a gitleaks-allowlisted example.** Severity: high. Evidence: `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5,7,9` (non-placeholder literals, masked `***`), `.gitleaks.toml:52-57` (owner-confirmed dead 2026-06-18), `infra/digichat-release/compose.profile-a-bundle.override.yml:11` (`local-dev-unused-first-party`). Why: the research-example allowlist exempts that one path from scanning, so a live value there would never be detected; the compose-override token is not allowlisted at all — the default ruleset does not detect it. Liveness of both is unverifiable here. Action: confirm-dead or rotate; reduce the allowlist to placeholder-shaped values only.

**R4 — the container `envVars` whitelist drops secrets silently.** Severity: high. Evidence: digichat `src/index.ts:32-56` vs `wrangler.toml:50-58` — `DIGICHAT_DATABASE_URL`, `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY` are `put` on the Worker but never forwarded. Why: an operator rotates a key, the secret list shows it, and the process never sees it. Action: add a test asserting every Worker secret name appears in `envVars` or is documented inert.

**R5 — a running Container serves its start-time env until recycled.** Severity: high. Evidence: `cloudflare/digithings-stack-cloudflare/README.md:18-23`, `cloudflare/digichat-cloudflare/src/paths.ts:22`, commit #4290. Why: `wrangler deploy` does not roll the container, so a rotated secret looks rotated while the old value stays live. Action: make the recycle step (bump `SHARED_DIGICHAT_CONTAINER_ID` / rebuild marker) mandatory in the rotation runbook.

**R6 — digikey's static bearer tokens have no rotation procedure and are duplicated.** Severity: high. Evidence: `digikey/src/digikey/server.py:60,117-121` (`DIGIKEY_ADMIN_TOKEN`), `settings.py:20` (`DIGIKEY_BFF_TOKEN`), `cloudflare/digichat-cloudflare/wrangler.toml:54` + `cloudflare/digithings-stack-cloudflare/wrangler.toml:136`. Why: compromise of the admin token grants key-issue/revoke; the BFF token must match across two Workers, so a one-sided rotation breaks chat auth. Action: document a two-surface rotation with a dual-accept window.

**R7 — the Cloudflare token alias family is still live and ambiguous.** Severity: medium. Evidence: stack `wrangler.toml:159,190-193`, `src/index.ts:89-93`, [vectorize cutover](vectorize-cutover.md):132-207. Why: `CLOUDFLARE_API_TOKEN` doubles as wrangler's own auth var (auth error 10000 when exported), and the legacy `VECTORIZE_*` / `D1_*` names are forwarded as fallbacks — a leaked legacy token stays valid with no obvious owner. Action: delete legacy secrets after verification.

**R8 — `AUTH_SECRET` spans four or more surfaces.** Severity: high. Evidence: `cloudflare/digichat-cloudflare/src/index.ts:47`, `wrangler.toml:50`, `docker-compose.yml:550`, `infra/digichat-release/.env.profile-a.example:17`. Why: a partial rotation invalidates sessions only on some instances, producing intermittent logouts. Action: enumerate every surface in the runbook and rotate atomically.

**R9 — the `wrangler.toml` secret checklist and the live Worker set diverge.** Severity: medium. Evidence: live `digithings-stack` list (16 names, this audit) vs `cloudflare/digithings-stack-cloudflare/wrangler.toml:145-155` which documents `R2_*`, `FRED_API_KEY`, `OPENAI_API_KEY`; `LITELLM_MASTER_KEY` is live but undocumented (`src/index.ts:109`). Why: operators rotate a documented name that is not deployed, or miss a live one (`LITELLM_MASTER_KEY`). Action: generate the checklist from `wrangler secret list`; reconcile the dead/missing entries.

**R10 — `MCP_EDGE_KEY` rotation is coupled to a literal in `DIGICHAT_EMBED_TENANTS`.** Severity: medium. Evidence: `cloudflare/digichat-cloudflare/README.md:115-117`, `cloudflare/digichat/config/examples/occ-embed.yaml:56-58`, stack `src/index.ts:343`. Why: the stack Worker secret is not forwarded to the container, so the tenant map carries the value literally; rotating only the Worker secret 401s the MCP edge. Action: rotate both in one change and verify the edge route.

**R11 — `DIGIKEY_DATABASE_URL` password rotation is undocumented.** Severity: medium. Evidence: stack `wrangler.toml:139`, `cloudflare/digithings-stack-cloudflare/README.md:69-71`, [digikey service key](digiquant-digikey-service-key.md):77-103. Why: the URL carries the Postgres password; there is no fallback (digikey refuses to start if unset, #4080), so any rotation mistake is an auth outage, and keys minted into the old store are lost on a DSN switch. Action: add a re-issue-and-verify runbook.

**R12 — `DIGIQUANT_VAULT_MASTER_KEY` is a single key with no rewrap path.** Severity: high. Evidence: `digiquant/src/digiquant/vault/envelope.py:79,80,141,151-175`. Why: AES-256-GCM with no default; rotating it makes every sealed broker credential unreadable, and `DIGIQUANT_VAULT_KEY_ID` has one label (`v1`). Action: KMS/rewrap runbook; seal a second key id before retiring the first.

**R13 — GitHub secret reads are repo-scoped with almost no environment gate.** Severity: high. Evidence: 4 of 72 workflows declare `environment: production` (`deploy-digithings-stack-cloudflare.yml:79`, `db-migrate.yml:105`, `sync-architecture-vault.yml:40`, `docs-onboard-digithings.yml:144`); `DIGITHINGS_PROJECT_TOKEN` is read by 10 workflow files, 25 `secrets.*` refs (`agent-backlog-snapshot.yml:28` … `project-status.yml:112`). Why: any workflow on any branch can read production credentials, and the project token is the widest-blast-radius CI credential. Action: move production reads behind GitHub Environments; scope the project token to fine-grained permissions.

## Gaps and unknowns

- **Pages env not enumerable.** `digithings-web` Pages project env vars are not listed by `wrangler secret list`; `cloudflare/digithings-web/wrangler.toml:24` documents a dead `OPENROUTER_API_KEY` (the `/chat` function returns 410), but the live Pages env is unknown.
- **Container app env not enumerable.** The digichat Container's runtime env is only visible as the Worker `envVars` whitelist in source; nothing confirms the actual container process env at runtime.
- **Every level is enumerable now** (repo secret/variable, org secret, `production` environment) — see [Storage surfaces](#storage-surfaces) and `make secrets-audit`, which reports a read it cannot place at any level as `unresolved`. Six are open: `DIGISEARCH_URL`, `E2E_BEARER_TOKEN`, `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `NOTIFY_FROM`, `OPENWIKI_LANGSMITH_API_KEY` (`execution-cron-check.yml`, `test-e2e.yml`, `docs-reindex-guide.yml`, `openwiki-update.yml`). Actions substitutes an empty string for each, so the consumer is dead or silently misconfigured; deciding per name is #4338.
- **Literal liveness.** Whether the committed `mcp.secrets.env.example` keys still work, and the `local-dev-unused-first-party` token, cannot be verified without their values.
- **Alias equality.** `R2_ACCOUNT_ID == CLOUDFLARE_ACCOUNT_ID`, the two `DIGIKEY_BFF_TOKEN` copies, and the `MCP_EDGE_KEY` vs tenant-map literal are inferred from config, not diffed against live state.
- **Legacy secrets.** Whether `VECTORIZE_*` / `D1_*` are still set on `digithings-stack` — the live list shows `VECTORIZE_ACCOUNT_ID` and `VECTORIZE_API_TOKEN` (but not `D1_ACCOUNT_ID` / `D1_API_TOKEN`), so the "safe to delete" claim is not fully verifiable.
- **Private key source.** The prod origin of `DIGIKEY_PRIVATE_KEY_PEM` (platform secret store vs `.env`) is not visible in-repo.
- **Revocation strength.** Whether prod sets `DIGIKEY_BLOCKLIST_REDIS_URL` and `DIGIKEY_REQUIRE_BLOCKLIST=1` (compose default `1` at `docker-compose.yml:35`; `.env.example:229` documents the production default `1`; code fallback `0` at `digikey/src/digikey/blocklist.py:41`).
- **Secret-manager adoption.** Cloudflare Secrets Store, 1Password, Infisical, and Doppler appear only as aspirational mentions; no repo evidence of use.
- **`projects/**` and `.local/`** are gitignored and not auditable from this checkout.

## Refreshing this inventory

```bash
# 1. Live Worker secret names (names + type only; secret_text has no readback).
#    Pin wrangler; unset CLOUDFLARE_API_TOKEN or wrangler authenticates as that
#    token and fails with auth error 10000 (stack wrangler.toml:167-180).
cd cloudflare/digichat-cloudflare   && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
cd cloudflare/digithings-stack-cloudflare && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
cd cloudflare/digithings-cron       && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
#    Pages (separate command surface): npx wrangler@4.133.0 pages secret list --project-name digithings-web
# 2. Declared Worker secret names + container envVars whitelist.
rg -n "wrangler secret put|secret_text|envVars|workerVars\." cloudflare
# 3. GitHub Actions secret/var references and any environment gate.
rg -n "secrets\.[A-Z_]+|vars\.[A-Z_]+|^\s*environment:" .github/workflows
# 4. Local templates and env-file declarations.
rg -n "^[A-Z][A-Z0-9_]+=" .env.example cloudflare/digichat/.env.example \
  infra/digichat-release/.env.profile-*.example docker-compose.yml
# 5. Python settings / os.environ reads.
rg -n "os\.getenv|os\.environ" --glob '*/src/**/*.py' digibase digikey digigraph digillm digiquant digisearch digismith digivault digiclaw
```

`.worktrees/` is gitignored (`.gitignore:5` — `/.worktrees/`), so a search launched from the main checkout silently skips a task worktree. Pass the worktree root as an explicit path argument, or add `--no-ignore`, when refreshing from inside one.
