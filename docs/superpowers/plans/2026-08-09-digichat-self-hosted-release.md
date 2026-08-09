# digichat Self-Hosted Release / Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make digichat installable by clients as a pinned GHCR image plus Profile A (digigraph) or Profile B (Foundry) config — without cloning the monorepo or using a shared SaaS digichat.

**Architecture:** digithings ships versioned digichat releases (`digichat-vX.Y.Z` + `ghcr.io/digithings-ai/digichat:vX.Y.Z`). Clients pull that image and choose a backend adapter (`digigraph` | `foundry`). Profile A runs digichat + digikey + digigraph + LiteLLM + digivault; Profile B runs digichat (+ db) against Azure Foundry via managed identity. digithings.ai/chat remains digithings’ own Profile A install (Tunnel + Pages iframe), not multi-tenant SaaS.

**Tech Stack:** digichat Next.js BFF image (GHCR), Docker Compose overlays, digikey / digigraph / digillm→LiteLLM / digivault (Profile A), Azure Foundry + DefaultAzureCredential (Profile B), Markdown install docs.

**Spec input:** [`docs/architecture/digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) (authoritative product model + gaps). Complements [`digichat-modular-frontend.md`](../../architecture/digichat-modular-frontend.md) §5 and [`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md).

## Global Constraints

- Digi module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digillm`, `digithings`) — never DigiChat / DigiGraph.
- No live shared digichat SaaS for clients; digithings.ai/chat is digithings’ own install only.
- Primary install unit: pinned `ghcr.io/digithings-ai/digichat:vX.Y.Z` — never `:latest` for production; never npm (`private: true`).
- Adapters only: `digigraph` | `foundry`. digigraph owns digillm→LiteLLM and digivault tools.
- `DIGICHAT_EMBED_TENANTS` is **runtime-only** (never a Docker build-arg — tokens leak in layers).
- `DIGICHAT_EMBED_HOSTS` is non-secret hostnames; today baked at image build via `next.config.ts` → CSP `frame-ancestors`.
- digithings has **no Azure**; Profile B examples must stay client-side / Azure-free on digithings infra.
- Corpus / crawl / OCR / vault ingest is **out of scope for v1** — list under Follow-ups only.
- Every code/docs change that ships as a PR must link a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`).

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/architecture/digichat-self-hosted-release.md` | Product sketch (already written); link to this plan |
| `docs/digichat/INSTALL.md` | Client-facing install guide (Profile A + B, env checklist, smoke) |
| `docs/DEPLOYMENT.md` | Fix digithings.ai/chat drift → digichat Node + digigraph + Tunnel |
| `infra/digichat-release/compose.digichat-release.yml` | Pull pinned GHCR digichat image (no monorepo build) |
| `infra/digichat-release/compose.profile-a.yml` | Minimal Profile A overlay (digichat + db + digikey + digigraph + LiteLLM + digivault) |
| `infra/digichat-release/.env.profile-a.example` | Env template for Profile A |
| `infra/digichat-release/.env.profile-b.example` | Env template for Profile B (Foundry tenant JSON) |
| `infra/digichat-release/compose.profile-b.yml` | digichat(+db)-only snippet for Foundry clients |
| `infra/digichat-release/README.md` | Operator index for release overlays |
| `Makefile` | `digichat-release-up VERSION=…` wrapping release overlay |
| `frontend/digichat/OPERATIONS.md` | Link install guide; clarify GHCR vs local build |
| `docs/architecture/digichat-modular-frontend.md` §5 | Link to INSTALL.md |
| `frontend/digichat/embed-hosts.txt` | Documented rebuild path; optional client host notes |
| `.github/workflows/publish-digichat-image.yml` | Unchanged core; optional smoke checklist doc only in v1 |
| `docs/digichat/RELEASE-SMOKE.md` | Post-publish smoke checklist |

---

### Task 1: Release packaging — document identity + smoke checklist

**Files:**
- Create: `docs/digichat/RELEASE-SMOKE.md`
- Modify: `docs/architecture/digichat-self-hosted-release.md` (status line only if needed; already linked from plan)
- Modify: `frontend/digichat/OPERATIONS.md` (add short “Release artifacts” subsection linking RELEASE-SMOKE + INSTALL)

**Interfaces:**
- Consumes: Existing workflows `release-please-digichat.yml` (tag `digichat-vX.Y.Z` on develop) and `publish-digichat-image.yml` (GHCR on main). Current app version `0.9.3` in `frontend/digichat/package.json`.
- Produces: Documented release identity + operator smoke steps (no workflow changes in this task).

- [x] **Step 1: Confirm current release artifacts exist**

Run:

```bash
jq -r .version frontend/digichat/package.json
jq -r .private frontend/digichat/package.json
test -f .github/workflows/release-please-digichat.yml
test -f .github/workflows/publish-digichat-image.yml
head -20 frontend/digichat/CHANGELOG.md
```

Expected: version like `0.9.3`, `private` = `true`, both workflows present, CHANGELOG has `[0.9.3]` section.

- [x] **Step 2: Write RELEASE-SMOKE.md**

Create `docs/digichat/RELEASE-SMOKE.md` with this content (adjust version placeholder to current package.json):

```markdown
# digichat release smoke checklist

