# Repo-split workflow map

No `.github/workflows` file moves into a private repo. Each path below is a
Cloudflare cron, a local-ci job, or a deletion. The record the test reads is
`scripts/repo_split_workflow_map.py`. This page is the same table for people.

Source: Chris, 2026-10-14, on DIG-3605. R5's three names are the ones that
comment gives: cron deploy, digichat image publish, gitleaks.

This change does not deploy and does not change a Cloudflare setting. Workflow
files stay until DIG-3608. DIG-3697 owns `scripts/deploy/runner.sh` and
`scripts/deploy/cron.sh`; they are not copied here.

| Repo | Path | Disposition | Where it lives |
| --- | --- | --- | --- |
| R1 | `.github/workflows/test-nautilus.yml` | local-ci | `ci.yml` workflow_call. Runner: DIG-3561. |
| R2 | `.github/workflows/deploy-digiquant-runner.yml` | local-ci | Signed-tag job `scripts/deploy/runner.sh` (DIG-3697). |
| R2 | `.github/workflows/pipeline-digiquant.yml` | cloudflare-cron | `house-run-09` in `apps/digithings-cron/src/jobs.ts`. |
| R2 | `.github/digiquant-pipeline.yml` | cloudflare-cron | Tunables for that same house-run. Not a workflow. |
| R2 | `.github/workflows/pipeline-checkpoint-archive.yml` | cloudflare-cron | `checkpoint-archive`. |
| R2 | `.github/workflows/pipeline-market-data-refresh.yml` | cloudflare-cron | `market-data-refresh-morning`, `market-data-refresh-evening`. |
| R2 | `.github/workflows/pipeline-research-metrics.yml` | cloudflare-cron | `research-metrics`. |
| R2 | `.github/workflows/pipeline-digiquant-prices.yml` | cloudflare-cron | `prices-at-open-13`, `prices-at-open-14`, `prices-fx-refresh`, `prices-fx-refresh-sun`, `prices-eod-macro`. |
| R2 | `.github/workflows/pipeline-digiquant-onchain.yml` | cloudflare-cron | `onchain`. |
| R2 | `.github/workflows/pipeline-digiquant-tearsheets.yml` | cloudflare-cron | `tearsheets`. |
| R2 | `.github/workflows/pipeline-digiquant-allocation-shadow.yml` | deletion | Producer workflow is absent. Isolation script stays. DIG-3608 removes the file. |
| R2 | `.github/workflows/sync-digiquant-runner-digikey-secret.yml` | local-ci | Manual and disarmed. Writes Worker secrets. No API call in this change. |
| R2 | `.github/workflows/sync-digiquant-runner-mail-secrets.yml` | local-ci | Manual and disarmed. Writes Worker secrets. No API call in this change. |
| R2 | `.github/workflows/test-digiquant.yml` | local-ci | `ci.yml` workflow_call. Runner: DIG-3561. |
| R3 | `.github/workflows/deploy-digiquant-cloudflare.yml` | local-ci | `scripts/build-digiquant.sh`. Pages watching `main` is the publish. |
| R3 | `.github/workflows/test-dashboard.yml` | local-ci | `ci.yml` workflow_call. Runner: DIG-3561. |
| R4 | `.github/workflows/book-pdf.yml` | local-ci | `npm run book:pdf --workspace digithings-web`. |
| R4 | `.github/workflows/deploy-digithings-cloudflare.yml` | local-ci | `scripts/build-digithings.sh`. Pages watching `main` is the publish. |
| R4 | `.github/workflows/refresh-repo-activity.yml` | cloudflare-cron | `refresh-repo-activity`. |
| R4 | `.github/workflows/test-web.yml` | local-ci | `ci.yml` workflow_call. Runner: DIG-3561. |
| R6 | `.github/workflows/datatap-answer-check.yml` | cloudflare-cron | `datatap-answer-check`. |
| R6 | `.github/workflows/occ-invite-key-rollout.yml` | local-ci | `scripts/check_occ_rollout_auth_guard.py`. |
| R5 | `.github/workflows/deploy-digithings-cron.yml` | local-ci | Signed-tag job `scripts/deploy/cron.sh` (DIG-3697). |
| R5 | `.github/workflows/publish-digichat-image.yml` | local-ci | Tag `digichat-v*`. Image publish, not the Worker deploy. |
| R5 | `.github/workflows/security-gitleaks.yml` | local-ci | `.gitleaks.toml`. |
