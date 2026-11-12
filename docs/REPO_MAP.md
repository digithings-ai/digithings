# Repository map

digithings is **eight repositories, not one**. Each repository owns itself: its
own CI, its own review, its own release, its own deploy. Nothing is a
subdirectory of anything else, and there is no umbrella checkout — the
pre-split monorepo was dissolved into these repositories and no longer exists.

This page is orientation only. A repository's own `README.md` is the source of
truth for what it builds and how it ships; this map does not restate those
details and does not grant access to any of the private repositories.

## The eight

| Id | Repository | Visibility | What it owns |
| --- | --- | --- | --- |
| **R0** | [`digithings`](https://github.com/digithings-ai/digithings) — *this repository* | public | The open-source core: the Python services (`digigraph`, `digiquant`, `digisearch`, `digikey`, `digitrace`, `digivault`, and the `digibase` / `digillm` / `digifetch` / `digiskills` / `digibot` / `digidev` / `digivoice` libraries), the digichat app and the digiweb design reference, the shared frontend packages under `packages/`, and the self-host stack. |
| **R1** | `digiquant-strategies` | private | Proprietary trading strategies and signals for the public `digiquant` engine. |
| **R2** | `digiquant-stack` | private | Proprietary digiquant backend: research pipeline, execution routing, data and broker adapters, desk API and database schema. |
| **R3** | `digiquant-web` | private | The digiquant.io site and the digiquant desk served under `/app`, as static exports. |
| **R4** | `digithings-web` | private | The digithings.ai site, the book and docs surfaces, and the brand kit. |
| **R5** | `digithings-stack` | private | The shared production platform: the Cloudflare Workers and the platform CI that a deploy runs through. |
| **R6** | `digichat-tenants` | private | Tenant content, seeds and config for hosted digichat deployments. |
| **R7** | *name withheld* | private | Confidential research automation. The name is withheld from the public tree — R0's private-terms guard rejects it — and the repository is not described further here. |

Only R0 is public. R1–R7 are named so that a reader of the public tree knows
where a component lives, not because they are installable or browsable from
here.

## How the public core and the private components meet

The private repositories depend on R0 through published artifacts, not through a
shared checkout:

- **Python** — R1 and R2 install a pinned, signed tag of their own distribution
  and import the public engine from the published `digi*` packages.
- **TypeScript** — the private frontends (R3, R4) render the shared
  `@digithings-ai/*` packages published on the public npm registry at exact
  versions.

That direction is deliberate: R0 publishes first, and a private repository pins
what it consumes. A change to R0 does not reach R1–R7 until they bump their pin.

## Why there is no monorepo

The repository layout used to be a single monorepo: every service, every
frontend, every private component and every deployable workflow in one tree.
That layout is gone. The split gives each repository one owner, one gate, one
release cadence, and keeps proprietary code and platform CI out of the public
tree.

Consequences worth knowing when reading older material:

- **A path that starts with another component's name is not a path in this
  repository.** `apps/digiquant-web/`, `cloudflare/*`, `scripts/local-ci/` and
  the platform workflows are R3/R4/R5 material.
- **This repository's CI is `.github/workflows/public-ci.yml`, and that is all
  of it.** Platform lanes, the merge queue and the local-ci gate live in R5.
- **Both static sites are built elsewhere.** digithings.ai comes from R4 and
  digiquant.io from R3; neither is built or deployed from this tree, and if you
  cannot find a build script here that is why.
- **Architecture decision records are historical.** ADRs under
  [`docs/adr/`](adr/) and older entries in [`docs/VISION.md`](VISION.md) that
  say "monorepo" are recording the world as it was when they were written. They
  are not updated to match the split; read them as dated records.

## Where to go next

| Question | Read |
| --- | --- |
| How do I work in this repository? | [`AGENTS.md`](../AGENTS.md), [`ONBOARDING.md`](../ONBOARDING.md) |
| What is in the R0 tree? | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| How do I self-host it? | [`docs/SELF_HOST.md`](SELF_HOST.md) |
| What deploys where? | [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) (R0-side view) |
| What did the split change? | [`docs/adr/`](adr/) |