After `digichat-vX.Y.Z` is tagged (release-please on develop) and
`ghcr.io/digithings-ai/digichat:vX.Y.Z` is published (publish workflow on main):

## Identity

| Artifact | Value |
|---|---|
| Git tag | `digichat-vX.Y.Z` |
| GHCR image | `ghcr.io/digithings-ai/digichat:vX.Y.Z` |
| Changelog | `frontend/digichat/CHANGELOG.md` |
| Install unit | **GHCR image** — not npm (`private: true`) |

Prefer the version pin. Do not use `:latest` in production.

## Checklist

1. [ ] `docker pull ghcr.io/digithings-ai/digichat:vX.Y.Z`
2. [ ] `docker run --rm --entrypoint curl ghcr.io/digithings-ai/digichat:vX.Y.Z -sf http://127.0.0.1:3000/api/health`  
   (or start with required Auth env + db and `curl` host-mapped `/api/health`)
3. [ ] Embed smoke: Profile A tenant fixture (`backend.type: digigraph`) — tool rows + answer via digigraph (not direct OpenRouter from digichat)
4. [ ] Optional: Foundry smoke only when Azure credentials are available (CI secrets or local MI) — skip if unavailable

## Related

- Client install: [INSTALL.md](INSTALL.md)
- Product model: [digichat-self-hosted-release.md](../architecture/digichat-self-hosted-release.md)
```

- [x] **Step 3: Link from OPERATIONS.md**

At the top of `frontend/digichat/OPERATIONS.md` (after the title / intro), add:

```markdown
## Release artifacts

- Install digichat from GHCR (`ghcr.io/digithings-ai/digichat:vX.Y.Z`), not npm.
- Post-publish smoke: [`docs/digichat/RELEASE-SMOKE.md`](../../docs/digichat/RELEASE-SMOKE.md)
- Client / operator install: [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) (added in later task)
```

- [x] **Step 4: Verify docs render / links**

Run:

```bash
test -f docs/digichat/RELEASE-SMOKE.md
rg -n "ghcr.io/digithings-ai/digichat" docs/digichat/RELEASE-SMOKE.md
rg -n "Release artifacts" frontend/digichat/OPERATIONS.md
```

Expected: files exist; GHCR pin mentioned; OPERATIONS subsection present.

- [x] **Step 5: Commit**

```bash
git add docs/digichat/RELEASE-SMOKE.md frontend/digichat/OPERATIONS.md
git commit -m "$(cat <<'EOF'
docs(digichat): document release identity and smoke checklist

EOF
)"
```

---

### Task 2: Compose overlay — pull pinned GHCR digichat (no build)

**Files:**
- Create: `infra/digichat-release/compose.digichat-release.yml`
- Create: `infra/digichat-release/README.md`
- Modify: `Makefile` (add `digichat-release-up` / `digichat-release-down`)

**Interfaces:**
- Consumes: Root `docker-compose.yml` service names `digichat` / `digichat-db` for merge patterns OR a standalone digichat(+db) definition that does **not** use `build:`.
- Produces: Overlay that sets `image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` and disables local build.

- [x] **Step 1: Create release compose overlay**

Create `infra/digichat-release/compose.digichat-release.yml`:

```yaml
# Pull a published digichat image instead of building from the monorepo.
# Usage (from repo root, with DIGICHAT_VERSION set):
#   docker compose -f docker-compose.yml \
#     -f infra/digichat-release/compose.digichat-release.yml \
#     --profile digichat up -d
#
# Clients without the monorepo should prefer compose.profile-a.yml /
# compose.profile-b.yml (later tasks) which are self-contained.

