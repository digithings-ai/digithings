# Review — PR #4501 `feat(digichat): drive a release install from one digichat.yaml`

- **Subject:** PR [#4501](https://github.com/digithings-ai/digithings/pull/4501) — branch `task/4500-digichat-config-driven-release` (tracking issue #4500)
- **Reviewed revision:** `27ec4efac` (original head); fixes landed in `912ff3b08`
- **Reviewer:** fresh-context read-only subagent (`general`, delegation `lively-golden-tiger`), 2026-09-22T21:03:39Z → 21:05:27Z. The author session did not review its own work.
- **Verdict:** APPROVE WITH NITS
- **Severity counts:** 0 blocker / 1 major / 3 minor / 3 nit

## What the change does

Makes the release install "install the image, edit one YAML file": every release
profile bind-mounts `./config:/app/config:ro` into the digichat service and
defaults `DIGICHAT_CONFIG_PATH` to `/app/config/digichat.yaml`; a documented
starter ships at `infra/digichat-release/config/digichat.yaml.example`; and
`make digichat-config-check` validates a config and prints the resolved
deployment(s) without secrets.

## Findings

### F1 — MAJOR: the documented recipe leads into the anonymous-fallback trap

`infra/digichat-release/config/digichat.yaml.example:20` ships a `deployment:`
block, and `infra/digichat-release/README.md:63` tells the reader to
`cp … digichat.yaml.example … digichat.yaml`. Every release
`.env.profile-*.example` also sets `DIGICHAT_EMBED_TENANTS` (hosts mode), and
`apps/digichat/src/lib/deploy-config/loader.ts:294` unconditionally retains a
file `deployment:` through the merge:

```ts
...(config?.deployment ? { deployment: config.deployment } : {})
```

so `getAnonymousClientInstall` (`loader.ts:447`) would serve the starter's
`auth: anonymous` / `gate.mode: ungated` / `llmAccess: operator` to any `/embed`
visitor whose host is unmatched. `check-config.ts:24` reads
`DIGICHAT_EMBED_TENANTS` from the shell and `make digichat-config-check` never
loads `.env.profile-a`, so the checker prints `shape: deployment` and does not
surface the collision.

**Resolution:** fixed (docs half) in `912ff3b08`. The starter header now has a
"pick one shape" note, the `deployment:` block is annotated, and all three docs
(`infra/digichat-release/README.md`, `docs/digichat/INSTALL.md`,
`infra/digichat-release/config/README.md`) spell out the two remedies: single
client → delete `DIGICHAT_EMBED_TENANTS`; many hostnames → use `hosts:` in the
file and drop `deployment:`. The loader hardening (drop/throw on `deployment`
when the registry is non-empty) was deliberately **not** taken here — it changes
loader behaviour for every install and belongs in its own change.

### F2 — MINOR: Profile B template used an invalid gate mode

`infra/digichat-release/.env.profile-b.example` had `"gateMode":"token"`, but
`apps/digichat/src/lib/embed-tenants.ts:272-273` accepts only
`turn_limited | ungated | trial_form`, so a copy-and-run Profile B failed the
container at boot in `parseEmbedTenants`. Pre-existing, untouched by the diff.

**Resolution:** fixed in `912ff3b08` → `"gateMode":"ungated"`.

### F3 — MINOR: `balanced` listed as a legacy disclosure mode

`digichat.yaml.example:58-61` listed
`off | collapsed | balanced | expanded | locked_open` for the legacy
`reasoning:` / `toolCalls:` keys. `foldLegacyDisclosure`
(`apps/digichat/src/lib/deploy-config/schema.ts:165-181`) maps anything not
`false/off/expanded/locked_open` to `compact`; `balanced` only exists on the
forward `view:` key.

**Resolution:** fixed in `912ff3b08` — the comment now lists
`off | collapsed | expanded | locked_open` and states that `balanced` is not
valid there.

### F4 — MINOR: the new mount silently shadows pre-existing baked-example paths

`./config:/app/config:ro` replaces `/app/config`, so a pre-existing deployment
with `DIGICHAT_CONFIG_PATH=/app/config/examples/skins/claude.yaml` now hits a
missing file and, because `allowMissingFile` defaults true
(`loader.ts:316`), falls back silently.

**Resolution:** fixed in `912ff3b08` — all three docs now carry the migration
line ("copy that file into `config/` first, or the path silently stops
resolving").

### F5 — NIT: `$(abspath)` depends on make's working directory

`Makefile:151` needs `$(abspath)` (the recipe `cd`s into `apps/digichat`), but it
expands against make's CWD, not the Makefile's directory, so invoking make from
a subdirectory would misresolve a relative `CONFIG`.

**Resolution:** fixed in `912ff3b08` — a comment above the target now says to
run make from the repo root.

### F6 — NIT: "falls back to the built-in dev default" was imprecise

With `DIGICHAT_EMBED_TENANTS` set, a missing file falls back to the **hosts
registry** (`loader.ts:337-338`), not the dev default.

**Resolution:** fixed in `912ff3b08` — the wording now names both paths.

### F7 — NIT: the starter ships permissive

`auth: anonymous`, `gate.mode: ungated`, `llmAccess: operator`, no token. Inert
while `DIGICHAT_EMBED_ENABLED=0`, but risky the moment embed is flipped on.

**Resolution:** fixed in `912ff3b08` — the starter's `gate:` block now warns to
pick a capped mode and set `token:` before exposing `/embed` publicly.

## Verified clean (coverage record)

- **Loader semantics** match the docs and no commit-message claim is
  contradicted: `DEFAULT_CONFIG_PATH="/app/config/digichat.yaml"`
  (`loader.ts:39`); `allowMissingFile` defaults true (`:316`); an empty file
  throws (`:330`); a missing file falls through (`:331-333`); an invalid file
  throws; resolution order file → `DIGICHAT_EMBED_TENANTS` → dev default
  (`:335-385`).
- **`check-config.ts`**: path order `argv[2] → env → DEFAULT_CONFIG_PATH`
  (`:14-15`); setting `process.env.DIGICHAT_CONFIG_PATH` before the call works
  because the loader defaults `env = opts.env ?? process.env` at call time
  (`loader.ts:314-315`); strict `allowMissingFile: false` (`:23`); `hosts:` shape
  enumerated (`:28`); no crash on the merge path; exits non-zero on every failure
  (try + `process.exit(1)` `:58`).
- **No secret leak**: token masked (`:51`), MCP ids only (`:49`), backend `type`
  only (`:46`); `toDigichatClientConfig` drops token / MCP url / consumeUrl /
  Foundry endpoint / requiredPlanTier (`client-projection.ts:173-243`).
- **Makefile**: `.PHONY` entry added (`:4`); an empty `CONFIG` expands to no arg.
- **Compose**: `volumes:` correctly nested at service indent in all four
  (`compose.profile-a.yml:225`, `compose.profile-a-bundle.yml:109`,
  `compose.profile-b.yml:43`, `docker-compose.yml:569`); no duplicate
  service-level volumes; `compose.profile-b.yml:67` has a top-level `volumes:`
  but no collision; `:ro` everywhere; relative paths correct per Compose project
  dir (`./config` for the release files, `./apps/digichat/config` for root);
  `infra/self-host/compose.ghcr.yml` is image-only and inherits the root mount;
  `compose.digichat-release.yml` likewise.
- **Example YAML** hand-validated against `schema.ts`: skin `digichat` ∈
  `THREAD_SKINS`; legacy `reasoning`/`toolCalls` fold to `view: compact` /
  `thinking: collapsed`, both valid; `backend.type: digigraph`; gate enums valid;
  no unknown keys under the `.strict()` objects.
- **Docs traps** ("invalid fails boot / missing falls back") match `loader.ts`
  and `src/instrumentation.ts:4-7`.
- **Examples are baked at `/app/config`** (`apps/digichat/Dockerfile:53`), so the
  "the mount replaces `/app/config`" claim is accurate.
- **No regression to env-registry-only installs**: a missing file with
  `allowMissingFile: true` plus the tenants env still yields a hosts config; the
  compose default change from `:-` empty to `/app/config/digichat.yaml` is
  behaviourally identical because `resolveConfigPath` already defaulted an empty
  value to `DEFAULT_CONFIG_PATH` (`loader.ts:44-45`).

## Evidence inspected

`github_get_commit(27ec4efac, include_diff)`, `github_pull_request_read(#4501,
get_diff)`, plus local reads of `loader.ts`, `schema.ts`, `client-projection.ts`,
`check-config.ts`, `instrumentation.ts`, `Dockerfile`, `thread-skins.ts`,
`view-modes.ts`, `embed-tenants.ts`, `Makefile`, `docker-compose.yml`, the four
release compose files, `infra/digichat-release/README.md`,
`infra/digichat-release/config/README.md`,
`infra/digichat-release/config/digichat.yaml.example`,
`infra/digichat-release/config/examples/README.md`,
`infra/self-host/compose.ghcr.yml`, `docs/digichat/INSTALL.md`.
`.env*` bodies are blocked by the repo's read guard; those files were reviewed
from the diff only.

## Verification after the fixes (`912ff3b08`)

- `apps/digichat` `npm run test` → 126 files / 1250 tests passed
- `apps/digichat` `npm run lint` → 0 errors (30 pre-existing warnings)
- `packages/ui` `npm run test` → 62 files / 447 tests passed
- `make doc-check` → OK (416 markdown files scanned)
- `make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml.example` → `digichat config OK`, `shape deployment`, 1 deployment
