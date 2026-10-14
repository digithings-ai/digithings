# R5 `digithings-stack` — tracked file inventory

This file lists the tracked paths that R5 takes over, as measured. It is generated from
`git ls-tree`; no list here is transcribed by hand.

- Ticket: DIG-3566. The decisions and findings live in that ticket's `plan` document.
- Measured at `d227b6ed526202aaa095b8e645804ef308dde813` (`github/develop`).
- Regenerate and check with the two commands in the last section of this file.

Counts are printed beside every list. Where a section splits a tree into destinations,
the parts are listed with their own counts and the parts sum to the total.

## A. Package inventory — exact tracked file lists

### A.1 `apps/digithings-stack-cloudflare` — 57 files

Sub-split: `container/` **30**, `src/` **21**, root **6** (control: sum = 57).

**→ R5: 47 files. → R6: 10 files** — the OCC seed carve-out, confirmed as
`container/seed/occ_help/` (6) + `container/seed/vault/clients/online-compliance-center/` (4).

R5 also keeps the remaining 24-file `container/seed/` tree.

```
.gitignore
README.md
container/entrypoint.sh
container/searxng/limiter.toml
container/seed/digithings_docs/architecture.md
container/seed/digithings_docs/chat-faq.md
container/seed/digithings_docs/digikey-auth.md
container/seed/digithings_docs/digisearch-rag.md
container/seed/digithings_docs/digivault-notes.md
container/seed/digithings_docs/overview.md
container/seed/digithings_docs/showcase.md
container/seed/occ_help/faq-documents.md
container/seed/occ_help/faq-getting-started.md
container/seed/occ_help/faq-overview.md
container/seed/occ_help/faq-policies.md
container/seed/occ_help/manual-portal.md
container/seed/occ_help/manual-search.md
container/seed/vault/clients/digithings/seed-architecture.md
container/seed/vault/clients/digithings/seed-chat-faq.md
container/seed/vault/clients/digithings/seed-digikey-auth.md
container/seed/vault/clients/digithings/seed-digisearch-rag.md
container/seed/vault/clients/digithings/seed-digivault-notes.md
container/seed/vault/clients/digithings/seed-overview.md
container/seed/vault/clients/digithings/seed-showcase.md
container/seed/vault/clients/online-compliance-center/seed-documents.md
container/seed/vault/clients/online-compliance-center/seed-getting-started.md
container/seed/vault/clients/online-compliance-center/seed-overview.md
container/seed/vault/clients/online-compliance-center/seed-policies.md
container/seed_chroma.sh
container/start_digikey.sh
container/start_digisearch.sh
container/supervisor/supervisord.conf
package.json
src/container-bind.test.js
src/container-booting-503.test.js
src/container-errors.ts
src/container-evicted-410.test.js
src/dashboard-api-mount.test.js
src/dashboard-api.ts
src/digichat-mount.test.js
src/digichat.ts
src/env-vars-pin.test.js
src/fixtures/price-GLD.parquet
src/index.ts
src/market-data.e2e.test.js
src/market-data.test.ts
src/market-data.ts
src/ports.test.ts
src/ports.ts
src/public-routes.test.js
src/route-modules.ts
src/stack-isolation.test.js
src/wake-readiness.test.js
src/zammad-mcp-route.test.js
tsconfig.json
vitest.config.ts
wrangler.toml
```

### A.2 `apps/digichat-cloudflare` — 12 files · **→ R5 (all)**

Worker `digithings-digichat`, one container, `DIGICHAT` Durable Object.

```
.gitignore
README.md
package.json
src/embed-flag.test.ts
src/embed-flag.ts
src/env-vars-pin.test.ts
src/index.ts
src/paths.test.ts
src/paths.ts
tsconfig.json
vitest.config.ts
wrangler.toml
```

### A.3 `apps/digitrace-langfuse` — 11 files · **→ R5 (all)**

```
.gitignore
README.md
docker-compose.local.yml
package.json
src/env-vars-pin.test.ts
src/index.ts
src/paths.test.ts
src/paths.ts
tsconfig.json
vitest.config.ts
wrangler.toml
```

### A.4 `apps/digithings-cron` — 39 files · **→ R5 (all)**

```
.gitignore
README.md
package.json
scripts/check-app-install.mjs
src/backfill-do.test.ts
src/backfill-do.ts
src/backfill-route.test.ts
src/backfill.test.ts
src/backfill.ts
src/counter-do.test.ts
src/counter-do.ts
src/deployed-triggers.test.ts
src/deployed-triggers.ts
src/dispatch.test.ts
src/dispatch.ts
src/env.ts
src/et-open.test.ts
src/et-open.ts
src/expected.test.ts
src/expected.ts
src/house-run-watch.test.ts
src/house-run-watch.ts
src/index.test.ts
src/index.ts
src/jobs.test.ts
src/jobs.ts
src/probe.test.ts
src/probe.ts
src/required-triggers.ts
src/trigger-alarm.test.ts
src/trigger-alarm.ts
src/trigger-contract.test.ts
src/trigger-contract.ts
src/twelvex-watch.test.ts
src/twelvex-watch.ts
src/wrangler-config.ts
tsconfig.json
vitest.config.ts
wrangler.toml
```