services:
  digichat:
    image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION:?set DIGICHAT_VERSION e.g. 0.9.3}
    build: !reset null
    pull_policy: always
```

Notes for implementer:
- Confirm Compose file version / merge semantics on the machine (`docker compose config`). If `build: !reset null` is unsupported on the installed Compose, use an explicit override that replaces the service block without a `build:` key (document the chosen pattern in README).
- Do **not** put secrets in this file.

- [x] **Step 2: Write infra README stub**

Create `infra/digichat-release/README.md`:

```markdown
# digichat release Compose overlays

Install unit: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (not npm, not `:latest`).

| File | Purpose |
|---|---|
| `compose.digichat-release.yml` | Override root Compose digichat to **pull** GHCR |
| `compose.profile-a.yml` | Minimal Profile A (digigraph stack) — added in Task 3 |
| `compose.profile-b.yml` | Profile B digichat-only (Foundry) — added in Task 4 |
| `.env.profile-a.example` / `.env.profile-b.example` | Env templates |

See [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md).
```

- [x] **Step 3: Makefile targets**

In `Makefile`, add to `.PHONY` and body:

```makefile
# Pull published digichat from GHCR (requires DIGICHAT_VERSION=0.9.3).
digichat-release-up:
	@test -n "$(VERSION)" || (echo "Usage: make digichat-release-up VERSION=0.9.3"; exit 1)
	DIGICHAT_VERSION=$(VERSION) docker compose \
	  -f docker-compose.yml \
	  -f infra/digichat-release/compose.digichat-release.yml \
	  --profile digichat up -d

digichat-release-down:
	DIGICHAT_VERSION=$(VERSION:-0.0.0) docker compose \
	  -f docker-compose.yml \
	  -f infra/digichat-release/compose.digichat-release.yml \
	  --profile digichat down
```

Fix `VERSION:-` syntax if Make needs `VERSION?=0.0.0` — prefer:

```makefile
digichat-release-down:
	@test -n "$(VERSION)" || (echo "Usage: make digichat-release-down VERSION=0.9.3"; exit 1)
	DIGICHAT_VERSION=$(VERSION) docker compose \
	  -f docker-compose.yml \
	  -f infra/digichat-release/compose.digichat-release.yml \
	  --profile digichat down
```

- [x] **Step 4: Validate compose config (no pull required if offline)**

Run:

```bash
DIGICHAT_VERSION=0.9.3 docker compose \
  -f docker-compose.yml \
  -f infra/digichat-release/compose.digichat-release.yml \
  --profile digichat config 2>&1 | tee /tmp/digichat-release-config.yml
rg -n "ghcr.io/digithings-ai/digichat:v0.9.3" /tmp/digichat-release-config.yml
# Must NOT show a build context for digichat when overlay wins:
rg -n "digichat:" -A20 /tmp/digichat-release-config.yml | head -40
```

Expected: resolved image is GHCR pin; digichat service has no monorepo `build` context (or build is empty/null).

- [x] **Step 5: Commit**

```bash
git add infra/digichat-release/compose.digichat-release.yml \
  infra/digichat-release/README.md Makefile
git commit -m "$(cat <<'EOF'
feat(digichat): compose overlay to pull pinned GHCR image

