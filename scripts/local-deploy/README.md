# Local build / deploy / publish (GitHub Actions exit)

GitHub Actions minutes are exhausted, so the build, deploy and publish
lanes below no longer run on GitHub. Their local replacements live in
this directory and run on Chris's Mac under his normal user. No Cloudflare
setting is changed by any script here, and nothing here deploys, publishes
or spends without an explicit live flag plus a named approval.

## Workflow map

| Disabled GitHub workflow | Local replacement | Needs secret? |
|---|---|---|
| `build-cloudflare-workers.yml` (worker build check) | `build_workers.sh` | No (`--dry-run`, no Docker) |
| `deploy-digiquant-cloudflare.yml` (digiquant.io Pages build check) | `build_sites.sh digiquant` | No |
| `deploy-digithings-cloudflare.yml` (digithings.ai Pages build check) | `build_sites.sh digithings` | No |
| `deploy-digithings-cron.yml` (cron Worker deploy) | `deploy_worker.sh digithings-cron` | Only with `--live` |
| `deploy-digiquant-runner.yml` (runner Worker + image deploy) | `deploy_worker.sh digiquant-runner` | Only with `--live` |
| `publish-digichat-image.yml` (GHCR publish) | `publish_image.sh digichat` | Only with `--push` |
| `publish-digillm-image.yml` (GHCR publish) | `publish_image.sh digillm` | Only with `--push` |

