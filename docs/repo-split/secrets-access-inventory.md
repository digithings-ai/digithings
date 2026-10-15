# DIG-3572 — Secrets + access inventory per repo (names only)

Scope: slice P of DIG-3518. Per repo R0–R7: secret **names** needed, where each
name lives today, where it moves, and what must leave public R0 + its history.
**Names only. No values are recorded here or in any artefact this ticket makes.**

Sources (read 2026-10-14, names only):
- `repo-split.md` (develop `83a104a10` tree scan) + plan PR #5695 branch
  `DIG-3518-repo-split-plan` (`docs/repo-split/{README,decisions,migration-plan,review}.md`).
- Live name scans, same day: `secrets.*` over `.github/workflows` (30 names);
  `config/contract/secrets.yaml` (37 `- name:` entries); `wrangler secret put`
  names in `scripts/` + `apps/`; `[vars]` keys in `apps/*/wrangler.toml`;
  Keychain **service names only** (`security dump-keychain`, `svce` field, no `-w`);
  `gh api repos/digithings-ai/digithings/environments` (copilot, cron,
  github-pages, production).
- No secret value was printed, pasted, logged, or committed at any step.

Hard limits honoured: planning, dry runs, and PRs into `develop` only. No repo
creation on Origin or GitHub, no history migration/push, no Cloudflare config
changes, no `main` merges, no Paperclip restart. Anything needing those goes to
Chris as a decision — none is needed for this slice.

TOP PRIORITY note (Chris 22:09, 2026-10-14, comment on this issue): GitHub
Actions minutes are exhausted; migration off GitHub (Cloudflare crons/workflows,
local Mac CI, Cursor Origin) is first. Missing GitHub Actions checks are **not**
failures; this PR records its local test pass in the PR body. This slice is a
docs-only PR into `develop` — explicitly allowed.

Decisions applied: D-G1 (stay on GitHub Free — private GH repos get **no**
branch protection, rulesets, environments, or environment secrets), D-G2 (mono
stays public until cutover), D-12' (fresh public R0), D-R3 (tags, not release
branches, in R0), D-G4 (private repos on self-hosted runners), D-G5 (deploy +
CI agents run on Chris's Mac under his normal user; Cloudflare Worker fallback),
D-G6 (signed release tags optional — deploy control is procedural, not
cryptographic), D-O1 (R0 GitHub-primary + Origin inbound mirror; R1–R7 Origin
primary in Chris's personal namespace), D-O2…D-O5 (answered, see PR #5695
`decisions.md`), D-T1 (tenant map in KV, fallback = digithings tenant only).

Consequence for secrets: on GitHub Free there is **nowhere on GitHub to store a
private-repo secret** (no environment secrets). Every R1–R7 runtime secret
therefore lives on the **Mac deploy agent** (Buildkite `deploy` queue, D-G5)
and is pushed to Cloudflare as a **Worker secret** (`wrangler secret put` from
that Mac) or into **KV/R2** by the tenant sync. Repos hold **names and wiring
only**. Local-only Keychain entries (`digithings-local/*`, dot-form
`digithings.*`) never enter any repo.

## R0 — `digithings` (public, GitHub-primary)

Keeps only what a public open-source repo may hold:
`GITHUB_TOKEN`, `NPM_TOKEN`, PyPI trusted publishing (no stored secret),
`CHEAPERINFERENCE_API_BASE`, `CHEAPERINFERENCE_API_KEY`,
`LANGSMITH_API_KEY` (openwiki-update job only).

Must be removed from R0 and scrubbed from its history (D-12, fresh-repo
cutover; mono renamed private then archived):
`CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`, `CORE_POSTGRES_URI`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`,
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_EMAIL_API_TOKEN`, `DIGIQUANT_DIGIKEY_API_KEY`,
`GH_DISPATCH_TOKEN`, `DIGITHINGS_PROJECT_TOKEN`, `NOTIFY_FROM`,
`CRON_KICK_SECRET`, `RUNNER_AUTH_TOKEN`, `D1_API_TOKEN`,
`DIGIKEY_ADMIN_TOKEN`, `DIGIKEY_BFF_TOKEN`, `DIGIKEY_DATABASE_URL`,
`DIGIKEY_PRIVATE_KEY_PEM`, `DIGIKEY_LITELLM_PROXY_KEY`,
`LITELLM_MASTER_KEY`, `LITELLM_PROXY_API_KEY`, `MCP_EDGE_KEY`,
`ZAMMAD_API_TOKEN`, `GLOOMBERB_SESSION_COOKIE`, `STRIPE_SECRET_KEY`,
`AUTH_SECRET`, `DIGICHAT_*_TOKEN` / `DIGICHAT_*_KEY` / `DIGICHAT_*_SECRET` /
`DIGICHAT_*_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, `AZURE_SEARCH_API_KEY`,
`BYOK_API_KEY`, `EXA_API_KEY`, `EXA_MONITOR_WEBHOOK_SECRET`, `XAI_API_KEY`,
`OPENROUTER_API_KEY`, provider review keys (`CEREBRAS_API_KEY`,
`DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`,
`NVIDIA_API_KEY`, `OLLAMA_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
`CURSOR_API_KEY`), `DIGISEARCH_SEED_API_KEY`, `DIGIGRAPH_UPSTREAM_API_KEY`,
`DIGICLAW_DIGIKEY_API_KEY`, `DIGIQUANT_VAULT_MASTER_KEY`,
`E2E_BEARER_TOKEN`, `DIGISEARCH_MONITORS_DB`.
Worker `[vars]` (non-secret config such as `SUPABASE_URL` public anon URL,
`DIGICHAT_EMBED_HOSTS`, `DIGISEARCH_URL`) are not secrets and stay as vars;
anything above that appears as a var today moves to a Worker secret instead.