EOF
)"
```

---

### Task 3: Profile A — minimal digigraph install path

**Files:**
- Create: `infra/digichat-release/compose.profile-a.yml`
- Create: `infra/digichat-release/.env.profile-a.example`
- Modify: `infra/digichat-release/README.md`
- Modify: `infra/digichat-digithings/README.md` (one paragraph pointing clients to release overlays; keep operator Tunnel path as digithings-specific)

**Interfaces:**
- Consumes: Existing service images / Dockerfiles for digikey, digigraph, LiteLLM, digivault from root Compose (or documented build-from-repo for stack services until those are also GHCR-published — digichat image is the primary client install unit; stack services may still build from source in v1 if no GHCR tags exist).
- Produces: Named minimal Profile A: digichat + digichat-db + digikey + digigraph + LiteLLM + digivault only (optional Redis via comment / profile).

- [x] **Step 1: Inventory which stack services already have pullable images**

Run:

```bash
rg -n "image:|build:" docker-compose.yml | head -80
```

Document in README:
- digichat → GHCR (Task 2)
- litellm → public `docker.litellm.ai/berriai/litellm:main-stable`
- digichat-db / digikey data → postgres / local volumes
- digikey / digigraph / digivault → if only `build:` exists today, Profile A overlay **builds those from repo** OR documents “clone monorepo for Profile A stack services until GHCR exists”. Prefer honesty: v1 Profile A for external clients who want digigraph may still need the monorepo for Python services; digichat Node itself must not require a monorepo build.

- [x] **Step 2: Write `.env.profile-a.example`**

```bash
# Profile A — digigraph-backed digichat
DIGICHAT_VERSION=0.9.3

AUTH_SECRET=replace-with-openssl-rand-base64-32
AUTH_URL=http://127.0.0.1:3005
AUTH_TRUST_HOST=true

DIGICHAT_POSTGRES_PASSWORD=digichat
DIGICHAT_AUTO_MIGRATE=1
DIGICHAT_EMBED_ENABLED=1

# Runtime registry — NEVER pass as Docker build-arg
DIGICHAT_EMBED_TENANTS={"example.com":{"slug":"example","gateMode":"ungated","activityDetail":"full","layout":"page","token":"replace-me","backend":{"type":"digigraph"}}}

DIGIGRAPH_INTERNAL_URL=http://digigraph:8000
DIGIKEY_URL=http://digikey:8005
DIGIKEY_BFF_TOKEN=replace-me

# On digigraph / LiteLLM host env (same compose project):
DIGIVAULT_URL=http://digivault:8004
# Provider keys for LiteLLM / digillm — see root .env.example
# OPENROUTER_API_KEY=...
# GROQ_API_KEY=...
```

- [x] **Step 3: Write `compose.profile-a.yml`**

Self-contained or monorepo-relative compose that:
1. Includes digichat from GHCR (`v${DIGICHAT_VERSION}`)
2. Includes digichat-db
3. Includes digikey, digigraph, litellm, digivault (profiles flattened so one `docker compose -f … up -d` brings Profile A)
4. Does **not** start digiquant / digisearch / digismith / heartbeat / observability unless commented as optional

Keep service wiring consistent with root `docker-compose.yml` (ports, healthchecks, `DIGIVAULT_URL` on digigraph). Prefer `extends` / include / copy-minimal — pick the pattern that `docker compose config` accepts; document it in README.

Acceptance shape:

```text
Browser → digichat → digigraph → digillm/LiteLLM
                           └─ digivault_hub → digivault
```

- [x] **Step 4: Validate config + document operator vs client**

Run:

```bash
# If overlay is monorepo-relative:
set -a && source infra/digichat-release/.env.profile-a.example && set +a
# (or export DIGICHAT_VERSION=0.9.3 and dummy secrets)
docker compose -f infra/digichat-release/compose.profile-a.yml config >/tmp/profile-a.yml
rg -n "ghcr.io/digithings-ai/digichat|digikey|digigraph|litellm|digivault|digiquant|digisearch" /tmp/profile-a.yml
```

Expected: digichat GHCR pin present; digikey/digigraph/litellm/digivault present; digiquant/digisearch absent (or clearly optional).

Update `infra/digichat-digithings/README.md` with:

```markdown
## Client / release installs

