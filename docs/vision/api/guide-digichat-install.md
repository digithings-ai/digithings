---
title: "digichat install — guide"
type: reference
status: generated
created: 2026-10-02
tags:
  - api
  - guide
---
# digichat install

> Install digichat from a pinned GHCR release — Profile A (digigraph) vs Profile B (Foundry).

digithings ships **self-hosted** AI infra. Clients install digichat **releases from GitHub** and run them in their cloud or on-prem. There is no live shared digichat SaaS for clients. `digithings.ai/chat` is digithings' own install of the same product.

### Install unit

```bash
docker build -f apps/digichat/Dockerfile \
  --build-arg DIGICHAT_VERSION=2.4.0 \
  --build-arg DIGICHAT_REVISION="$(git rev-parse HEAD)" \
  -t digichat:2.4.0 .
```

- Git tag: `digichat-vX.Y.Z`
- Published image: not yet. The publish workflow is back and builds an image from each `digichat-vX.Y.Z` tag, but no tag after `digichat-v2.3.2` has been cut, so there is nothing published to pull. Until the next release, digichat builds from source.
- Changelog: `apps/digichat/CHANGELOG.md`
- Pin by digest once you publish the image yourself — do not rely on `:latest`.

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

Does not start digiquant / digisearch / digitrace / heartbeat. Full operator guide: `docs/digichat/INSTALL.md`. Minimal compose overlays live under `infra/digichat-release/`.

See also [[digichat]].
