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
| Current app version | `0.9.3` (`frontend/digichat/package.json`) |

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