digithings’ Tunnel host is **this** operator path. Clients installing digichat
themselves should use [`infra/digichat-release/`](../digichat-release/) and
[`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) (Profile A or B).
```

- [x] **Step 5: Commit**

```bash
git add infra/digichat-release/compose.profile-a.yml \
  infra/digichat-release/.env.profile-a.example \
  infra/digichat-release/README.md \
  infra/digichat-digithings/README.md
git commit -m "$(cat <<'EOF'
feat(digichat): Profile A minimal digigraph compose overlay

EOF
)"
```

---

### Task 4: Profile B — Foundry-only docs + digichat-only snippet

**Files:**
- Create: `infra/digichat-release/compose.profile-b.yml`
- Create: `infra/digichat-release/.env.profile-b.example`
- Modify: `infra/digichat-release/README.md`

**Interfaces:**
- Consumes: digichat Foundry adapter (`backend.type: foundry`, `projectEndpoint`, `agentName`); host Azure identity via `DefaultAzureCredential`.
- Produces: Minimal digichat(+db) compose + env template. digithings remains Azure-free; snippet is for client Azure environments (DataTap-like).

- [ ] **Step 1: Write `.env.profile-b.example`**

```bash
# Profile B — Foundry-backed digichat (client Azure only; digithings has no Azure)
DIGICHAT_VERSION=0.9.3

AUTH_SECRET=replace-with-openssl-rand-base64-32
AUTH_URL=https://digichat.client.example
AUTH_TRUST_HOST=true

DIGICHAT_POSTGRES_PASSWORD=digichat
DIGICHAT_AUTO_MIGRATE=1
DIGICHAT_EMBED_ENABLED=1

# No DIGIGRAPH_* / DIGIKEY_* required.
# Tenant backend is Foundry — MI / DefaultAzureCredential on the host.
DIGICHAT_EMBED_TENANTS={"client.example.com":{"slug":"client","gateMode":"token","activityDetail":"full","layout":"page","token":"replace-embed-token","backend":{"type":"foundry","projectEndpoint":"https://YOUR_FOUNDRY_PROJECT.services.ai.azure.com/api/projects/YOUR_PROJECT","agentName":"YOUR_AGENT"}}}
```

- [ ] **Step 2: Write `compose.profile-b.yml`**

```yaml
# Profile B — digichat (+ Postgres) only. Backend = Foundry on the host identity.
# digithings does not run this. Clients mirror DataTap ACA pattern with Compose or ACA.

services:
  digichat-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: digichat
      POSTGRES_PASSWORD: ${DIGICHAT_POSTGRES_PASSWORD:-digichat}
      POSTGRES_DB: digichat
    volumes:
      - digichat_pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U digichat -d digichat"]
      interval: 5s
      timeout: 5s
      retries: 10

  digichat:
    image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION:?set DIGICHAT_VERSION}
    pull_policy: always
    ports:
      - "${DIGICHAT_PUBLISH_HOST:-127.0.0.1}:${DIGICHAT_PUBLISH_PORT:-3005}:3000"
    env_file:
      - ${DIGICHAT_ENV_FILE:-.env.profile-b}
    environment:
      NODE_ENV: production
      AUTH_TRUST_HOST: ${AUTH_TRUST_HOST:-true}
      DIGICHAT_DATABASE_URL: postgresql://digichat:${DIGICHAT_POSTGRES_PASSWORD:-digichat}@digichat-db:5432/digichat
      DIGICHAT_AUTO_MIGRATE: "1"
    depends_on:
      digichat-db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:3000/api/health"]
      interval: 20s
      timeout: 5s
      retries: 5
      start_period: 25s

volumes:
  digichat_pg:
```

Adjust healthcheck / curl availability to match the published image (same as root Compose). Document: host must provide Azure credentials for Foundry calls; no Foundry API key in digichat env.

- [ ] **Step 3: Validate compose config**

Run:

```bash
DIGICHAT_VERSION=0.9.3 docker compose \
  -f infra/digichat-release/compose.profile-b.yml \
  --env-file infra/digichat-release/.env.profile-b.example \
  config >/tmp/profile-b.yml
rg -n "ghcr.io/digithings-ai/digichat|digigraph|digikey|foundry" /tmp/profile-b.yml
```

Expected: digichat GHCR only (+ postgres); no digigraph/digikey services.

- [ ] **Step 4: README table update**

Ensure `infra/digichat-release/README.md` lists Profile B files and states digithings has no Azure / DataTap ACA is client-only.

- [ ] **Step 5: Commit**

```bash
git add infra/digichat-release/compose.profile-b.yml \
  infra/digichat-release/.env.profile-b.example \
  infra/digichat-release/README.md
git commit -m "$(cat <<'EOF'
docs(digichat): Profile B Foundry-only compose snippet

EOF
)"
```

---

### Task 5: Client install guide (INSTALL.md) + cross-links

**Files:**
- Create: `docs/digichat/INSTALL.md`
- Modify: `docs/architecture/digichat-modular-frontend.md` (§5 Near-term / End goal — link INSTALL)
- Modify: `frontend/digichat/OPERATIONS.md` (replace stub link if Task 1 left a forward ref)
- Modify: `docs/architecture/digichat-self-hosted-release.md` (link INSTALL under See also)

**Interfaces:**
- Consumes: Tasks 1–4 artifacts + config tables from the sketch §3.
- Produces: First-class client page: pull GHCR → choose A/B → env checklist → smoke.

- [ ] **Step 1: Write INSTALL.md**

Create `docs/digichat/INSTALL.md` covering:

1. **Product model** (short): self-hosted; no shared SaaS; digithings.ai/chat is digithings’ own install.
2. **Install unit:** `docker pull ghcr.io/digithings-ai/digichat:vX.Y.Z` — not npm.
3. **Profile A** steps pointing at `infra/digichat-release/compose.profile-a.yml` + `.env.profile-a.example`.
4. **Profile B** steps pointing at `compose.profile-b.yml` + Foundry tenant JSON.
5. **Env checklist** (always / A-only / B-only) copied from sketch §3.
6. **Embed CSP note:** stock GHCR uses `frontend/digichat/embed-hosts.txt`; new parent hosts need rebuild (Task 7) until runtime CSP exists.
7. **Smoke:** `/api/health`; embed with `host` + `token`; Profile A expects digigraph tool activity.
8. **Out of scope:** corpus ingest → “see Follow-ups in the architecture sketch”.

Include concrete smoke commands:

```bash
docker pull ghcr.io/digithings-ai/digichat:v0.9.3
curl -sf http://127.0.0.1:3005/api/health | jq .
# Embed (Profile A first-party style host query — clients always pass token):
# open http://127.0.0.1:3005/embed?host=client.example.com&token=…
```

- [ ] **Step 2: Cross-link**

In `digichat-modular-frontend.md` §5 after “Near-term foundation”, add:

```markdown
**Install guide:** [`docs/digichat/INSTALL.md`](../digichat/INSTALL.md)
```

In sketch See also + OPERATIONS, add the same link.

- [ ] **Step 3: Verify links**

Run:

```bash
rg -n "docs/digichat/INSTALL.md|INSTALL.md" \
  docs/architecture/digichat-modular-frontend.md \
  docs/architecture/digichat-self-hosted-release.md \
  frontend/digichat/OPERATIONS.md \
  infra/digichat-release/README.md
test -f docs/digichat/INSTALL.md
```

Expected: all four reference INSTALL; file exists.

- [ ] **Step 4: Commit**

```bash
git add docs/digichat/INSTALL.md \
  docs/architecture/digichat-modular-frontend.md \
  docs/architecture/digichat-self-hosted-release.md \
  frontend/digichat/OPERATIONS.md
git commit -m "$(cat <<'EOF'
docs(digichat): client self-hosted install guide

EOF
)"
```

---

### Task 6: Gap fix — DEPLOYMENT.md digithings.ai/chat drift

**Files:**
- Modify: `docs/DEPLOYMENT.md` (sections “Public domain routing”, “digithings.ai/chat — digichat marketing pane”, smoke for `/chat`)

**Interfaces:**
- Consumes: Truth from `infra/digichat-digithings/README.md` + ADR-0018 (iframe → digichat Node via Tunnel; digigraph path).
- Produces: DEPLOYMENT.md that no longer claims Pages Function + native digichat-ui OpenRouter loop for `/chat`.

- [ ] **Step 1: Locate stale claims**

Run:

```bash
rg -n "Pages Function|useStackChat|functions/api/chat|native @digithings/digichat-ui|OpenRouter" docs/DEPLOYMENT.md
```

- [ ] **Step 2: Replace public routing /chat sections**

Replace the Phase 3 “native digichat-ui + Pages Function” bullets with:

```markdown
## Public domain routing

One public domain serves marketing + chat shell:

- **Marketing shell:** `digithings.ai` — Cloudflare Pages (`frontend/digithings-web/`).
- **Visitor chat:** `digithings.ai/chat` — Pages iframe → digichat Node `/embed`
  (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`, e.g. Tunnel hostname `digichat.digithings.ai`).
  Backend: digichat → digigraph → digillm → LiteLLM (+ digivault tools).
