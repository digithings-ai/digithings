# Pick 2: Stack-service GHCR — Gap Plan After #2023

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Pick 2 so clients run Profile A (digichat + digikey + digigraph + LiteLLM + digivault) by **pulling** GHCR images — no monorepo `docker compose build` for those services.

**Architecture:** [#2023](https://github.com/digithings-ai/digithings/pull/2023) already added a publish workflow + root Compose GHCR overlay. Remaining work glues that overlay into the digichat-release Profile A path, publishes the first GHCR packages (workflow is main-only), and documents pin/upgrade + config packaging so INSTALL no longer requires `--build`.

**Tech Stack:** GHCR (`ghcr.io/digithings-ai/{digikey,digigraph,digivault}`), Docker Compose overlays, Makefile targets, digichat release docs under `infra/digichat-release/` + `docs/digichat/INSTALL.md`.

**Related:** Parent self-host plan [`2026-08-09-digichat-self-hosted-release.md`](2026-08-09-digichat-self-hosted-release.md) Follow-up #3. Architecture gaps: [`docs/architecture/digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) §5. PR under review for this pick: [#2023](https://github.com/digithings-ai/digithings/pull/2023) (merged to **develop** 2026-08-09; **not** on `main` yet).

## Global Constraints

- Digi module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digillm`, `digithings`).
- Pick 2 does **not** change digichat CSP (Pick 1) or ingest pipelines (Pick 3).
- digichat keeps its own publish workflow (`publish-digichat-image.yml`); stack publish must not absorb digichat.
- Production pins: never `:latest` for client installs; prefer `DIGI_IMAGE_TAG=sha-<12>` (stack) and `DIGICHAT_VERSION` / `DIGICHAT_IMAGE_TAG=vX.Y.Z` (digichat).
- LiteLLM stays the public upstream image (`docker.litellm.ai/berriai/litellm:main-stable`) — digithings does **not** republish LiteLLM.
- Every shipping PR links a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`).

---

## 1. Validation of #2023 vs Pick 2 intent

**Verdict: partial** — publish + root overlay land the platform pieces; Profile A / INSTALL still require monorepo **build**, and GHCR packages do not exist until the workflow runs on `main`.

| Pick 2 requirement | #2023 status | Evidence |
|---|---|---|
| Publish digikey / digigraph / digivault to GHCR | **Workflow only** | `.github/workflows/publish-service-images.yml` builds those three (+ digiquant, digisearch, digismith, digiclaw). Tags: `:sha-<12>`, `:latest`, `:v<pyproject>`. |
| Images actually pullable today | **Fail (ops)** | `gh api orgs/digithings-ai/packages/container/{digikey,digigraph,digivault}` → **404**. digichat packages exist (`v0.9.3`). Workflow `on.push.branches: [main]`; #2023 merge target was **develop** only (`3345a577`). PR test plan still has “after merge to main: run Publish once”. |
| Compose overlay usable without monorepo **image** build | **Partial** | `infra/self-host/compose.ghcr.yml` + `make pull-ghcr` / `make up-ghcr` reset `build:` and set `image: ghcr.io/digithings-ai/<svc>:${DIGI_IMAGE_TAG:-latest}`. Still needs a **repo clone** for `docker-compose.yml`, `config/`, and `.env`. |
| Profile A / INSTALL path without monorepo build | **Fail (glue)** | `infra/digichat-release/compose.profile-a.yml` still `build:` digikey / digigraph / digivault. `INSTALL.md` and `infra/digichat-release/README.md` still say “clone + `--build`”. |
| Version pin compatible with digichat GHCR tags | **Pass (design)** | Separate vars: `DIGI_IMAGE_TAG` (stack) vs `DIGICHAT_IMAGE_TAG` / `DIGICHAT_VERSION` (digichat release-please). Documented in `compose.ghcr.yml` header + `docs/templates/self-host/README.md`. |
| LiteLLM handling | **Pass** | Not in publish matrix. Overlay leaves LiteLLM as `docker.litellm.ai/berriai/litellm:main-stable` (root compose). |
| Two overlays / glue | **Gap** | Root path: `docker-compose.yml` + `compose.ghcr.yml` (full stack; digivault behind `--profile digivault`). Client path: self-contained `compose.profile-a.yml` (minimal Profile A, still builds Python). No documented “Profile A = release compose + GHCR pins” recipe. |
| Conflict with Pick 1 (runtime CSP) | **None** | #2023 does not touch digichat CSP / `embed-hosts` / Next headers. digichat image publish remains separate. |
| Conflict with Pick 3 (ingest → digivault) | **None** | digivault image + `DIGIVAULT_URL` / `DIGIVAULT_ROOT` volume contracts unchanged. Ingest can target the same URL/volume once Profile A pulls GHCR digivault. |

