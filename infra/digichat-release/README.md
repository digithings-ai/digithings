# digichat release Compose overlays

Install unit: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (not npm, not `:latest`).

| File | Purpose |
|---|---|
| `compose.digichat-release.yml` | Override root Compose digichat to **pull** GHCR |
| `compose.profile-a.yml` | Minimal Profile A (digigraph stack) — added in Task 3 |
| `compose.profile-b.yml` | Profile B digichat-only (Foundry) — added in Task 4 |
| `.env.profile-a.example` / `.env.profile-b.example` | Env templates |

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

See [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) (added in a later task) and [`docs/digichat/RELEASE-SMOKE.md`](../../docs/digichat/RELEASE-SMOKE.md).