- digithings has **no Azure**. DataTap digichat ACA is client-only.
- Operator runbook: [`infra/digichat-digithings/README.md`](../infra/digichat-digithings/README.md).
- Product model: [`docs/architecture/digichat-modular-frontend.md`](architecture/digichat-modular-frontend.md) §5.
- Client install: [`docs/digichat/INSTALL.md`](digichat/INSTALL.md).
```

Update “digithings.ai/chat — digichat marketing pane” to describe iframe + Tunnel + digigraph (retire Function/OpenRouter/Supabase copy). Update smoke: remove `POST https://digithings.ai/api/chat` Pages Function check; keep `GET /chat` shell + point operators to Tunnel origin `/api/health` and vault-grounded browser smoke from infra README.

- [ ] **Step 3: Verify no stale Function claims remain**

Run:

```bash
rg -n "functions/api/chat|useStackChat|CORE_SUPABASE|Pages Function.*chat" docs/DEPLOYMENT.md || true
rg -n "digigraph|Tunnel|INSTALL.md|digichat-digithings" docs/DEPLOYMENT.md
```

Expected: no live Function chat path as current truth; digigraph/Tunnel/install links present.

- [ ] **Step 4: Commit**

```bash
git add docs/DEPLOYMENT.md
git commit -m "$(cat <<'EOF'
docs(digichat): align DEPLOYMENT.md with digigraph Tunnel cutover

EOF
)"
```

