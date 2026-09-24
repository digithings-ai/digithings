# digichat release Compose overlays

Install unit: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (not npm, not `:latest`).

| File | Purpose |
|---|---|
| `compose.digichat-release.yml` | Override root Compose digichat to **pull** GHCR |
| `compose.profile-a.yml` | Minimal Profile A (digigraph stack) — **pull** GHCR (N images) |
| `compose.profile-a-bundle.yml` | Profile A **one stack image** (CF supervisord parity) + digichat |
| `compose.profile-b.yml` | Profile B digichat(+db) only (Foundry) |
| `.env.profile-a.example` | Env template for Profile A (multi-image) |
| `.env.profile-a-bundle.example` | Env template for Profile A bundle |
| `.env.profile-b.example` | Env template for Profile B |
| `config/` | Config mount for every profile: LiteLLM + digigraph + **digichat** |
| `config/digichat.yaml.example` | Starter deployment config — `cp` to `config/digichat.yaml` and edit |

## Image inventory (Profile A)

| Service | Source |
|---|---|
| digichat | **GHCR** `ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` |
| digichat-db | Public `postgres:16-alpine` |
| digikey-blocklist-redis | Public `redis:7-alpine` |
| litellm | Public `docker.litellm.ai/berriai/litellm:main-stable` |
| digikey / digigraph / digivault | **GHCR** `ghcr.io/digithings-ai/<svc>:${DIGI_IMAGE_TAG}` |

Pin stack and digichat tags separately (`DIGI_IMAGE_TAG` ≠ `DIGICHAT_VERSION`). Prefer
`DIGI_IMAGE_TAG=sha-<12>` or `v0.1.0` in production — never `:latest`.