## R1 — `digiquant-strategies` (private, Origin)

Needs **no stored secret**. Build/publish uses the short-lived Origin token
minted by the CI agent at job time (D-Q7: git tag pins, no registry). No
service-role, broker, or provider keys. No Keychain move. No wrangler binding.

## R2 — `digiquant-stack` (private, Origin)

Deploy-time set, held **only on the Mac deploy agent** (Buildkite `deploy`
queue), pushed to Workers via `wrangler secret put` and to Supabase via
`supabase db push` from that Mac. Never in the repo.
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_EMAIL_API_TOKEN`, `NOTIFY_FROM`, `CORE_SUPABASE_URL`,
`CORE_SUPABASE_SERVICE_KEY`, `CORE_POSTGRES_URI`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET` (writer:
`digithings-archive`), `DIGIQUANT_DIGIKEY_API_KEY`, `LANGFUSE_BASE_URL`,
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `CHEAPERINFERENCE_API_BASE`,
`CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`,
`DATABASE_URL` (dashboard-api Worker), `DIGICHAT_DASHBOARD_SUPABASE_URL`,
`DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY`, `DIGIKEY_URL`,
`DIGIKEY_ADMIN_TOKEN`, `DIGIKEY_BFF_TOKEN`, `DIGIKEY_DATABASE_URL`,
`DIGIKEY_PRIVATE_KEY_PEM`, `DIGIKEY_LITELLM_PROXY_KEY`,
`DIGICHAT_EMBED_TENANTS` (own Worker copy; R6 is the source of truth),
`AUTH_SECRET`, `CRON_KICK_SECRET`, `RUNNER_AUTH_TOKEN`, `D1_API_TOKEN`.
Today: GitHub `production`/`cron` environment secrets + `secrets.*` in the
pipeline/digiquant workflows. Moves to: Mac deploy-agent env + Worker secrets;
no GitHub environment exists for Origin repos.

## R3 — `digiquant-web` (private, Origin)

Public-anon only. `NEXT_PUBLIC_SUPABASE_URL` + anon key (public), Pages deploy
by direct upload from the Mac agent on a Chris-cut release tag (D-Pages — no
stored Pages token in the repo). No service-role key, `CORE_SUPABASE_SERVICE_KEY`, no broker keys. Today: Pages Git integration on
`digiquant-io` (auto-deploy from `main` — disconnected at cutover).

## R4 — `digithings-web` (private, Origin)

Pages deploy token only, held on the Mac and used for direct upload (D-Pages).
No API keys, no service-role, no `byok` secrets in repo (`byok-providers.json`
via `@digithings/catalog`). Today: Pages Git integration on `digithings-ai`.

## R5 — `digithings-stack` (private, Origin)

