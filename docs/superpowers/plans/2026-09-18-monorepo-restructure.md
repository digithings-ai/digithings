# Phase 0.1 — adopt the shadcn `next-monorepo` shape

**Goal.** Make the JS side of this repo literally match shadcn's
`template=next-monorepo`: shared libraries under `packages/`, applications under
`apps/`, one `components.json` convention per consumer, and a `npx shadcn add`
flow that lands parts in the shared package. This lands **before** the design
reference is frozen as canon (phase 0.2 = kit-wide logical CSS + RTL proof,
phase 0.3 = kit-level `cursor-pointer`), because every later rebuild task reads
paths and aliases from here.

**Evidence.** Full blast-radius inventory:
`/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/rebuild/inventory-paths-monorepo.md`
(produced from `wt-rebuild`, `origin/develop` @ `44ff6d109`).

## Corrected final mapping

| New path | From | Notes |
|---|---|---|
| `packages/ui` | `cloudflare/digiweb/web` | **the whole `@digithings/web` library** (≈30 subpath exports: `./ui`, `./styles/*`, chat, finance, data-layout …) — not just `src/ui` |
| `packages/design` | `cloudflare/digiweb/design` | `tokens.css`, `site/`, `releases.json`, `MANIFEST.json`? |
| `packages/digichat-ui` | `cloudflare/digichat-ui` | |
| `packages/brand`? | `cloudflare/digiweb/brand` | unmapped in the first draft — decision needed |
| `apps/digithings-web` | `cloudflare/digithings-web` | |
| `apps/digiquant-web` | `cloudflare/digiquant-web` | |
| `apps/dashboard` | `cloudflare/dashboard` | separate export into `dist/dashboard/`, `basePath: /dashboard` |
| `apps/reference` | `cloudflare/digiweb/reference` | the design canon |
| `apps/digichat` | `cloudflare/digichat` | out of scope for the rebuild, moved for consistency; nested `cli/` + `reference/` ride along (not workspaces) |
| `apps/digichat-cloudflare` / `apps/digithings-cron` / `apps/digithings-stack-cloudflare` | same names under `cloudflare/` | Workers — `apps/` vs a `workers/` tier is a decision |
| *(unchanged)* | `digigraph/ digiquant/ digikey/ digisearch/ digismith/ digiclaw/ digibase/ digivault/ digiskills/ …` | Python services are not part of this move |
| *(unchanged)* | `scripts/`, `.github/`, `docs/`, `Makefile` | scripts stay at root; their *contents* change |

`cloudflare/` does **not** fully dissolve: `scripts/build-manifest.mjs`, docs and
`MANIFEST.json` still reference it.

## Top 10 riskiest touchpoints (from the inventory)

1. Root `package.json` `workspaces` + `package-lock.json` — a manifest/lock mismatch fails `npm ci` in every JS lane.
2. `scripts/check_frontend_canon.py:179` runs `git ls-files cloudflare` — after the move it scans nothing and reports a **silent false green**.
3. Tailwind `@source` globs point outside each app (`apps/digithings-web` L54, dashboard L77, digiquant-web L44, reference L34, chatbot-shell L9, digichat L50) — build stays green, site renders unstyled.
4. `scripts/build-digithings.sh:47,53,120` and `scripts/build-digiquant.sh:39,67,93` — these are the **production Cloudflare Pages build commands**; a wrong workspace path breaks deploys, not just CI.
5. `.github/workflows/ci.yml:76-121` + `scripts/ci_paths.yaml` — app lanes silently skip; merges land untested.
6. `deploy-digithings-cloudflare.yml:9,39-41`, `deploy-digiquant-cloudflare.yml:9-12` — deploy build checks stop firing.
7. `release-please-config.json:6,16` + `.release-please-manifest.json:2` — releases stop or versions drift.
8. `Dockerfile.digichat-cloudflare:12-44`, `cloudflare/digichat/Dockerfile:9-34`, `docker-compose.yml:532` — image builds abort.
9. `apps/reference/next.config.mjs:7,17` `turbopack.root = join(here, "..")` — after the move it roots a different tree (OOM/behaviour change).
10. `dashboard/vitest.config.ts:39-40`, `digiquant-web/vitest.config.ts:15-16` — `../digiweb/web` alias becomes unresolvable.

## Cannot be changed by a commit (human steps)

- **Cloudflare Pages project settings**: root directory, build command (`bash scripts/build-*.sh`), output `dist`, `NODE_VERSION=22`, env vars (`NEXT_PUBLIC_SUPABASE_*`, `NEXT_PUBLIC_DIGICHAT_*`, `NEXT_PUBLIC_DASHBOARD_AUTH`), watch paths, production branch.
- **Worker identity**: `wrangler.toml` `name` / routes / `class_name` / DO migrations must stay byte-identical or live infra is orphaned; `wrangler secret put` binds to the name.
- **GitHub ruleset required-check job names** (renaming a job silently un-requires it).
- External: `twelve-x` dispatch, `ghcr.io/digithings-ai/digichat`, D1/Supabase/R2.

## Decisions this plan needs

1. **Package name**: keep `@digithings/web` (zero import churn) or rename to
   `@digithings/ui` (matches the template's `@workspace/ui`, ~4 apps + docs + tests
   touched, one mechanical commit)?
2. **Workers home**: `apps/` alongside the sites, a separate `workers/` tier, or stay
   under `cloudflare/` for now?
3. **`cloudflare/` end state**: dissolve entirely (brand → `packages/brand`, scripts
   and MANIFEST relocated) or keep a residual `cloudflare/` for non-JS assets?

## Order of operations (one atomic commit for the mechanical move)

1. `git mv` each workspace (history preserved), then update in the **same commit**:
   root `workspaces`, every `name`, every `@digithings/*` import if renaming, each
   app's `tsconfig` paths, `next.config.mjs` (`transpilePackages`,
   `outputFileTracingRoot`, `turbopack.root`), `vitest.config.ts` aliases,
   `components.json` aliases, all Tailwind `@source` globs, `functions/` mirroring.
2. Regenerate `package-lock.json`; prove `npm ci` on a clean checkout.
3. Update `scripts/*` (build-*, check_frontend_canon, ci_paths.yaml,
   project_routing.json, install-workspace, run_stack_local, Dockerfiles,
   docker-compose, release-please config).
4. Update `.github/workflows/**` paths/filters; **do not rename job names**.
5. Docs and agent rules: `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*`,
   `docs/**`, `agents.yml` + `make agents-init`, `docs/agent-skills/**`.
6. Verification: `npm ci` clean, canon guard (with a positive control that it
   actually scans the new paths), all four app builds, reference build, every
   test lane, `make test-baseline`, and a deploy dry-run of both Pages build scripts
   in a temp dir.
7. Human step: update the two Pages projects' build settings before merging.

## Rollback

Single branch (`feat/rebuild-sites-from-reference`) → the restructure is one
atomic commit (plus the lockfile); `git revert` restores the previous layout
without touching application code.
