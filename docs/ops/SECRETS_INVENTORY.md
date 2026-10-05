# Secrets inventory — digithings

Names and locations only. **This file never contains secret values.** Cloudflare Worker secrets are stored as `secret_text`, which is write-only: `wrangler secret list` returns each name and its type but never the value, so no readback path exists even for the operator. Local `.env` files and committed example templates are referenced by path and line; any literal found committed is masked `***` and labelled `plaintext-literal`. Every claim below carries a `file:line` or a named command.

Rebuilt from four read-only sweeps (cloudflare / python / plumbing / docs) plus a live `wrangler secret list` against the three Workers, at `origin/develop` commit `35d91f641`. Two sweep claims were rechecked and corrected here: `.env.example:240` and `.env.example:278` are `replace-with-…` placeholders (not live values). A later recount of `.github/workflows` (49 YAML files) found **1** job declaring `environment: production` (`deploy-digiquant-runner.yml`); the 2026-09 audit's "four workflows" list named files that are not in the tree. That gap is now closed for CI: **DIG-248 (2026-10-04)** added a third environment, `cron` (no reviewers, no wait timer, no branch policy), and declared it on **all 32 jobs that read a non-automatic `secrets.*` name**, so the only two job shapes left without a gate are `deploy-digiquant-runner.yml:deploy` (still `production`, deliberately) and jobs that read nothing but the automatic `GITHUB_TOKEN`. See [R13](#risk-register).

## How to read this table

- **Name** — the environment-variable name read by code. Alias families (`CLOUDFLARE_API_TOKEN` / `VECTORIZE_API_TOKEN` / `D1_API_TOKEN`) are merged into one row, separated by `·`.
- **Consumer (file:line)** — where the value is read at runtime.
- **Defined in (file:line)** — where the name is declared or stored (Worker-secret checklist in `wrangler.toml`, GitHub secret reference, `.env` template, compose).
- **Readback?** — whether an operator can read the stored value back. `no — write-only` for a Worker `secret_text`; `yes` for plain `[vars]`, `.env` files, and GitHub variables.
- **Rotation blast radius** — what breaks if the value changes without updating every copy.
- **Duplicate copies** — other surfaces holding the same logical credential. Equality is **inferred from config, never verified against live state**.
- **Notes** — coupling, dead/inert status, or `plaintext-literal`.

## Storage surfaces