---

### Task 7: Gap fix — embed-hosts / CSP rebuild path for clients

**Files:**
- Modify: `docs/digichat/INSTALL.md` (CSP subsection — expand)
- Modify: `frontend/digichat/ARCHITECTURE.md` (Environment variables / embed hosts — “client rebuild” note)
- Modify: `frontend/digichat/embed-hosts.txt` (header comment: how clients add hosts)
- Optional doc-only: `docs/digichat/EMBED-HOSTS-REBUILD.md` if INSTALL would get too long

**Interfaces:**
- Consumes: Build-arg `DIGICHAT_EMBED_HOSTS` in `frontend/digichat/Dockerfile` and publish workflow reading `embed-hosts.txt`. CSP evaluated at `next build` via `next.config.ts` importing `security-headers.ts`.
- Produces: Documented rebuild path for new parent domains. **Do not** implement runtime `frame-ancestors` in v1 unless a separate issue explicitly expands scope (sketch lists evaluate-runtime as optional).

- [ ] **Step 1: Document rebuild commands in INSTALL.md**

Add section:

```markdown
## Custom embed parent hosts (CSP)

The published GHCR image bakes `frame-ancestors` from
`frontend/digichat/embed-hosts.txt` at build time. If your parent site hostname
is not in that list, either:

1. Open a digithings PR to add the hostname to `embed-hosts.txt` (no secrets), or
2. Rebuild the image yourself:

```bash
docker build -f frontend/digichat/Dockerfile \
  --build-arg DIGICHAT_EMBED_HOSTS=your.example.com,www.your.example.com \
  -t digichat:custom .
```

Still set `DIGICHAT_EMBED_TENANTS` at **runtime** with tokens — never as a build-arg.
```

- [ ] **Step 2: Comment in embed-hosts.txt**

Extend the file header:

```text
# Plain hostnames for DIGICHAT_EMBED_HOSTS (build-time CSP frame-ancestors).
# No secrets — safe as a Docker build-arg. One hostname per line; # comments ignored.
# Clients with new parents: add a line here (PR) or rebuild with --build-arg
# DIGICHAT_EMBED_HOSTS=... — see docs/digichat/INSTALL.md § Custom embed parent hosts.
```

- [ ] **Step 3: ARCHITECTURE.md one-liner**

Under `DIGICHAT_EMBED_HOSTS` env row, add: “Stock GHCR image uses `embed-hosts.txt`; other parents need rebuild or a future runtime CSP change.”

- [ ] **Step 4: Verify**

Run:

```bash
rg -n "Custom embed parent hosts|rebuild" docs/digichat/INSTALL.md
rg -n "DIGICHAT_EMBED_HOSTS" frontend/digichat/Dockerfile
```

