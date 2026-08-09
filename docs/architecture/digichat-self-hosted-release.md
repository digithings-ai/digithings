# digichat self-hosted release / install shape

> Design sketch — how digithings ships digichat so **clients host their own**
> installs. Complements [`digichat-modular-frontend.md`](digichat-modular-frontend.md)
> §5 (product model) and the digithings operator runbook
> [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

**Status:** Sketch (2026-08-09) — Gaps in §5 updated for Tasks 1–8 of the implementation plan  
**Related:** [ADR-0018](../adr/0018-digichat-path-routing.md), [`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md)  
**Naming:** Digi module names are always lowercase in prose.

## Implementation plan

Bite-sized tasks (release packaging → Profile A/B → install guide → gap fixes):  
[`docs/superpowers/plans/2026-08-09-digichat-self-hosted-release.md`](../superpowers/plans/2026-08-09-digichat-self-hosted-release.md)

---

## Product model (authoritative)

| Claim | Meaning |
|---|---|
| digithings = **self-hosted AI infra** | Clients install digichat **releases from GitHub** and run them in **their** cloud / on-prem. |
| No shared SaaS digichat | There is **no** live digichat all clients point at. |
| digithings.ai/chat | digithings’ **own** install of the same product (optional operator host + Tunnel), not multi-tenant SaaS. |
| Same pattern as DataTap | Client-hosted digichat Node + **their** backend (Foundry **or** digigraph stack). |
| digichat | Modular frontend + BFF + adapters (`digigraph` \| `foundry`). digigraph owns digillm → LiteLLM → OpenRouter and digivault as tools. |
| Future doc demos | Client install + corpus ingest into **their** digivault — not a digichat fork. |

**Hard rule:** scale by shipping a clean release + adapters + configurable digigraph/digivault modules. Custom work is env, secrets, and ingest — not a second chat app.

---

## 1. Release artifacts

### Today (what exists)

| Artifact | Status | Notes |
|---|---|---|
| **Git tag** `digichat-vX.Y.Z` | Exists | [release-please-digichat.yml](../../.github/workflows/release-please-digichat.yml) on `develop`; changelog in `frontend/digichat/CHANGELOG.md`. Current app version: `0.9.3` (`private: true` in package.json). |
| **GHCR image** `ghcr.io/digithings-ai/digichat:vX.Y.Z` (+ `:latest`) | Exists | [publish-digichat-image.yml](../../.github/workflows/publish-digichat-image.yml) on `main` when `frontend/digichat/**` changes; skips if that version tag already published. Build-arg `DIGICHAT_EMBED_HOSTS` from `frontend/digichat/embed-hosts.txt` (CSP `frame-ancestors` only — no secrets). |
| **npm package for digichat Node** | Does **not** exist | App is `private: true`; clients do not `npm install digichat`. |
| **`@digithings/digichat-ui`** | Workspace / site embed | Shared React UI for marketing shells and digichat itself — **not** the self-host install unit. |
| **Compose local image** `digi-digichat:latest` | Dev / operator | Root `docker-compose.yml` **builds** from repo context; does not pull GHCR by default. |
| **DataTap path** | Client-side (out of repo) | Pulls same GHCR image into client Azure (ACA); GHCR→ACR mirror is a **manual** client ops step (documented in phase plans, not a digithings workflow). |

### Target (what we want operators / clients to use)

1. **Primary install unit:** pinned GHCR image `ghcr.io/digithings-ai/digichat:vX.Y.Z` (never rely on `:latest` for production).
2. **Release identity:** GitHub Release / tag `digichat-vX.Y.Z` + CHANGELOG (already the release-please signal).
3. **Optional:** thin Compose / Helm / ACA snippets that **pull** that image + declare env — not a requirement to clone the monorepo.
4. **Not primary:** cloning the monorepo and `docker compose build` (fine for digithings operators and contrib; wrong default for clients).
5. **Not an install path:** publishing digichat Node to npm.

```text
release-please (develop) → digichat-vX.Y.Z tag + CHANGELOG
promote to main          → publish-digichat-image → ghcr.io/.../digichat:vX.Y.Z
client / digithings ops  → pull image + set env + choose profile A or B
```

---

## 2. Minimal install profiles

Two supported shapes. Same digichat image; different backends and deps.

### Profile A — digithings-shaped digigraph stack

**Who:** digithings’ own `/chat` host; clients who want digigraph + digillm + digivault (doc chatbot, vault-grounded agents).

```text
Browser / parent site iframe
  → digichat Node (/embed or full app)
       → digigraph (DIGIGRAPH_INTERNAL_URL)
            → digillm → LiteLLM → OpenRouter (or other providers)
            → digivault_hub → digivault (DIGIVAULT_URL on digigraph)
```

**Minimum services**

| Service | Role |
|---|---|
| digichat + digichat-db | BFF + optional conversation / key store |
| digikey | JWT / BFF session for digigraph |
| digigraph | Orchestration brain |
| LiteLLM (+ provider keys) | Via digillm |
| digivault | Vault tool behind digigraph (when grounded chat matters) |

Optional: digisearch, digiquant, digismith, Redis (LiteLLM cache) — only if the deploy needs those tools / health surfaces.

**digithings operator path today:** Compose profiles `digichat` + `digivault` (+ `litellm-cache` as needed) and Cloudflare Tunnel — see [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md). Public marketing URL stays `digithings.ai/chat` (Pages shell + iframe); digichat Node may be `digichat.digithings.ai` (Tunnel). digithings has **no Azure**.

### Profile B — Foundry-only client

**Who:** Azure clients (e.g. DataTap pattern) whose brain is Azure AI Foundry, not digigraph.

```text
Browser / parent site iframe
  → digichat Node (/embed)
       → Foundry adapter (managed identity / DefaultAzureCredential)
```

**Minimum services**

| Service | Role |
|---|---|
| digichat (+ digichat-db if persistence / machine keys needed) | BFF + embed |
| Azure identity + Foundry project | Backend; configured per tenant in `DIGICHAT_EMBED_TENANTS` |

No digigraph, digikey, LiteLLM, or digivault required on the client box. digithings does **not** host this; DataTap ACA stays client-only.

---

## 3. Config surface (what operators must set)

### Build-time (image / CSP)

| Variable | Required | Notes |
|---|---|---|
| `DIGICHAT_EMBED_HOSTS` | For embed CSP | Comma-separated parent hostnames. Safe as Docker build-arg. Published GHCR image uses `embed-hosts.txt` (includes digithings + DataTap hosts). Client-specific parents not in that list need a **rebuild** or a client-built image with their hosts — gap today. |

### Runtime — always (both profiles)

| Variable | Purpose |
|---|---|
| `AUTH_SECRET` / `AUTH_URL` / `AUTH_TRUST_HOST` | Auth.js |
| `DIGICHAT_DATABASE_URL` | Postgres (recommended; Compose wires digichat-db) |
| `DIGICHAT_AUTO_MIGRATE=1` | Apply Drizzle migrations on start |
| `DIGICHAT_EMBED_ENABLED` / embed gating | As needed for `/embed` |
| `DIGICHAT_EMBED_TENANTS` | **Runtime JSON registry** — hostname → branding, gate, `activityDetail`, `token`, `backend`. **Never** a Docker build-arg (tokens in layers). |

Illustrative registry shape (see ARCHITECTURE.md for full schema):

```json
{
  "client.example.com": {
    "slug": "client",
    "gateMode": "ungated",
    "activityDetail": "full",
    "layout": "page",
    "token": "<required-secret>",
    "backend": { "type": "digigraph" }
  }
}
```

Foundry tenant: `"backend": { "type": "foundry", "projectEndpoint": "https://…", "agentName": "…" }` (plus Azure MI on the host). digithings tenants: `backend.type: digigraph` only.

First-party digithings hosts (`digithings.ai` / `www.digithings.ai`) may skip embed token when registered; **customer** embeds always need a matching `token`.

### Runtime — Profile A only

| Variable | Purpose |
|---|---|
| `DIGIGRAPH_INTERNAL_URL` | digigraph base |
| `DIGIKEY_URL` + `DIGIKEY_BFF_TOKEN` | Preferred upstream auth (or `DIGIGRAPH_UPSTREAM_API_KEY`) |
| On digigraph: `DIGIVAULT_URL`, LiteLLM / digillm provider keys | Vault tool + LLM path |

### Runtime — Profile B only

| Surface | Purpose |
|---|---|
| Tenant `backend.type: foundry` + endpoint / agent | Wired in `DIGICHAT_EMBED_TENANTS` |
| Host Azure identity | Foundry calls via `DefaultAzureCredential` — no Foundry API key in digichat env |

### Parent site (marketing / product shell)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` | Iframe origin (e.g. Tunnel hostname) |
| Embed URL | `/embed?host=<parent-host>&token=…` (token omitted only for first-party digithings) |

---

## 4. What digithings ships vs what stays per-client

### digithings ships (product / repo)

1. digichat UI + BFF + adapters (`digigraph` \| `foundry`)
2. Versioned GHCR image + git tags / CHANGELOG
3. digigraph → digillm → LiteLLM + digivault-as-tool modules (for Profile A)
4. Tenant **config shape** (`DIGICHAT_EMBED_TENANTS`) and embed activity contract
5. Operator runbooks and (target) client install snippets for profiles A and B
6. digithings’ **own** optional public install (digithings.ai/chat) as a reference deployment — not a client endpoint

### Per-client (their install)

1. Where digichat runs (Compose, ACA, k8s, VM + Tunnel, …)
2. Backend choice and secrets (digigraph stack vs Foundry MI)
3. Parent hostnames, embed tokens, branding / gate / `activityDetail`
4. Corpus and ingest into **their** digivault (crawl → PDF/OCR → notes) — same digichat release, different vault content
5. GHCR→private registry mirror if required (e.g. ACR) — client ops, not digithings CI

---

## 5. Gaps vs current repo

| Gap | Detail |
|---|---|
| ~~**No client-facing install guide**~~ | **Addressed:** [`docs/digichat/INSTALL.md`](../digichat/INSTALL.md) — pull GHCR + Profile A/B + env checklist + smoke. Linked from modular-frontend §5 and OPERATIONS.md. |
| ~~**Compose builds, does not pull**~~ | **Addressed:** [`infra/digichat-release/compose.digichat-release.yml`](../../infra/digichat-release/compose.digichat-release.yml) overlays root Compose to `image: ghcr.io/digithings-ai/digichat:v…`. |
| ~~**Makefile is local-dev shaped**~~ | **Addressed:** `make digichat-release-up VERSION=…` / `digichat-release-down` (see Makefile digichat help block + [`infra/digichat-release/README.md`](../../infra/digichat-release/README.md) command matrix). |
| **`DIGICHAT_EMBED_HOSTS` baked into published image** | **Documented rebuild path:** INSTALL.md § Custom embed parent hosts + `embed-hosts.txt` header. **Remaining:** runtime `frame-ancestors` so stock GHCR works for new parents without rebuild (Follow-ups). |
| ~~**Docs drift**~~ | **Addressed:** [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md) aligns digithings.ai/chat with digigraph + Tunnel (no live Pages Function chat path). |
| ~~**No Foundry-only Compose snippet**~~ | **Addressed:** [`compose.profile-b.yml`](../../infra/digichat-release/compose.profile-b.yml) + `.env.profile-b.example` (digithings stays Azure-free). |
| ~~**Profile A “minimal” not named**~~ | **Addressed:** [`compose.profile-a.yml`](../../infra/digichat-release/compose.profile-a.yml) + GHCR pull via `DIGI_IMAGE_TAG` (see INSTALL). **Ops remaining:** first `publish-service-images.yml` run on `main` so packages exist. |
| ~~**npm confusion risk**~~ | **Addressed:** INSTALL.md + RELEASE-SMOKE state install unit = GHCR image, not npm (`private: true`). |

### Still open (Follow-ups — not v1)

- Runtime CSP `frame-ancestors`
- ~~GHCR for digikey / digigraph / digivault~~ — **Addressed** in compose/INSTALL (`DIGI_IMAGE_TAG`); packages land after promote to `main` + publish workflow
- Corpus / crawl / OCR / vault ingest pipelines
- CI automation of RELEASE-SMOKE
- Helm / ACA stubs beyond Compose Profile B

---

## 6. Suggested next implementation issues

Short backlog (file as separate `agent-task` issues; no epic required):

- **Docs: client install page** — “Pull `ghcr.io/digithings-ai/digichat:vX.Y.Z`, Profile A vs B, env checklist, smoke.” Link from modular-frontend §5 and OPERATIONS.md.
- **Fix DEPLOYMENT.md digithings.ai/chat** — Align with digigraph + Tunnel cutover; retire Pages Function copy.
- **Compose overlay: pull GHCR** — e.g. `compose.digichat-release.yml` with `image:` pin + env file template (no monorepo build context).
- **Compose overlay: Profile A minimal** — digichat + db + digikey + digigraph + LiteLLM + digivault only; document optional profiles.
- **CSP / embed hosts for clients** — Document rebuild-with-`DIGICHAT_EMBED_HOSTS` **or** evaluate runtime frame-ancestors strategy so stock GHCR works for new parent hosts without republishing secrets.
- **Makefile target** — `digichat-release-up VERSION=0.9.3` (or similar) wrapping the release overlay.
- **Profile B snippet** — Minimal digichat-only deploy example (Compose or ACA stub) + Foundry tenant JSON; point at DataTap as reference, keep digithings Azure-free.
- **Release smoke checklist** — After each `digichat-v*` publish: GHCR pull, `/api/health`, embed smoke for digigraph tenant fixture (and Foundry if credentials available in CI secrets — optional).

---

## See also

- Client install: [`docs/digichat/INSTALL.md`](../digichat/INSTALL.md)
- Product end-state: [`digichat-modular-frontend.md`](digichat-modular-frontend.md) §5
- digithings operator host: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md)
- Path routing: [ADR-0018](../adr/0018-digichat-path-routing.md)
- Env / embed schema: [`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md) § Embed tenant registry, § Environment variables
- Local ops: [`frontend/digichat/OPERATIONS.md`](../../frontend/digichat/OPERATIONS.md)
- Release smoke: [`docs/digichat/RELEASE-SMOKE.md`](../digichat/RELEASE-SMOKE.md)