`deploy-digithings-stack-cloudflare.yml` and `deploy-digichat-cloudflare-container.yml`
are both in the repo again: the stack lane was re-derived on `develop` on 2026-10-20
(DIG-4612, #6013) and the digichat lane on 2026-10-22 (DIG-5120). Both were
**re-derived, not reverted** — the files deleted on 2026-10-01 by `f54af7052`
(#4919, Human Gate, DIG-2843) had no `production` environment gate, so a
push-triggered successor would have deployed production on every merge. The
re-derived lanes deploy on a manual `workflow_dispatch` only, behind
`environment: production`, and they deploy through each app's `npm run deploy`
wrapper. `deploy_worker.sh` remains the local path, because it takes any directory
under `apps/`.

## The release branch: one ref, one Worker at a time

`release/vX.Y.Z` is the ref production deploys from — the pre-push hook's
branch taxonomy allows only `release/v<major>.<minor>.<patch>`, which is why
the branch is version-shaped rather than named after Cloudflare.

```sh
git worktree add ~/cf-rel release/v0.2.0
cd ~/cf-rel && npm ci --no-audit --no-fund
bash scripts/local-deploy/deploy_worker.sh digiquant-runner            # dry-run
LOCAL_DEPLOY_APPROVED_BY=Chris \
  bash scripts/local-deploy/deploy_worker.sh digiquant-runner --live --yes
```

- **One app per run.** `<app>` is a directory under `apps/`, so updating one
  Worker never rebuilds or redeploys the others.
- **The branch is the pin.** Merge or cherry-pick onto it when you want that
  change live. `main` is not the deploy source, so promoting `develop` to
  `main` and deploying a Worker are independent decisions.
- **A container app needs its image inputs first.** `deploy_worker.sh` runs
  `scripts/package_r5_image_inputs.py` automatically before a live container
  deploy. Without it the docker build fails
  `failed to compute cache key ... not found`, which is how `digiquant-runner`
  sat on its 2026-10-01 image for two weeks while every gate stayed green.
- **If a container deploy dies on the image push, re-run the deploy.**
  Observed 2026-10-18 on the first live run:

  ```
  failed to do request: Put "https://registry.cloudflare.com/v2/.../blobs/uploads/...":
    write tcp 192.168.65.3:...->192.168.65.1:3128: write: broken pipe
  ```

  The push leaves the VM through Docker Desktop's proxy at `192.168.65.1:3128`,
  which forwards to the host's `wireproxy` on `127.0.0.1:18450` — the rotating
  VPN slot. A slot rotation mid-upload breaks the pipe. Nothing is corrupted:
  the build is cached and the image is still tagged locally.

  **Recover by re-running the deploy, not by pushing by hand.** `wrangler`
  mints the registry credential as part of the deploy, and that credential is
  short-lived — a later manual `docker push` fails `401 Unauthorized` against
  a perfectly good image even though `docker-credential-desktop` still returns
  a username and secret. Re-running re-authenticates *and* re-pushes; blobs
  already in the registry are skipped, and Docker's layer cache makes the
  rebuild much cheaper than the first run.

## Safety rules (all four scripts)

- **Dry by default.** `deploy_worker.sh` runs `wrangler deploy --dry-run`;
  `publish_image.sh` builds and boot-probes but never pushes. A live write
  needs the explicit flag (`--live` / `--push`).
- **Live needs a named approval.** The live flag additionally requires
  `LOCAL_DEPLOY_APPROVED_BY` to be set to the approver (Chris for
  production). No approval string, no live write. This is the local form of
  "no prod deploy without Chris's OK".
- **Secrets arrive as environment variables** (`CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID`, GHCR login via `docker login`). No secret is
  printed, logged or committed. Logs live under
  `~/.config/digithings/logs/local-deploy/`.
- **Cloudflare Worker fallback.** There is no second host and no new
  Worker. The fallback is that these scripts run on any Mac checkout of
  the same ref: all inputs are the repo plus environment variables, so a
  run elsewhere reproduces byte-identical artefacts. Schedules keep firing
  from the already-deployed `digithings-cron` Worker; nothing here changes
  that configuration.

## Examples

```sh
bash scripts/local-deploy/build_workers.sh
bash scripts/local-deploy/build_workers.sh dashboard-api
bash scripts/local-deploy/build_sites.sh all
bash scripts/local-deploy/deploy_worker.sh digithings-cron
LOCAL_DEPLOY_APPROVED_BY=Chris \
  bash scripts/local-deploy/deploy_worker.sh digithings-cron --live
bash scripts/local-deploy/publish_image.sh digichat --ref develop
bash scripts/local-deploy/publish_image.sh digillm --tag digillm-v0.2.0
```

## Per-service releases: one train, one tag per surface

`release/vX.Y.Z` is the release **train** — the ref carrying a promoted set of
changes for every service at once. Each deployable surface also gets its own
**annotated tag on that train**, so what a single service was released as stays
visible and returnable:

```
dashboard-api-v0.2.0                  digiquant-runner-v0.2.0
digichat-cloudflare-v0.2.0            digithings-cron-v0.2.0
digidata-api-v0.2.0                   digithings-stack-cloudflare-v0.2.0
digithings-web-v0.2.0                 twelvex-runner-v0.2.0
dashboard-v0.2.0          (Pages)     digichat-v0.2.0          (Pages)
digiquant-web-v0.2.0      (Pages)     digiquant-app-v0.2.0     (Pages)
```

Updating ONE service is then:

```sh
git fetch github --tags
git checkout -B deploy/<surface> <surface>-v0.2.0
scripts/local-deploy/deploy_worker.sh <surface> --live
```

**Why tags and not a branch per service.** The repository's branch taxonomy
(`scripts/hooks/pre-push.sh`, mirrored in `scripts/github-rulesets/01-branch-naming.json`
and pinned in sync by `tests/scripts/test_branch_taxonomy_release_please.sh`) admits
only `release/vX.Y.Z` in the release namespace, and these are monorepo services — a
long-lived branch per service would have to replicate every change to a shared
package. **Tags are exempt from the branch taxonomy** (the hook polices `refs/heads/`
only), so this needs no governance change at all.

The `<surface>-v0.2.0` tags sit on the *release-train* axis deliberately: they cannot
collide with release-please's `<component>-v<semver>` lineage (e.g. `digichat-v2.4.0`),
which release-please owns and which must not be pre-empted by hand.