Platform deploy set, held **only on the Mac deploy agent**, Worker runtime
secrets via `wrangler secret put` from that Mac. Never in the repo.
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_EMAIL_API_TOKEN`, `GH_DISPATCH_TOKEN` (re-scoped to Buildkite
pipelines for R2+R7 at the move; GitHub Actions dispatch retires),
`DIGITHINGS_PROJECT_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CURSOR_API_KEY`
(token-canary), provider-review keys, `DIGIKEY_ADMIN_TOKEN`,
`DIGIKEY_BFF_TOKEN`, `DIGIKEY_DATABASE_URL`, `DIGIKEY_PRIVATE_KEY_PEM`,
`DIGIKEY_URL`, `DIGIGRAPH_INTERNAL_URL`, `MCP_EDGE_KEY`,
`ZAMMAD_API_TOKEN` (stack-edge path; live Zammad uses `ZAMMAD_API_TOKEN` via
`tokenEnv`, never committed), `AUTH_SECRET`, `DATABASE_URL`,
`DIGICHAT_MONITOR_TOKENS`, `DIGICHAT_PLAN_PROOF_SECRET`,
`DIGICHAT_EMBED_TENANTS` (runtime read; source of truth moves to KV via R6,
fallback = digithings tenant only per D-T1), `GROQ_API_KEY` (where still
wired). Service bindings (`RUNNER`, `DASHBOARD_API`) carry no secret.
Today: hand-run `wrangler deploy` from local trees + `secrets.*` in
deploy/cron workflows. Moves to: tag-driven deploy from the Mac agent
(P2 gate hook); the Cloudflare-app-for-Cursor auto-deploy path is forbidden
(O5) and is never installed.

## R6 — `digichat-tenants` (private, Origin)

Tenant-data repo: schema + sources only, **no live keys in the repo**.
`CLOUDFLARE_API_TOKEN` (KV + R2 write scoped, held on the Mac, used by the
`kv-sync` script), `DIGICHAT_EMBED_TENANTS` content (pushed to KV namespace
`TENANT_CONFIG`, never committed with live values), R2 seed objects (pushed,
not stored as secrets), `OCC_INVITE_KEY` (see below), `ZAMMAD_API_TOKEN`
(server-side only). `config/examples/occ-embed.yaml` keeps `tokenEnv` **names**
only. `DIGI_TENANT_CORPUS_MAP` fallback is removed from the stack Worker at
the move (D-T1); `seed/occ_help` + `seed/vault/clients/*` sources live here
and are fetched from R2 at boot.

## R7 — `twelve-x` (private, Origin, exists)

Moves in P4.7 with full history (D-O5: no client gate; GitHub repo archived
read-only 90 days, then deleted). Needs: anon Supabase URL + anon key,
`D1_API_TOKEN` (twelvex D1 API), Pages/desk deploy via Mac agent. No
service-role, no strategies keys, no tenant keys. Client desk pages
(`apps/dashboard` twelve-x paths + `apps/digidata-api`) land here; the desk
gate/palette become pluggable (D-X1).

## OCC invite key + tenant tokens + edge keys (Keychain, names only)

Live human-held names (Keychain service names, values never touched):
`digithings.occ-invite-key`, `digithings.mcp-edge-key`,
`digithings.zammad-edge-key`, `digithings.tenant-token-digiquant-io`,
`digithings.tenant-token-digithings-ai`.
These stay in Keychain + Cloudflare Worker secrets + KV. They are **never
committed** to any repo (R0/R5/R6 hold procedure and `tokenEnv` names only,
per DIG-1612/#5308). Rotation is a human/Keymaster action, not part of the
file move.

## Local-only Keychain (`digithings-local/*`, never moves)

`digithings-local/CHEAPERINFERENCE_API_KEY`,
`digithings-local/DIGICHAT_API_KEY`,
`digithings-local/DIGICLAW_DIGIKEY_API_KEY`,
`digithings-local/DIGIGRAPH_UPSTREAM_API_KEY`,
`digithings-local/DIGIKEY_ADMIN_TOKEN`,
`digithings-local/DIGIKEY_BFF_TOKEN`,
`digithings-local/DIGISEARCH_SEED_API_KEY`,
`digithings-local/E2E_BEARER_TOKEN`,
`digithings-local/MCP_EDGE_KEY`, plus `digithings/DIGIKEY_ADMIN_TOKEN` and
the `digithings` metadata entry. Local dev only (see
`~/.config/digithings/local-stack-secrets.yaml`). Never pushed to Origin,
GitHub, Cloudflare, or any repo.

## Access inventory (who holds what after the move)

- Chris: everything (namespace owner, Keychain holder, release-tag cutter,
  Buildkite org creator, Pages/Cloudflare account owner).
- DevOps Lead + digiquant seats: R2 deploy via the Mac `deploy` queue (no
  direct secret copies; short-lived job env only).
- UI seats: R3/R4 build on `ci` queue (no credentials); Claude UI review as today.
- Client-delivery seat: R6 folder-scoped (CODEOWNERS per client later).
- Agents: act as Chris (D-O4) — Origin rulesets and the optional tag gate are
  advisory/procedural, not hard controls. Seat instructions forbid cutting
  release tags; the audit log records every tag.
- Public contributors: R0 only, via DCO + GitHub-hosted CI; self-hosted
  runners never touch public repos (fork-PR execution risk).

## What this slice does NOT do (explicitly out of bounds)

No repo creation, no history push/filter-repo, no `wrangler secret put`, no
KV/R2 writes, no rotation, no `main` merge, no Cloudflare project
reconnection, no Pages domain move. The per-repo path manifest (file:line
couplings, exposure dates) stays on DIG-3518 documents, not in this public
repo (review.md G7). Follow-ups needing Chris go to him as decisions, not as
agent actions.
