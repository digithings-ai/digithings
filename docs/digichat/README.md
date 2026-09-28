# digichat docs — index

Start here. Single version source: `apps/digichat/package.json` (currently `2.3.2`,
corroborated by `.release-please-manifest.json` and `apps/digichat/CHANGELOG.md`).
Any other version number in these guides is drift — fix it, don't work around it.

## In this folder

| Doc | Read it when |
|---|---|
| [`SKIN-GALLERY.md`](SKIN-GALLERY.md) | Doing any digichat UI work — the `/baseline` gallery is the single surface for all skin iteration |
| [`INSTALL.md`](INSTALL.md) | Installing self-hosted digichat from the pinned GHCR image (profiles A/B, config, CSP) |
| [`RELEASE-SMOKE.md`](RELEASE-SMOKE.md) | After a `digichat-v*` publish — GHCR pull, `/api/health`, embed smoke |
| [`ONBOARDING.html`](ONBOARDING.html) | Operator visual onboard (open in a browser) |
| [`CLIENT-DOCS-ONBOARD.md`](CLIENT-DOCS-ONBOARD.md) | Running the offline docs-onboard pipeline (`scripts/docs_onboard/`) for client-doc grounding |
| [`DESIGN-THEMES.md`](DESIGN-THEMES.md) | Theming the official assistant-ui Thread with digiweb CSS variables (contract: `packages/ui/CHAT_THEME.md`) |
| [`STOCK-SMOKE.md`](STOCK-SMOKE.md) | Manually checking the stock product path after assistant-ui slices |

## Elsewhere (canonical homes)

- Product + BFF: [`apps/digichat/ARCHITECTURE.md`](../../apps/digichat/ARCHITECTURE.md),
  [`apps/digichat/AGENTS.md`](../../apps/digichat/AGENTS.md) (pre-flight checklist),
  [`apps/digichat/OPERATIONS.md`](../../apps/digichat/OPERATIONS.md),
  [`apps/digichat/CONTROLS.md`](../../apps/digichat/CONTROLS.md),
  [`apps/digichat/README.md`](../../apps/digichat/README.md)
- UI ownership plan (Part B workstreams WS1–WS6):
  [`../architecture/digichat-ui-ownership.md`](../architecture/digichat-ui-ownership.md)
- Self-hosted release architecture:
  [`../architecture/digichat-self-hosted-release.md`](../architecture/digichat-self-hosted-release.md)
- Config program plan:
  [`../architecture/digichat-config-program-plan.md`](../architecture/digichat-config-program-plan.md)
- ADRs: [`0018`](../adr/0018-digichat-path-routing.md) path routing,
  [`0027`](../adr/0027-opencode-digichat-cli-foundation.md) CLI foundation,
  [`0028`](../adr/0028-digichat-web-foundation-and-opencode-distribution.md) web foundation,
  [`0029`](../adr/0029-secrets-management.md) secrets management

## Deliberately out of scope here

Historical plans under `docs/superpowers/plans/` and dated notes under `docs/reviews/`
are point-in-time records — read them as history, don't update them to current versions.
`docs/openapi/digichat.json` carries its own API spec version (not the app version).
`packages/design/releases.json` is owned by the design-release feed.
