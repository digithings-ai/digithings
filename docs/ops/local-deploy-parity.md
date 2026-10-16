# local-deploy-parity

Deploy a website or app surface to Cloudflare Workers from the same artifact
the local self-host stack serves, and check that the local surface and the
recorded production surface still agree on their bindings.

Two commands, both from `scripts/dt`:

| Command | What it does |
| --- | --- |
| `python3 scripts/dt deploy <surface> --dry-run` | Builds the surface and runs `wrangler deploy --dry-run`, then prints the bindings and routes diff. Nothing is uploaded. |
| `python3 scripts/dt doctor parity` | Compares every surface against the recorded production census and prints the parity checklist. |

`--list` on `deploy` prints the surface names without touching anything.

## The surfaces

The registry is the `workers:` table in
[config/contract/services.yaml](../../config/contract/services.yaml), which is
the same file `scripts/dt up` reads. `deploy` cross-checks that registry
against a live `apps/*/wrangler.toml` enumeration, so neither side can drift
silently:

- a `wrangler.toml` that the registry does not list is reported with
  `in_registry = false` in `--json`;
- a registry row whose file is missing is reported as a config error, not as a
  broken Worker.

Seven surfaces are registered today:

| Surface | Config | Kind |
| --- | --- | --- |
| `dashboard-api` | `apps/dashboard-api/wrangler.toml` | Worker |
| `digithings-cron` | `apps/digithings-cron/wrangler.toml` | Worker |
| `digithings-digichat` | `apps/digichat-cloudflare/wrangler.toml` | Worker |
| `digithings-stack` | `apps/digithings-stack-cloudflare/wrangler.toml` | Worker |
| `digiquant-runner` | `apps/digiquant-runner/wrangler.toml` | Worker |
| `digitrace-langfuse` | `apps/digitrace-langfuse/wrangler.toml` | Worker |
| `digithings-web` | `apps/digithings-web/wrangler.toml` | Pages |

`digithings-web` is a Pages project: its config has no `main` and has
`pages_build_output_dir`. That is detected from the config, not from a hard
coded name, so a future Pages surface is classified the same way.

A surface can be named by worker name, by app directory (`dashboard-api`), or
by config path.

## Same artifact as the local stack

There is no separate production build path.

- **Workers** have no `build` script: `wrangler` bundles `main` on the fly, so
  the dry run bundles exactly the module `wrangler dev` serves. The plan
  therefore contains no build step for a Worker.
- **Pages** gets `npm run build` from its own `package.json`, which is the
  script `npm run dev` already uses, producing the `out/` directory that
  `wrangler pages deploy` consumes.

Wrangler is resolved through the same `DT_<TOOL>_CMD` override the rest of the
local stack uses (`DT_WRANGLER_CMD`). The default is `npx --yes
wrangler@<version>`, where the version is read from `package-lock.json`
(`node_modules/wrangler`) rather than remembered.

## What the dry run needs

- `npm ci` at the repository root. The dry run bundles from source, so a
  checkout without `node_modules` fails with a resolver error.
- **Docker, even in dry-run.** The four container Workers build their image as
  part of the deploy, and wrangler says so explicitly: *"The Docker CLI is
  needed to build the configured image(s) before deploying (even in dry-run
  mode)"*. `deploy` therefore adds `/opt/homebrew/bin` and `/usr/local/bin` to
  the step PATH when those directories exist, because an agent shell often
  lacks `/usr/local/bin` where the Docker CLI lives.
- Expect minutes, not seconds: the four container surfaces build a real image.
  A local run of all seven took about 15 minutes.

If a step fails, the table shows the last output line only, and wrangler's last
line is usually a pointer to its log file. The log is under
`$TMPDIR/paperclip-opencode-config-*/.wrangler/logs/`.

## Pages and the dry run

`wrangler pages deploy` has no `--dry-run` flag; passing one is an error
(`Unknown arguments: dry-run, dryRun`). For a Pages surface the dry run
therefore:

1. runs the build, which is the part that can be verified locally, and
2. reports the upload step as **SKIPPED** with the reason.

A Worker dry run never passes `--dry-run` for a Pages surface and never emits
an upload step. The real upload for `digithings-web` is emitted only on a
non-dry run.

## The production gate

`--env production` refuses to build a plan unless the approval token is
present in the environment:

```
DT_DEPLOY_APPROVED_BY=chris
```

Set it by Chris, interactively. The comparison is exact: a different value, a
different name, or trailing whitespace is a refusal with exit code 2, and the
refusal happens before any step runs. `--env dev` has no hosted target at all,
so there is nothing to approve.