### What #2023 *did* deliver (keep)

- Publish workflow for seven Python services (including Profile A’s three).
- Root GHCR overlay + Makefile `pull-ghcr` / `up-ghcr` / `up-ghcr-digichat`.
- Operator docs: `docs/DEPLOYMENT.md` § Pull from GHCR, `docs/templates/self-host/README.md`, `RELEASES.md` pointers.
- OpenAPI export/contracts (orthogonal to Pick 2; do not undo).

### What Pick 2 still needs (summary)

1. Images on GHCR (promote to `main` + first publish).
2. Profile A compose + INSTALL switched from **build** → **pull**.
3. Explicit glue between `infra/self-host/` and `infra/digichat-release/` (one recommended client command).
4. Honest remaining clone surface: `config/litellm.yaml` (+ digigraph config mount) until a config-bundle task (Task 4).

---

## File Structure (remaining work)

| File | Responsibility |
|---|---|
| `.github/workflows/publish-service-images.yml` | Already exists — run on `main` / `workflow_dispatch` (ops Task 1) |
| `infra/digichat-release/compose.profile-a.yml` | Switch digikey / digigraph / digivault to GHCR `image:` + `pull_policy`; drop `build:` |
| `infra/digichat-release/.env.profile-a.example` | Add `DIGI_IMAGE_TAG` (+ keep `DIGICHAT_VERSION`) |
| `infra/digichat-release/compose.profile-a.ghcr.yml` | Optional thin overlay if prefer keep build file for contributors — **prefer in-place edit of profile-a** (YAGNI: one file) |
| `infra/digichat-release/README.md` | Image inventory + command matrix: pull, not `--build` |
| `docs/digichat/INSTALL.md` | Profile A steps: pull GHCR stack; remove “must clone to build Python” honesty block (replace with pin story) |
| `docs/architecture/digichat-self-hosted-release.md` §5 | Mark stack GHCR gap addressed after Tasks 1–3 |
| `Makefile` | `digichat-profile-a-up` wrapping Profile A compose (no `--build`) |
| `docs/templates/self-host/README.md` | Cross-link Profile A minimal path vs full-stack `up-ghcr` |
| `infra/digichat-release/config/` *(Task 4)* | Vendored minimal `litellm.yaml` (+ note digigraph `DIGI_CONFIG_PATH`) so clients need no monorepo `config/` |

---

## 2. Gaps remaining after #2023

Ordered implementation tasks below. This is **not** merge-only: glue + first publish + doc honesty are required for Pick 2 intent.

---

### Task 1: First GHCR publish (ops gate)