**Cloudflare Worker secret (`secret_text`).** Set with `wrangler secret put` or the Workers Secrets HTTP API (`{"type":"secret_text"}`). The former `sync-cheaperinference-cf-secrets.yml` workflow is not in `.github/workflows` (removed in the strict-essentials cut). Write-only. Names only — the 2026-09 audit at `35d91f641` listed the sets below; the stack line is **not** a live re-read (see [Folded stack worker](#folded-stack-worker--secret-maintenance-2026-09-27) for the 2026-09-27 recount of **25** names; the three documented #4700 deletes from that set are 22, not a live dashboard count):

- `digithings-digichat` (10): AUTH_SECRET, CHEAPERINFERENCE_API_KEY, DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY, DIGICHAT_DASHBOARD_SUPABASE_URL, DIGICHAT_EMBED_TENANTS, DIGICHAT_PLAN_PROOF_SECRET, DIGIGRAPH_INTERNAL_URL, DIGIKEY_BFF_TOKEN, DIGIKEY_URL, OPENROUTER_API_KEY
- `digithings-stack` (16 at the 2026-09 audit, **superseded**): CHEAPERINFERENCE_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, D1_DATABASE_MAP, DIGIKEY_ADMIN_TOKEN, DIGIKEY_BFF_TOKEN, DIGIKEY_DATABASE_URL, DIGIKEY_PRIVATE_KEY_PEM, GROQ_API_KEY, LITELLM_MASTER_KEY, LITELLM_PROXY_API_KEY, MCP_EDGE_KEY, OPENROUTER_API_KEY, VECTORIZE_ACCOUNT_ID, VECTORIZE_API_TOKEN, ZAMMAD_API_TOKEN
- `digithings-cron` (1): GH_DISPATCH_TOKEN

**Container env (Worker `envVars` whitelist).** A Container only receives what the Worker's `envVars` object forwards. The standalone digichat whitelist is [`apps/digichat-cloudflare/src/index.ts:32-56`](../../apps/digichat-cloudflare/src/index.ts). The stack Worker runs three Container classes, each with its own `envVars`: `DigiStackContainer` ([`apps/digithings-stack-cloudflare/src/index.ts:89-146`](../../apps/digithings-stack-cloudflare/src/index.ts)), `DigiQuantMcpContainer` (`:218-227`), and `DigiChatContainer` (`:256`, `envVars` at `:277-305`). A secret that is `put` on the Worker but missing from `envVars` never reaches the process — silently. Known drops: `DIGICHAT_DATABASE_URL`, `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY` on digichat; `DIGI_CONFIG_PATH`, `DIGI_PROJECT_CONFIG`, `DIGI_WORKFLOW_PROFILE`, `DIGI_ALLOWED_TOOLS` on the stack.

**GitHub repo secret / var.** Repo-scoped by default. As of DIG-248 (2026-10-04) every job that reads a non-automatic `secrets.*` name declares an environment: **32 on `cron`** (no reviewers, no wait timer, no branch policy) and **1 on `production`** (`deploy-digiquant-runner.yml:33`). Before that, only 1 of 49 workflows had any gate. The 2026-09 audit named four files that are not in `.github/workflows` (`deploy-digithings-stack-cloudflare.yml`, `db-migrate.yml`, `sync-architecture-vault.yml`, `docs-onboard-digithings.yml`). The names themselves are still **repo- or org-scoped**; the migration of their values to `cron` scope is the open human step in [R13](#risk-register). The repo-level sets were read back on 2026-09-18: **15 secrets** — `CHEAPERINFERENCE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_EMAIL_API_TOKEN`, `CORE_POSTGRES_URI`, `CORE_SUPABASE_SERVICE_KEY`, `CORE_SUPABASE_URL`, `DIGIQUANT_DIGIKEY_API_KEY`, `DIGITHINGS_PROJECT_TOKEN`, `GH_DISPATCH_TOKEN`, `NOTIFY_FROM`, `R2_ACCESS_KEY_ID`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_SECRET_ACCESS_KEY` — and **11 variables** (`CHEAPERINFERENCE_API_BASE`, `DIGIKEY_URL`, `DIGI_*_PROJECT_NUMBER`). `CLOUDFLARE_EMAIL_API_TOKEN` — a dedicated Cloudflare API token carrying **Email Sending: Edit**, deliberately not the broad `CLOUDFLARE_API_TOKEN` — and `NOTIFY_FROM` (`DigiQuant <notifications@digiquant.io>`) were stored on 2026-09-18 (#4358); a live send was queued through the sender that day and the daily probe is green. `make secrets-audit` reproduces both directions (reads with no repo secret, and repo secrets nothing reads) and, with `admin:org` on the token since 2026-09-18, classifies every read by level: 11 repo variables, **13 org secrets** (`CEREBRAS_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CURSOR_API_KEY`, `DEEPSEEK_API_KEY`, `FRED_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `LANGSMITH_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`; all `all` visibility, so every repo inherits them) and the `production` environment's 1 name (`D1_DATABASE_MAP`). Both duplicate-definition cases the tool reported were resolved on 2026-09-18: the repo-level `FRED_API_KEY` and the `production`-environment copies of `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` were deleted, so each name now has exactly one home and `repo-over-org` / `env-over-repo` are both clean. The 68 legacy `||`-alias fallbacks this table used to imply (the real name followed by `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VECTORIZE_API_TOKEN`, `D1_API_TOKEN`, `VECTORIZE_ACCOUNT_ID` or `D1_ACCOUNT_ID` in 10 workflows) were removed on 2026-09-18: `CORE_*` was always set, so no fallback ever fired (#4338).

**Two related corrections landed with DIG-248 (2026-10-04).** `CHEAPERINFERENCE_API_BASE` is a repo **variable**, and the two workflow reads of it (`pipeline-digiquant.yml:230` and `:295`) wrote `${{ vars.X || secrets.X || 'https://api.cheaperinference.com/v1' }}`. A repo variable is never visible through the `secrets.` context, so the middle term was dead — but it was a dead **fallback**, not a live break: `vars.` is evaluated first and the variable is set. The `secrets.` term was removed rather than promoted to a secret, because the value is a non-secret base URL. `SUPABASE_SERVICE_ROLE_KEY` (repo secret, written 2026-09-25) duplicates `CORE_SUPABASE_SERVICE_KEY` (2026-06-25) — two service-role credentials for the same job, so rotating one leaves the other live with no owner. **Decision: `CORE_SUPABASE_SERVICE_KEY` is canonical**, because every `.github` read and the multi-service row above already use it; `SUPABASE_SERVICE_ROLE_KEY` is deleted rather than rotated. Both are service-role keys, so the deletion needs Chris to confirm no external consumer holds the newer value.

Six repo secrets that no `.github` YAML read were deleted on 2026-09-17/18: `COPILOT_GITHUB_TOKEN` (its requesting job was removed in #1894) and `DIGI_CHECKPOINTER_POSTGRES_URI` (alias collapsed into `CORE_POSTGRES_URI` by #4317), plus four whose live copies are Cloudflare Worker / runtime env values rather than CI inputs — `DIGICHAT_PLAN_PROOF_SECRET`, `DIGICHAT_DASHBOARD_SUPABASE_URL`, `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY`, `EXA_API_KEY`. Nothing in CI read them, and GitHub secrets are write-only, so no retrievable value was lost.

**Local `.env` / `.dev.vars`.** Gitignored, dev only. Root `.env` (`.gitignore:31`), `apps/digichat/.env.local`, `apps/digithings-web/.dev.vars` (nested `.gitignore`), `.local/secrets/digithings-byok.env` (`.gitignore:34`), `projects/*/.env`.

**Plaintext literal committed in config.** A real value committed to the repo. Two exist: the FRED / CoinGecko / Alpha Vantage keys, in a gitleaks-allowlisted path ([`.gitleaks.toml:14`](../../.gitleaks.toml)); and the `local-dev-unused-first-party` embed token, which the allowlist does **not** cover — the default ruleset simply does not detect it.

## Inventory

### (a) identity, auth & signing

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `AUTH_SECRET` · `NEXTAUTH_SECRET` | `apps/digichat-cloudflare/src/index.ts:47` | `apps/digichat-cloudflare/wrangler.toml:50`; `docker-compose.yml:550` | no — write-only | every Auth.js session/JWT invalid; all logins | digichat Worker, compose profiles, root `.env` | `AUTH_URL` must change in lockstep |
| `DIGIKEY_PRIVATE_KEY_PEM` | `apps/digithings-stack-cloudflare/src/index.ts:67`; `digikey/src/digikey/crypto_keys.py:61` | `apps/digithings-stack-cloudflare/wrangler.toml:137` | no — write-only | every minted JWT + JWKS; org-wide 401 | password manager; **not** a repo-level or `production`-env secret at the 2026-09-18 read-back | RS256, static `kid=digikey-1`, no overlap |
| `DIGIKEY_ADMIN_TOKEN` | `apps/digithings-stack-cloudflare/src/index.ts:68`; `digikey/src/digikey/server.py:60` | `apps/digithings-stack-cloudflare/wrangler.toml:138`; `docker-compose.yml:37` | no — write-only | key-issue / revoke admin ops (503 when unset) | stack Worker; compose | static bearer, `compare_digest` |
| `DIGIKEY_BFF_TOKEN` | `apps/digichat-cloudflare/src/index.ts:51`; `apps/digithings-stack-cloudflare/src/index.ts:66`; `digikey/src/digikey/settings.py:20` | both `wrangler.toml:54` / `:136` | no — write-only | digichat BFF session exchange; chat auth | 2 Workers + compose + profiles | **must match across both Workers** |
| `DIGICHAT_PLAN_PROOF_SECRET` | `apps/digichat-cloudflare/src/index.ts:52` | `apps/digichat-cloudflare/wrangler.toml:55` | no — write-only | Desk+ plan proofs (`X-Embed-Plan-Proof`) | digichat Worker only | must match digiquant verifier |
| `DIGICHAT_EMBED_TENANTS` | `apps/digichat-cloudflare/src/index.ts:48` | `apps/digichat-cloudflare/wrangler.toml:51` | no — write-only | all tenant routing + per-tenant `token` | digichat Worker; release profiles | carries literal `MCP_EDGE_KEY` copy; profile value `plaintext-literal` |
| `MCP_EDGE_KEY` · `MCP_EDGE_KEYS` | `apps/digithings-stack-cloudflare/src/index.ts:343` | `apps/digithings-stack-cloudflare/wrangler.toml:35` (comment) | no — write-only | `/_stack/mcp/*` returns 401 | literal inside `DIGICHAT_EMBED_TENANTS` | rotate both places |
| `CRON_KICK_SECRET` | `apps/digithings-cron/src/index.ts:134` (also guards `:174,197`) | `apps/digithings-cron/wrangler.toml:28` (comment) | no — write-only | `POST /kick` returns 404 | cron Worker only | optional, fail-closed |
| `GH_DISPATCH_TOKEN` | `apps/digithings-cron/src/dispatch.ts:289` (bearer `:298`) | `apps/digithings-cron/wrangler.toml:24` (comment) | no — write-only | all cron→GitHub dispatch | GH repo secret (source) | fine-grained PAT `digithings-cron-dispatch` (settings id 19179726, expires 2027-09-15). **Shared with the DIG-71 alarm — see R14.** Grants on `digithings-ai/digithings` + `digithings-ai/twelve-x`: **Actions: read and write**, **Issues: read and write** (added 2026-10-04). Editing the permission did **not** re-issue the value, so no Worker secret push was needed. No Contents grant — so the token can only be used over REST, not via `gh issue create` (GraphQL `defaultBranchRef`). Not yet in Bitwarden (DIG-95) |
| `DIGITHINGS_PROJECT_TOKEN` | 7 workflow files, 22 `secrets.*` refs (`agent-backlog-snapshot.yml:28` … `pipeline-maintenance.yml:910`) | GH repo secret | n/a (GH secret) | GitHub Projects v2 / GraphQL automation | widest CI token | see R13 |
| `DIGIQUANT_DIGIKEY_API_KEY` · `DIGICLAW_DIGIKEY_API_KEY` · `DIGIKEY_API_KEY` | `digibase/src/digibase/service_auth.py:107`; `digiclaw/src/digiclaw/digikey_auth.py:13` | GH repo secret; `.env` | n/a | service-to-service JWT exchange fails | GH + local `.env` | `dgk_*` key, scopes per service |
| `AUTH_OIDC_CLIENT_SECRET` | Auth.js OIDC flow | `apps/digichat/.env.example:24` | yes (`.env`) | OIDC login breaks | IdP + digichat env | empty default |
| `DIGISEARCH_SEED_API_KEY` | `scripts/seed_digisearch_local.py:7` | shell export (`Makefile:159`) | n/a | local seed ingest 403 | dev only | needs `digisearch:ingest` |
| `E2E_BEARER_TOKEN` | minted in `test-e2e.yml` from the compose stack (`digikey.cli issue-key` → `/v1/oauth/token`) | not stored at any level, by design (#4357) | n/a | protected-route e2e skips | CI only | test fixture; a stored JWT would expire |

### (b) provider / LLM API keys

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `OPENROUTER_API_KEY` | `digillm/src/digillm/client.py:242`; stack `src/index.ts:135` | org secret; stack `wrangler.toml:179` | no — write-only | house LLM routing 401 | GH + stack Worker + digichat Worker (**dead**) + local `.env` | triplicated; see R4 |
| `CHEAPERINFERENCE_API_KEY` | `digillm/src/digillm/client.py:485`; stack `src/index.ts:138` | GH repo secret; stack `wrangler.toml:180` | no — write-only | house default LiteLLM upstream 401 | GH + stack Worker + digichat Worker (**dead**) | put with `wrangler secret put` / `gh secret set`; no sync workflow in `.github/workflows` |
| `GROQ_API_KEY` | stack `src/index.ts:134`; GH workflows | org secret; stack `wrangler.toml:179` | no — write-only | digigraph/LiteLLM calls 401 | GH + stack Worker + `.env` | |
| `OPENAI_API_KEY` | stack `src/index.ts:136`; `digigraph/src/digigraph/model_config.py:510` | nothing at any level (2026-09-18) — `unresolved`; documented at `wrangler.toml:179` | no — write-only | OpenAI models + embeddings 401 | GH + stack (documented) + `.env` | absent from live stack set (R9) |
| `GEMINI_API_KEY` · `ANTHROPIC_API_KEY` · `XAI_API_KEY` · `OLLAMA_API_KEY` | `digigraph/src/digigraph/model_config.py:510`; `digillm/src/digillm/client.py:233` | `project_config.py:26-27`; `.env.example:24,34` | yes (`.env`) | respective provider models 401 | local `.env` only | BYOK / operator keys |
| `LITELLM_MASTER_KEY` · `LITELLM_PROXY_API_KEY` · `DIGIKEY_LITELLM_PROXY_KEY` | `digillm/src/digillm/client.py:362`; stack `src/index.ts:109`; `digikey/src/digikey/server.py:300` | stack `src/index.ts:108-109`; `docker-compose.yml:36,127` | no — write-only | LiteLLM proxy auth; digichat proxy bearer | stack Worker + compose `DIGIKEY_*` fallback | `LITELLM_MASTER_KEY` live but undocumented |
| `MISTRAL_API_KEY` · `CEREBRAS_API_KEY` · `DEEPSEEK_API_KEY` · `NVIDIA_API_KEY` | `pipeline-provider-review.yml:92-97` | org secrets | n/a | provider-review job probes fail | CI only | not used by services |
| `LANGSMITH_API_KEY` | `digitrace/src/digitrace/config.py:27`; `openwiki-update.yml` | org secret (2026-09-18) | n/a | tracing export stops | GH only | #4357 dropped the separate `OPENWIKI_LANGSMITH_API_KEY` read — the OpenWiki step reuses this key |
| `DATABASE_URL` · `NEXTAUTH_SECRET` · `NEXTAUTH_URL` · `SALT` · `ENCRYPTION_KEY` (Langfuse) | `apps/digitrace-langfuse/src/index.ts` `langfuseEnvVars` | `apps/digitrace-langfuse/wrangler.toml` secrets checklist; `docs/ops/digitrace-langfuse.md` | no — write-only | Langfuse Web/Worker refuse or auth breaks | digitrace-langfuse Worker only | Phase 1 #4930; names only — never commit URIs/keys |
| `CLICKHOUSE_URL` · `CLICKHOUSE_MIGRATION_URL` · `CLICKHOUSE_USER` · `CLICKHOUSE_PASSWORD` · `CLICKHOUSE_DB` | `apps/digitrace-langfuse/src/index.ts` | `apps/digitrace-langfuse/wrangler.toml`; runbook | no — write-only | Langfuse ingest/UI analytics fail | digitrace-langfuse Worker; external CH only | **not** a CF lite Container; ≥2 CPU / 8 GiB guidance |
| `REDIS_CONNECTION_STRING` · `REDIS_HOST` · `REDIS_PORT` · `REDIS_AUTH` | `apps/digitrace-langfuse/src/index.ts` | `apps/digitrace-langfuse/wrangler.toml`; runbook | no — write-only | Langfuse queues stall | digitrace-langfuse Worker; external Redis | prefer connection string |
| `LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT` · `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` · `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY` | `apps/digitrace-langfuse/src/index.ts` | `apps/digitrace-langfuse/wrangler.toml`; bucket `digitrace-langfuse-events` | no — write-only | event upload / OTLP persistence fails | digitrace-langfuse Worker + R2 S3 token | bucket name/prefix are plain `[vars]` |
| `FRED_API_KEY` | stack `src/index.ts:180`; `digiquant/src/digiquant/cli/prices.py:519` | org secret only (the repo copy was deleted 2026-09-18 — `repo-over-org` is clean); `wrangler.toml:151`; committed example | no — write-only | macro/market-data reads fail | GH + stack (documented) + committed example | absent live (R9); `plaintext-literal` in example |
| `EXA_API_KEY` · `EXA_MONITOR_WEBHOOK_SECRET` | `digisearch/src/digisearch/web_exa.py:34`; monitors | `.env.example:102,112` | yes (`.env`) | web search dormant; webhook fails closed | local `.env` | |
| `AZURE_SEARCH_API_KEY` · `COHERE_API_KEY` | `digisearch/.../azure_search.py:36`; `search/reranker.py:50` | `.env.example` | yes (`.env`) | backend disabled / rerank falls back | local `.env` | optional backends |
| `ZAMMAD_API_TOKEN` | stack `src/index.ts:111` | stack `wrangler.toml:150`; `docker-compose.yml:457-458` | no — write-only | read-only Zammad MCP 401 | stack Worker + `.env` | raw token or `Token token=` |
| `CLOUDFLARE_EMAIL_API_TOKEN` · `CLOUDFLARE_ACCOUNT_ID` · `NOTIFY_FROM` | `execution-cron-check.yml:45-47`; `digiquant/src/digiquant/notify/cloudflare_email.py`; `digiquant/.../staging_secrets.py` | all three are repo secrets (2026-09-18) | no — write-only | digest email stops; the daily probe fails closed (exit 2) | GH + `.env` | replaced Mailgun in #4358; the token carries **Email Sending: Edit** and is deliberately not the deploy token |
| `DIGISEARCH_SMTP_USER` · `DIGISEARCH_SMTP_PASS` | `digisearch/src/digisearch/monitors/delivery.py:320` | `.env.example:109` | yes (`.env`) | monitor email delivery fails | local `.env` | |
| `FRED_API_KEY` · `COINGECKO_API_KEY` · `ALPHA_VANTAGE_API_KEY` · `SEC_EDGAR_USER_AGENT` | `digiquant/.../research ingest` | `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5-12`; history-only `digiquant/src/digiquant/olympus/atlas/config/mcp.secrets.env.example` (absent at HEAD, byte-identical literals, verified 2026-10-04) | n/a | research ingest fails | committed example, gitleaks-allowlisted | `plaintext-literal`; owner-confirmed dead 2026-06-18 |
| `OMNIROUTE_API_KEY` · `OMNIROUTE_AUTH_PASSWORD` | `docker-compose.yml:358,384-385` | `.env.example:14-15` | yes (`.env`) | omniroute profile breaks | local `.env` | vendor default forbidden |

### (c) infrastructure tokens (Cloudflare / Supabase / DB)

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` · `VECTORIZE_API_TOKEN` · `D1_API_TOKEN` | stack `src/index.ts:89-93`; `digivault/src/digivault/server.py:171`; `scripts/d1_sync.py:442` | stack `wrangler.toml:159,190-193`; GH repo secret (`CLOUDFLARE_API_TOKEN` only — the `VECTORIZE_*` / `D1_*` aliases are not repo-level in the 2026-09-18 read-back) | no — write-only | Vectorize + D1 sync; deploy workflows | stack Worker (canonical + legacy), GH, local `.env` | **also wrangler's own auth var** — see R7 |
| `CLOUDFLARE_ACCOUNT_ID` · `VECTORIZE_ACCOUNT_ID` · `D1_ACCOUNT_ID` · `R2_ACCOUNT_ID` | stack `src/index.ts:88-93` | stack `wrangler.toml:156,190-193`; GH repo secret (`CLOUDFLARE_ACCOUNT_ID` · `R2_ACCOUNT_ID`; the Vectorize/D1 aliases are not repo-level) | no — write-only | account selection for Vectorize/D1/R2 | stack Worker (4 aliases), GH, `.env` | account id, not a credential |
| `D1_DATABASE_MAP` | stack `src/index.ts:94`; `digivault/src/digivault/server.py:235` | stack `wrangler.toml:165`; GH `production` environment secret — not repo-level | no — write-only | per-tenant D1 corpus routing | stack Worker + GH | JSON of names→ids |
| `CORE_SUPABASE_URL` · `SUPABASE_URL` | `digibase/src/digibase/connectors/supabase.py:112`; many pipelines | GH repo secret; `.env` | n/a | Supabase/PostgREST access breaks | GH + `.env` | canonical + legacy alias |
| `CORE_SUPABASE_SERVICE_KEY` · `SUPABASE_SERVICE_ROLE_KEY` · `CORE_SUPABASE_ANON_KEY` | `digibase/.../supabase.py:113`; `digisearch`, `digivault`, `digiquant` | GH repo secret; `.env` | n/a | full DB read/write | GH + `.env` (multi-service) | service key = full access |
| `DIGICHAT_DASHBOARD_SUPABASE_URL` · `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY` | `apps/digichat-cloudflare/src/index.ts:53-55` | `apps/digichat-cloudflare/wrangler.toml:56-57` | no — write-only | dashboard token verify | digichat Worker + dashboard `NEXT_PUBLIC_*` | anon key is publishable |
| `CORE_POSTGRES_URI` | `pipeline-checkpoint-archive.yml:53`; `pipeline-market-data-refresh.yml:33`; `pipeline-digiquant.yml:306`; `digigraph/.../graph.py:180` | GH repo secret | n/a | checkpointer / archive / market-data registry fail | GH only | see [core-postgres-uri secret](core-postgres-uri-secret.md); `db-migrate.yml` is not in `.github/workflows` |
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
| `ALPACA_OAUTH_CLIENT_ID` · `ALPACA_OAUTH_CLIENT_SECRET` | `digiquant/.../staging_secrets.py:28-29` | `.env`; `apps/dashboard/.env.local.example` | yes (`.env`) | broker OAuth connect fails | Supabase EF + `.env` | broker path — human gate |
| `GLOOMBERB_SESSION_COOKIE` | `digiquant/src/digiquant/data/gloomberb/client.py:1450`; `digiquant/src/digiquant/data/gloomberb/agent_tools.py:194-197` | `.env`; stack Worker (`wrangler.toml:186`); forwarded `index.ts:222` | yes (`.env`) | session-gated digifetch tools off | `.env` + stack Worker | construction-time read, not import-time (`client.py:16-17`); in-process cache keys on the current env so a changed cookie builds a new client; hosted MCP still needs a container recycle (R5) |
| `DIGIKEY_BLOCKLIST_REDIS_URL` · `DIGIKEY_REQUIRE_BLOCKLIST` | `digikey/src/digikey/blocklist.py:36,41` | `.env`; container env | yes | revoked JTIs stay valid / fail-closed 503 | code default is fail-closed; `DIGIKEY_REQUIRE_BLOCKLIST=0` is the local opt-out (`blocklist.py` `require_blocklist_enabled`). Compose default `1` (`docker-compose.yml:35`); `.env.example:226` | see [ADR-0007](../adr/0007-digikey-revocation.md) |
| per-watch delivery secret (HMAC) | `digisearch/src/digisearch/server.py:1941`; `monitors/delivery.py:102` | monitor store (not a fixed env) | n/a | webhook signature verify fails | per-watch row | rotates per watch |
| `DIGIQUANT_EXECUTION_ROUTING` | `digiquant/.../envcompat.py:14` | `.env` | yes (`.env`) | live-routing kill switch | local `.env` | alias `OLYMPUS_KAIROS_ROUTING`; broker path |
| `BYOK_PROVIDER` · `BYOK_API_KEY` | `scripts/digiquant_seal_byok.py:4` | `.local/secrets/digithings-byok.env` | yes (local file) | sealed BYOK provider unusable | local secret file | gitignored `.gitignore:34` |

### (e) dev-only affordances that weaken security

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `DIGIKEY_ALLOW_EPHEMERAL_KEY` · `DIGIKEY_ALLOW_DEV_GLOBAL` | `digikey/src/digikey/crypto_keys.py:65`; `settings.py:12`; stack `src/index.ts:64-65` | stack `wrangler.toml:203-204` (`"0"`); `run_stack_local.sh:76,78` (`1`) | yes | `1` = silent RSA rotation / `*`-scope `dev_global` keys | wrangler + compose + local script | keep `0` in prod — see R2 |
| `DIGICHAT_DEV_AUTH` · `DIGICHAT_DEV_PASSWORD` · `DIGICHAT_LOCAL_AUTH_KEY` | digichat dev auth | `apps/digichat/.env.example:70,72`; `.env` | yes (`.env`) | weakens/removes auth | local `.env` | dev only |
| `DIGICHAT_BOOTSTRAP_API_KEY` | digichat bootstrap | `apps/digichat/.env.example:62`; `.env` | yes (`.env`) | bootstrap key-issue path | local `.env` | prefer `db:create-key` in prod |
| `DIGICHAT_LEGACY_EMBED_ENABLED` · `DIGICHAT_EMBED_ENABLED` · `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS` | `apps/digichat-cloudflare/src/embed-flag.ts:1-20` | `wrangler.toml:74`; release profiles | yes | `1` = **anonymous embed relay** | wrangler + profiles | fail-closed default `0` |
| `DIGICHAT_REQUIRE_ROOT_AUTH` | `apps/digichat-cloudflare/src/index.ts:39` | `wrangler.toml:73` (`"0"`) | yes | root-auth wall off | wrangler + index default | shipped `"0"` |
| `DIGI_DISABLE_RATE_LIMIT` | `digigraph/src/digigraph/rate_limit.py:249`; digisearch | `.env`/test env | yes | rate limiting off | tests/local | never prod |
| `DIGISEARCH_ALLOW_MEMORY_RETRIEVAL` | `digisearch/src/digisearch/retrieval/pgvector.py:302` | test env | yes | in-memory retrieval fallback | tests/local | never prod |
| `DIGI_TRUSTED_PROXIES` · `DIGICHAT_TRUSTED_PROXIES` | `digigraph/src/digigraph/rate_limit.py:160`; digichat `index.ts:44` | env / unset | yes | IP allowlist for rate-limit headers | env | referenced, not always defined |

### (f) non-secret config still deployed as a secret

| Name | Consumer (file:line) | Defined in (file:line) | Readback? | Rotation blast radius | Duplicate copies | Notes |
|---|---|---|---|---|---|---|
| `DIGIGRAPH_INTERNAL_URL` · `DIGIKEY_URL` · `DIGIQUANT_INTERNAL_URL` · `DIGITRACE_INTERNAL_URL` · `DIGISEARCH_INTERNAL_URL` | digichat `src/index.ts:49-50` | digichat `wrangler.toml:52-53` | no — write-only | chat backend / JWT exchange upstream | digichat Worker; GH var `DIGIKEY_URL` | URLs stored as secrets |
| `DIGISEARCH_URL` | `pipeline-digiquant.yml:155` | not set; the workflow falls back to `https://search.digithings.ai` | n/a | pipeline uses the hosted URL | — | the `docs-reindex-guide.yml` apply step was removed (#4357): it posts a local filesystem path with no auth header |
| `DIGIKEY_ISSUER` · `DIGIKEY_AUDIENCE` · `DIGIKEY_KEY_ID` · `DIGIKEY_JWKS_URL` | stack `src/index.ts:61-62,73`; `jwt_verify.py:60` | stack `wrangler.toml:202-203`; code defaults `src/index.ts:62,73`, `digikey/src/digikey/crypto_keys.py:62` | yes | `iss`/`aud` mismatch fails all verification | wrangler + entrypoint defaults | plain vars, not secrets |
| `DIGICHAT_EMBED_HOSTS` | `apps/digichat-cloudflare/src/index.ts:41` | `apps/digichat-cloudflare/wrangler.toml:74` | yes | embed CSP `frame-ancestors` | wrangler + index default | not a secret |
| `CHEAPERINFERENCE_API_BASE` · `OPENAI_API_BASE` · `DIGI_HOUSE_UPSTREAM` | stack `src/index.ts:78,106-107` | `wrangler.toml:147,212` | yes | LiteLLM upstream selection | GH var + secret + defaults | base URL |
| `STUB_TSV_ENABLED` · `DIGI_MAINTENANCE_PROJECT_NUMBER` · `ENABLE_CLAUDE_PR_REVIEW` | GH workflows | GH repo **vars** | n/a | CI toggles | GH only | vars, correctly |
| `DIGI_CONFIG_PATH` · `DIGI_PROJECT_CONFIG` · `DIGI_WORKFLOW_PROFILE` · `DIGI_ALLOWED_TOOLS` | stack `wrangler.toml:213-221` | wrangler `[vars]` | yes | nothing — container default wins | inert | documented dead config (#2304/#2306) |
| `DIGIQUANT_MARKET_DATA_BACKEND` · `CHROMA_PATH` · `DIGIVAULT_ROOT` · `DIGISEARCH_INDEX` · `DIGI_TENANT_CORPUS_MAP` · `DIGI_LLM_MODE` | stack `src/index.ts:79-96,179` | stack `wrangler.toml:211,222-233` | yes | RAG index / market-data seam / LLM mode | wrangler + code defaults | plain vars |

## The twelve-x developer laptop `.env` — every key has an owner (DIG-526)

This section is deliberately **not** one row per key in the table above. It is the
twelve-x repo's local `.env` — a storage surface no row above covers, because the
inventory above is built from `digithings` readers. **Seventeen names** live there
with no recorded owner: the two PrimeMarket session keys (one of which has no
writer at all), the two desk-login keys, and thirteen more.
Named on 2026-10-05 by reading **key names only** from
`/Users/chrisstefan/Code/twelve-x/.env` (mode `-rw-------`, gitignored at
twelve-x `.gitignore:1`); **no value was read, printed, or copied.**

**Why this surface is not inert.** twelve-x `config.py:21` runs
`load_dotenv(_PROJECT_DIR / ".env", override=False)` at import, so any twelve-x
process started from that checkout — including a laptop run of the PrimeMarket
heartbeat itself — reads this file. `override=False` means a shell or CI variable
wins, which is the right precedence, and is also why a green CI heartbeat says
nothing at all about this copy. It is a **second live copy**, not a scratch file.

### (g1) the two PrimeMarket session keys — the two copies, one owner

| Name | Where the second copy is | Read by | Readback? | **Owner** | Recorded refresh path |
|---|---|---|---|---|---|
| `PRIMEMARKET_SESSION_TOKEN` | GitHub **Actions repo secret** on `digithings-ai/twelve-x`; **and** this `.env` | `nodes/scrape.py:661`; `scripts/primemarket_session_heartbeat.py:59`; CI probes it | no for the secret, yes for `.env` | **Security** (agent `b14d7a18`), with Chris as the only human who can execute it | `twelve-x/scripts/refresh_session_cookie.sh` — verifies live, then `gh secret set PRIMEMARKET_SESSION_TOKEN --repo "$REPO" --body "$VALUE"` (`scripts/refresh_session_cookie.sh:81`). Source of the value is Chris signing in at `https://desk.prime-terminal.com` and copying `localStorage['pmt_auth_token']`. **Rotate on expiry detection, never on a calendar** — measured: an authenticated call at 2026-09-15T00:08Z did **not** extend the window that 401'd at 06:04Z (`docs/PRIMEMARKET_DESK_API.md:157-165`) |
| `PRIMEMARKET_SESSION_COOKIE` | **only** here. Not in CI since DIG-249 (`8368932`, 2026-10-05) | `nodes/scrape.py:559,662` — legacy path, verified then used as a fallback | yes (`.env`) | **Security** | **NONE — this is the finding.** `refresh_session_cookie.sh` writes only the token; the cookie-paste branch was deleted by DIG-249 (`8368932`). Last write: **2026-09-14T10:33Z**, recorded at `docs/PRIMEMARKET_DESK_API.md:161` — the only refresh history that exists for it — and the same doc's 2026-09-17 follow-up records that the desk had moved to the Bearer scheme and **the cookie was never the session the pmt endpoints consult** (`:171-172`). So this is a copy nothing refreshes, of a mechanism the desk stopped accepting. Delete it; do not rotate it |

Consequence to state plainly: **a `primemarket-session-expired` alert tells you
about the Actions secret only.** The `.env` copy has no alert and no probe, and for
the cookie it has no writer either. As of `github/develop` `4f308ef` the single
twelve-x alert body
(`.github/workflows/primemarket_session_heartbeat.yml:62-75`) names neither copy —
it says only that the interim desk session is no longer valid. Closing that gap is
the open half of DIG-526 in twelve-x, tracked on twelve-x PR **#258** (open,
against `develop`; it also adds the "did not run" and "probe blocked" alert classes
that the 2026-08-01→08-15 checkout failures and the 96-hour no-run window of
2026-09-28T06:03:54Z→2026-10-02T06:03:23Z went unreported). Until it merges, this
row and the alert are inconsistent with each other, and the alert is the weaker of
the two.

### (g2) the desk login pair — a vendor login, not an application credential

| Name | Where | Read by | **Owner** | Status |
|---|---|---|---|---|
| `PRIMEMARKET_USERNAME` | this `.env`, **and** the repo secret on `digithings-ai/twelve-x` (passed at `.github/workflows/daily_run_reusable.yml:115` and `market_context_ingest.yml:72`; marked a "dormant credential-login route (DIG-249) … may legitimately be empty") | `config.py:27` `get_primemarket_credentials()` | **Security** | **Vendor login for `https://desk.prime-terminal.com`.** Not an API key, not a service account — a human's desk credentials. Login is captcha-gated since ~2026-07-29, so no code path can authenticate with it |
| `PRIMEMARKET_PASSWORD` | same — this `.env` and the repo secret (`daily_run_reusable.yml:116`, `market_context_ingest.yml:73`) | `config.py:28` | **Security** | Same |

So this pair lives in **three** places, not one: this `.env`, the repo secret, and
the code path. The repo-secret copies are the ones CI would use, and whether they
are populated is unverified — GitHub secrets are write-only, so I cannot read them
back, only confirm the names exist. That is a gap, not a clean bill of health.

This pair is still **live code**: `config.py:27-32` raises unless both are set, and
`nodes/scrape.py:692` calls it as the last-resort login fallback after both supplied
sessions fail. That ordering is deliberate and load-bearing — twelve-x
`docs/PRIMEMARKET_DESK_API.md:139-152` explains that "try the supplied session, else
fall back to credentials" is *not* implemented as a fallback chain, because a
rejected session would then fire a real credential attempt against the live vendor
account on every run. The chain is: session token, then cookie, then **this pair**.
So these two values are the only thing standing between a stale session and a failed
pipeline — and they are also the most damaging pair on this laptop, because they
authenticate as a person, not as a job.

DIG-249 (`8368932`) was recorded as dropping "the dead desk login pair", and the
twelve-x `README.md` says the pair is not required. What actually landed is
narrower: the pair came out of the **required-secrets preflight**
(`daily_run_reusable.yml:55-58`) and is still *passed* to the steps
(`:115-116`, `market_context_ingest.yml:72-73`), while the code and this `.env`
still carry it. Two consequences, both for Security to resolve and neither blocking:

1. If the PrimeMarket path is switched off (the open A/B question on DIG-478, card
   `295f3d75`), delete the pair in all three places — this `.env`, the
   `digithings-ai/twelve-x` repo secret, and the two workflow env blocks. It is the
   highest-value item on the laptop and the only one that is a human's account, and
   the repo secret is the copy nobody would remember to delete.
2. While the path is live, this pair is a standing credential with no rotation
   date and no alert. It is captcha-gated in practice, so treat it as
   password-manager material rather than an env var: **move it to Bitwarden
   (DIG-95) or delete it**, and do not leave it as the fallback of last resort.

### (g3) the remaining thirteen names — one owner each

Thirteen names in twelve rows (`TWELVEX_R2_*` shares a row). All thirteen live in
this `.env`; each row names the CI copy where one exists. Eleven are read by twelve-x
code — `config.py`, `nodes/llm.py`, or `nodes/scrape.py` — and two, marked
**no reader** below, are read by nothing on `github/develop`. Every one now has a
named owner rather than an implied one.

| Name | Read by | CI copy | **Owner** | Note |
|---|---|---|---|---|
| `SUPABASE_SERVICE_KEY` | `config.py:38` — **legacy** fallback | `TWELVEX_SUPABASE_SERVICE_KEY` is canonical | **Security** | Renamed to `TWELVEX_SUPABASE_SERVICE_KEY` in `7658a22` (2026-06-25, #57). `config.py:38` is an `or` chain — canonical first, legacy second — so this local copy **does** satisfy `get_supabase_key()`, and the raise at `config.py:42` fires only when both names are empty. What is wrong here is the **error text**: `:42` names only the canonical var, so a run with both empty reports a missing `TWELVEX_SUPABASE_SERVICE_KEY` when the operator did supply a service key under the old name. Working today, misleading when it breaks. Rename here to the canonical name and delete the alias |
| `CORE_SUPABASE_SERVICE_KEY` | `config.py:67` | repo secret (canonical per the 2026-10-04 decision) | **Security** | Service-role = full DB read/write. See the multi-service row in (c) and `docs/ops/SECRETS_ROTATION.md` |
| `CORE_SUPABASE_URL` | `config.py:107` (has a hardcoded default) | repo secret | **Security** | Public project-ref, not a secret — belongs in the (f) family |
| `TWELVEX_R2_ACCESS_KEY_ID` · `TWELVEX_R2_SECRET_ACCESS_KEY` · `TWELVEX_R2_ACCOUNT_ID` | `config.py:386-388` | repo secrets `R2_*` | **Security** | twelve-x archive bucket. Distinct from the digithings `R2_*` pair in (c) — different bucket, same account |
| `TWELVEX_R2_BUCKET` | `config.py:391` (defaults `twelve-x-archive`) | repo secret `R2_BUCKET` | **Security** | A bucket **name**, not a credential — belongs in the (f) family |
| `OPENROUTER_API_KEY` | `nodes/llm.py:73` notes the CI/`.env` key mismatch | org secret | **Security** | Same org-level key as the (b) row; this is its local copy. Triplicated per R4 |
| `CHEAPERINFERENCE_API_KEY` | **no reader** — twelve-x never reads this name; CI maps it *into* `OPENAI_API_KEY` (`daily_run_reusable.yml:61,109`) | repo secret | **Security** | House gateway key, but in twelve-x it is a **CI-side alias only**, not a runtime env name. The runtime name is `OPENAI_API_KEY` (read `nodes/llm.py:102-104`; `validate_llm_credentials` raises `MissingLLMCredentialsError` at `:113-116` if it is empty or a placeholder — the `CHEAPERINFERENCE_API_KEY` mention at `:114` is inside that error *message*). A local copy under this name is dead weight; set `OPENAI_API_KEY` locally |
| `CHEAPERINFERENCE_API_BASE` | **no reader** — `git grep CHEAPERINFERENCE_API_BASE github/develop` is empty in twelve-x | none **in twelve-x** (it *is* a live digithings repo variable — see [Storage surfaces](#storage-surfaces) and row (f)) | **Security** | **Dead name in twelve-x.** The house base is `OPENAI_API_BASE` (`config.py:193`, read `nodes/llm.py:86`). The repo qualifier matters: grepping this name in `digithings` finds live workflow reads, so "no reader" is true of twelve-x only |
| `OPENAI_API_KEY` | `nodes/llm.py:102-104` | mapped from `CHEAPERINFERENCE_API_KEY` in CI | **Security** | See the `unresolved` note on the (b) row — this `.env` copy is the only place it exists |
| `OPENAI_API_BASE` | `nodes/llm.py:86` | none (literal in workflows) | **Security** | Base URL, not a secret |
| `NOTION_API_TOKEN` | **no reader** — `git grep NOTION github/develop` in twelve-x is empty | none | **Security** | **Dead name.** No Python, shell, or workflow file in twelve-x reads it, so nothing here can tell you whether the value is still live at Notion — only Notion can. Delete here, and revoke at Notion if a twelve-x-integrated page ever existed |

### (g4) the surface-level fix, and why it is not this section

A table row is an accountability record, not a control. Three changes make this
surface stop being anyone's problem:

1. **Move the laptop's session keys out of `.env`** into Bitwarden Secrets Manager
   (DIG-95), same as `GH_DISPATCH_TOKEN` per R14. Then there is one copy, it has a
   writer, and the refresh script's `gh secret set` becomes the only path.
2. **Delete the three names nothing reads** — `NOTION_API_TOKEN`,
   `CHEAPERINFERENCE_API_BASE`, and `PRIMEMARKET_SESSION_COOKIE`; and rename
   `SUPABASE_SERVICE_KEY` → `TWELVEX_SUPABASE_SERVICE_KEY` plus
   `CHEAPERINFERENCE_API_KEY` → `OPENAI_API_KEY` so the local copies stop shadowing
   what CI supplies. Verified dead or uncanonical against `github/develop`, not
   inferred.
3. **Give the desk login pair a decision** — Bitwarden or delete, in all three
   places it lives. It is a human's account credential; the `.env` is the wrong home
   for it, and the repo secret is the copy nobody remembers.
4. **Check whether the repo-secret copies of the desk login pair are even set.**
   Unanswerable from here — GitHub secrets are write-only — so it is a human step.

None of these are done here. This section records the owner and the refresh path so
the next person is not guessing, and every claim above carries a `file:line`, a
commit, or a named command.

## Review coverage for this section

Reviewed in-session on 2026-10-05 by a fresh-context reviewer, which found and
forced the correction of five substantive errors in the first draft: a claim that
the `SUPABASE_SERVICE_KEY` copy could not satisfy its reader (it does — `config.py:38`
is an `or` chain; only the raise *message* is misleading), a claim that both
twelve-x alert bodies were already copy-aware (there is one, and it names neither
copy), and three citations whose line numbers did not contain the cited facts
(`PRIMEMARKET_DESK_API.md:151` → `:161`, `:160-162` → `:171-172`, and
`PRIMEMARKET_SESSION_TOKEN` is not read by `config.py` at all). It also corrected
"this `.env` only" for the desk login pair — those two names are in the repo secret
too and still passed by two workflows — and split "dead" from "uncanonical" for
the Supabase name. The takeaway for the next writer: **verify a line citation by
reading the line on `github/develop`, not the working tree, and check the other
repo before calling a shared name dead.**

## Risk register

**R1 — `DIGIKEY_PRIVATE_KEY_PEM` has no rollover path.** Severity: critical. Evidence: `digikey/src/digikey/crypto_keys.py:61`, `digikey/src/digikey/jwt_issue.py:88`, [`digikey/ARCHITECTURE.md`](../../digikey/ARCHITECTURE.md):305-335. Why: static `kid=digikey-1`, no JWKS overlap or grace period; rotating invalidates every outstanding JWT until each consumer refetches (300 s cache, `DIGIKEY_JWKS_CACHE_SEC`). Action: run `docs/ops/SECRETS_ROTATION.md`; implement multi-key JWKS overlap per `docs/adr/0029-secrets-management.md`.

**R2 — dev bypass flags (`DIGIKEY_ALLOW_DEV_GLOBAL`, `DIGIKEY_ALLOW_EPHEMERAL_KEY`) silently weaken auth if set in prod.** Severity: critical. Evidence: `digikey/src/digikey/settings.py:12`, `crypto_keys.py:65`, stack `wrangler.toml:203-204` (`"0"`), `scripts/run_stack_local.sh:76,78` (`1`). Why: `dev_global` mints `*`-scope keys; ephemeral key rotates JWKS on restart, breaking cross-instance verification. Action: assert `0` at deploy; keep the fail-closed default.

**R3 — real API keys are committed in a gitleaks-allowlisted example.** Severity: high. Evidence: `digiquant/src/digiquant/research/config/mcp.secrets.env.example:5,7,9` (non-placeholder literals, masked `***`), `.gitleaks.toml:52-57` (owner-confirmed dead 2026-06-18), `infra/digichat-release/compose.profile-a-bundle.override.yml:11` (`local-dev-unused-first-party`). Why: the research-example allowlist exempts that one path from scanning, so a live value there would never be detected; the compose-override token is not allowlisted at all — the default ruleset does not detect it. Liveness of both is unverifiable here. Action: confirm-dead or rotate; reduce the allowlist to placeholder-shaped values only.

**R4 — the container `envVars` whitelist drops secrets silently.** Severity: high. Evidence: digichat `src/index.ts:32-56` vs `wrangler.toml:50-58` — `DIGICHAT_DATABASE_URL`, `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY` are `put` on the Worker but never forwarded. Why: an operator rotates a key, the secret list shows it, and the process never sees it. Action: add a test asserting every Worker secret name appears in `envVars` or is documented inert.

**R5 — a running Container serves its start-time env until recycled.** Severity: high. Evidence: `apps/digithings-stack-cloudflare/README.md:27-28`, `apps/digichat-cloudflare/src/paths.ts:23`, commit #4290. Why: `wrangler deploy` does not roll the container, so a rotated secret looks rotated while the old value stays live. Action: make the recycle step (bump `SHARED_DIGICHAT_CONTAINER_ID` / rebuild marker) mandatory in the rotation runbook.

**R6 — digikey's static bearer tokens have no rotation procedure and are duplicated.** Severity: high. Evidence: `digikey/src/digikey/server.py:60,117-121` (`DIGIKEY_ADMIN_TOKEN`), `settings.py:20` (`DIGIKEY_BFF_TOKEN`), `apps/digichat-cloudflare/wrangler.toml:54` + `apps/digithings-stack-cloudflare/wrangler.toml:136`. Why: compromise of the admin token grants key-issue/revoke; the BFF token must match across two Workers, so a one-sided rotation breaks chat auth. Action: document a two-surface rotation with a dual-accept window.

**R7 — the Cloudflare token alias family is still live and ambiguous.** Severity: medium. Evidence: stack `wrangler.toml:159,190-193`, `src/index.ts:89-93`, [vectorize cutover](vectorize-cutover.md):132-207. Why: `CLOUDFLARE_API_TOKEN` doubles as wrangler's own auth var (auth error 10000 when exported), and the legacy `VECTORIZE_*` / `D1_*` names are forwarded as fallbacks — a leaked legacy token stays valid with no obvious owner. Action: delete legacy secrets after verification.

**R8 — `AUTH_SECRET` spans four or more surfaces.** Severity: high. Evidence: `apps/digichat-cloudflare/src/index.ts:47`, `wrangler.toml:50`, `docker-compose.yml:550`, `infra/digichat-release/.env.profile-a.example:17`. Why: a partial rotation invalidates sessions only on some instances, producing intermittent logouts. Action: enumerate every surface in the runbook and rotate atomically.

**R9 — the `wrangler.toml` secret checklist and the live Worker set diverge.** Severity: medium. Evidence: last in-repo live recount is 25 names on `digithings-stack` (2026-09-27, [Folded stack worker](#folded-stack-worker--secret-maintenance-2026-09-27)); the 16-name list in [Storage surfaces](#storage-surfaces) is the superseded 2026-09 audit. `apps/digithings-stack-cloudflare/wrangler.toml:169-245` documents `R2_*`, `FRED_API_KEY`, `OPENAI_API_KEY`, `GLOOMBERB_SESSION_COOKIE`; `LITELLM_MASTER_KEY` is forwarded (`src/index.ts:143`) but still absent from that checklist. Why: operators rotate a documented name that is not deployed, or miss a live one (`LITELLM_MASTER_KEY`). Action: generate the checklist from `wrangler secret list`; reconcile the dead/missing entries.

**R10 — `MCP_EDGE_KEY` rotation is coupled to a literal in `DIGICHAT_EMBED_TENANTS`.** Severity: medium. Evidence: `apps/digichat-cloudflare/README.md:115-117`, `apps/digichat/config/examples/occ-embed.yaml:56-58`, stack `src/index.ts:343`. Why: the stack Worker secret is not forwarded to the container, so the tenant map carries the value literally; rotating only the Worker secret 401s the MCP edge. Action: rotate both in one change and verify the edge route.

**R11 — `DIGIKEY_DATABASE_URL` password rotation is undocumented.** Severity: medium. Evidence: stack `wrangler.toml:139`, `apps/digithings-stack-cloudflare/README.md:69-71`, [digikey service key](digiquant-digikey-service-key.md):77-103. Why: the URL carries the Postgres password; there is no fallback (digikey refuses to start if unset, #4080), so any rotation mistake is an auth outage, and keys minted into the old store are lost on a DSN switch. Action: add a re-issue-and-verify runbook.

**R12 — `DIGIQUANT_VAULT_MASTER_KEY` is a single key with no rewrap path.** Severity: high. Evidence: `digiquant/src/digiquant/vault/envelope.py:79,80,141,151-175`. Why: AES-256-GCM with no default; rotating it makes every sealed broker credential unreadable, and `DIGIQUANT_VAULT_KEY_ID` has one label (`v1`). Action: KMS/rewrap runbook; seal a second key id before retiring the first.

**R13 — GitHub secret reads are repo-scoped with almost no environment gate.** Severity: high (mitigation half-landed 2026-10-04). Evidence: `DIGITHINGS_PROJECT_TOKEN` is read by 7 workflow files, 22 `secrets.*` refs (`agent-backlog-snapshot.yml:28` … `pipeline-maintenance.yml:910`); `CORE_SUPABASE_URL` and `CORE_SUPABASE_SERVICE_KEY` 31 each, the four `R2_*` names 9 each, `CLOUDFLARE_ACCOUNT_ID` 5, `CLAUDE_CODE_OAUTH_TOKEN` 5, `CLOUDFLARE_API_TOKEN` 4. Why: any workflow on any branch can read these, and the project token is the widest-blast-radius CI credential. Action: ~~move production reads behind GitHub Environments~~; scope the project token to fine-grained permissions.

**R13 status — the code half landed on 2026-10-04 (DIG-248).** Two separate defects were fixed, and one is still open:

1. **Gate: done.** A third environment, `cron`, was created with **no required reviewers, no wait timer and no branch policy**, so a job pointing at it runs immediately and no scheduled pipeline can stall. Every one of the **32 jobs that read a non-automatic `secrets.*` name** across 18 files now declares `environment: cron`; `deploy-digiquant-runner.yml:deploy` keeps `environment: production`. **Deliberately not `production`**: that environment carries `required_reviewers: [chrizefan]` plus a custom branch policy, so pointing 32 more jobs at it would have made every scheduled pipeline wait for manual approval — the automation would have stopped while looking like flaky crons. The three files that read nothing but the automatic `GITHUB_TOKEN` (`ci-pr-hygiene.yml`, `ci-pr-title.yml`, `refresh-repo-activity.yml`) need no gate.
2. **Scope: OPEN, blocked on a human.** Environment-scope secrets are invisible to jobs that do not declare that environment, so the gate above is inert until the values actually exist at `cron` scope. GitHub secrets are write-only, so the 18 repo names and 11 org names have to be **re-entered by Chris** in the `cron` environment and only then deleted from repo/org scope — in that order, after this change merges and one scheduled cycle passes green. `deploy-digiquant-runner.yml:deploy` also needs fresh `production`-scope copies of `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, whose `production` copies were deleted 2026-09-18; `D1_DATABASE_MAP` is already there. Until that happens, a new `secrets.*` name added to a `cron` job will resolve to empty exactly as it would with no environment at all — the gate is real but currently unpopulated.

**R14 — one personal PAT is the only GitHub credential for every org-wide clock *and* for the alarm that reports on them.** Severity: high (accepted 2026-10-05, DIG-363). Evidence: `GH_DISPATCH_TOKEN` is a fine-grained **personal** access token on a human account (settings id 19179726, `digithings-ai/digithings` + `digithings-ai/twelve-x`, expires 2027-09-15); the `digithings-cron` Worker holds it as its only GitHub credential. It authorizes all **38** distinct cron expressions' `workflow_dispatch` POST (`apps/digithings-cron/wrangler.toml:37-76` `[triggers]`, posted at `apps/digithings-cron/src/dispatch.ts:289,295-298`), and the DIG-71 short-day alarm, which posts to `POST /repos/$ALERT_ISSUE_REPO/issues/$ALERT_ISSUE_NUMBER/comments` with the same token and no other. Why: the credential that reports "the clocks stopped" is the credential that stops the clocks, so **one event on one human account is a correlated outage of the workload and its own alarm in a single move** — 2FA re-enrolment, a lockout, a password change under account-wide PAT revocation, offboarding, or account deletion. Two aggravating properties: fine-grained PAT permissions are **not readable over any GitHub API**, so grant drift on this credential is invisible to tooling; and revocation is an **account-level** action, so rotation cannot be done by an agent or on a schedule — only reactively, by a human. Action: **accepted risk, not mitigated** — Chris chose B (keep the PAT) and the shared token on 2026-10-05, declining a GitHub App because that would add a second long-lived secret with power to mint dispatch and issue tokens. Re-open if any of: the PAT reaches its 2027-09-15 expiry (rotate reactively, [runbook](SECRETS_ROTATION.md#4-gh_dispatch_token)); the alarm lands on a second credential; or the token moves to Bitwarden (DIG-95), which changes custody but **not** this coupling. Adding a second credential for the alarm would reverse the deliberate `GH_ISSUE_TOKEN`-must-not-exist rule (`apps/digiquant-runner/wrangler.toml:14,20`) and would have to be argued on its own merits.

## Gaps and unknowns

- **Pages env not enumerable.** `digithings-web` Pages project env vars are not listed by `wrangler secret list`; `apps/digithings-web/wrangler.toml:24` documents a dead `OPENROUTER_API_KEY` (the `/chat` function returns 410), but the live Pages env is unknown.
- **Container app env not enumerable.** The digichat Container's runtime env is only visible as the Worker `envVars` whitelist in source; nothing confirms the actual container process env at runtime.
- **Every level is enumerable now** (repo secret/variable, org secret, `production` environment) — see [Storage surfaces](#storage-surfaces) and `make secrets-audit`, which reports a read it cannot place at any level as `unresolved`. No **CI** read is unresolved any more: the last two, `CLOUDFLARE_EMAIL_API_TOKEN` and `NOTIFY_FROM`, were stored on 2026-09-18 (#4358); the daily `execution-cron-check` probe then went green (`notify_configured=1`) and a real send was queued through the sender. (`make secrets-audit` only judges `secrets.*` reads under `.github/**`, so a name in this table that no workflow reads — `OPENAI_API_KEY`, for instance — is outside it.) #4357 resolved the other three: `E2E_BEARER_TOKEN` is now minted in-workflow from the compose stack, the OpenWiki step reads the org-level `LANGSMITH_API_KEY`, and the `docs-reindex-guide.yml` apply step that read `DIGISEARCH_URL` was removed (it posts a local filesystem path with no auth). #4358 replaced the Mailgun sender with Cloudflare Email Sending: digiquant.io is onboarded on that account and the sender is live.
- **Literal liveness.** Whether the committed `mcp.secrets.env.example` keys still work, and the `local-dev-unused-first-party` token, cannot be verified without their values.
- **Alias equality.** `R2_ACCOUNT_ID == CLOUDFLARE_ACCOUNT_ID`, the two `DIGIKEY_BFF_TOKEN` copies, and the `MCP_EDGE_KEY` vs tenant-map literal are inferred from config, not diffed against live state.
- **Legacy secrets.** Whether `VECTORIZE_*` / `D1_*` are still set on `digithings-stack` — the live list shows `VECTORIZE_ACCOUNT_ID` and `VECTORIZE_API_TOKEN` (but not `D1_ACCOUNT_ID` / `D1_API_TOKEN`), so the "safe to delete" claim is not fully verifiable.
- **Private key source.** The prod origin of `DIGIKEY_PRIVATE_KEY_PEM` (platform secret store vs `.env`) is not visible in-repo.
- **Revocation strength.** Whether prod sets `DIGIKEY_BLOCKLIST_REDIS_URL`. The code default is fail-closed; `DIGIKEY_REQUIRE_BLOCKLIST=0` is the local opt-out (`blocklist.py` `require_blocklist_enabled`). Compose default `1` at `docker-compose.yml:35`; `.env.example:226`.
- **Secret-manager adoption.** Cloudflare Secrets Store, 1Password, Infisical, and Doppler appear only as aspirational mentions; no repo evidence of use.
- **Fine-grained PAT grants are not machine-readable.** The permissions on a fine-grained PAT (`GH_DISPATCH_TOKEN`) can only be viewed and edited on the GitHub settings page — GitHub exposes no REST or GraphQL endpoint for them, and the token value is shown once at creation and never again. So the grant recorded on the `GH_DISPATCH_TOKEN` row is operator-reported, not agent-verified, and it cannot be swept by `make secrets-audit`. Agent-side confirmation that a grant exists has to come from a real call against the endpoint it gates.
- **`projects/**` and `.local/`** are gitignored and not auditable from this checkout.

## Folded stack worker — secret maintenance (2026-09-27)

The single folded worker (`digithings-stack`) owns the dashboard-api and digichat
secrets behind the isolation seam (fold slices #4686/#4688/#4690, launch-readiness
#4693/#4694). Secret values are write-only in Cloudflare (`secret list` shows
names only) and local `.env` files are unreadable to agents, so maintenance
splits three ways. The last in-repo recount is 25 names (2026-09-27 via
`wrangler secret list -c apps/digithings-stack-cloudflare/wrangler.toml`);
that recount **supersedes** the 16-name 2026-09 audit in [Storage surfaces](#storage-surfaces)
and was not re-run here. The three #4700 consolidation deletes below (they run
only after the manual production deploy carrying the fallback chain) are 25 − 3 = 22.

### Agent-settable (values documented in-repo, plaintext)

```bash
CFG=apps/digithings-stack-cloudflare/wrangler.toml
echo "https://graph.digithings.ai" | npx wrangler secret put DIGIGRAPH_INTERNAL_URL -c $CFG
echo "https://key.digithings.ai" | npx wrangler secret put DIGIKEY_URL -c $CFG
```

`SUPABASE_URL` needs no `put` — it ships as plaintext `[vars]` in the stack
`wrangler.toml` (#4700; public project-ref, same as the standalone
dashboard-api worker).

`MARKET_DATA_URL` stays unset (optional; closes resolve honest-empty, same as the
standalone dashboard-api worker). `DIGIKEY_BFF_TOKEN` is already on the worker
and is forwarded to the container by the `envVars` whitelist — nothing to set.

### Agent-generatable (random, must match on both workers until cutover)

`AUTH_SECRET` and `DIGICHAT_PLAN_PROOF_SECRET` must carry the same value on the
stack worker and the standalone digichat worker until the route cutover, or
sessions/proof links validate on one worker and fail on the other. Generate once
per secret, pipe the same temp file into both `put` calls, then delete it (shell
file redirects must stay inside the workspace; never commit the file):

```bash
openssl rand -hex 32 > scratch-rot-auth.txt
npx wrangler secret put AUTH_SECRET -c apps/digithings-stack-cloudflare/wrangler.toml < scratch-rot-auth.txt
npx wrangler secret put AUTH_SECRET -c apps/digichat-cloudflare/wrangler.toml < scratch-rot-auth.txt
rm -f scratch-rot-auth.txt
```

Rotation invalidates outstanding chat sessions (`AUTH_SECRET`) and issued
plan-proof links (`DIGICHAT_PLAN_PROOF_SECRET`) — one-time logout, flag it.

### Human-only (real values unreachable to agents)

`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, and
`DIGICHAT_EMBED_TENANTS` exist only on the standalone workers (write-only) or in
the owner's vault. The owner pastes each one:

```bash
CFG=apps/digithings-stack-cloudflare/wrangler.toml
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY -c $CFG
npx wrangler secret put SUPABASE_ANON_KEY -c $CFG
npx wrangler secret put DIGICHAT_EMBED_TENANTS -c $CFG
```

#4700 consolidation ops (stack worker only, AFTER the manual deploy carrying
the `index.ts` fallback chain is verified — deleting early breaks the digichat
container; the standalone digichat worker keeps its own `DIGICHAT_*` names
until cutover retirement):

```bash
CFG=apps/digithings-stack-cloudflare/wrangler.toml
npx wrangler secret delete DIGICHAT_DASHBOARD_SUPABASE_URL -c $CFG
npx wrangler secret delete DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY -c $CFG
npx wrangler secret delete SUPABASE_URL -c $CFG
```

(The lingering `SUPABASE_URL` secret would shadow the new `[vars]` value —
secrets take precedence — so it must be deleted for the demotion to take
effect. Arithmetic on the 2026-09-27 set: 25 − 3 = 22 names. That is not a
live re-list.)

### Gotchas

- `CLOUDFLARE_API_TOKEN` exported in the shell makes wrangler authenticate as
  that token and fail with auth error 10000 — run with `env -u CLOUDFLARE_API_TOKEN`.
- `secret put` needs no redeploy, but containers serve their start-time env
  until recycled — bump the `SHARED_*_CONTAINER_ID` marker after rotation.
- Verify by names only; never print values, never write them to repo files.

## Refreshing this inventory

```bash
# 1. Live Worker secret names (names + type only; secret_text has no readback).
#    Pin wrangler; unset CLOUDFLARE_API_TOKEN or wrangler authenticates as that
#    token and fails with auth error 10000 (stack wrangler.toml:167-180).
cd apps/digichat-cloudflare   && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
cd apps/digithings-stack-cloudflare && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
cd apps/digithings-cron       && env -u CLOUDFLARE_API_TOKEN npx wrangler@4.133.0 secret list
#    Pages (separate command surface): npx wrangler@4.133.0 pages secret list --project-name digithings-web
# 2. Declared Worker secret names + container envVars whitelist.
rg -n "wrangler secret put|secret_text|envVars|workerVars\." cloudflare
# 3. GitHub Actions secret/var references and any environment gate.
rg -n "secrets\.[A-Z_]+|vars\.[A-Z_]+|^\s*environment:" .github/workflows
# 4. Local templates and env-file declarations.
rg -n "^[A-Z][A-Z0-9_]+=" .env.example apps/digichat/.env.example \
  infra/digichat-release/.env.profile-*.example docker-compose.yml
# 5. Python settings / os.environ reads.
rg -n "os\.getenv|os\.environ" --glob '*/src/**/*.py' digibase digikey digigraph digillm digiquant digisearch digitrace digivault digiclaw
```

Ageing is a **manual** check, not an automated one: `make secrets-staleness` runs `scripts/secret_staleness_check.py --open-issue`, which lists every repo, org and `cron`-environment secret **name** with its last-written date, reports the ones past the 90-day rotation window, and opens or updates one tracking issue titled `Ops: GitHub secrets past the 90-day rotation window`, ordered widest-blast-radius first (org before repo before environment, then oldest first). It reads no value — `gh secret list` returns names and dates only.

It needs a token with the `repo` scope (plus `admin:org` for the org level), and a workflow's `GITHUB_TOKEN` never has that scope: it is a GitHub App installation token, and GitHub's `permissions:` vocabulary has no key for secrets at all. Run 37235973852 (2026-10-04) measured this directly, with `actions: read` visibly granted and all three listings still returning HTTP 403, which disproved the grant #5063 had added for it and is why that permission was removed again. So the automation deliberately does not attempt the ageing at all rather than reporting three levels NOT CHECKED and looking like a working control: Paperclip DIG-477 (option D, Chris, 2026-10-05) took the ageing half **out of CI** and kept the drift half. `.github/workflows/secret-staleness-check.yml` is now `workflow_dispatch` only with no inputs, runs `secret_staleness_check.py --gates-only`, needs `contents: read` and nothing else — in particular not `issues: write`, because it no longer files or closes a tracker. It is still dispatched monthly at `17 6 1 * *` by the `secret-staleness` job on the digithings-cron Worker (no clock lives in `.github/workflows`, by repo policy), and there it does the drift half only. Run it from an operator's shell on the Mac, where `gh auth` already carries `repo` and `admin:org`.

It is **not** the Keymaster weekly key report: that report is built from Bitwarden and never reads the GitHub Actions secrets API, so it cannot age anything.

**What this costs, stated plainly:** nothing will notice a credential going dead except `token-canary.yml`, which probes only `DIGITHINGS_PROJECT_TOKEN` and `GH_DISPATCH_TOKEN`. Of the 16 names below, the other 14 have no automated liveness check of any kind — `FRED_API_KEY` appears in no workflow file at all. That is the deliberate trade of option D, which is that the next rotation is decided by someone remembering to ask. What keeps that from becoming "nobody remembers" is the monthly manual job recorded just below, tracked as Paperclip DIG-668.

Measured by hand on 2026-10-04: **16 of 33 listed names are past 90 days** — `DIGITHINGS_PROJECT_TOKEN` at 163 days, `CORE_SUPABASE_SERVICE_KEY` and `CORE_SUPABASE_URL` at 100, and all 13 org secrets (oldest: `CURSOR_API_KEY` and `FRED_API_KEY`, 165 and 165). Until this half is automated again, those 16 are tracked in this section rather than by a clock. Keeping this section current is a **monthly manual job**: run `make secrets-staleness` from a shell whose `gh auth` carries `repo` and `admin:org`, then update this section with the count and the date measured. Paperclip **DIG-668** holds that job and its steps. Re-measure rather than trusting the numbers above — they carry the date they were taken, and age is not death: `DIGITHINGS_PROJECT_TOKEN` sat at 163 days while `token-canary.yml` validated it daily.

### The gate is a manifest, and the manifest is checked

`.github/environments.json` records the protection rules of every environment a workflow may name: wait timer, required reviewers, allowed branches, and the date a human last read them off the API. Two things depend on it.

**The no-queue rule.** A job gated on an environment with a required reviewer holds its `concurrency` group from the moment the run starts, so one unapproved run silently stops every later run of that workflow. That cost 15 days of migrations once already (#2541). `tests/scripts/test_workflow_environment_concurrency.py` therefore exempts a gated job from that rule only when the manifest says its environment cannot wait, and it fails on any `environment:` a workflow declares that the manifest does not describe. Three older assertions that a workflow must carry no gate at all were rewritten on 2026-10-04 for the same reason: `environment:` is the only mechanism that scopes a secret to one environment, so the 32-job gate is a control, and refusing it in a test protects nothing. The rewritten tests assert the stronger property instead — the job is gated on an environment that cannot wait.

**Drift.** Protection rules can be armed in the GitHub UI, where no test runs and no commit is made. If someone later adds a required reviewer to `cron`, all 32 gated pipelines would queue behind an approval instead of running, and the symptom is "the cron got flaky". `secret_staleness_check.py` therefore compares the manifest against the live protection rules on every run and **exits non-zero on any difference** — deliberately unlike `--fail-overdue`, because a credential nobody rotated is a human decision, while a stalled automation is not. That failure is the only one the staleness job can produce; a secret past the window never fails it, and since DIG-477 it does not even read the window on that job (`--gates-only`), so gate drift is now the *only* code path in CI that can fail at all.

One limit on that, recorded because the sentence above reads stronger than the code is: drift is only detected if the environments **can be read**. When every read fails — a lost `contents: read`, a `gh` outage, a malformed manifest — the gate list comes back empty, `any(...)` over no rows is false, and the job exits 0 having checked nothing. The summary does say `NOT CHECKED` per environment with the reason, so it is not a false green in the sense DIG-477 was about, but it is green. This is pre-existing on develop rather than introduced by DIG-477; it becomes more load-bearing now only because ageing is gone and this is the sole control left. Tracked as Paperclip DIG-682.

Measured on 2026-10-04, all four environments agree with the manifest: `copilot`, `cron` and `github-pages` cannot wait, `production` can (`required_reviewers: [chrizefan]`, branches `main`).

`.worktrees/` is gitignored (`.gitignore:5` — `/.worktrees/`), so a search launched from the main checkout silently skips a task worktree. Pass the worktree root as an explicit path argument, or add `--no-ignore`, when refreshing from inside one.
