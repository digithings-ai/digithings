# digichat release smoke checklist

> **This checklist cannot be run as written.** The image publish workflow
> (`publish-digichat-image.yml`) was removed in the strict-essentials cut
> (`f54af7052`, #4919), so tagging a release no longer produces an image anywhere
> — `ghcr.io/digithings-ai/digichat` does not exist (verified 2026-10-06). Steps
> 1–2 below assume a published image; until the build lane is restored (DIG-1242)
> substitute a local build. The steps themselves — probe, health, embed, Foundry
> — remain correct for whatever image you built.

## Identity

| Artifact | Value |
|---|---|
| Git tag | `digichat-vX.Y.Z` |
| Published image | **none today** — build locally, or import to your own registry |
| Changelog | `apps/digichat/CHANGELOG.md` |
| Install unit | **a built image** — not npm (`private: true`) |
| Current app version | `2.4.0` (`apps/digichat/package.json` on `develop`) |

Existing clients (DataTap and others) run digichat images already imported into
their own Azure registry (`datatapchatregistry.azurecr.io`). Those copies are
unaffected by anything here.

Prefer a digest pin. Do not use `:latest` in production.

## Checklist

1. [ ] Build or import the image, and record its digest:
       `docker inspect --format '{{ index .RepoDigests 0 }}' <image>`
2. [ ] Confirm the image carries its source revision, then probe it:
       `docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' <image>`
       `docker run --rm --entrypoint curl <image> -sf http://127.0.0.1:3000/api/health`  
   (or start with required Auth env + db and `curl` host-mapped `/api/health`)
2b. [ ] Bind the image to the tag, per
       [`docs/ops/digichat-datatap-aca.md`](../ops/digichat-datatap-aca.md) §2.
3. [ ] Embed smoke: Profile A tenant fixture (`backend.type: digigraph`) — tool rows + answer via digigraph (not direct OpenRouter from digichat)
4. [ ] Optional: Foundry smoke only when Azure credentials are available (CI secrets or local MI) — skip if unavailable

## Profile A stack pull (Pick 2)

Requires stack images on GHCR (`DIGI_IMAGE_TAG` after `publish-service-images.yml` on `main`).

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

## Related

- Client install: [INSTALL.md](INSTALL.md)
- Product model: [digichat-self-hosted-release.md](../architecture/digichat-self-hosted-release.md)