- [ ] **Step 5: Commit**

```bash
git add docs/digichat/INSTALL.md frontend/digichat/embed-hosts.txt frontend/digichat/ARCHITECTURE.md
git commit -m "$(cat <<'EOF'
docs(digichat): document embed-hosts CSP rebuild path for clients

EOF
)"
```

---

### Task 8: Wire Makefile release help + final acceptance pass

**Files:**
- Modify: `Makefile` (help comments near digichat targets)
- Modify: `infra/digichat-release/README.md` (end-to-end command matrix)
- Modify: `docs/architecture/digichat-self-hosted-release.md` §5 Gaps — mark items addressed vs remaining

**Interfaces:**
- Consumes: Tasks 1–7 deliverables.
- Produces: Single acceptance checklist an implementer can run before opening the PR.

- [ ] **Step 1: Acceptance checklist (run all)**

```bash
# Docs present
test -f docs/digichat/INSTALL.md
test -f docs/digichat/RELEASE-SMOKE.md
test -f infra/digichat-release/compose.digichat-release.yml
test -f infra/digichat-release/compose.profile-a.yml
test -f infra/digichat-release/compose.profile-b.yml

# Naming — no CamelCase Digi product names in new docs
! rg -n '\bDigi(Chat|Graph|Key|Vault|Things)\b' docs/digichat/ infra/digichat-release/ \
  || (echo "Fix Digi CamelCase in prose" && exit 1)

# Compose configs resolve
DIGICHAT_VERSION=0.9.3 docker compose \
  -f docker-compose.yml \
  -f infra/digichat-release/compose.digichat-release.yml \
  --profile digichat config >/dev/null

DIGICHAT_VERSION=0.9.3 docker compose \
  -f infra/digichat-release/compose.profile-b.yml config >/dev/null

# DEPLOYMENT drift cleared
! rg -n 'functions/api/chat\.ts' docs/DEPLOYMENT.md

# Cross-links
rg -n 'INSTALL.md' docs/architecture/digichat-modular-frontend.md
```

- [ ] **Step 2: Update sketch §5 Gaps table**

For each gap that this plan’s implementation closes, change Detail to “Addressed: see INSTALL.md / infra/digichat-release/ …” or strike through. Leave runtime CSP + stack-service GHCR + ingest as open if not done.

- [ ] **Step 3: Commit**

```bash
git add Makefile infra/digichat-release/README.md docs/architecture/digichat-self-hosted-release.md
git commit -m "$(cat <<'EOF'
docs(digichat): close self-hosted release acceptance gaps

EOF
)"
```

---

## Follow-ups (out of scope for v1)

Do **not** implement in this plan. File as separate `agent-task` issues later:

1. **Corpus / ingest pipelines** — crawl → PDF/OCR → digivault notes for client doc chatbots (modular-frontend §5 “Later”).
2. **Runtime `frame-ancestors`** — evaluate so stock GHCR works for new parents without rebuild (sketch gap).
3. **GHCR for digikey / digigraph / digivault** — so Profile A needs zero monorepo clone.
4. **CI release smoke** — automate RELEASE-SMOKE against GHCR after publish (Foundry optional via secrets).
5. **Helm / ACA stubs** beyond Compose Profile B — only if clients request.
6. **npm package** — explicitly never; keep `private: true`.

---

## Spec coverage self-check

| Spec requirement | Task |
|---|---|
| Primary install = pinned GHCR | 1, 2, 5 |
| Release identity tag + CHANGELOG | 1 |
| Compose pull overlay (not only build) | 2 |
| Makefile release target | 2, 8 |
| Profile A minimal digigraph path | 3 |
| Profile B Foundry snippet + docs | 4 |
| Client install guide | 5 |
| DEPLOYMENT.md drift | 6 |
| Embed hosts rebuild path | 7 |
| npm not an install path | 1, 5 (stated) |
| digithings.ai/chat = own install | 5, 6 |
| Corpus ingest later only | Follow-ups |

## Placeholder scan

No TBD / “implement later” inside Tasks 1–8. Follow-ups are explicitly deferred.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-09-digichat-self-hosted-release.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
**2. Inline Execution** — execute in-session with executing-plans checkpoints
