# Worker deploy jobs (local-ci)

One job per Worker. Each script is a local-ci job: run it on a clean
checkout of a signed release tag. There is no GitHub workflow and no
Buildkite pipeline. This directory does not poll for tags and does not
install a launchd job.

| Job | Tag | App | Worker |
|---|---|---|---|
| `stack` | `stack-vX.Y.Z` | `apps/digithings-stack-cloudflare` | `digithings-stack` |
| `digichat` | `digichat-vX.Y.Z` | `apps/digichat-cloudflare` | `digithings-digichat` |
| `langfuse` | `langfuse-vX.Y.Z` | `apps/digitrace-langfuse` | `digitrace-langfuse` |
| `cron` | `cron-vX.Y.Z` | `apps/digithings-cron` | `digithings-cron` |
| `runner` | `runner-vX.Y.Z` | `apps/digiquant-runner` | `digiquant-runner` |
| `dashboard-api` | `dashboard-api-vX.Y.Z` | `apps/dashboard-api` | `dashboard-api` |
| `corpus-index` | `corpus-index-vX.Y.Z` | no source on `develop` | `corpus-index` |
| `digidata-api` | `digidata-api-vX.Y.Z` | `apps/digidata-api` | `digidata-api` |

`corpus-index` has no source directory on `develop` (repo-split review G1).
Its job still requires a signed tag, then refuses. It does not create a
Worker or a Cloudflare setting.

## Gate

Every job refuses unless all of these hold:

1. The tag name is `<job>-vX.Y.Z`.
2. `git verify-tag` passes against `scripts/deploy/allowed_signers`.
3. That file contains at least one public key. It ships with none, so
   every tag is refused until Chris adds his signing key.
4. The checkout is clean and `HEAD` is the tagged commit.

A live `wrangler deploy` is not in these scripts. `--live` exits 2.
Dry-run is `wrangler deploy --dry-run` and only runs after the gate.

```sh
bash scripts/deploy/stack.sh --tag stack-v1.2.3
```

local-ci checks the tag out, then runs that command. This directory
does not install a launchd job and does not call Cloudflare.
