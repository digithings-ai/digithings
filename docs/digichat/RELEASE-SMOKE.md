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
| Current app version | `1.0.0` (`frontend/digichat/package.json`) |

`ghcr.io/digithings-ai/digichat:v0.9.3` remains on GHCR for existing clients
(DataTap and others). Do not delete or retag it.

Prefer the version pin. Do not use `:latest` in production.

## Checklist

1. [ ] `docker pull ghcr.io/digithings-ai/digichat:vX.Y.Z`
2. [ ] `docker run --rm --entrypoint curl ghcr.io/digithings-ai/digichat:vX.Y.Z -sf http://127.0.0.1:3000/api/health`  
   (or start with required Auth env + db and `curl` host-mapped `/api/health`)
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
