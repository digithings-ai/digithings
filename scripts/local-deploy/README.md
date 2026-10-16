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

`deploy-digithings-stack-cloudflare.yml` and `publish-service-images.yml`
are still active on GitHub, so they have no local replacement yet. When
they are disabled, they land here under the same shape: dry-run by
default, live only with `--live` plus a named approval.

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
