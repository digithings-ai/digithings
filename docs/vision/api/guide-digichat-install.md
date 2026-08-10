---
title: "digichat install — guide"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - guide
---
# digichat install

> Install digichat from a pinned GHCR release — Profile A (digigraph) vs Profile B (Foundry).

digithings ships **self-hosted** AI infra. Clients install digichat **releases from GitHub** and run them in their cloud or on-prem. There is no live shared digichat SaaS for clients. `digithings.ai/chat` is digithings' own install of the same product.

### Install unit

```bash
docker pull ghcr.io/digithings-ai/digichat:v0.9.3
```

- Git tag: `digichat-vX.Y.Z`
- GHCR image: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (currently published through `v0.9.3`)
- Changelog: `frontend/digichat/CHANGELOG.md`
- Pin a published tag — do not assume a version exists on GHCR until the digichat release workflow has published it from `main`.

### Profiles

- **A — digigraph stack** — digichat + db + digikey + digigraph + LiteLLM + digivault. Adapters: digigraph owns digillm→LiteLLM and digivault.
- **B — Azure AI Foundry** — digichat + db only (`DefaultAzureCredential`). For client Azure environments; digithings has no Azure.

### Profile A (digigraph)

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, DIGI_IMAGE_TAG, provider keys

make digichat-profile-a-up
```

Does not start digiquant / digisearch / digismith / heartbeat. Full operator guide: `docs/digichat/INSTALL.md`. Minimal compose overlays live under `infra/digichat-release/`.

See also [[digichat]].