Stack packages are published by [`publish-service-images.yml`](../../.github/workflows/publish-service-images.yml)
on `main` (after #2023). Until the first publish, `docker pull` for digikey /
digigraph / digivault will 404 — promote develop → main, then run the workflow.

Optional: LiteLLM cache Redis via `--profile litellm-cache` and `REDIS_URL=redis://redis:6379` in the env file. Leave `REDIS_URL` unset when Redis is not running — an empty value makes LiteLLM exit 3.

## Pull pinned digichat (monorepo operators)

From the repo root, with a published version (e.g. `1.0.0`):

```bash
make digichat-release-up VERSION=1.0.0
# or:
DIGICHAT_VERSION=1.0.0 docker compose \
  -f docker-compose.yml \
  -f infra/digichat-release/compose.digichat-release.yml \
  --profile digichat up -d
```

The overlay sets `image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` and clears the monorepo `build:` via Compose merge `build: !reset null` (Compose v2.24+ / v5).

Tear down: `make digichat-release-down VERSION=1.0.0`.

Existing clients (including DataTap) may keep `DIGICHAT_VERSION=0.9.3` —
`ghcr.io/digithings-ai/digichat:v0.9.3` stays on GHCR.

## The deployment config — one file per install

Every profile bind-mounts this directory at `/app/config` (read-only) and points
digichat at `/app/config/digichat.yaml`. That one YAML file is the install:
skin, chrome, gate, tools, MCP servers, and backend.

```bash
cp infra/digichat-release/config/digichat.yaml.example \
   infra/digichat-release/config/digichat.yaml
# edit it — the client's skin, title, welcome copy, gate, backend

make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml
# prints the resolved deployment(s); fails loudly on an invalid file
```

Validate **before** `up -d`. A missing file falls back silently — to the
`DIGICHAT_EMBED_TENANTS` registry when that is set, otherwise to the built-in dev
default. An invalid file fails the container at boot. `make
digichat-config-check` catches both (it reads the path you pass, not your `.env`,
so pass the file explicitly).

Three traps:

- **The mount replaces `/app/config`.** The image's baked
  `/app/config/examples/*` is *not* reachable in these profiles — copy any
  reference config you want into `config/`. For a catalog skin alone, set
  `DIGICHAT_CHROME_SKIN=<id>` instead of editing YAML. If you previously pointed
  `DIGICHAT_CONFIG_PATH` at a baked example, copy that file into `config/`
  first, or the path silently stops resolving.
- **Pick one shape — the env templates already set the other one.** Every
  `.env.profile-*.example` sets `DIGICHAT_EMBED_TENANTS` (hosts mode), and that
  merges *with* a `deployment:` block rather than replacing it. The
  `deployment:` block is what serves an unmatched host, so running the `cp`
  above while keeping that env var leaves an anonymous, ungated fallback install
  on your operator keys. Single client: delete `DIGICHAT_EMBED_TENANTS` from the
  env file. Many hostnames: use `hosts:` in the file and drop `deployment:`.

Full reference configs: [`apps/digichat/config/examples/`](../../apps/digichat/config/examples/).
Client-facing guide: [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md).

## Profile A — digigraph stack

Self-contained compose under this directory. Flattened profiles: one `up -d`
(no `--build`) brings digichat + db + digikey + digigraph + LiteLLM + digivault
from GHCR / public images. Config mounts from `./config` (vendored here).

```text
Browser → digichat → digigraph → digillm/LiteLLM
                           └─ digivault_hub → digivault
```

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS,
# DIGI_IMAGE_TAG, provider keys

make digichat-profile-a-up
# or:
docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a up -d
```

Does **not** start digiquant / digisearch / digismith / heartbeat / observability.

Full monorepo stack (all Python services) alternative: [`docs/templates/self-host/README.md`](../../docs/templates/self-host/README.md)
(`make up-ghcr` + `--profile digichat --profile digivault`).

## Profile A bundle — one stack image (Cloudflare parity)

Preferred **local** path for website digichat while CF backends use the same
Dockerfile (`Dockerfile.digithings-stack-cloudflare` + supervisord): digikey +
digigraph + digisearch + digivault + LiteLLM + Redis in **one** container.
digichat (+ Postgres) stay separate.

```text
Browser → digichat → digithings-stack:8000 (digigraph)
                  → digithings-stack:8005 (digikey)
                       └─ loopback digisearch / digivault / LiteLLM
```

```bash
# Stop monorepo N-container stack first if ports 8000/8005/3005 are taken
docker compose --profile digichat --profile digivault down   # from repo root

cp infra/digichat-release/.env.profile-a-bundle.example \
   infra/digichat-release/.env.profile-a-bundle
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_VERSION, GROQ_API_KEY, …

make digichat-profile-a-bundle-up
# tear down: make digichat-profile-a-bundle-down
```

Stack-only `docker run` (no digichat UI): see
[`apps/digithings-stack-cloudflare/README.md`](../../apps/digithings-stack-cloudflare/README.md).

| Goal | Prefer |
|---|---|
| Website digichat local / CF parity | **bundle** (`compose.profile-a-bundle.yml`) |
| Client install with per-service GHCR pins | multi-image (`compose.profile-a.yml`) |
| digiquant / full monorepo | root `docker-compose.yml` |

### Chat-only digigraph (no digiquant)

Profile A digigraph is **research_rag only**. The stack image ships
`config/digiproject.yaml` and sets:

- `DIGI_PROJECT_CONFIG=/app/config/digiproject.profile-a-local.yaml` (stock
  local/self-host — no D1, so `allowed_tools` omits `digivault_get_note`; the
  D1-backed Cloudflare stack overrides this to `digiproject.yaml`, which includes it)
- `DIGI_WORKFLOW_PROFILE=research_rag`
- `DIGI_ALLOWED_TOOLS=digisearch,digivault_search_notes` (fallback only — read
  solely when the project config above fails to load; kept in sync with
  whichever `digiproject*.yaml` is actually mounted, not a separate default)
- `DIGIQUANT_URL=` (empty)

digichat probes only digigraph (`DIGICHAT_ENABLED_SERVICES=digigraph`). OCC and
website chat must never surface `DIGIQUANT_DATA_DIR` errors.

**Local JSON env:** Docker's env-file parser strips unescaped `"` inside
`DIGICHAT_EMBED_TENANTS` / `DIGI_TENANT_CORPUS_MAP`. Prefer single-quoting those
values in `.env.profile-a-bundle`, or use
`compose.profile-a-bundle.override.yml` (YAML-quoted JSON + optional
`digi-digichat:local`). `make digichat-profile-a-bundle-up` includes the override
when that file exists.

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
| Pull GHCR digichat (monorepo overlay) | `make digichat-release-up VERSION=1.0.0` |
| Tear down GHCR overlay | `make digichat-release-down VERSION=1.0.0` |
| Profile A (digigraph, pull) | `make digichat-profile-a-up` |
| Profile A bundle (1 stack image + digichat) | `make digichat-profile-a-bundle-up` |
| Full stack GHCR (monorepo overlay) | `make up-ghcr` (+ `--profile digichat --profile digivault`) |
| Profile B (Foundry) | `docker compose -f infra/digichat-release/compose.profile-b.yml --env-file infra/digichat-release/.env.profile-b up -d` |
| Local monorepo build | `make up-digichat` |
| Validate the deployment config | `make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml` |
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