No command in this path reads a production secret. The deploy path renders
placeholder names and kinds only, following the DIG-2959 pattern.

## The parity checklist

`dt doctor parity` compares each surface against the recorded production census
in [config/self-host/parity-baseline.json](../../config/self-host/parity-baseline.json)
(`surface.wrangler`). Every dimension is a real diff over binding names and
kinds, never over values.

| Dimension | How it is measured |
| --- | --- |
| `bindings vs production` | Every advertised binding kind, compared name-by-name and kind-by-kind. |
| `R2 buckets` | The `r2_bucket` kind alone. |
| `KV / DO bindings` | The `kv_namespace` and `durable_object_namespace` kinds. |
| `D1 local DBs + migrations` | Reported against the local owner: `wrangler dev` owns the local database, so a local D1 file is not the artefact that would prove parity. |
| `routes` | Reads `[[routes]]` (both `pattern` and `custom_domain` rows). The local stack addresses fixed loopback ports, so route equivalence is a deploy-time claim. |
| `secret placeholders` | Names and kinds rendered; no value is read. |
| `migration replay` | The baseline's `appliedFromEmpty` of `totalMigrations`. Re-measuring the replay is DIG-3087's lane. |

Verdicts, and what they are allowed to mean:

- **MATCH** — both sides were measured and agree.
- **DIFFERS** — both sides were measured and disagree; the detail lists
  `local-only` and `production-only` names.
- **UNKNOWN** — the check could not see the thing the checklist asks for. It
  names the reason. UNKNOWN is never reported as a match.

The overall verdict is `DIFFERS` if any row differs, `PARTIAL` if any row is
unknown, `MATCH` only when every row was measured. `--require-all` turns an
UNKNOWN into exit code 1, for a gate that needs a complete measurement.

### Measured result

`python3 scripts/dt doctor parity --json`, against develop at the time of
writing: verdict **PARTIAL**, `{MATCH: 30, DIFFERS: 0, UNKNOWN: 13, total: 43}`.

| Verdict | Dimensions |
| --- | --- |
| MATCH | `bindings vs production` 7, `R2 buckets` 7, `KV / DO bindings` 7, `secret placeholders` 7, `D1 local DBs + migrations` 2 |
| DIFFERS | none |
| UNKNOWN | `routes` 7, `D1 local DBs + migrations` 5, `migration replay` 1 |

The 13 UNKNOWN rows are honest gaps, not defects: routes are a deploy-time
claim, the five D1 surfaces declare `[[migrations]]` whose local owner is
`wrangler dev`, and the migration replay belongs to DIG-3087.

### Measured dry run

`dt deploy <surface> --dry-run` ran for all seven surfaces with exit code 0.
Six Workers reported a real `wrangler deploy --dry-run` success; the four
container surfaces also printed a Docker build link, which is the proof the
image build ran. `digithings-web` built and skipped the upload, as described
above.

## Supabase exit

The parity baseline carries the migration census: `appliedFromEmpty` 126 of
`totalMigrations` 137, with the recorded verdict *"The chain in this repo is NOT
replayable from an empty database. 126 of 137 files apply; 11 need objects that
exist only on the managed Supabase project or were created out of repo."* Those
11 are the ones that keep a service on its Supabase container. A service that
has moved off Supabase declares a D1
binding and an R2 bucket in its wrangler config, and those bindings are what
the parity rows above compare.

Services that have not migrated keep their Supabase container in
`docker-compose.yml` and are **not** a parity defect: the checklist compares a
Worker's bindings with production, and a missing compose entry for a Worker is
not evidence of drift. `digiquant-runner` is the one registered surface that
has a compose twin, and it publishes no port, so for that one "same routes" is
a service-binding claim rather than a port claim.

## Reproduce

```
npm ci                                    # once, repository root
python3 scripts/dt deploy --list
python3 scripts/dt doctor parity
python3 scripts/dt deploy dashboard-api --dry-run
python3 scripts/dt deploy digithings-web --dry-run
```

Exit codes follow the rest of `dt`: 0 ok, 1 a check or step failed, 2 a usage
error or a refused production run.

## Overrides

| Variable | Effect |
| --- | --- |
| `DT_WRANGLER_CMD` | Replaces the resolved wrangler command. |
| `DT_DEPLOY_APPROVED_BY` | The production approval token. |

## Limits

- Route parity is not measured locally, only declared. A real route diff needs a
  deploy.
- The local D1 file is owned by `wrangler dev`, so it cannot serve as the
  artefact for the D1 parity claim.
- The migration replay is read from the baseline, not re-measured here.
- `--dry-run` on a Pages surface verifies the build, not the upload.