**Files:**
- No code change required if `publish-service-images.yml` already on the commit promoted to `main`.
- Modify only if promote path needs a docs note: `RELEASES.md` (one line: “first publish after #2023”).

**Interfaces:**
- Consumes: Workflow on `main` (push path filter or `workflow_dispatch` with `service=all`).
- Produces: Pullable `ghcr.io/digithings-ai/{digikey,digigraph,digivault}:sha-*` / `:latest` / `:v0.1.0` (current pyproject versions).

- [ ] **Step 1: Confirm packages still missing**

```bash
for s in digikey digigraph digivault; do
  echo "== $s =="
  gh api "orgs/digithings-ai/packages/container/$s/versions" --jq '.[0].metadata.container.tags' \
    || echo "missing"
done
```

Expected today: missing / 404 for all three.

- [ ] **Step 2: Ensure workflow commit is on `main`**

```bash
git fetch origin
git merge-base --is-ancestor 3345a577 origin/main && echo on-main || echo NOT-on-main
```

If `NOT-on-main`: open/merge the normal `develop` → `main` promotion that includes #2023 (do **not** force-push). After merge:

```bash
gh workflow run "Publish: service images" --ref main -f service=all
gh run list --workflow=publish-service-images.yml --limit 3
```

Expected: run succeeds; packages exist.

- [ ] **Step 3: Verify pull**

```bash
docker pull ghcr.io/digithings-ai/digikey:latest
docker pull ghcr.io/digithings-ai/digigraph:latest
docker pull ghcr.io/digithings-ai/digivault:latest
# Prefer recording a sha pin from the run:
# DIGI_IMAGE_TAG=sha-<12-char-sha from workflow output>
```

Expected: pulls succeed (public package or after `docker login ghcr.io`).

- [ ] **Step 4: Commit** (only if RELEASES note added)

```bash
git add RELEASES.md
git commit -m "$(cat <<'EOF'
docs(root): note first stack GHCR publish after #2023

EOF
)"
```

**Acceptance:** `docker pull` works for digikey, digigraph, digivault. Without this task, Tasks 2–3 cannot smoke for real.

---

### Task 2: Profile A compose — pull GHCR instead of build

**Files:**
- Modify: `infra/digichat-release/compose.profile-a.yml`
- Modify: `infra/digichat-release/.env.profile-a.example`
- Modify: `Makefile` (add `digichat-profile-a-up` / `down`)

**Interfaces:**
- Consumes: `DIGI_IMAGE_TAG` (default pin documented; after Task 1 use a real `sha-…` or `v0.1.0`), `DIGICHAT_VERSION` for digichat.
- Produces: `docker compose -f infra/digichat-release/compose.profile-a.yml … up -d` with **no** `--build` and no `build:` keys on digikey / digigraph / digivault.

- [ ] **Step 1: Rewrite service image blocks in `compose.profile-a.yml`**

Replace the digikey / digivault / digigraph `build:` + local `image: digi-*:latest` blocks with GHCR pulls. Keep env, volumes, healthchecks, depends_on identical.

Header comment (replace the honesty block):

```yaml
# Profile A — minimal digigraph-backed digichat install
#
# Services: digichat (GHCR) + digichat-db + digikey (+ blocklist Redis) +
# digigraph + LiteLLM + digivault. Does NOT start digiquant / digisearch /
# digismith / heartbeat / observability.
#
# Pull path (no monorepo image build):
#   cp infra/digichat-release/.env.profile-a.example \
#      infra/digichat-release/.env.profile-a
#   # set DIGI_IMAGE_TAG + DIGICHAT_VERSION + secrets
#   docker compose -f infra/digichat-release/compose.profile-a.yml \
#     --env-file infra/digichat-release/.env.profile-a up -d
#
# Requires Compose that can resolve ${DIGI_IMAGE_TAG}. LiteLLM remains the
# public berriai image. config/ is still mounted from monorepo root until
# Task 4 vendors a minimal litellm.yaml under this directory.
```

digikey service (pattern for digivault + digigraph too):

```yaml
  digikey:
    image: ghcr.io/digithings-ai/digikey:${DIGI_IMAGE_TAG:-v0.1.0}
    pull_policy: always
    # … keep ports, env_file, environment, volumes, depends_on, healthcheck …
```

```yaml
  digivault:
    image: ghcr.io/digithings-ai/digivault:${DIGI_IMAGE_TAG:-v0.1.0}
    pull_policy: always
    # … unchanged env/volumes …
```

```yaml
  digigraph:
    image: ghcr.io/digithings-ai/digigraph:${DIGI_IMAGE_TAG:-v0.1.0}
    pull_policy: always
    # … unchanged env/volumes; keep DIGIVAULT_URL default http://digivault:8004 …
```

Leave `litellm` as:

```yaml
  litellm:
    image: docker.litellm.ai/berriai/litellm:main-stable
```

Leave digichat as:

```yaml
  digichat:
    image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION:?set DIGICHAT_VERSION e.g. 0.9.3}
    pull_policy: always
```

- [ ] **Step 2: Extend `.env.profile-a.example`**

Add near `DIGICHAT_VERSION`:

```bash
# Stack Python services (digikey / digigraph / digivault) — pin for production.
# Prefer sha-<12-char-git-sha> from the publish-service-images run that matches
# the release you tested. :latest is for smoke only.
DIGI_IMAGE_TAG=v0.1.0
```

- [ ] **Step 3: Makefile targets**

```makefile
.PHONY: digichat-profile-a-up digichat-profile-a-down
digichat-profile-a-up:
	@test -f infra/digichat-release/.env.profile-a || \
	  (echo "Copy .env.profile-a.example → .env.profile-a and set secrets"; exit 1)
	docker compose -f infra/digichat-release/compose.profile-a.yml \
	  --env-file infra/digichat-release/.env.profile-a up -d

digichat-profile-a-down:
	docker compose -f infra/digichat-release/compose.profile-a.yml \
	  --env-file infra/digichat-release/.env.profile-a down
```

Do **not** pass `--build`.

- [ ] **Step 4: Validate compose config (no network required for config resolve)**

```bash
export DIGICHAT_VERSION=0.9.3 DIGI_IMAGE_TAG=v0.1.0
export AUTH_SECRET=test DIGIKEY_BFF_TOKEN=test
docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a.example \
  config >/tmp/profile-a-ghcr.yml
rg -n 'ghcr.io/digithings-ai/(digikey|digigraph|digivault|digichat)|build:' /tmp/profile-a-ghcr.yml
```

Expected:
- digikey / digigraph / digivault / digichat images are `ghcr.io/digithings-ai/…`
- LiteLLM remains `docker.litellm.ai/…`
- No `build:` context for digikey / digigraph / digivault / digichat

- [ ] **Step 5: Commit**

```bash
git add infra/digichat-release/compose.profile-a.yml \
  infra/digichat-release/.env.profile-a.example Makefile
git commit -m "$(cat <<'EOF'
feat(digichat): Profile A pulls digikey/digigraph/digivault from GHCR

EOF
)"
```

---

### Task 3: Docs glue — INSTALL + release README + architecture gaps

**Files:**
- Modify: `docs/digichat/INSTALL.md` (Profile A section)
- Modify: `infra/digichat-release/README.md` (inventory + command matrix)
- Modify: `docs/templates/self-host/README.md` (cross-link Profile A)
- Modify: `docs/architecture/digichat-self-hosted-release.md` §5 Follow-ups

**Interfaces:**
- Consumes: Task 2 compose + env vars.
- Produces: One recommended client path; distinguishes full-stack `make up-ghcr` (includes digiquant etc.) from minimal Profile A.

- [ ] **Step 1: Replace INSTALL Profile A honesty block**

In `docs/digichat/INSTALL.md`, replace the “v1 honesty: … build from the monorepo” paragraph and `--build` command with:

```markdown
### Profile A — digigraph stack

```text
Browser → digichat → digigraph → digillm/LiteLLM
                           └─ digivault_hub → digivault
```

Pull **all** Profile A services from GHCR (digichat + digikey + digigraph + digivault).
LiteLLM uses the public berriai image. Pin stack and digichat tags separately:

| Variable | Example | Services |
|---|---|---|
| `DIGICHAT_VERSION` | `0.9.3` | digichat → `…/digichat:v0.9.3` |
| `DIGI_IMAGE_TAG` | `sha-<12>` or `v0.1.0` | digikey, digigraph, digivault |

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, DIGI_IMAGE_TAG, provider keys

make digichat-profile-a-up
# or:
docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a up -d
```

Does **not** start digiquant / digisearch / digismith / heartbeat / observability.

Until a config bundle ships (see stack-ghcr plan Task 4), this compose still mounts
`config/` from a digithings checkout for LiteLLM / digigraph. You need the **files**,
not a local image build.

Full monorepo stack (all Python services) alternative: [`docs/templates/self-host/README.md`](../templates/self-host/README.md) (`make up-ghcr` + `--profile digivault --profile digichat`).
```

- [ ] **Step 2: Update `infra/digichat-release/README.md` inventory**

```markdown
| Service | Source |
|---|---|
| digichat | **GHCR** `ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` |
| digichat-db | Public `postgres:16-alpine` |
| digikey-blocklist-redis | Public `redis:7-alpine` |
| litellm | Public `docker.litellm.ai/berriai/litellm:main-stable` |
| digikey / digigraph / digivault | **GHCR** `ghcr.io/digithings-ai/<svc>:${DIGI_IMAGE_TAG}` |
```

Command matrix row:

```markdown
| Profile A (digigraph, pull) | `make digichat-profile-a-up` |
| Full stack GHCR (monorepo overlay) | `make up-ghcr` (+ `--profile digichat --profile digivault`) |
```

Remove “no GHCR tags yet” / `--build` wording.

- [ ] **Step 3: Cross-link self-host template**

At end of `docs/templates/self-host/README.md`:

```markdown
## Minimal digichat Profile A

Clients who only need digichat + digikey + digigraph + LiteLLM + digivault should use
[`infra/digichat-release/`](../../../infra/digichat-release/) and
[`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md) — not the full-stack
`make up-ghcr` path (which also starts digiquant / digisearch / digismith by default).
```

- [ ] **Step 4: Mark architecture gap**

In `docs/architecture/digichat-self-hosted-release.md` §5:

- Profile A row: change “Remaining: digikey / digigraph / digivault still build…” → **Addressed:** GHCR pull via `compose.profile-a.yml` + `DIGI_IMAGE_TAG` (see INSTALL).
- Still-open Follow-ups: remove “GHCR for digikey / digigraph / digivault”; keep runtime CSP + ingest + CI smoke + Helm.

- [ ] **Step 5: Verify naming + links**

```bash
! rg -n '\bDigi(Chat|Graph|Key|Vault|Things)\b' docs/digichat/INSTALL.md infra/digichat-release/README.md
rg -n 'DIGI_IMAGE_TAG|digichat-profile-a-up|ghcr.io/digithings-ai/digikey' \
  docs/digichat/INSTALL.md infra/digichat-release/README.md
```

- [ ] **Step 6: Commit**

```bash
git add docs/digichat/INSTALL.md infra/digichat-release/README.md \
  docs/templates/self-host/README.md \
  docs/architecture/digichat-self-hosted-release.md
git commit -m "$(cat <<'EOF'
docs(digichat): Profile A install pulls stack services from GHCR

EOF
)"
```

---

### Task 4: Config packaging (reduce monorepo clone to optional)

**Why:** Even with GHCR images, Profile A mounts `../../config` for LiteLLM and digigraph. Pick 2 intent (“no monorepo clone/build”) is incomplete until clients can run from a small release directory.

**Files:**
- Create: `infra/digichat-release/config/litellm.yaml` (copy minimal production-safe subset from `config/litellm.yaml` — strip local-only Ollama Cloud hacks if they confuse clients; keep OpenRouter/Groq-shaped models clients actually need)
- Create: `infra/digichat-release/config/README.md` (what to edit; do not commit secrets)
- Modify: `infra/digichat-release/compose.profile-a.yml` volume paths: `./config:/app/config:ro` (relative to compose file dir)
- Modify: `docs/digichat/INSTALL.md` (clone no longer required for Profile A when using release dir alone)

**Interfaces:**
- Consumes: Existing `config/litellm.yaml` patterns; digigraph `DIGI_CONFIG_PATH=/app/config`.
- Produces: A client can copy `infra/digichat-release/` (+ `.env`) and `docker compose -f compose.profile-a.yml up -d` without the rest of the monorepo.

- [ ] **Step 1: Vendor minimal litellm config**

```bash
mkdir -p infra/digichat-release/config
# Start from repo config, then trim for Profile A clients:
cp config/litellm.yaml infra/digichat-release/config/litellm.yaml
```

Edit the copy so client docs say: set `OPENROUTER_API_KEY` / `GROQ_API_KEY` in `.env.profile-a`; no hardcoded secrets in the yaml.

Add `infra/digichat-release/config/README.md`:

```markdown
# Profile A config mount

Mounted read-only into LiteLLM and digigraph as `/app/config`.

- `litellm.yaml` — proxy models / timeouts. Edit locally; do not commit API keys.
- digigraph also reads this path (`DIGI_CONFIG_PATH`). Keep filenames stable.
```

- [ ] **Step 2: Point compose volumes at `./config`**

In `compose.profile-a.yml`, change:

```yaml
    volumes:
      - ./config:/app/config:ro
```

for both `litellm` and `digigraph` (replace `../../config`).

- [ ] **Step 3: Validate**

```bash
DIGICHAT_VERSION=0.9.3 DIGI_IMAGE_TAG=v0.1.0 AUTH_SECRET=t DIGIKEY_BFF_TOKEN=t \
  docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a.example config \
  | rg -n 'config:|/app/config'
```

Expected: bind source resolves under `infra/digichat-release/config`.

- [ ] **Step 4: Commit**

```bash
git add infra/digichat-release/config infra/digichat-release/compose.profile-a.yml \
  docs/digichat/INSTALL.md
git commit -m "$(cat <<'EOF'
feat(digichat): vendor Profile A litellm config for clone-free pull

EOF
)"
```

**Acceptance:** From a tarball/checkout of **only** `infra/digichat-release/` (+ Docker), Profile A config resolves. (Images still from GHCR after Task 1.)

---

### Task 5: End-to-end smoke (after Task 1 images exist)

**Files:**
- Modify: `docs/digichat/RELEASE-SMOKE.md` (add Profile A stack pull checklist subsection)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: Operator checklist proving Pick 2.

- [ ] **Step 1: Add smoke subsection to RELEASE-SMOKE.md**

```markdown
## Profile A stack pull (Pick 2)

1. [ ] `docker pull ghcr.io/digithings-ai/digikey:${DIGI_IMAGE_TAG}`
2. [ ] `docker pull ghcr.io/digithings-ai/digigraph:${DIGI_IMAGE_TAG}`
3. [ ] `docker pull ghcr.io/digithings-ai/digivault:${DIGI_IMAGE_TAG}`
4. [ ] `docker pull ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}`
5. [ ] `make digichat-profile-a-up` (no `--build`)
6. [ ] `curl -sf http://127.0.0.1:8005/healthz` (digikey)
7. [ ] `curl -sf http://127.0.0.1:8000/healthz` (digigraph)
8. [ ] `curl -sf http://127.0.0.1:8004/healthz` (digivault)
9. [ ] `curl -sf http://127.0.0.1:3005/api/health` (digichat)
10. [ ] Embed smoke: digigraph tool row (not direct OpenRouter from digichat)
```

- [ ] **Step 2: Run smoke locally (operator host)**

```bash
# with real .env.profile-a filled in
make digichat-profile-a-up
curl -sf http://127.0.0.1:8005/healthz && curl -sf http://127.0.0.1:8000/healthz \
  && curl -sf http://127.0.0.1:8004/healthz && curl -sf http://127.0.0.1:3005/api/health
```

Expected: all four health endpoints return success.

- [ ] **Step 3: Commit**

```bash
git add docs/digichat/RELEASE-SMOKE.md
git commit -m "$(cat <<'EOF'
docs(digichat): Profile A GHCR stack smoke checklist

EOF
)"
```

---

## 3. Fit with picks 1 and 3

| Contract | Owner | Pick 2 rule |
|---|---|---|
| digichat image / tags | Pick 1 + digichat release | **Independent.** Stack publish must not rebuild digichat. Runtime CSP (Pick 1) only changes digichat Node headers/env; Profile A keeps `DIGICHAT_VERSION` pins. |
| Allowed embed parents | Pick 1 | No change in this plan. INSTALL may still mention rebuild **until** Pick 1 ships; do not invent a stack workaround. |
| `DIGIVAULT_URL` | Profile A / digigraph | Keep default `http://digivault:8004` on digigraph. Pick 3 ingest **writes** into digivault (HTTP and/or `DIGIVAULT_ROOT` volume); must use the same URL/volume the running digivault container exposes. |
| digivault write scopes | digikey / digivault | Ingest (Pick 3) needs `digivault:write` (or equivalent) — orthogonal to image pull. Do not weaken auth in Pick 2. |
| Vault data volume | Compose `digivault_data` → `/data/vault` | Stable across GHCR digivault upgrades; Pick 3 should document writing into this volume or via note CRUD API — not into digichat. |
| Full-stack vs Profile A | Ops docs | `make up-ghcr` ≠ Profile A (extra services). Clients follow digichat-release; operators may use full overlay. |