### A.5 Root Dockerfiles owned by R5 — 4 files

6 tracked Dockerfiles sit at the repository root; the 4 below are the ones R5 owns. The
other 2 (`Dockerfile.digillm`, `Dockerfile.digiquant-runner`) stay where they are.

| File | Destination |
|---|---|
| `Dockerfile.digichat-cloudflare` | R5 root |
| `Dockerfile.digithings-stack-cloudflare` | R5 root |
| `Dockerfile.digitrace-langfuse-web` | R5 root |
| `Dockerfile.digitrace-langfuse-worker` | R5 root |

One Dockerfile R5 needs but does not own is named in `plan` section B.1.

### A.6 `infra/` — 22 files · **→ R5 (19) + 2 inferred + 1 contested**

The count is **22**. An earlier revision of the plan said 19; `infra/` grew after
that revision was written. The section is part of finding F16.

Destination split: the 19 `digichat-*` files are R5; the 2 `self-host/**` files read as R5
only by inference from decision D-R5-2, which that decision marks inferred; `local-proxy/`
(1 file) is unassigned and is carried as open item H7.

```
digichat-digithings/README.md
digichat-release/.env.profile-a-bundle.example
digichat-release/.env.profile-a.example
digichat-release/.env.profile-b.example
digichat-release/README.md
digichat-release/compose.digichat-release.yml
digichat-release/compose.profile-a-bundle.override.yml
digichat-release/compose.profile-a-bundle.yml
digichat-release/compose.profile-a.yml
digichat-release/compose.profile-b.yml
digichat-release/config/README.md
digichat-release/config/byok-providers.json
digichat-release/config/digichat.yaml.example
digichat-release/config/digiproject.profile-a-local.yaml
digichat-release/config/digiproject.yaml
digichat-release/config/examples/README.md
digichat-release/config/litellm.yaml
digichat-release/config/model-policy.json
digichat-release/config/model_modes.yaml
local-proxy/Caddyfile
self-host/compose.ghcr.yml
self-host/routine-watch/com.digithings.routine-watch.plist
```

### A.7 `scripts/` — R5-owned

`scripts/` holds 221 tracked files in total, so it is not an inventory section: R5 takes the
groups below, not the directory.

| Group | Count | Destination |
|---|---|---|
| `scripts/zammad_mcp/` | 10 | R5 (decision D-R5-3) |
| OCC rollout guards | 6 | R5 (finding F13) |
| Self-host parity | 2 | R5 (decision D-R5-2); they read R0 `config/self-host/**` (finding F9) |
| `merge_litellm_cheaperinference.py` | 1 | R5 |

The OCC rollout guard paths at this ref:

- `check_occ_rollout_auth_guard.py`
- `occ_invite_key_fixture_server.mjs`
- `occ_invite_key_rollout.sh`
- `test_occ_rollout_scope_guard.sh`
- `test_verify_occ_invite_key.sh`
- `verify_occ_invite_key.sh`

`config/` for R5 is three files; the full list is in `plan` section A.7.

### A.8 `docs/ops/` — 35 files (full list)

This directory is not all runbooks: it also holds a Grafana tree, an OTel collector
config, two `.sql` files and three data files. The triage is in `plan` section E.2.

```
2026-10-06-d8c5-restart-root-cause.md
2026-10-06-stranded-branch-triage.tsv
2026-10-06-stranded-work-and-backup-report.md
2026-10-06-t2-branch-decisions.md
CLIENT_PIPELINES.md
HOUSE_BOOK_SCOPE.md
OCC_INVITE_KEY.md
SECRETS_INVENTORY.md
SECRETS_ROTATION.md
agent-state-errorreason-clearing.md
branch-hygiene-policy.md
checkpoint-archive-vacuum.md
core-postgres-uri-secret.md
credential-ownership.md
cutoff_inception_20260717.sql
datatap-azure-az-guard.md
digichat-aca-secret-fingerprints.json
digichat-datatap-aca.md
digifetch-post-deploy-verification.md
digiquant-digikey-service-key.md
digiquant-runner.md
digithings-cron.md
digitrace-langfuse.md
gloomberb-session-cookie.md
grafana/dashboards/digithings-overview.json
grafana/provisioning/dashboards/default.yml
grafana/provisioning/datasources/prometheus.yml
local-deploy-parity.md
otel/otel-collector-config.yaml
paperclip-routine-watch.md
policy-check-credential.md
prometheus/prometheus.yml
restatement_20260623_20260907.sql
supabase-exit-twelve-x-cutover-runbook.md
vectorize-cutover.md
```

## B. How to regenerate and check this file

```sh
python3 docs/repo-split/verify_r5_inventory.py . HEAD docs/repo-split/R5-inventory.md
```

The verifier re-derives each `### A.` list from git and compares it as a set. It prints
the measured count beside the claimed count, so a stale claim cannot hide behind a
matching list. It exits 0 when every list is exact and 1 on any mismatch.
