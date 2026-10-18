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

`deploy-digithings-stack-cloudflare.yml` is named by both apps' READMEs and
by `docs/ops/SECRETS_INVENTORY.md`, but **it does not exist in the repo** — it
was deleted on 2026-10-01 by `f54af7052` (#4919, Human Gate, DIG-2843), and
`deploy-digichat-cloudflare-container.yml` went with it. `deploy_worker.sh`
already covers both, because it takes any directory under `apps/`; there was
never a replacement to write.

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