**Conflicts:** none identified between #2023 / this gap plan and Pick 1 or Pick 3, provided digichat publish stays separate and digivault URL/volume contracts stay stable.

```text
Pick 1 (digichat CSP) ── stock digichat tag embeds any parent
Pick 2 (this plan)    ── same tag + pulled digikey/digigraph/digivault
Pick 3 (ingest)       ── fill digivault; digichat/digigraph unchanged
```

---

## Spec coverage self-check

| Requirement | Task |
|---|---|
| digikey/digigraph/digivault published + pullable | 1 |
| Profile A compose without monorepo build | 2 |
| INSTALL / README honesty + glue vs self-host overlay | 3 |
| Version pins compatible with digichat tags | 2, 3 (`DIGI_IMAGE_TAG` ≠ `DIGICHAT_VERSION`) |
| LiteLLM stays external pull | 2 (unchanged image) |
| Clone-free config for LiteLLM/digigraph | 4 |
| Smoke proving Pick 2 | 5 |
| No Pick 1 / Pick 3 conflicts | §3 |

## Placeholder scan

No TBD inside Tasks 1–5. Optional future work **not** in this plan: Helm/ACA, CI automation of RELEASE-SMOKE, publishing a digithings LiteLLM fork (explicitly rejected).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-09-digichat-stack-ghcr.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
**2. Inline Execution** — execute in-session with executing-plans checkpoints
