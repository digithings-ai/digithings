# Repo split (G07)

Plan for splitting the digithings monorepo into one public repo and seven private repos,
with per-repo release branches and no Cloudflare deploys from `main`.
**Updated 2026-10-29:** private repos live on local Forgejo, and the single tenants repo (R6)
is replaced by one repo per client. See [below](#2026-10-29-client-repos-forgejo-homes-package-releases-d-c1--d-c13).

| File | What it is |
|---|---|
| [review.md](review.md) | Critical review of the 8-repo proposal. **Verdict: MODIFY** — topology agreed, mechanics changed. |
| [migration-plan.md](migration-plan.md) | Phased plan P0–P6: order of moves, per-repo recipe, validation, rollback, docs to update. |
| [client-template/](client-template/) | Generic skeleton for every `digithings-ai/<client-slug>` repo (reference copy of the Forgejo template). |
| [decisions.md](decisions.md) | Decision register: gate decisions for Chris, changed and unchanged recommendations. |
| [repo-split.mmd](repo-split.mmd) / [repo-split.png](repo-split.png) | Target topology after the modifications. |

The original proposal (with the file:line coupling inventory) and the per-path manifest are kept on
the tracking issue (DIG-3518), not in this public repo: they map where non-public files sit in history.

## Target repos

| # | Repo | Visibility | Role |
|---|---|---|---|
| R0 | `digithings` | public | OSS modules, SDKs, UI packages, digichat engine, MCP tooling |
| R1 | `digiquant-strategies` | private (Forgejo, was Origin) | proprietary strategies + optimiser (plugin) |
| R2 | `digiquant-stack` | private (Forgejo, was Origin) | production backend (runner, desk API, schema, pipeline) |
| R3 | `digiquant-web` | private (Forgejo, was Origin) | Brief desk + digiquant.io |
| R4 | `digithings-web` | private (Forgejo, was Origin) | digithings.ai, digibook, brand |
| R5 | `digithings-stack` | private (Forgejo, was Origin) | shared production platform (stack, digichat Worker, cron) |
| ~~R6~~ | ~~`digichat-tenants`~~ | superseded 2026-10-29 | one private `digithings-ai/<client-slug>` repo per client (D-C2) |
| R7 | `<client-slug>` (exists) | private (Origin) | client desk + digidata-api |

## Status

Gate decisions answered 2026-10-14 (Free plan, mono public until cutover, fresh R0, tags, self-hosted runners); plan revised to match. Later the same day Chris directed that the private repos live on **Cursor Origin**; the plan now covers that (Origin capabilities checked against Cursor's docs). D-O1, D-O2, D-O4, D-O5 answered the same day (R0 stays GitHub-primary, agents on Chris's account); D-O3 (Buildkite) STRUCK 23:36, runner is local-ci; D-G6 mandatory since 23:18. D-G5 / D-G6 answered 2026-10-14 17:40 CEST (deploys + CI on Chris's Mac under his normal user, Cloudflare Worker as fallback; signed tags mandatory, D-G6). Nothing has moved yet.

**Update 2026-10-29:** the private homes changed from Cursor Origin to Forgejo (digiforge), and per-client repos replace R6. See [2026-10-29: client repos, Forgejo homes, package releases](#2026-10-29-client-repos-forgejo-homes-package-releases-d-c1--d-c13). Client repos live in the Forgejo `digithings-ai` org, and the template repo `digithings-ai/client-template` exists there (naming revised 22:56, see [decisions.md](decisions.md)); no monorepo code has moved yet.

## 2026-10-29: client repos, Forgejo homes, package releases (D-C1 … D-C13)

Answered by the owner on 2026-10-29 (22:29 Rome). Full register: [decisions.md](decisions.md#client-repos-and-forgejo-homes--answered-2026-10-29);
phases: [migration-plan.md](migration-plan.md#client-repos-epic-2026-10-29-phases-c0c6).

- **All private repos live on local Forgejo** (digiforge), with a private GitHub backup
  pushed at releases. This replaces Cursor Origin as the private home (D-C1). R0 stays
  GitHub-primary (D-O1 unchanged).
- **R6 `digichat-tenants` is superseded** by one private `digithings-ai/<client-slug>` repo per client in the
  Forgejo `digithings-ai` org, created from the [`client-template`](client-template/) (D-C2, D-C4).
- **The client repo is the source of its tenant config**; its deploy writes the tenant doc
  to KV, which stays the runtime store (D-C3). Per Chris's decision of 2026-10-29, this reverses the earlier "KV only, no repo sync" ruling (refactor 1.7 in [migration-plan.md](migration-plan.md)) for client repos.
- **Packages:** Python modules release to PyPI as `digithings-<module>`, JS packages to npmjs
  `@digithings-ai/*`, at each promotion the owner approves; dev builds go to the Forgejo
  registry (D-C5, D-C6, D-C8).
- **Deploys:** option A (manual `make deploy-<env>`) now, option B (a Woodpecker job on a
  signed tag) once the gate is proven (D-C9). Agents may deploy a client's staging host;
  prod needs a tag signed by the owner (D-C11).
- **Client tooling is private:** a client's MCP server and all of its tooling move to its
  client repo (D-C10). Client repos start fresh, without history (D-C12).

### Client template

[`client-template/`](client-template/) is the reference copy of the template that every
`digithings-ai/<client-slug>` repo starts from. The live copy is the private Forgejo template repo
`digithings-ai/client-template`; this folder is kept in R0 because it is generic (an `example.com`
tenant, no client data), it documents the layout the repo-split plan depends on, and it
sits under `docs/` so the R0 workspaces, test paths and linters do not pick it up as code.
Changes land here first by pull request, then sync to Forgejo.

| Target repo map (after D-C2) | Home |
|---|---|
| R0 `digithings` | GitHub public (primary), Forgejo mirror for the local loop |
| R1–R5 | Forgejo (private) + private GitHub backup |
| ~~R6 `digichat-tenants`~~ | superseded by `digithings-ai/<client-slug>` repos |
| R7 (exists) | unchanged (hold stands); gets the template docs in place |
| `digithings-ai/client-template` | Forgejo template repo (private) |
| `digithings-ai/<client-slug>` | Forgejo (private) + private GitHub backup at releases |
