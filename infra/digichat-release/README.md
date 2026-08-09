# digichat release Compose overlays

Install unit: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (not npm, not `:latest`).

| File | Purpose |
|---|---|
| `compose.digichat-release.yml` | Override root Compose digichat to **pull** GHCR |
| `compose.profile-a.yml` | Minimal Profile A (digigraph stack) |
| `compose.profile-b.yml` | Profile B digichat(+db) only (Foundry) |
| `.env.profile-a.example` | Env template for Profile A |
| `.env.profile-b.example` | Env template for Profile B |

## Image inventory (Profile A)

| Service | Source |
|---|---|
| digichat | **GHCR** `ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` |
| digichat-db | Public `postgres:16-alpine` |
| digikey-blocklist-redis | Public `redis:7-alpine` |
| litellm | Public `docker.litellm.ai/berriai/litellm:main-stable` |
| digikey / digigraph / digivault | **Build from monorepo** (`digi-*:latest`) — no GHCR tags yet |

v1 honesty: external clients who want Profile A (digigraph) still need a clone of this
monorepo to build the Python stack services. digichat Node itself must **not** require a
monorepo build — it always pulls the pinned GHCR image. Stack-service GHCR is a follow-up.

Optional: LiteLLM cache Redis via `--profile litellm-cache` and `REDIS_URL=redis://redis:6379`.

## Pull pinned digichat (monorepo operators)

From the repo root, with a published version (e.g. `0.9.3`):

```bash
make digichat-release-up VERSION=0.9.3
# or:
DIGICHAT_VERSION=0.9.3 docker compose \
  -f docker-compose.yml \
  -f infra/digichat-release/compose.digichat-release.yml \
  --profile digichat up -d
```

The overlay sets `image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` and clears the monorepo `build:` via Compose merge `build: !reset null` (Compose v2.24+ / v5).

Tear down: `make digichat-release-down VERSION=0.9.3`.

## Profile A — digigraph stack

Self-contained compose under this directory (paths `../..` → monorepo root). Flattened
profiles: one `up -d --build` brings digichat + db + digikey + digigraph + LiteLLM + digivault.

```text
Browser → digichat → digigraph → digillm/LiteLLM
                           └─ digivault_hub → digivault
```

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, provider keys

docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a up -d --build
```

Does **not** start digiquant / digisearch / digismith / heartbeat / observability.

## Profile B — Foundry (client Azure only)

digithings has **no Azure**. This snippet is for client environments (DataTap-like ACA /
Compose). Services: digichat (GHCR) + digichat-db only — no digigraph / digikey / LiteLLM.

```text
Browser → digichat → Foundry (DefaultAzureCredential on the host)
```

```bash
cp infra/digichat-release/.env.profile-b.example \
   infra/digichat-release/.env.profile-b
# edit AUTH_SECRET, AUTH_URL, DIGICHAT_EMBED_TENANTS (foundry backend)

docker compose -f infra/digichat-release/compose.profile-b.yml \
  --env-file infra/digichat-release/.env.profile-b up -d
```

Host must supply Azure identity for Foundry; do not put a Foundry API key in digichat env.

## Command matrix

| Goal | Command |
|---|---|
| Pull GHCR digichat (monorepo overlay) | `make digichat-release-up VERSION=0.9.3` |
| Tear down GHCR overlay | `make digichat-release-down VERSION=0.9.3` |
| Profile A (digigraph) | `docker compose -f infra/digichat-release/compose.profile-a.yml --env-file infra/digichat-release/.env.profile-a up -d --build` |
| Profile B (Foundry) | `docker compose -f infra/digichat-release/compose.profile-b.yml --env-file infra/digichat-release/.env.profile-b up -d` |
| Local monorepo build | `make up-digichat` |
| Client install guide | [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) |
| Populate client docs (offline) | [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../docs/digichat/CLIENT-DOCS-ONBOARD.md) |
| Post-publish smoke | [`docs/digichat/RELEASE-SMOKE.md`](../../docs/digichat/RELEASE-SMOKE.md) |
| Custom embed CSP hosts | [`INSTALL.md` § Custom embed parent hosts](../../docs/digichat/INSTALL.md#custom-embed-parent-hosts-csp) |

digithings’ own Tunnel host remains the operator path in
[`infra/digichat-digithings/`](../digichat-digithings/). Clients should prefer these overlays
and [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md).

Docs onboard (URL → digivault / digisearch) is an offline ops job beside Profile A —
see [`CLIENT-DOCS-ONBOARD.md`](../../docs/digichat/CLIENT-DOCS-ONBOARD.md) and
[`CLIENT_PIPELINES.md`](../../docs/ops/CLIENT_PIPELINES.md).

See also [`docs/digichat/RELEASE-SMOKE.md`](../../docs/digichat/RELEASE-SMOKE.md).
